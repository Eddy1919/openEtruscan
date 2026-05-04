"""Tests for the multilingual embedding layer.

These run in CI with no model downloads — MockEmbedder is the test
double. Tests for the real XLMREmbedder are in a separate class that
skips unless the [transformers] extra is installed.
"""

from __future__ import annotations

import pytest

from openetruscan.ml.embeddings import (
    DEFAULT_HIDDEN_DIM,
    Embedder,
    EmbedderInfo,
    MockEmbedder,
)


# ---------------------------------------------------------------------------
# MockEmbedder (the unconditional path)
# ---------------------------------------------------------------------------


class TestMockEmbedder:
    def test_inherits_embedder_abc(self):
        assert issubclass(MockEmbedder, Embedder)

    def test_info_carries_dim_and_id(self):
        em = MockEmbedder(dim=42, model_id="unit-mock")
        assert isinstance(em.info, EmbedderInfo)
        assert em.info.dim == 42
        assert em.info.model_id == "unit-mock"
        assert em.info.revision

    def test_default_dim_matches_xlm_r_base(self):
        em = MockEmbedder()
        assert em.info.dim == DEFAULT_HIDDEN_DIM == 768

    def test_embed_words_returns_correct_shape(self):
        em = MockEmbedder(dim=16)
        out = em.embed_words(["clan", "avil", "turce"])
        assert out.shape == (3, 16)

    def test_embed_empty_returns_empty_matrix(self):
        em = MockEmbedder(dim=16)
        out = em.embed_words([])
        assert out.shape == (0, 16)

    def test_embed_is_deterministic(self):
        """Same word → same vector across calls and across embedder
        instances. Required for reproducible tests + populate runs."""
        em1 = MockEmbedder(dim=32)
        em2 = MockEmbedder(dim=32)
        v1 = em1.embed_words(["clan"])
        v2 = em2.embed_words(["clan"])
        import numpy as np

        assert np.allclose(v1, v2)

    def test_embed_is_l2_normalised(self):
        """Vectors are normalised so cosine == inner product downstream."""
        import numpy as np

        em = MockEmbedder(dim=64)
        out = em.embed_words(["clan", "avil", "θuθθa"])
        norms = np.linalg.norm(out, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-6)

    def test_different_words_get_different_vectors(self):
        import numpy as np

        em = MockEmbedder(dim=128)
        a, b = em.embed_words(["clan", "filius"])
        assert not np.allclose(a, b), "different words must not collide"


# ---------------------------------------------------------------------------
# Real XLMREmbedder (only if transformers + torch are installed)
# ---------------------------------------------------------------------------


class TestXLMREmbedderImport:
    """Don't actually load XLM-R in CI (1+ GB download). Just verify
    the class imports and gracefully complains when the extras are
    missing."""

    def test_class_importable(self):
        from openetruscan.ml.embeddings import XLMREmbedder

        assert XLMREmbedder is not None

    def test_clear_error_when_transformers_missing(self, monkeypatch):
        """If transformers isn't installed, instantiating should raise
        ImportError with a clear pointer to the [transformers] extra."""
        import sys

        # Simulate "transformers not importable" by poisoning sys.modules.
        original = sys.modules.get("transformers")
        monkeypatch.setitem(sys.modules, "transformers", None)
        try:
            from openetruscan.ml.embeddings import XLMREmbedder

            with pytest.raises(ImportError, match="transformers"):
                XLMREmbedder()
        finally:
            if original is not None:
                sys.modules["transformers"] = original


# ---------------------------------------------------------------------------
# Real-model integration (opt-in via the `real_model` marker)
# ---------------------------------------------------------------------------
#
# These tests instantiate the actual XLM-R-base encoder (≈1.1 GB download
# on first run, ≈3 GB peak RAM, ~30 s warmup) and verify the wiring
# end-to-end. They're skipped by default in CI because the cost is
# disproportionate to the assurance — the mock tests already cover
# correctness of the populate / lookup pipeline. Enable in CI by setting
# the `ENABLE_REAL_MODEL_TESTS` repo variable to `true`; locally run with
# `pytest -m real_model` after `pip install -e '.[transformers]'`.


@pytest.mark.real_model
class TestXLMREmbedderRealModel:
    """End-to-end smoke tests against a real multilingual encoder.

    Each test re-loads the model — gensim/transformers session-scoped
    fixtures could amortise the cost, but the test set is intentionally
    tiny (3 tests) so the simple path is fine. If this grows, fold the
    embedder into a session-scoped fixture.
    """

    @pytest.fixture(scope="class")
    def embedder(self):
        """Skip the entire class if [transformers] extras aren't here."""
        pytest.importorskip("torch", reason="needs [transformers] extra")
        pytest.importorskip(
            "transformers", reason="needs [transformers] extra"
        )
        from openetruscan.ml.embeddings import XLMREmbedder

        return XLMREmbedder(model_id="xlm-roberta-base", batch_size=8)

    def test_real_dim_matches_xlmr_base(self, embedder):
        """xlm-roberta-base hidden_size is 768. If this drifts we want to
        know — the pgvector schema is keyed on it."""
        assert embedder.info.dim == 768
        assert embedder.info.model_id == "xlm-roberta-base"

    def test_real_embed_returns_normalised_vectors(self, embedder):
        import numpy as np

        out = embedder.embed_words(["clan", "avil", "θuθθa"])
        assert out.shape == (3, 768)
        norms = np.linalg.norm(out, axis=1)
        # L2-normalised within atol — minor float drift from the
        # pooling+normalize chain is expected.
        assert np.allclose(norms, 1.0, atol=1e-3), norms

    def test_real_etruscan_word_clusters_near_latin_equivalent(self, embedder):
        """The single signal that distinguishes a real cross-lingual
        encoder from a mock: an Etruscan word and its known Latin
        equivalent should be CLOSER in cosine than two unrelated words.

        Without LoRA fine-tuning this is a weak signal (XLM-R has no
        Etruscan in pretraining), but the multilingual sub-word vocab
        gives the comparison enough structure that the inequality
        usually holds. Treated as a sanity check, not a quality bar.
        """
        v_clan, v_filius, v_unrelated = embedder.embed_words(
            ["clan", "filius", "platform"]
        )
        sim_pair = float(v_clan @ v_filius)
        sim_unrelated = float(v_clan @ v_unrelated)
        # If the inequality flips, log both sims so the failure message
        # actually tells you what went wrong.
        assert sim_pair >= sim_unrelated - 0.05, (
            f"clan~filius={sim_pair:.3f} should be >= clan~platform={sim_unrelated:.3f}; "
            f"if not, the encoder may have regressed or the surface forms drifted"
        )
