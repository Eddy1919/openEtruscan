"""Tests for the CLI interface."""

import inspect

from click.testing import CliRunner

import openetruscan.core.cli as cli_module
from openetruscan.core.cli import __version__, main
from openetruscan.core.corpus import Inscription, SearchResults


class TestCLI:
    """Test CLI commands."""

    def setup_method(self):
        self.runner = CliRunner()

    def test_normalize_command(self):
        result = self.runner.invoke(main, ["normalize", "LARTHAL"])
        assert result.exit_code == 0
        assert "canonical" in result.output

    def test_normalize_json_output(self):
        result = self.runner.invoke(main, ["normalize", "-j", "Larθal"])
        assert result.exit_code == 0
        assert '"canonical"' in result.output

    def test_convert_to_old_italic(self):
        result = self.runner.invoke(main, ["convert", "--to", "old_italic", "Larθal"])
        assert result.exit_code == 0

    def test_convert_to_phonetic(self):
        result = self.runner.invoke(main, ["convert", "--to", "phonetic", "Larθal"])
        assert result.exit_code == 0
        assert "tʰ" in result.output

    def test_list_adapters(self):
        result = self.runner.invoke(main, ["adapters"])
        assert result.exit_code == 0
        assert "etruscan" in result.output

    def test_validate_nonexistent_file(self):
        result = self.runner.invoke(main, ["validate", "/tmp/nonexistent_file.txt"])
        # click.Path(exists=True) will catch this
        assert result.exit_code != 0

    def test_version(self):
        result = self.runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output


class _StubCorpus:
    """In-memory stand-in for Corpus, driving the DB-backed CLI commands."""

    def __init__(self, by_id=None, fts_result=None):
        self.by_id = by_id or {}
        self.fts_result = fts_result
        self.added = []
        self.images = []

    def get_by_ids(self, ids):
        found = [self.by_id[i] for i in ids if i in self.by_id]
        return SearchResults(inscriptions=found, total=len(found))

    def search(self, text=None, limit=100, **kwargs):
        if self.fts_result is not None:
            return SearchResults(inscriptions=[self.fts_result], total=1)
        return SearchResults(inscriptions=[], total=0)

    def add(self, inscription, language="etruscan"):
        self.added.append(inscription)

    def add_image(self, image_id, inscription_id, filename, mime_type, description, file_hash):
        self.images.append((image_id, inscription_id, filename))

    def count(self):
        return len(self.by_id)

    def close(self):
        pass


class TestClassifyCommand:
    """`classify` must resolve its argument as an ID, not as full-text."""

    def setup_method(self):
        self.runner = CliRunner()

    def test_classify_uses_exact_id_over_fts(self, monkeypatch):
        target = Inscription(id="ETR_042", raw_text="mi larθa")
        decoy = Inscription(id="OTHER_ID", raw_text="etr 042 mention")
        stub = _StubCorpus(by_id={"ETR_042": target}, fts_result=decoy)
        monkeypatch.setattr(cli_module, "_get_corpus", lambda db=None: stub)

        result = self.runner.invoke(main, ["classify", "ETR_042", "-c", "funerary"])
        assert result.exit_code == 0, result.output
        assert [i.id for i in stub.added] == ["ETR_042"]
        assert stub.added[0].classification == "funerary"

    def test_classify_falls_back_to_fts_with_note(self, monkeypatch):
        decoy = Inscription(id="OTHER_ID", raw_text="etr 042 mention")
        stub = _StubCorpus(by_id={}, fts_result=decoy)
        monkeypatch.setattr(cli_module, "_get_corpus", lambda db=None: stub)

        result = self.runner.invoke(main, ["classify", "ETR_042", "-c", "votive"])
        assert result.exit_code == 0, result.output
        assert "full-text match 'OTHER_ID'" in result.output
        assert [i.id for i in stub.added] == ["OTHER_ID"]

    def test_classify_missing_everywhere_fails(self, monkeypatch):
        stub = _StubCorpus()
        monkeypatch.setattr(cli_module, "_get_corpus", lambda db=None: stub)

        result = self.runner.invoke(main, ["classify", "NOPE", "-c", "votive"])
        assert result.exit_code == 1
        assert stub.added == []


class TestUploadImageCommand:
    """`upload-image` must link the file in the DB, not just claim success."""

    def setup_method(self):
        self.runner = CliRunner()

    def test_upload_image_links_row(self, monkeypatch, tmp_path):
        monkeypatch.setenv("IMAGES_DIR", str(tmp_path / "images"))
        src = tmp_path / "stele.jpg"
        src.write_bytes(b"fake-jpeg-bytes")

        stub = _StubCorpus(by_id={"ETR_001": Inscription(id="ETR_001", raw_text="x")})
        monkeypatch.setattr(cli_module, "_get_corpus", lambda db=None: stub)

        result = self.runner.invoke(main, ["upload-image", str(src), "--id", "ETR_001"])
        assert result.exit_code == 0, result.output
        assert len(stub.images) == 1
        assert stub.images[0][1] == "ETR_001"

    def test_upload_image_unknown_inscription_fails(self, monkeypatch, tmp_path):
        monkeypatch.setenv("IMAGES_DIR", str(tmp_path / "images"))
        src = tmp_path / "stele.jpg"
        src.write_bytes(b"fake-jpeg-bytes")

        stub = _StubCorpus()
        monkeypatch.setattr(cli_module, "_get_corpus", lambda db=None: stub)

        result = self.runner.invoke(main, ["upload-image", str(src), "--id", "MISSING"])
        assert result.exit_code == 1
        assert stub.images == []


class TestTrainNeuralCommand:
    """Regression tests for the train-neural → train_from_corpus call site.

    The command used to pass ``db_path=`` to a method whose parameter is
    ``db_url``, so every invocation TypeError'd after argument parsing. The
    stub below re-binds the CLI's kwargs against the REAL method signature,
    so any future rename breaks these tests instead of production.
    """

    def setup_method(self):
        self.runner = CliRunner()

    def test_train_neural_kwargs_bind_to_real_signature(self, monkeypatch, tmp_path):
        import openetruscan.ml.neural as neural

        calls = {}
        real_signature = inspect.signature(neural.NeuralClassifier.train_from_corpus)

        class _StubClassifier:
            def __init__(self, arch):
                calls["arch"] = arch

            def train_from_corpus(self, **kwargs):
                real_signature.bind(self, **kwargs)  # raises TypeError on drift
                calls["kwargs"] = kwargs
                return {"val_f1_macro": 0.5}

            def save(self, out):
                pass

            def export_onnx(self, path):
                pass

        monkeypatch.setattr(neural, "NeuralClassifier", _StubClassifier)
        result = self.runner.invoke(
            main,
            [
                "train-neural",
                "--db",
                "postgresql://user:pw@localhost/db",
                "--arch",
                "cnn",
                "--output",
                str(tmp_path),
                "--epochs",
                "1",
            ],
        )
        assert result.exit_code == 0, result.output
        assert calls["arch"] == "cnn"
        assert calls["kwargs"]["db_url"] == "postgresql://user:pw@localhost/db"
        assert calls["kwargs"]["epochs"] == 1

    def test_train_neural_requires_db_url(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        result = self.runner.invoke(
            main, ["train-neural", "--arch", "cnn", "--output", str(tmp_path)]
        )
        assert result.exit_code == 1
        assert "DATABASE_URL" in result.output
