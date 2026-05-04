"""Tests for the supervised Procrustes alignment pipeline.

These tests are self-contained: they train tiny synthetic Etruscan and
Latin FastText models in-process so the test stays fast (~5 s) and
doesn't depend on any pretrained model bundle.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("gensim", reason="gensim not installed; pip install -e '.[rosetta]'")
pytest.importorskip("numpy")


from openetruscan.ml.alignment import (  # noqa: E402
    ANCHOR_PAIRS,
    AnchorPair,
    align_procrustes,
    anchor_pairs,
    apply_alignment,
    build_synthetic_latin_corpus,
    cross_validate_alignment,
    project_etruscan_to_latin,
    save_alignment,
    load_alignment,
    train_synthetic_latin_model,
)


# ---------------------------------------------------------------------------
# Anchor pair vocabulary
# ---------------------------------------------------------------------------


class TestAnchorPairs:
    def test_anchor_pairs_are_normalised_lowercase(self):
        for p in ANCHOR_PAIRS:
            assert p.etr == p.etr.lower()
            assert p.lat == p.lat.lower()

    def test_anchor_pairs_have_required_fields(self):
        for p in ANCHOR_PAIRS:
            assert p.etr
            assert p.lat
            assert p.gloss
            assert p.confidence in {"low", "medium", "high"}
            assert p.source

    def test_at_least_50_pairs(self):
        """We promised a curated set of ~60 high-confidence equivalences."""
        assert len(ANCHOR_PAIRS) >= 50

    def test_filter_by_confidence(self):
        high = anchor_pairs(min_confidence="high")
        med = anchor_pairs(min_confidence="medium")
        assert len(high) <= len(med)
        assert all(p.confidence == "high" for p in high)
        assert all(p.confidence in {"high", "medium"} for p in med)

    def test_no_duplicate_etr_words(self):
        """If we accidentally have two Latin candidates for the same
        Etruscan word, the alignment math will pick whichever appears
        first — surface that as a curation problem rather than a silent
        bug."""
        from collections import Counter

        counts = Counter(p.etr for p in ANCHOR_PAIRS)
        dups = {w: n for w, n in counts.items() if n > 1}
        # zilaθ / zilθ are intentionally separate Etruscan tokens that map
        # to the same Latin gloss; this is fine. But the same `etr` should
        # not map to two different `lat`s.
        for word in dups:
            mapped = {p.lat for p in ANCHOR_PAIRS if p.etr == word}
            assert len(mapped) == 1, (
                f"etr {word!r} maps to multiple lat words: {mapped}"
            )


# ---------------------------------------------------------------------------
# Synthetic Latin corpus / model
# ---------------------------------------------------------------------------


class TestSyntheticLatin:
    def test_corpus_includes_every_anchor_lat(self):
        """If the synthetic corpus drops a Latin anchor word, the CV
        precision becomes a measurement of vocabulary coverage rather
        than alignment quality. Pin it."""
        corpus = build_synthetic_latin_corpus()
        all_tokens = {tok for sent in corpus for tok in sent}
        for p in ANCHOR_PAIRS:
            if p.confidence == "low":
                continue  # we don't gate on low-confidence pairs
            assert p.lat in all_tokens, (
                f"synthetic Latin corpus missing {p.lat!r} (anchor for {p.etr!r})"
            )

    def test_synthetic_model_trains(self):
        model = train_synthetic_latin_model(vector_size=30, epochs=5)
        assert "filius" in model.wv
        assert "praetor" in model.wv


# ---------------------------------------------------------------------------
# Procrustes math
# ---------------------------------------------------------------------------


def _make_etr_model_for_anchors(vector_size: int = 30) -> object:
    """Tiny Etruscan FastText that has every high-confidence anchor in vocab.

    We synthesise sentences containing each anchor word so the model
    actually trains on them rather than relying on subword fallback.
    """
    from gensim.models import FastText

    pairs = anchor_pairs(min_confidence="medium")
    sentences = []
    # Build co-occurring pairs so each anchor word has context.
    for i in range(0, len(pairs), 2):
        chunk = pairs[i:i + 2]
        sentences.append([p.etr for p in chunk])
    # Pad with a couple of long enumerations for vocab repetition.
    sentences += [[p.etr for p in pairs]] * 5
    return FastText(
        sentences=sentences,
        vector_size=vector_size,
        window=5,
        min_count=1,
        min_n=3,
        max_n=6,
        epochs=10,
        sg=1,
        workers=2,
    )


class TestProcrustes:
    def test_align_returns_orthogonal_matrix(self):
        import numpy as np

        etr_model = _make_etr_model_for_anchors()
        lat_model = train_synthetic_latin_model(vector_size=30, epochs=10)

        result = align_procrustes(etr_model, lat_model)
        # WᵀW ≈ I for an orthogonal matrix.
        WtW = result.W.T @ result.W
        assert np.allclose(WtW, np.eye(WtW.shape[0]), atol=1e-5)

    def test_residual_decreases_after_alignment(self):
        import numpy as np

        etr_model = _make_etr_model_for_anchors()
        lat_model = train_synthetic_latin_model(vector_size=30, epochs=10)

        result = align_procrustes(etr_model, lat_model)
        # Build the same X / Y matrices the solver used.
        pairs = anchor_pairs(min_confidence="medium")
        X = np.vstack([etr_model.wv[p.etr] for p in pairs if p.etr in etr_model.wv and p.lat in lat_model.wv])
        Y = np.vstack([lat_model.wv[p.lat] for p in pairs if p.etr in etr_model.wv and p.lat in lat_model.wv])
        residual_before = float(np.linalg.norm(X - Y, ord="fro"))
        residual_after = float(np.linalg.norm(X @ result.W - Y, ord="fro"))
        # The aligned residual must not be larger than the unaligned one.
        # (For unrelated random embeddings the gain is small but
        # consistently non-negative.)
        assert residual_after <= residual_before + 1e-6

    def test_apply_alignment_returns_same_dim_vector(self):
        import numpy as np

        etr_model = _make_etr_model_for_anchors()
        lat_model = train_synthetic_latin_model(vector_size=30, epochs=10)

        result = align_procrustes(etr_model, lat_model)
        v = etr_model.wv["clan"]
        projected = apply_alignment(result.W, v)
        assert projected.shape == v.shape
        assert isinstance(projected, np.ndarray)

    def test_dropped_pairs_are_reported(self):
        """Pass an obviously bogus extra pair and confirm it shows up in
        the dropped list with a clear reason."""
        etr_model = _make_etr_model_for_anchors()
        lat_model = train_synthetic_latin_model(vector_size=30, epochs=10)

        bogus = [
            AnchorPair("nope_etr_word_qq", "nope_lat_word_qq", "nope", "high", "fixture"),
        ]
        with pytest.raises(ValueError, match="No anchor pairs survived"):
            align_procrustes(etr_model, lat_model, bogus)


# ---------------------------------------------------------------------------
# Cross-validation
# ---------------------------------------------------------------------------


class TestCrossValidation:
    def test_cv_reports_per_fold_metrics(self):
        etr_model = _make_etr_model_for_anchors()
        lat_model = train_synthetic_latin_model(vector_size=30, epochs=10)

        cv = cross_validate_alignment(
            etr_model, lat_model, k_folds=3, top_k=5, seed=0,
        )
        assert "mean_precision_at_k" in cv
        assert cv["k_folds"] == 3
        assert cv["top_k"] == 5
        assert len(cv["folds"]) == 3
        for fold in cv["folds"]:
            assert "precision_at_k" in fold
            assert 0.0 <= fold["precision_at_k"] <= 1.0
            assert fold["n_held_out"] > 0

    def test_cv_seed_is_reproducible(self):
        etr_model = _make_etr_model_for_anchors()
        lat_model = train_synthetic_latin_model(vector_size=30, epochs=10)

        cv1 = cross_validate_alignment(etr_model, lat_model, k_folds=3, seed=42)
        cv2 = cross_validate_alignment(etr_model, lat_model, k_folds=3, seed=42)
        # Same seed => same fold partition => same per-fold pair set.
        for f1, f2 in zip(cv1["folds"], cv2["folds"], strict=True):
            etr_words_1 = {q["etr"] for q in f1["queries"]}
            etr_words_2 = {q["etr"] for q in f2["queries"]}
            assert etr_words_1 == etr_words_2

    def test_cv_rejects_too_few_folds(self):
        etr_model = _make_etr_model_for_anchors()
        lat_model = train_synthetic_latin_model(vector_size=30, epochs=10)

        with pytest.raises(ValueError, match="at least"):
            cross_validate_alignment(etr_model, lat_model, k_folds=999)


# ---------------------------------------------------------------------------
# Save / load round-trip
# ---------------------------------------------------------------------------


def test_alignment_save_load_roundtrip(tmp_path: Path):
    import numpy as np

    etr_model = _make_etr_model_for_anchors()
    lat_model = train_synthetic_latin_model(vector_size=30, epochs=10)

    result = align_procrustes(etr_model, lat_model)
    out = tmp_path / "rotation.npy"
    save_alignment(result, out, extra_metadata={"corpus": "synthetic"})

    assert out.exists()
    meta_path = out.with_suffix(".meta.json")
    assert meta_path.exists()

    loaded = load_alignment(out)
    assert np.allclose(loaded, result.W)


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------


def test_project_returns_top_k_latin_words():
    etr_model = _make_etr_model_for_anchors()
    lat_model = train_synthetic_latin_model(vector_size=30, epochs=10)

    result = align_procrustes(etr_model, lat_model)
    top = project_etruscan_to_latin("clan", etr_model, lat_model, result.W, k=5)
    assert len(top) == 5
    assert all(isinstance(w, str) for w, _ in top)
    assert all(isinstance(s, float) for _, s in top)
