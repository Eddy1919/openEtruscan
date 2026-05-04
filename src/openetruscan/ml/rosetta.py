"""Rosetta Vector Space — Phase 1: monolingual FastText models.

This module is the foundation for the unsupervised cross-language alignment
described in ROADMAP.md. Phase 1 alone does not produce translations; it
produces a self-contained Etruscan word-embedding model that we then sanity-
check (held-out perplexity, neighbour-cluster inspection) before deciding
whether the alignment phase is worth pursuing.

Design choices:

* **FastText, not Word2Vec** — Etruscan is heavily inflected and the corpus
  is small (~50k tokens). Sub-word n-grams let rare inflected forms inherit
  vector quality from the more frequent forms of the same root.
* **gensim** as the implementation — production-grade, on PyPI, no GPU
  required, well-documented. The model is ~50 MB on disk for a 100-dim
  space with 5-grams, which fits comfortably in api memory if we ever
  serve it in-process.
* **The "language" parameter** — extract_training_corpus accepts a language
  filter so we can use the same pipeline for the Latin/Sabellic ingests
  in Phase 1b. Those will arrive via separate ingest scripts (TODO) but
  share this training path.

Public surface:

    extract_training_corpus(...) -> Iterator[list[str]]
    train_model(...) -> tuple[FastText, dict]
    nearest(model, word, k=10) -> list[tuple[str, float]]

CLI:

    python -m openetruscan.ml.rosetta train --output models/etruscan.bin
    python -m openetruscan.ml.rosetta nearest --model models/etruscan.bin --word zich
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from typing import Any

logger = logging.getLogger("openetruscan.rosetta")


# ---------------------------------------------------------------------------
# Corpus extraction
# ---------------------------------------------------------------------------

# Tokeniser is intentionally simple: split on whitespace + ASCII punctuation,
# keep Greek-derived Etruscan glyphs (θ, χ, φ, ś) as part of the token. The
# corpus has already been canonicalised by the ingest pipeline so we don't
# re-do diacritic stripping here.
_TOKEN_SPLIT = re.compile(r"[\s.,;:!?\"'()\[\]\-_/\\|]+")


def _tokenise(text: str) -> list[str]:
    """Split a canonical inscription string into word tokens.

    NFC-normalise first so combining marks stay attached to their base
    character (matters for Etruscan's modified theta/sigma).
    """
    if not text:
        return []
    text = unicodedata.normalize("NFC", text).lower()
    return [t for t in _TOKEN_SPLIT.split(text) if t]


async def _extract_from_db(
    language: str = "etruscan",
    min_tokens: int = 2,
) -> list[list[str]]:
    """Pull canonical strings from the corpus DB and tokenise them.

    Skips rows whose canonical text tokenises to fewer than ``min_tokens``
    tokens — single-word inscriptions exist but contribute almost no
    contextual signal to the embedding.
    """
    from openetruscan.db.session import async_session_factory
    from sqlalchemy import select
    from openetruscan.db.models import Inscription

    sessions: list[list[str]] = []
    async with async_session_factory() as session:
        stmt = select(Inscription.canonical).where(Inscription.language == language)
        result = await session.execute(stmt)
        for (canonical,) in result.all():
            toks = _tokenise(canonical or "")
            if len(toks) >= min_tokens:
                sessions.append(toks)
    return sessions


def extract_training_corpus(
    language: str = "etruscan",
    min_tokens: int = 2,
    *,
    inline_rows: list[str] | None = None,
) -> Iterator[list[str]]:
    """Yield tokenised inscriptions for FastText training.

    Two modes:

    * **DB mode** (default): pulls from the live corpus. Requires a working
      ``DATABASE_URL`` and the async session factory.
    * **Inline mode**: pass ``inline_rows`` to feed canonical strings
      directly. Used by tests and by anyone running the pipeline against
      a fixture corpus.
    """
    if inline_rows is not None:
        for raw in inline_rows:
            toks = _tokenise(raw)
            if len(toks) >= min_tokens:
                yield toks
        return

    rows = asyncio.run(_extract_from_db(language=language, min_tokens=min_tokens))
    yield from rows


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

# Defaults tuned for an ancient-language corpus of ~50k tokens. Reasoning:
#
# * vector_size=100 — the manifold can't support more than that at this
#   token count without overfitting. Increase only if/when the corpus
#   grows ≥10x.
# * window=5 — average inscription length is short; a wider window mostly
#   pulls noise from sentence boundaries.
# * min_count=2 — drop hapax legomena. They hurt training (no signal to
#   learn from) but we keep them retrievable via sub-word n-grams.
# * min_n=3, max_n=6 — character n-gram range. 3-grams capture most
#   Etruscan suffixes (-al, -nas, -χva), 6-grams capture short root+suffix
#   units. Larger ranges blow up the n-gram dictionary.
# * epochs=20 — small corpus, more passes. Overfitting risk is low because
#   FastText regularises via the n-gram smoothing.
DEFAULT_TRAINING_PARAMS: dict[str, Any] = {
    "vector_size": 100,
    "window": 5,
    "min_count": 2,
    "min_n": 3,
    "max_n": 6,
    "epochs": 20,
    "workers": 2,
    "sg": 1,  # skip-gram; better than CBOW for small corpora.
}


def train_model(
    sentences: list[list[str]],
    out_path: Path | None = None,
    **overrides: Any,
) -> tuple[Any, dict[str, Any]]:
    """Train a FastText model on the given tokenised sentences.

    Returns ``(model, metadata)``. Persists the model to ``out_path`` (and
    a sibling ``.meta.json`` with the metadata dict) if ``out_path`` is set.

    Metadata captures everything needed to reproduce or evaluate the run:
    parameters, corpus size, vocab size, training duration, optional loss
    curve. The metadata file is what ROADMAP.md calls out as the
    reproducibility anchor for any paper coming out of this work.
    """
    try:
        from gensim.models import FastText
    except ImportError as e:
        raise ImportError(
            "Rosetta training requires the [rosetta] extra: "
            "pip install -e '.[rosetta]'"
        ) from e

    params = {**DEFAULT_TRAINING_PARAMS, **overrides}
    n_sentences = len(sentences)
    n_tokens = sum(len(s) for s in sentences)
    if n_sentences == 0:
        raise ValueError("Refusing to train on an empty corpus.")

    logger.info(
        "Training FastText: %d sentences / %d tokens / params=%s",
        n_sentences, n_tokens, params,
    )
    t0 = time.time()
    model = FastText(sentences=sentences, **params)
    duration_s = time.time() - t0

    metadata = {
        "params": params,
        "corpus": {
            "n_sentences": n_sentences,
            "n_tokens": n_tokens,
            "n_unique_tokens_seen": len(model.wv.key_to_index),
        },
        "vocab_size": len(model.wv),
        "training_duration_s": round(duration_s, 2),
        "gensim_version": _gensim_version(),
        "format_version": 1,
    }

    if out_path is not None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        model.save(str(out_path))
        meta_path = out_path.with_suffix(out_path.suffix + ".meta.json")
        meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
        logger.info("Wrote model to %s and metadata to %s", out_path, meta_path)

    return model, metadata


def _gensim_version() -> str:
    try:
        import gensim

        return gensim.__version__
    except ImportError:
        return "unknown"


# ---------------------------------------------------------------------------
# Nearest-neighbour helper
# ---------------------------------------------------------------------------


def nearest(model: Any, word: str, k: int = 10) -> list[tuple[str, float]]:
    """Return the ``k`` closest tokens to ``word`` in the embedding space.

    Falls back to FastText's sub-word path for OOV queries — that's the
    whole point of using FastText: a never-seen inflection of a known root
    still gets a sensible vector.
    """
    word = unicodedata.normalize("NFC", word).lower()
    return [(w, float(score)) for w, score in model.wv.most_similar(word, topn=k)]


def load_model(path: str | Path) -> Any:
    """Convenience loader. Raises a friendly error if [rosetta] isn't installed."""
    try:
        from gensim.models import FastText
    except ImportError as e:
        raise ImportError(
            "pip install -e '.[rosetta]' to load FastText models."
        ) from e
    return FastText.load(str(path))


# ---------------------------------------------------------------------------
# Phase 1b — Sabellic / Early-Latin ingest hooks (NOT IMPLEMENTED)
# ---------------------------------------------------------------------------


def extract_latin_corpus_from_edr(*_args: Any, **_kwargs: Any) -> Iterator[list[str]]:
    """TODO: ingest pre-100 BCE inscriptions from Epigraphic Database Roma.

    Each external corpus needs its own license review and normalisation
    pipeline. Tracking as a separate work-item:
      - EDR API: http://www.edr-edr.it/ (CC-BY)
      - Tokenisation rules: Latin abbreviations (e.g. M·F → marci filius)
        need expansion before training, otherwise the abbreviated form
        becomes its own token and dilutes the root.
      - Date filter: only pre-100 BCE rows so we're aligning Etruscan
        against vocabulary contemporaneous with its productive period.
    """
    raise NotImplementedError(
        "EDR Latin ingest not yet wired. See ROADMAP.md Phase 1b."
    )


def extract_oscan_umbrian_corpus(*_args: Any, **_kwargs: Any) -> Iterator[list[str]]:
    """TODO: ingest Oscan + Umbrian from ImagInes Italicae or Untermann digitisation.

    Same shape as the Latin ingest — the training path is shared. What
    differs is the source repository, license, and abbreviation table.
    """
    raise NotImplementedError(
        "Oscan/Umbrian ingest not yet wired. See ROADMAP.md Phase 1b."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli_train(args: argparse.Namespace) -> int:
    sentences = list(extract_training_corpus(language=args.language))
    if not sentences:
        print(f"No {args.language} sentences found in corpus.", file=sys.stderr)
        return 1
    _, metadata = train_model(sentences, out_path=Path(args.output))
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    return 0


def _cli_nearest(args: argparse.Namespace) -> int:
    model = load_model(args.model)
    for word, score in nearest(model, args.word, k=args.k):
        print(f"{score:.4f}\t{word}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_train = sub.add_parser("train", help="Train a FastText model on the corpus")
    p_train.add_argument("--output", required=True, help="Path to write the .bin model")
    p_train.add_argument("--language", default="etruscan")
    p_train.set_defaults(fn=_cli_train)

    p_near = sub.add_parser("nearest", help="Look up nearest neighbours of a word")
    p_near.add_argument("--model", required=True)
    p_near.add_argument("--word", required=True)
    p_near.add_argument("--k", type=int, default=10)
    p_near.set_defaults(fn=_cli_nearest)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
