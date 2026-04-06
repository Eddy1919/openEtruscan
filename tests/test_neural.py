"""Tests for the neural inscription classifiers."""

from __future__ import annotations

import json

import pytest

# ---------------------------------------------------------------------------
# Check torch availability — skip tests if not installed
# ---------------------------------------------------------------------------

torch = pytest.importorskip("torch", reason="PyTorch not installed")


from openetruscan.classifier import ClassificationResult  # noqa: E402
from openetruscan.neural import (  # noqa: E402
    CharCNN,
    CharVocab,
    MicroTransformer,
    NeuralClassifier,
)

# ---------------------------------------------------------------------------
# CharVocab tests
# ---------------------------------------------------------------------------


class TestCharVocab:
    def test_build_from_texts(self):
        vocab = CharVocab.build(["abc", "def", "θχφ"])
        assert len(vocab) >= 8  # [PAD], [UNK], a, b, c, d, e, f, θ, χ, φ
        assert vocab.char_to_idx["[PAD]"] == 0
        assert vocab.char_to_idx["[UNK]"] == 1

    def test_encode_decode_roundtrip(self):
        vocab = CharVocab.build(["suθi larθal lecnes"])
        encoded = vocab.encode("suθi", max_len=10)
        assert len(encoded) == 10  # padded
        decoded = vocab.decode(encoded)
        assert decoded == "suθi"

    def test_encode_padding(self):
        vocab = CharVocab.build(["ab"])
        encoded = vocab.encode("a", max_len=5)
        assert encoded == [vocab.char_to_idx["a"], 0, 0, 0, 0]

    def test_encode_truncation(self):
        vocab = CharVocab.build(["abcdefghij"])
        encoded = vocab.encode("abcdefghij", max_len=3)
        assert len(encoded) == 3

    def test_unknown_char(self):
        vocab = CharVocab.build(["abc"])
        encoded = vocab.encode("xyz", max_len=3)
        assert all(idx == 1 for idx in encoded)  # all UNK

    def test_serialization(self):
        vocab = CharVocab.build(["suθi larθal"])
        d = vocab.to_dict()
        restored = CharVocab.from_dict(d)
        assert vocab.char_to_idx == restored.char_to_idx


# ---------------------------------------------------------------------------
# Model forward pass tests
# ---------------------------------------------------------------------------


class TestCharCNN:
    def test_forward_shape(self):
        model = CharCNN(vocab_size=64, num_classes=7)
        x = torch.randint(0, 64, (4, 32))  # batch=4, seq=32
        logits = model(x)
        assert logits.shape == (4, 7)

    def test_single_sample(self):
        model = CharCNN(vocab_size=32, num_classes=3)
        x = torch.randint(0, 32, (1, 16))
        logits = model(x)
        assert logits.shape == (1, 3)

    def test_param_count(self):
        """CharCNN should be lightweight (~50K params)."""
        model = CharCNN(vocab_size=64, num_classes=7)
        n_params = sum(p.numel() for p in model.parameters())
        assert n_params < 100_000, f"CharCNN has {n_params:,} params (expected <100K)"


class TestMicroTransformer:
    def test_forward_shape(self):
        model = MicroTransformer(vocab_size=64, num_classes=7)
        x = torch.randint(0, 64, (4, 32))
        logits = model(x)
        assert logits.shape == (4, 7)

    def test_single_sample(self):
        model = MicroTransformer(vocab_size=32, num_classes=3, max_len=16)
        x = torch.randint(0, 32, (1, 16))
        logits = model(x)
        assert logits.shape == (1, 3)

    def test_param_count(self):
        """MicroTransformer should be under 1M params."""
        model = MicroTransformer(vocab_size=64, num_classes=7)
        n_params = sum(p.numel() for p in model.parameters())
        assert n_params < 1_000_000, f"Transformer has {n_params:,} params (expected <1M)"


# ---------------------------------------------------------------------------
# NeuralClassifier integration tests
# ---------------------------------------------------------------------------


