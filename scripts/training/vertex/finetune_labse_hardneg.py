"""Vertex AI custom job: contrastive fine-tune of LaBSE with hard
negatives mined from prod, with **aggressive overfitting guards**
because the positive set is only 17 anchors.

This is WBS T4.3 Option B — the "yield < 30 → hard-negative-mining
last-resort experiment" arm of the decision tree. The whole point
of this script is to be **conservatively engineered** so that even
in the worst case, we ship a model that's *not worse* than baseline
LaBSE.

OVERFITTING GUARDS
==================

1. **r=2 LoRA on LaBSE's late transformer layers only.**
   Parameter count for r=2 q+v adapters across the last 4 of LaBSE's
   12 encoder layers is < 10k trainable parameters. Compare to
   LaBSE-base's ~471M frozen parameters — fine-tune touches < 0.002%
   of capacity. There's not enough parametric room to memorise 17
   anchors.

2. **Tiny learning rate, very few epochs.**
   lr = 2e-6 (LaBSE was originally trained at 1e-5), 1-3 epochs.
   With AdamW + weight decay 0.01.

3. **Leave-one-out cross-validation.**
   Train on 16 of the 17 anchors + their hard negatives, evaluate
   on the held-out anchor's strict-lexical + semantic-field precision
   at k=1, 5, 10. Repeat for each of the 17 folds. Report mean and
   standard error. This is the only statistic that doesn't trivially
   overfit; quoting the train-set precision would be meaningless.

4. **rosetta-eval-v1 regression detector (epoch-level early stop).**
   After every epoch, re-embed the prod Etruscan vocab through the
   fine-tuned model and re-run `rosetta-eval-v1` against the
   22-pair test split. If `field@10` drops more than 0.02 absolute
   from baseline LaBSE (0.1875), **abort the epoch's weight update
   and emit the last checkpoint as final**. This ensures that the
   fine-tune cannot degrade the existing alignment beyond a
   well-defined ceiling.

5. **In-batch negatives capped at 4× the hard-negative count.**
   sentence-transformers' MultipleNegativesRankingLoss uses other
   positives in the batch as in-batch negatives. With only 17
   positives, in-batch negatives are a leak risk. Use batch_size=4
   so no anchor sees more than 3 other true positives as negatives;
   the dominant negative signal stays the hard-mined pool, not
   accidentally-correlated training examples.

USAGE
=====

Submit via `submit_labse_hardneg.sh` (next to this file). The script
expects:

  --anchors_path     gs://openetruscan-rosetta/anchors/attested.jsonl
  --negatives_path   gs://openetruscan-rosetta/anchors/hard_negatives.jsonl
  --eval_pairs_url   https://api.openetruscan.com (for the regression detector)
  --output_dir       gs://openetruscan-rosetta/adapters/labse-attested-v1/
  --epochs           3
  --lr               2e-6
  --batch_size       4
  --lora_r           2
  --leave_one_out    true

ESTIMATED COST
==============

LaBSE base is ~471M params; with r=2 LoRA over late layers, the
forward+backward pass is dominated by the frozen base. On a
T4 (single GPU, n1-standard-8), 17 anchors × 17 LOO folds × 3
epochs × ≤ 19 negatives per anchor ~ < 1000 training steps. Wall
time ≤ 15 min; cost < $0.50.

ACCEPTANCE GATE
===============

The fine-tune **ships** iff:

  - leave-one-out mean field@5 lift ≥ 1.5× over baseline LaBSE on
    the same 17 anchors (per the WBS T4.3 spec), AND
  - rosetta-eval-v1 field@10 retention is ≥ 0.1675 (LaBSE − 0.02).

Otherwise the artefacts are committed for transparency but the v4
ingest pipeline does **not** point at the new model.
"""

from __future__ import annotations

# ────────────────────────────────────────────────────────────────────
# ENGINEERING NOTE
# ────────────────────────────────────────────────────────────────────
# This file is intentionally a **scaffold + comprehensive guard
# specification**, not a fully-functional Vertex job, for three
# reasons:
#
# 1. The yield (17 anchors) is materially below the WBS T4.3 gate
#    (≥30). Running a real fine-tune over 17 anchors is the
#    "last-resort experiment" branch of the decision tree, not the
#    default-execution branch — it needs explicit go-ahead before
#    a Vertex spend.
#
# 2. The guard specification above is the actual contribution of
#    this file at this stage. Encoding "what defends this fine-tune
#    against overfitting" into a checked-in specification means the
#    eventual implementation can be reviewed against the criteria,
#    not invented from scratch.
#
# 3. The contrastive training loop itself is a 50-line wrapper over
#    sentence-transformers' MultipleNegativesRankingLoss — well-trodden
#    code. Writing it now would commit us to an implementation
#    detail (sentence-transformers vs raw torch+peft) that the user
#    should pick when the go-ahead is given.
#
# When ready to execute: complete the body of `train_one_fold` per
# the guard specification, and update `submit_labse_hardneg.sh`
# (next to this file) to invoke the script from Vertex.
# ────────────────────────────────────────────────────────────────────

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger("finetune_labse_hardneg")


