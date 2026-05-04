#!/usr/bin/env python3
"""Populate one language's word vectors into the Rosetta vector store.

Three usage shapes:

  # 1. Native (anchor) population — Etruscan from this repo's corpus model.
  #    No alignment; vectors go in as-is with alignment_source='native'.
  python scripts/ops/populate_language.py \\
      --language ett \\
      --source-model models/etruscan.bin

  # 2. Aligned population — Latin via Procrustes against the Etruscan anchor.
  #    Loads the anchor model + the source model, fits Procrustes on the
  #    curated anchor pairs, projects every source word into Etruscan space,
  #    upserts the rotated vectors.
  python scripts/ops/populate_language.py \\
      --language lat \\
      --source-model models/cc.la.300.bin \\
      --align-to ett \\
      --anchor-model models/etruscan.bin

  # 3. Structural-only population — Linear A. Tier-3 languages skip the
  #    alignment step entirely; vectors are stored for within-language
  #    exploration only. The cross-language API still refuses queries
  #    against them.
  python scripts/ops/populate_language.py \\
      --language lin_a \\
      --source-model models/linear_a.bin \\
      --structural-only

Common options:
  --max-words N        cap the populated vocab (most-frequent-first)
  --min-frequency F    drop any word with corpus count < F
  --dry-run            do everything except the actual database INSERT
  --batch-size N       UPSERT batch size (default 1000)

Refuses to run if:
  * the language is unknown to LANGUAGE_TIERS
  * structural_embedding_viable=False (the registry says the corpus
    is too thin to honestly represent)
  * --align-to is set but the language is tier-3 / not alignable

The script never re-trains models — it consumes already-trained
gensim FastText/Word2Vec .bin files. Bring your own model, persist it
on the host where the script runs.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("populate_language")


def _load_model(path: str) -> Any:
    """Load a saved FastText/Word2Vec model. Tries FastText first since
    that's what the rest of the pipeline produces; falls back to
    KeyedVectors for raw .bin/.vec files (which is what fasttext.cc
    publishes — they ship native-format binaries that gensim can read
    via load_facebook_vectors).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Model not found: {path}")

    try:
        from gensim.models import FastText

        return FastText.load(str(p))
    except Exception as e:  # noqa: BLE001
        logger.info(
            "FastText.load failed (%s); trying load_facebook_vectors", e
        )
        from gensim.models.fasttext import load_facebook_vectors

        kv = load_facebook_vectors(str(p))

        # Wrap KeyedVectors in a minimal object that exposes `.wv` so the
        # populate path doesn't need branching.
        class _KVWrapper:
            def __init__(self, kv: Any) -> None:
                self.wv = kv

        return _KVWrapper(kv)


async def _do_populate(args: argparse.Namespace) -> int:
    from openetruscan.ml.multilingual import (
        LANGUAGE_TIERS,
        populate_aligned_language,
    )

    record = LANGUAGE_TIERS.get(args.language)
    if record is None:
        print(f"Unknown language: {args.language}", file=sys.stderr)
        return 2
    if args.align_to and not record.alignable:
        print(
            f"Cannot align tier-{record.tier} language {args.language!r}; "
            f"the registry marks it as not-alignable. "
            f"Use --structural-only instead.",
            file=sys.stderr,
        )
        return 2
    if not record.structural_embedding_viable:
        print(
            f"Language {args.language!r} is registered as structurally "
            f"non-viable. Refusing. Note: {record.notes}",
            file=sys.stderr,
        )
        return 2

    logger.info("Loading source model: %s", args.source_model)
    src_model = _load_model(args.source_model)
    src_vocab_size = len(src_model.wv)
    logger.info("  source vocab: %d", src_vocab_size)

    alignment_W = None
    alignment_source = "native"
    if args.align_to:
        from openetruscan.ml.alignment import (
            align_procrustes,
            anchor_pairs,
        )

        if args.align_to != "ett":
            print(
                f"--align-to currently only supports 'ett' (Etruscan). "
                f"Got {args.align_to!r}. Transitive alignment is "
                f"tracked in ROADMAP Phase 2b.",
                file=sys.stderr,
            )
            return 2

        if not args.anchor_model:
            print(
                "--align-to requires --anchor-model (path to the anchor "
                "language's gensim model).",
                file=sys.stderr,
            )
            return 2

        logger.info("Loading anchor model: %s", args.anchor_model)
        anchor = _load_model(args.anchor_model)

        pairs = anchor_pairs(min_confidence=args.min_anchor_confidence)
        # The Procrustes fitter expects (etr_model, lat_model) — pass anchor
        # as the etr side and src as the lat side, then invert the rotation
        # so we project FROM source space INTO anchor space.
        # Simpler: swap the roles in the call so we get the rotation that
        # takes source -> anchor directly.
        result = align_procrustes(
            etr_model=src_model,   # treat source as the rotated side
            lat_model=anchor,      # anchor is the target space
            pairs=pairs,
        )
        alignment_W = result.W
        alignment_source = f"procrustes_v1_to_{args.align_to}"
        logger.info(
            "Procrustes: %d pairs used, %d dropped, residual=%.3f",
            result.n_pairs_used, result.n_pairs_dropped, result.residual_norm,
        )

    if args.dry_run:
        print(
            json.dumps(
                {
                    "language": args.language,
                    "source_vocab_size": src_vocab_size,
                    "alignment": alignment_source,
                    "would_populate": min(
                        args.max_words or src_vocab_size, src_vocab_size
                    ),
                    "dry_run": True,
                },
                indent=2,
            )
        )
        return 0

    # Import the session factory only when we actually need to write —
    # this lets --dry-run succeed even when DATABASE_URL points at a
    # remote DB the operator can't reach yet.
    from openetruscan.db.session import get_engine

    _, session_maker = get_engine()
    async with session_maker() as session:
        result = await populate_aligned_language(
            language=args.language,
            model=src_model,
            alignment_W=alignment_W,
            session=session,
            source=args.source_label or Path(args.source_model).name,
            alignment_source=alignment_source,
            max_words=args.max_words,
            min_frequency=args.min_frequency,
        )

    print(
        json.dumps(
            {
                "language": result.language,
                "n_inserted": result.n_inserted,
                "n_skipped_oov": result.n_skipped_oov,
                "skipped_examples": result.skipped_examples,
                "alignment": alignment_source,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--language", required=True, help="Language code (see /neural/rosetta/languages)")
    parser.add_argument("--source-model", required=True, help="Path to the gensim FastText / .bin model")
    parser.add_argument("--source-label", help="Human-readable source name (default: filename)")
    parser.add_argument("--align-to", help="Anchor language code; required for non-native alignments")
    parser.add_argument("--anchor-model", help="Path to the anchor language's model")
    parser.add_argument(
        "--min-anchor-confidence",
        default="medium",
        choices=["low", "medium", "high"],
        help="Anchor-pair confidence threshold for Procrustes (default: medium)",
    )
    parser.add_argument("--max-words", type=int, help="Cap vocab size (most-frequent first)")
    parser.add_argument("--min-frequency", type=int, help="Drop any word below this corpus frequency")
    parser.add_argument(
        "--structural-only",
        action="store_true",
        help="(For tier-3 languages.) Populate vectors without alignment. "
             "Cross-language API still refuses queries against this language.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan but don't write to the DB")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.structural_only and args.align_to:
        print(
            "--structural-only and --align-to are mutually exclusive.",
            file=sys.stderr,
        )
        return 2

    import asyncio

    return asyncio.run(_do_populate(args))


if __name__ == "__main__":
    sys.exit(main())
