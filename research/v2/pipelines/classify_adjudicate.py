"""Adjudication-queue builder for Stream A.

Reads the raw jury output and produces three artifacts:

1. `classify_candidate_gold.jsonl` — rows where all jury models agree AND
   every model returned confidence ≥ medium. These are the "easy" rows; a
   philologist may still spot-check, but they are not the bottleneck.

2. `classify_adjudication_queue.jsonl` — rows where the jury split. Each row
   carries the proposed labels per model, the disagreement type, and metadata
   the philologist needs to decide. The queue is stratified by class so the
   philologist sees a balanced sample.

3. `classify_jury_summary.json` — aggregate stats: Krippendorff α (overall
   and per-class), label-confusion across raters, throughput metrics.

The Krippendorff α is computed per the eval/bootstrap module — same
implementation used in the final eval, so the agreement number reported
here is directly comparable to the post-adjudication number.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# Allow running as a script from anywhere in the repo
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from research.v2.eval.bootstrap import krippendorff_alpha_nominal  # noqa: E402
from research.v2.eval.classify_metrics import CLASSES  # noqa: E402

UNANIMITY_CONF_FLOOR = {"high", "medium"}


def load_jury(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Group jury rows by inscription id. Drops duplicate (model, id) pairs."""
    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            grouped[row["id"]][row["model"]] = row
    return {k: list(v.values()) for k, v in grouped.items()}


def load_test_pool(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            out[row["id"]] = row
    return out


def classify_row(jury_rows: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """Decide the disposition of a single inscription.

    Returns (disposition, summary):
        disposition in {"candidate_gold", "queue", "all_unsure"}
        summary contains per-model labels, the consensus label, etc.
    """
    labels = [r["label"] for r in jury_rows]
    confidences = [r["confidence"] for r in jury_rows]
    label_counts = Counter(labels)
    consensus, n_top = label_counts.most_common(1)[0]
    n_raters = len(jury_rows)

    if all(label == "unsure" for label in labels):
        disposition = "all_unsure"
    elif n_top == n_raters and consensus != "unsure" and all(
        c in UNANIMITY_CONF_FLOOR for c in confidences
    ):
        disposition = "candidate_gold"
    else:
        disposition = "queue"

    summary = {
        "consensus_label": consensus,
        "n_agree": n_top,
        "n_raters": n_raters,
        "per_model": [
            {
                "model": r["model"],
                "label": r["label"],
                "confidence": r["confidence"],
                "rationale": r["rationale"],
            }
            for r in jury_rows
        ],
    }
    return disposition, summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jury", type=Path, required=True,
                    help="JSONL produced by classify_jury.py")
    ap.add_argument("--test-pool", type=Path, required=True,
                    help="The frozen test JSONL from classify_split.py")
    ap.add_argument("--out-gold", type=Path, required=True,
                    help="Output JSONL of unanimous candidate-gold rows.")
    ap.add_argument("--out-queue", type=Path, required=True,
                    help="Output JSONL of rows for human adjudication.")
    ap.add_argument("--out-summary", type=Path, required=True,
                    help="Output JSON with aggregate jury stats.")
    ap.add_argument("--require-n-raters", type=int, default=3,
                    help="Drop rows with fewer than this many raters.")
    args = ap.parse_args(argv)

    jury = load_jury(args.jury)
    pool = load_test_pool(args.test_pool)

    # Build a ratings matrix for Krippendorff: one column per rater (sorted),
    # one row per inscription. Use None when a rater is missing.
    all_models: list[str] = sorted(
        {r["model"] for rows in jury.values() for r in rows}
    )
    ratings: list[list[str | None]] = []
    candidate_gold_rows: list[dict[str, Any]] = []
    queue_rows: list[dict[str, Any]] = []
    all_unsure: list[str] = []
    skipped_thin: list[str] = []

    for insc_id in sorted(pool):
        rows = jury.get(insc_id, [])
        if len(rows) < args.require_n_raters:
            skipped_thin.append(insc_id)
            continue
        # Krippendorff row
        per_model: dict[str, str] = {r["model"]: r["label"] for r in rows}
        ratings.append([per_model.get(m) for m in all_models])

        disp, summary = classify_row(rows)
        pool_row = pool[insc_id]
        record = {
            **pool_row,
            "jury_summary": summary,
            "disposition": disp,
        }
        if disp == "candidate_gold":
            candidate_gold_rows.append({
                **record,
                "gold_label": summary["consensus_label"],
                "gold_label_source": "candidate_jury_unanimous",
            })
        elif disp == "all_unsure":
            all_unsure.append(insc_id)
        else:
            queue_rows.append(record)

    # Stratify queue by silver_label so the philologist sees balanced classes.
    queue_rows.sort(key=lambda r: (r.get("silver_label", ""), r["id"]))

    alpha_overall = krippendorff_alpha_nominal(ratings) if ratings else float("nan")
    # Per-class alpha: include only rows where at least one rater labelled
    # this class.
    alpha_per_class: dict[str, float] = {}
    for cls in CLASSES:
        sub = [row for row in ratings if cls in row]
        alpha_per_class[cls] = (
            krippendorff_alpha_nominal(sub) if len(sub) >= 5 else float("nan")
        )

    # Write outputs
    args.out_gold.parent.mkdir(parents=True, exist_ok=True)
    with args.out_gold.open("w") as f:
        for r in candidate_gold_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with args.out_queue.open("w") as f:
        for r in queue_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    label_pair_counts: Counter[tuple[str, str]] = Counter()
    for row in ratings:
        for i, a in enumerate(row):
            for b in row[i + 1 :]:
                if a is None or b is None:
                    continue
                key = tuple(sorted([a, b]))
                label_pair_counts[key] += 1

    summary_payload: dict[str, Any] = {
        "n_inscriptions_pool": len(pool),
        "n_inscriptions_rated": len(ratings),
        "n_raters": len(all_models),
        "raters": all_models,
        "candidate_gold_count": len(candidate_gold_rows),
        "queue_count": len(queue_rows),
        "all_unsure_count": len(all_unsure),
        "thin_rated_skipped": len(skipped_thin),
        "krippendorff_alpha_overall": alpha_overall,
        "krippendorff_alpha_per_class": alpha_per_class,
        "top_disagreement_pairs": [
            {"pair": list(k), "count": v}
            for k, v in label_pair_counts.most_common(15)
        ],
    }
    args.out_summary.write_text(json.dumps(summary_payload, indent=2, sort_keys=True) + "\n")

    print(f"Pool size:         {len(pool)}", file=sys.stderr)
    print(f"Rated rows:        {len(ratings)}", file=sys.stderr)
    print(f"Candidate gold:    {len(candidate_gold_rows)}", file=sys.stderr)
    print(f"Adjudication queue: {len(queue_rows)}", file=sys.stderr)
    print(f"All-unsure:         {len(all_unsure)}", file=sys.stderr)
    print(f"Krippendorff α:    {alpha_overall:.3f}  (target ≥ 0.80)", file=sys.stderr)
    if alpha_overall < 0.60 and ratings:
        print("  WARNING: α below 0.60 indicates the codebook is ambiguous.",
              file=sys.stderr)
        print("  Consider revising codebook before adjudicating the queue.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
