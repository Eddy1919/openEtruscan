"""Compute Krippendorff's α between two adjudicators' spot-check CSVs.

Usage:
    python compute_alpha.py spot_check_30_adjudicator_A.csv spot_check_30_adjudicator_B.csv

Reports:
- α overall on the `adjudicator_decision` column
- Per-row disagreements (so you can look at them)
- Recommendation (proceed / revise codebook / abort)

No external dependencies — pure Python 3.10+.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path


def krippendorff_alpha_nominal(ratings: list[list[str | None]]) -> float:
    """Krippendorff's α for nominal data with missing values.

    `ratings[item][rater]` = label or None. Returns α in [-1, 1].
    """
    values: set[str] = set()
    for row in ratings:
        for v in row:
            if v is not None:
                values.add(v)
    if not values:
        return float("nan")
    vlist = sorted(values)
    vidx = {v: i for i, v in enumerate(vlist)}
    k = len(vlist)
    coincidences = [[0.0] * k for _ in range(k)]
    for row in ratings:
        valid = [v for v in row if v is not None]
        m = len(valid)
        if m < 2:
            continue
        for i, a in enumerate(valid):
            for j, b in enumerate(valid):
                if i == j:
                    continue
                coincidences[vidx[a]][vidx[b]] += 1.0 / (m - 1)
    totals = [sum(row) for row in coincidences]
    n_total = sum(totals)
    if n_total == 0:
        return float("nan")
    obs = sum(coincidences[i][j] for i in range(k) for j in range(k) if i != j)
    exp = sum(totals[i] * totals[j] / (n_total - 1) for i in range(k) for j in range(k) if i != j)
    if exp == 0:
        return 1.0 if obs == 0 else float("nan")
    return 1.0 - obs / exp


def load_decisions(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    with path.open() as f:
        for row in csv.DictReader(f):
            dec = row.get("adjudicator_decision", "").strip().lower()
            if dec:
                out[row["id"]] = dec
    return out


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    a_path, b_path = Path(sys.argv[1]), Path(sys.argv[2])
    a = load_decisions(a_path)
    b = load_decisions(b_path)
    all_ids = sorted(set(a) | set(b))

    ratings = [[a.get(i), b.get(i)] for i in all_ids]
    rated = [r for r in ratings if r[0] is not None and r[1] is not None]
    alpha = krippendorff_alpha_nominal(rated) if rated else float("nan")

    agree = sum(1 for r in rated if r[0] == r[1])
    disagree = [(i, a[i], b[i]) for i in all_ids if i in a and i in b and a[i] != b[i]]

    print(f"Adjudicator A: {a_path.name}  ({len(a)} decisions)")
    print(f"Adjudicator B: {b_path.name}  ({len(b)} decisions)")
    print(f"Rated by both: {len(rated)} rows")
    print(f"Agreement    : {agree}/{len(rated)} = {agree / max(len(rated), 1):.1%}")
    print(f"Krippendorff α: {alpha:.3f}\n")

    if disagree:
        print(f"── disagreements ({len(disagree)}) ──")
        for insc_id, av, bv in disagree:
            print(f"  {insc_id:<14} A={av:<10} B={bv}")
        print()

    if alpha >= 0.80:
        print("→ α ≥ 0.80: codebook is reliable. Proceed to full 79-row adjudication.")
        return 0
    elif alpha >= 0.60:
        print("→ 0.60 ≤ α < 0.80: codebook is partially reliable.")
        print("   Review disagreements with project lead; may need v2.0.1 codebook revision.")
        return 1
    else:
        print("→ α < 0.60: codebook is too ambiguous in its current form.")
        print("   Do NOT proceed to full adjudication. Contact project lead.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