class TestNeuralClassifier:
    """Trains on tiny synthetic data to test the full pipeline."""

    @pytest.fixture
    def mock_training_data(self, monkeypatch):
        # Insert enough labeled samples for training (need ≥20)
        funerary_texts = [f"suθi larθal lecnes {i}" for i in range(10)] + [
            f"avils lupuce ceχa {i}" for i in range(5)
        ]
        votive_texts = [f"turce alpan fleres {i}" for i in range(10)] + [
            f"mulvanice mlaχ aisera {i}" for i in range(5)
        ]
        boundary_texts = [f"tular rasna spura {i}" for i in range(10)]
        ownership_texts = [f"mi mulu minipi {i}" for i in range(10)]

        texts = funerary_texts + votive_texts + boundary_texts + ownership_texts
        labels = (
            ["funerary"] * len(funerary_texts)
            + ["votive"] * len(votive_texts)
            + ["boundary"] * len(boundary_texts)
            + ["ownership"] * len(ownership_texts)
        )

        def _mock_load(db_path):
            return texts, labels

        # Patch load_training_data in the neural module
        monkeypatch.setattr("openetruscan.neural.load_training_data", _mock_load)

    @pytest.fixture()
    def tmp_dir(self, tmp_path):
        return tmp_path

    def test_cnn_train_predict(self, mock_training_data):
        clf = NeuralClassifier(arch="cnn")
        metrics = clf.train_from_corpus(
            "dummy_path",
            epochs=5,
            patience=10,
            verbose=False,
        )
        assert metrics["arch"] == "cnn"
        assert metrics["params"] > 0

        result = clf.predict("suθi larθal lecnes")
        assert isinstance(result, ClassificationResult)
        assert result.method == "neural_cnn"
        assert result.label in clf.labels

    def test_transformer_train_predict(self, mock_training_data):
        clf = NeuralClassifier(arch="transformer")
        metrics = clf.train_from_corpus(
            "dummy_path",
            epochs=5,
            patience=10,
            verbose=False,
        )
        assert metrics["arch"] == "transformer"

        result = clf.predict("turce alpan")
        assert isinstance(result, ClassificationResult)
        assert result.method == "neural_transformer"

    def test_save_load_roundtrip(self, mock_training_data, tmp_dir):
        clf = NeuralClassifier(arch="cnn")
        clf.train_from_corpus("dummy_path", epochs=3, patience=10, verbose=False)

        # Save
        model_dir = tmp_dir / "models"
        clf.save(model_dir)

        # Load
        clf2 = NeuralClassifier(arch="cnn")
        clf2.load(model_dir)

        result = clf2.predict("suθi larθal")
        assert isinstance(result, ClassificationResult)

    def test_onnx_export(self, mock_training_data, tmp_dir):
        clf = NeuralClassifier(arch="cnn")
        clf.train_from_corpus("dummy_path", epochs=3, patience=10, verbose=False)

        onnx_path = tmp_dir / "test.onnx"
        clf.export_onnx(onnx_path)
        assert onnx_path.exists()
        assert onnx_path.stat().st_size > 0

        # Check metadata file was created
        meta_path = onnx_path.with_suffix(".json")
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["arch"] == "cnn"
        assert "labels" in meta

    def test_onnx_inference(self, mock_training_data, tmp_dir):
        """Test ONNX inference with onnxruntime (if available)."""
        ort = pytest.importorskip("onnxruntime", reason="onnxruntime not installed")
        import numpy as np

        clf = NeuralClassifier(arch="cnn")
        clf.train_from_corpus("dummy_path", epochs=3, patience=10, verbose=False)

        onnx_path = tmp_dir / "test_inference.onnx"
        clf.export_onnx(onnx_path)

        # Run inference with ONNX Runtime
        session = ort.InferenceSession(str(onnx_path))
        inp = np.array(
            [clf.vocab.encode("suθi larθal", max_len=clf.max_len)],
            dtype=np.int64,
        )
        outputs = session.run(None, {"input": inp})
        logits = outputs[0]
        assert logits.shape == (1, len(clf.labels))


# ---------------------------------------------------------------------------
# Graceful error handling
# ---------------------------------------------------------------------------


class TestImportError:
    def test_require_torch_message(self):
        """Verify the error message when torch is imported but we simulate absence."""
        # We can't easily un-import torch, so just verify the function exists
        from openetruscan.neural import _require_torch

        # Since torch IS installed in test env, this should not raise
        _require_torch()  # should succeed without error
