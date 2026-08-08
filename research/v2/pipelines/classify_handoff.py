"""Build the philologist handoff bundle from adjudication outputs.

The v2.0 handoff bundle (`research/v2/handoff/v2.0-etr/`) was generated ad
hoc from jury outputs that lived only in a since-retired GCP project's
cloudbuild bucket — when that project went away, so did the ability to
regenerate the bundle. This script makes the bundle a deterministic function
of the in-repo adjudication artifacts, so it can never be orphaned again.

Inputs are exactly what `classify_adjudicate.py` writes (queue JSONL, gold
JSONL, summary JSON). Outputs mirror the v2.0 bundle's shape:

- `adjudication_queue.csv` — every disagreement row, one column set per
  rater (label / confidence / rationale), plus empty `adjudicator_decision`
  and `adjudicator_notes` columns for the human to fill in.
- `spot_check_30_adjudicator_A.csv` / `_B.csv` — identical stratified
  30-row sub-samples drawn seeded from queue ∪ gold, for the blind
  inter-rater α ≥ 0.80 gate (`compute_alpha.py` in the bundle dir).

Usage
-----
    python -m research.v2.pipelines.classify_handoff \\
        --queue research/v2/results/classify/classify_queue_v2_0_4.jsonl \\
        --gold research/v2/results/classify/classify_candidate_gold_v2_0_4.jsonl \\
        --out-dir research/v2/handoff/v2.0.4-etr \\
        --seed 42
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _rater_slug(model: str) -> str:
    """Column-prefix slug for a rater model id: keep it terse but unambiguous."""
    return model.replace(".", "").replace("/", "_").replace("@", "_")


def rows_to_csv(rows: list[dict[str, Any]], out: Path, raters: list[str]) -> None:
    fields = [
        "id",
        "raw_text",
        "canonical_transliterated",
        "translation",
        "silver_label",
        "silver_confidence",
    ]
    for m in raters:
        slug = _rater_slug(m)
        fields += [f"{slug}_label", f"{slug}_confidence", f"{slug}_rationale"]
    fields += ["adjudicator_decision", "adjudicator_notes"]

    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            rec = {k: row.get(k, "") for k in fields[:6]}
            per_model = {p["model"]: p for p in row.get("jury_summary", {}).get("per_model", [])}
            for m in raters:
                slug = _rater_slug(m)
                p = per_model.get(m, {})
                rec[f"{slug}_label"] = p.get("label", "")
                rec[f"{slug}_confidence"] = p.get("confidence", "")
                rec[f"{slug}_rationale"] = p.get("rationale", "")
            rec["adjudicator_decision"] = ""
            rec["adjudicator_notes"] = ""
            writer.writerow(rec)


def stratified_sample(rows: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    """Deterministic ~n-row sample, spread across silver labels round-robin."""
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(rows, key=lambda r: str(r["id"])):
        by_label[row.get("silver_label", "")].append(row)
    rng = random.Random(seed)
    for bucket in by_label.values():
        rng.shuffle(bucket)
    out: list[dict[str, Any]] = []
    while len(out) < n and any(by_label.values()):
        for label in sorted(by_label):
            if by_label[label] and len(out) < n:
                out.append(by_label[label].pop())
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--queue", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--spot-check-n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    queue = _load_jsonl(args.queue)
    gold = _load_jsonl(args.gold)
    if not queue:
        print(f"ERROR: empty queue at {args.queue}", file=sys.stderr)
        return 1

    raters = sorted(
        {
            p["model"]
            for row in queue + gold
            for p in row.get("jury_summary", {}).get("per_model", [])
        }
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows_to_csv(queue, args.out_dir / "adjudication_queue.csv", raters)

    spot = stratified_sample(queue + gold, args.spot_check_n, args.seed)
    for adjudicator in ("A", "B"):
        rows_to_csv(
            spot,
            args.out_dir / f"spot_check_{args.spot_check_n}_adjudicator_{adjudicator}.csv",
            raters,
        )

    print(
        f"handoff bundle: queue={len(queue)} spot-check={len(spot)} raters={raters} "
        f"-> {args.out_dir}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
