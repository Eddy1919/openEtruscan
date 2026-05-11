#!/usr/bin/env python3
"""Mine hard negatives for LaBSE contrastive fine-tuning (WBS T4.3, Option B).

For each kept anchor in `research/anchors/attested.jsonl`, ask the
production `/neural/rosetta` endpoint for LaBSE's top-N Latin / Greek
neighbours of the Etruscan source word, then **drop the correct
positive equivalent and keep the rest** as the negative pool for that
anchor.

KNOWN LIMITATION (surfaced when running this script live against prod
on 2026-05-11)
==========================================================================
The naïve API path **does not work for literary anchors**. The 17 kept
attested anchors are extracted from classical-author passages
(Suetonius, Livy, Strabo, …), and almost none of them appear in the
prod `language_word_embeddings` table — which is built from
inscription tokens, not from literary citations. So
``GET /neural/rosetta?word=aesar&from=ett&to=lat`` returns
``neighbours: []`` for 16/17 anchors. Only ``apa`` (which happens to
exist in both an inscription and a literary attestation) returns a
real top-k.

The right execution path for hard-negative mining is **offline
encoding against the GCS embeddings JSONL**:

    1. Download gs://openetruscan-rosetta/embeddings/labse-v1.jsonl
       (~3.3 GiB; covers ett + grc + lat under (LaBSE, v1)).
    2. Filter to the target language(s) you care about.
    3. Load `sentence-transformers/LaBSE` locally and encode the 17
       anchor source words to 768-d vectors.
    4. Compute cosines against the filtered target vectors; take
       top-k; drop the positive equivalent.
    5. Write the JSONL out the same way this script does.

That path is a 50-line follow-up; the API path is preserved here for
documentary purposes and so that **if** a future ingestion populates
the prod table with the literary anchors, this script Just Works
again. The fine-tune in `scripts/training/vertex/finetune_labse_hardneg.py`
is the same regardless of which path produces the negatives, so the
scaffold is complete on the fine-tune side.

The output JSONL has one row per anchor with:

    {
      "etruscan_word": "aesar",
      "positive_equivalent": "deus",
      "positive_language": "lat",
      "hard_negatives": ["deum", "diuus", "divis", ...],
      "source": "Suetonius Divus Augustus",
      "passage_index": 1199
    }

This is the **data-generation** half of Option B. The fine-tune
itself lives in `scripts/training/vertex/finetune_labse_hardneg.py`
(below) and is **strongly guarded against overfitting** because the
positive set is only 17 anchors.

Overfitting guards (justified in the docstring of the fine-tune
script):

  - r=2 LoRA on LaBSE's late layers only (parameter count < 10k).
  - 1-3 epochs maximum, lr ≤ 5e-6.
  - Leave-one-out validation: for each of the 17 anchors, train on
    the other 16 + their negatives and measure on the held-out one.
    Report mean precision@5 across the 17 folds; this is the only
    statistic that doesn't trivially overfit.
  - **Regression detector:** during every epoch, re-eval against
    `rosetta-eval-v1` test split's `field@10`. If it drops by more
    than 0.02 absolute from the baseline LaBSE column, abort the
    epoch — the model is destroying its existing alignment.

USAGE
-----

```bash
# Mine top-20 hard negatives per anchor against prod API:
python scripts/research/mine_hard_negatives.py

# Use a different anchor file or a different API:
python scripts/research/mine_hard_negatives.py \
  --anchors research/anchors/attested.jsonl \
  --api-url https://api.openetruscan.com \
  --k 30
```

The output lands at `research/anchors/hard_negatives.jsonl` by default.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_ANCHORS = REPO_ROOT / "research" / "anchors" / "attested.jsonl"
DEFAULT_OUTPUT = REPO_ROOT / "research" / "anchors" / "hard_negatives.jsonl"
DEFAULT_API = "https://api.openetruscan.com"

logger = logging.getLogger("mine_hard_negatives")


def _query_neighbours(
    api_url: str,
    word: str,
    from_lang: str,
    to_lang: str,
    k: int,
    timeout_s: float = 30.0,
) -> list[tuple[str, float]]:
    """Ask /neural/rosetta for the top-k Latin/Greek neighbours of an
    Etruscan source word using the default (LaBSE) embedder.

    Returns (word, cosine_similarity) pairs.
    """
    resp = requests.get(
        f"{api_url}/neural/rosetta",
        params={
            "word": word,
            "from": from_lang,
            "to": to_lang,
            "k": k,
            # Default embedder = LaBSE/v1; we mine negatives that LaBSE
            # itself confuses for the positive, NOT v4 ones.
        },
        timeout=timeout_s,
    )
    resp.raise_for_status()
    data = resp.json()
    neighbours = data.get("neighbours") or []
    return [(n["word"], float(n["similarity"])) for n in neighbours]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--anchors", type=Path, default=DEFAULT_ANCHORS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--api-url", default=DEFAULT_API)
    parser.add_argument(
        "--k",
        type=int,
        default=20,
        help="Top-k neighbours per anchor; the correct positive is dropped so the final negative count is k-1 (or k if positive wasn't in top-k).",
    )
    parser.add_argument(
        "--from-lang",
        default="ett",
        help="Source language for the API query (default ett).",
    )
    parser.add_argument(
        "--rate-sleep",
        type=float,
        default=2.1,
        help="Seconds between API requests (default 2.1, matches the eval harness's polite pacing).",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not args.anchors.is_file():
        logger.error("anchors file not found: %s", args.anchors)
        return 2

    anchors: list[dict[str, Any]] = []
    with args.anchors.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            anchors.append(json.loads(line))

    logger.info("mining hard negatives for %d anchors via %s", len(anchors), args.api_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    n_written = 0
    n_skipped = 0
    with args.output.open("w", encoding="utf-8") as out:
        for i, anchor in enumerate(anchors, 1):
            etr = anchor["etruscan_word"]
            pos = anchor["equivalent"]
            to_lang = anchor["equivalent_language"]
            try:
                neighbours = _query_neighbours(
                    args.api_url, etr, args.from_lang, to_lang, args.k
                )
            except Exception as exc:
                logger.warning("API error on %r → skipping: %s", etr, exc)
                n_skipped += 1
                time.sleep(args.rate_sleep)
                continue

            # Drop the correct positive (case-insensitive, light normalisation).
            neg_pool = [
                w for (w, _sim) in neighbours
                if w.strip().lower() != pos.strip().lower()
            ]
            row = {
                "etruscan_word": etr,
                "positive_equivalent": pos,
                "positive_language": to_lang,
                "hard_negatives": neg_pool,
                "n_negatives": len(neg_pool),
                "source": anchor.get("source", ""),
                "passage_index": anchor.get("passage_index"),
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            n_written += 1
            logger.info(
                "%d/%d  %s → %s : %d negatives",
                i, len(anchors), etr, pos, len(neg_pool),
            )
            time.sleep(args.rate_sleep)

    logger.info("wrote %d rows → %s (%d skipped)", n_written, args.output, n_skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
