#!/usr/bin/env python3
"""Populate one language's word vectors into the Rosetta vector store.

Usage shapes:

  # Etruscan, fine-tuned LoRA adapter on top of XLM-R-base.
  python scripts/ops/populate_language.py \\
      --language ett \\
      --base-model xlm-roberta-base \\
      --adapter models/etr-lora-v1 \\
      --vocab-from-corpus

  # Latin, just the base XLM-R (no adapter — Latin is in the encoder's
  # pretraining).
  python scripts/ops/populate_language.py \\
      --language lat \\
      --base-model xlm-roberta-base \\
      --vocab-from-file vocabs/latin_top_100k.txt

  # Linear A, structural-only with a custom encoder (no LoRA, no
  # multilingual claim).
  python scripts/ops/populate_language.py \\
      --language lin_a \\
      --base-model models/linear_a-encoder \\
      --vocab-from-file vocabs/linear_a.txt

Common options:
  --vocab-from-corpus   pull words from the inscriptions table for that
                        language (Etruscan uses this; the others bring
                        their own vocab list)
  --vocab-from-file F   newline-separated word list
  --max-words N         cap the populated vocab
  --dry-run             everything except the actual DB INSERT
  --use-mock-embedder   for testing: deterministic SHA-256-derived
                        vectors, no model download needed

Refuses:
  * unknown language codes (must be in LANGUAGE_TIERS)
  * structural_embedding_viable=False languages (corpus too thin)
  * dim mismatch between embedder and the language's expected_dim
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Iterable
from pathlib import Path

logger = logging.getLogger("populate_language")


def _vocab_from_file(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]


async def _vocab_from_corpus(language_db_code: str) -> list[str]:
    """Pull a vocabulary list from the inscriptions table for one language.

    Returns words sorted by descending corpus frequency. The DB stores
    inscriptions with `language` ∈ {etruscan, latin, ...}; the mapping
    from our LANGUAGE_TIERS code (`ett`) to the DB string (`etruscan`)
    happens here so the registry stays clean.
    """
    from collections import Counter

    from sqlalchemy import select

    from openetruscan.db.models import Inscription
    from openetruscan.db.session import get_engine

    _, session_maker = get_engine()
    async with session_maker() as session:
        stmt = select(Inscription.canonical).where(
            Inscription.language == language_db_code
        )
        result = await session.execute(stmt)
        canonicals = [c for (c,) in result.all() if c]

    # Etruscan inscriptions use `:` and `·` as word dividers (Bonfante
    # 2002 §10) — many lines have NO spaces, only colons. Convert to
    # whitespace BEFORE tokenising so the vocab is real word forms.
    # `.` and `-` stay attached: `ve.i.tule` is one phonological unit;
    # `velxiti-leθes` is one onomastic compound.
    DIVIDERS = str.maketrans({":": " ", "·": " "})
    counts: Counter[str] = Counter()
    for c in canonicals:
        for tok in c.lower().translate(DIVIDERS).split():
            tok = tok.strip(",;!?\"'()[]")
            if tok:
                counts[tok] += 1
    return [w for w, _ in counts.most_common()]


async def _run(args: argparse.Namespace) -> int:
    from openetruscan.ml.multilingual import (
        LANGUAGE_TIERS,
        populate_language,
    )

    record = LANGUAGE_TIERS.get(args.language)
    if record is None:
        print(f"Unknown language: {args.language}", file=sys.stderr)
        return 2
    if not record.structural_embedding_viable:
        print(
            f"Language {args.language!r} is registered as structurally "
            f"non-viable. Refusing. Note: {record.notes}",
            file=sys.stderr,
        )
        return 2

    # 1. Resolve vocabulary.
    if args.vocab_from_corpus:
        # Map our registry code to the DB language string. Currently
        # only Etruscan corpus is in our DB; everything else expects
        # --vocab-from-file.
        if args.language != "ett":
            print(
                f"--vocab-from-corpus only supports the Etruscan corpus today. "
                f"For {args.language!r} use --vocab-from-file.",
                file=sys.stderr,
            )
            return 2
        words = await _vocab_from_corpus("etruscan")
    elif args.vocab_from_file:
        words = _vocab_from_file(Path(args.vocab_from_file))
    else:
        print(
            "Provide either --vocab-from-corpus or --vocab-from-file.",
            file=sys.stderr,
        )
        return 2

    if args.max_words is not None:
        words = words[: args.max_words]
    logger.info("Resolved vocabulary: %d words", len(words))

    # 2. Build the embedder.
    if args.use_mock_embedder:
        from openetruscan.ml.embeddings import MockEmbedder

        embedder = MockEmbedder(dim=record.expected_dim, model_id="mock")
    else:
        from openetruscan.ml.embeddings import XLMREmbedder

        embedder = XLMREmbedder(
            model_id=args.base_model,
            adapter_path=args.adapter,
        )

    info = embedder.info
    logger.info("Embedder: %s rev=%s dim=%d", info.model_id, info.revision, info.dim)

    # 3. Dry-run early-exit.
    if args.dry_run:
        print(
            json.dumps(
                {
                    "language": args.language,
                    "n_words": len(words),
                    "embedder": info.model_id,
                    "embedder_revision": info.revision,
                    "embedder_dim": info.dim,
                    "expected_dim": record.expected_dim,
                    "dry_run": True,
                },
                indent=2,
            )
        )
        return 0

    # 4. Embed + upsert.
    from openetruscan.db.session import get_engine

    _, session_maker = get_engine()
    async with session_maker() as session:
        result = await populate_language(
            language=args.language,
            words=words,
            embedder=embedder,
            session=session,
            source=args.source_label or info.model_id,
        )
    print(
        json.dumps(
            {
                "language": result.language,
                "n_inserted": result.n_inserted,
                "n_skipped_empty": result.n_skipped_empty,
                "skipped_examples": result.skipped_examples,
                "embedder_model_id": result.embedder_model_id,
                "embedder_revision": result.embedder_revision,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--language", required=True)
    parser.add_argument("--base-model", default="xlm-roberta-base")
    parser.add_argument("--adapter", help="Path to a saved LoRA / PEFT adapter directory")
    parser.add_argument("--vocab-from-corpus", action="store_true")
    parser.add_argument("--vocab-from-file", help="Newline-separated vocab file")
    parser.add_argument("--max-words", type=int)
    parser.add_argument("--source-label", help="Human-readable source string (default: model_id)")
    parser.add_argument(
        "--use-mock-embedder",
        action="store_true",
        help="Use deterministic SHA-256 vectors instead of a real encoder. For tests.",
    )
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(list(argv) if argv is not None else None)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
