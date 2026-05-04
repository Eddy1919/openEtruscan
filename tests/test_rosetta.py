"""Tests for the Rosetta Phase-1 FastText pipeline.

Trains on a synthetic Etruscan-like corpus (no DB, no external models) so
the test stays fast (~1 s) and self-contained. The synthetic corpus is
deliberately small but lexically rich enough that a few well-known
nearest-neighbour invariants should hold.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# All Rosetta tests require gensim. Skip cleanly if the [rosetta] extra
# isn't installed in this environment.
pytest.importorskip("gensim", reason="gensim not installed; pip install -e '.[rosetta]'")

from openetruscan.ml.rosetta import (  # noqa: E402
    DEFAULT_TRAINING_PARAMS,
    extract_training_corpus,
    load_model,
    nearest,
    train_model,
    _tokenise,
)


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------


class TestTokenise:
    def test_basic_split(self):
        assert _tokenise("larθal velinas") == ["larθal", "velinas"]

    def test_strips_ascii_punctuation(self):
        assert _tokenise("avil. svalce, larθal:lecnes") == [
            "avil", "svalce", "larθal", "lecnes",
        ]

    def test_lowercases(self):
        assert _tokenise("LARTH") == ["larth"]

    def test_keeps_etruscan_glyphs(self):
        toks = _tokenise("śuθi χva θana")
        assert toks == ["śuθi", "χva", "θana"]

    def test_empty(self):
        assert _tokenise("") == []
        assert _tokenise(None or "") == []


# ---------------------------------------------------------------------------
# Inline corpus extraction
# ---------------------------------------------------------------------------


class TestExtractTrainingCorpus:
    def test_inline_rows_pass_through_tokenised(self):
        rows = ["larθal velinas", "arnθ spurinas", "single"]
        out = list(extract_training_corpus(inline_rows=rows, min_tokens=2))
        assert out == [["larθal", "velinas"], ["arnθ", "spurinas"]]

    def test_min_tokens_filter(self):
        out = list(extract_training_corpus(
            inline_rows=["a b c", "x"], min_tokens=2
        ))
        assert out == [["a", "b", "c"]]

    def test_min_tokens_one_keeps_singletons(self):
        out = list(extract_training_corpus(
            inline_rows=["alone"], min_tokens=1
        ))
        assert out == [["alone"]]


# ---------------------------------------------------------------------------
# Training pipeline
# ---------------------------------------------------------------------------


def _synthetic_corpus() -> list[list[str]]:
    """A small but coherent corpus.

    Two recurring "name + verb + place" templates. The repetition gives
    FastText enough signal to learn that ``larθal`` and ``larθa`` are
    near-neighbours (shared 4-gram ``larθ``) and that ``cerveteri`` and
    ``tarquinia`` cluster as places.
    """
    base = [
        "larθal velinas suθi cerveteri",
        "larθa velinas avil cerveteri",
        "arnθ spurinas suθi tarquinia",
        "arnθ spurinas avil tarquinia",
        "θana velinas svalce cerveteri",
        "velia spurinas svalce tarquinia",
        "larθal lecnes turce flerχva",
        "arnθ lecnes turce flerχva",
        "θana lecnes mulvanice flerχva",
    ]
    # Repeat to get past min_count=2 and give skip-gram more co-occurrence
    # passes. Real corpora are far larger; this is just to stabilise the
    # training run.
    return [_tokenise(s) for s in base * 6]


class TestTrainModel:
    def test_trains_and_returns_metadata(self):
        sentences = _synthetic_corpus()
        model, metadata = train_model(sentences, epochs=10)

        assert metadata["corpus"]["n_sentences"] == len(sentences)
        assert metadata["corpus"]["n_tokens"] == sum(len(s) for s in sentences)
        assert metadata["vocab_size"] > 0
        assert metadata["params"]["sg"] == DEFAULT_TRAINING_PARAMS["sg"]
        assert "training_duration_s" in metadata
        assert metadata["format_version"] == 1

    def test_empty_corpus_raises(self):
        with pytest.raises(ValueError, match="empty corpus"):
            train_model([])

    def test_save_and_reload(self, tmp_path: Path):
        sentences = _synthetic_corpus()
        out = tmp_path / "etr.bin"
        train_model(sentences, out_path=out, epochs=10)

        assert out.exists()
        meta = out.with_suffix(out.suffix + ".meta.json")
        assert meta.exists()

        reloaded = load_model(out)
        # Round-trip: a token in the training data should be queryable.
        nbrs = nearest(reloaded, "velinas", k=3)
        assert len(nbrs) == 3
        assert all(isinstance(s, float) for _, s in nbrs)

    def test_oov_query_via_subword(self, tmp_path: Path):
        """Sub-word n-grams should give a sensible vector for an unseen
        morphological variant of a known root.

        ``larθa`` is in the training data; ``larθus`` is not but shares
        the 4-gram ``larθ``. FastText should produce a non-zero
        nearest-neighbour list.
        """
        sentences = _synthetic_corpus()
        out = tmp_path / "etr.bin"
        train_model(sentences, out_path=out, epochs=10)

        reloaded = load_model(out)
        nbrs = nearest(reloaded, "larθus", k=5)  # unseen form
        assert len(nbrs) == 5
        # The seen variants of the same root should be among the top hits.
        seen_roots = {w for w, _ in nbrs}
        assert seen_roots & {"larθal", "larθa"}, (
            f"FastText sub-word fallback failed: nbrs={nbrs!r}"
        )

    def test_morphology_sanity(self):
        """``larθal`` and ``larθa`` share a 4-gram root and should be
        among each other's top neighbours after enough epochs."""
        model, _ = train_model(_synthetic_corpus(), epochs=20)
        top5_for_larθal = {w for w, _ in nearest(model, "larθal", k=5)}
        assert "larθa" in top5_for_larθal, (
            f"morphology pairing failed: larθal top-5 = {top5_for_larθal!r}"
        )