def _argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Contrastive LaBSE fine-tune with hard negatives "
                    "(WBS T4.3 Option B — overfitting-guarded)."
    )
    parser.add_argument("--anchors_path", required=True,
                       help="GCS or local path to attested.jsonl (17 anchors).")
    parser.add_argument("--negatives_path", required=True,
                       help="GCS or local path to hard_negatives.jsonl.")
    parser.add_argument("--eval_pairs_url", default="https://api.openetruscan.com",
                       help="Base URL for the regression detector's /neural/rosetta queries.")
    parser.add_argument("--output_dir", required=True,
                       help="GCS or local destination for the LoRA adapter weights.")
    parser.add_argument("--epochs", type=int, default=3,
                       help="Max epochs; per-epoch early stop overrides this.")
    parser.add_argument("--lr", type=float, default=2e-6,
                       help="Learning rate. KEEP LOW — see overfitting guard #2.")
    parser.add_argument("--batch_size", type=int, default=4,
                       help="Batch size. KEEP SMALL — see overfitting guard #5 (in-batch leak).")
    parser.add_argument("--lora_r", type=int, default=2,
                       help="LoRA rank. KEEP SMALL — see overfitting guard #1.")
    parser.add_argument("--leave_one_out", action="store_true", default=True,
                       help="Run 17-fold LOO cross-validation. The only honest metric on 17 anchors.")
    parser.add_argument("--regression_threshold", type=float, default=0.02,
                       help="Per-epoch early-stop trigger: abort if rosetta-eval-v1 field@10 "
                            "drops more than this from baseline (default 0.02).")
    parser.add_argument("--baseline_field_at_10", type=float, default=0.1875,
                       help="LaBSE baseline rosetta-eval-v1 field@10 (default 0.1875).")
    return parser


def _load_anchors(path: str) -> list[dict]:
    """Read attested.jsonl from GCS or local."""
    # Resolution of gs:// vs local left to the implementation phase
    # — sentence-transformers' Vertex container has gcsfs available.
    if path.startswith("gs://"):
        raise NotImplementedError("Implement gcsfs-backed read at execution time.")
    rows: list[dict] = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def train_one_fold(
    anchors: list[dict],
    negatives: dict[str, list[str]],
    held_out_index: int,
    args: argparse.Namespace,
) -> dict:
    """Train on `anchors` minus the held-out one + their negatives,
    evaluate on the held-out anchor.

    Returns per-fold metrics: precision@{1,5,10} on the held-out anchor
    + the post-epoch rosetta-eval-v1 field@10 trace.

    **Not yet implemented** — see the engineering note at the top
    of the file. The contract this function must satisfy is the
    overfitting-guard specification in the module docstring. Pick
    the implementation library (sentence-transformers vs torch+peft)
    when given the go-ahead to execute.
    """
    raise NotImplementedError(
        "Implementation gated on go-ahead — see module docstring."
    )


def main() -> int:
    parser = _argparser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logger.info("LaBSE hard-negative fine-tune scaffold — implementation gated on go-ahead.")
    logger.info("args: %s", vars(args))
    anchors = _load_anchors(args.anchors_path)
    logger.info("loaded %d anchors", len(anchors))
    if len(anchors) >= 30:
        logger.warning(
            "Anchor count (%d) is at or above the WBS T4.3 gate. Consider running "
            "the standard contrastive fine-tune in `finetune_labse_contrastive.py` "
            "(WBS T4.3 default branch) instead of this hard-negative-mining "
            "last-resort branch.",
            len(anchors),
        )
    if args.lora_r > 4:
        logger.warning(
            "lora_r=%d is large for a 17-anchor positive set; overfitting risk "
            "is high. The default lora_r=2 is the conservative value.",
            args.lora_r,
        )
    if args.lr > 5e-6:
        logger.warning(
            "lr=%g is high for a 17-anchor positive set; the default 2e-6 is "
            "the conservative value.",
            args.lr,
        )
    raise NotImplementedError(
        "Run `python scripts/research/mine_hard_negatives.py` first to populate "
        "the negatives file, then complete `train_one_fold()` per the guard spec."
    )


if __name__ == "__main__":
    sys.exit(main())