# ---------------------------------------------------------------------------
# Phase 1b stubs: should fail loudly until implemented
# ---------------------------------------------------------------------------


def test_latin_ingest_is_explicitly_unimplemented():
    from openetruscan.ml.rosetta import extract_latin_corpus_from_edr

    with pytest.raises(NotImplementedError, match="Phase 1b"):
        list(extract_latin_corpus_from_edr())


def test_oscan_umbrian_ingest_is_explicitly_unimplemented():
    from openetruscan.ml.rosetta import extract_oscan_umbrian_corpus

    with pytest.raises(NotImplementedError, match="Phase 1b"):
        list(extract_oscan_umbrian_corpus())


# ---------------------------------------------------------------------------
# Character-level pretraining
# ---------------------------------------------------------------------------


class TestCharacterModel:
    def test_char_streams_preserve_word_boundaries(self):
        from openetruscan.ml.rosetta import _sentences_as_char_streams

        streams = _sentences_as_char_streams([["ab", "cd"], ["x"]])
        assert streams == [["a", "b", " ", "c", "d"], ["x"]]

    def test_char_model_trains(self):
        from openetruscan.ml.rosetta import train_character_model

        model = train_character_model(_synthetic_corpus(), vector_size=20, epochs=5)
        # The character vocab should include at least the Latin letters
        # used by the synthetic corpus, plus the space separator.
        assert "l" in model.wv
        assert "a" in model.wv
        assert " " in model.wv

    def test_char_model_empty_corpus_raises(self):
        from openetruscan.ml.rosetta import train_character_model

        with pytest.raises(ValueError, match="empty corpus"):
            train_character_model([])


class TestTrainModelWithCharInit:
    def test_seeds_all_word_vectors(self):
        """Every in-vocab word should be seeded from char vectors."""
        from openetruscan.ml.rosetta import train_model_with_char_init

        sentences = _synthetic_corpus()
        model, metadata = train_model_with_char_init(sentences, epochs=10)
        ci = metadata["char_init"]
        assert ci["n_word_vectors_seeded"] == ci["n_word_vectors_total"]
        assert ci["char_vocab_size"] > 0
        assert metadata["format_version"] == 2

    def test_char_init_save_reload(self, tmp_path: Path):
        from openetruscan.ml.rosetta import train_model_with_char_init

        out = tmp_path / "char_init.bin"
        train_model_with_char_init(_synthetic_corpus(), out_path=out, epochs=10)
        assert out.exists()
        # Metadata file should distinguish char-init from baseline runs.
        import json

        meta = json.loads(out.with_suffix(".bin.meta.json").read_text())
        assert meta["format_version"] == 2
        assert "char_init" in meta

    def test_char_init_morphology_still_works(self):
        """Adding char-init shouldn't break the basic morphology pairing."""
        from openetruscan.ml.rosetta import train_model_with_char_init

        model, _ = train_model_with_char_init(_synthetic_corpus(), epochs=20)
        top5 = {w for w, _ in nearest(model, "larθal", k=5)}
        assert "larθa" in top5
