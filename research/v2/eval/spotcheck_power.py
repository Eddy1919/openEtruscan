"""How reliably does an n-row dual spot-check decide "Krippendorff α ≥ 0.80"?

The v2 handoff gates full adjudication on two philologists reaching α ≥ 0.80
on a 30-row blind spot-check. This simulates that decision so the gate's error
rates are known before anyone spends the hours.

Generative model: each item's class is drawn from the spot-check's class mix;
with probability ρ both raters give that label, otherwise each rater draws
independently from the class marginals. Under this model the population
Krippendorff α (nominal) equals ρ, so ρ is set to the assumed true α.

The pre-registered gate is unchanged; this only reports how often a point
estimate on n rows lands on the right side of 0.80.

Usage:
    python -m research.v2.eval.spotcheck_power \
        --spot-csv research/v2/handoff/v2.0.4-etr/spot_check_30_adjudicator_A.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path

from research.v2.eval.bootstrap import krippendorff_alpha_nominal

GATE = 0.80
TRUE_ALPHAS = (0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95)
NS = (30, 50, 75, 100)


def class_mix(spot_csv: Path, label_col: str = "silver_label") -> dict[str, float]:
    with spot_csv.open() as f:
        counts = Counter(row[label_col].strip().lower() for row in csv.DictReader(f))
    total = sum(counts.values())
    return {k: v / total for k, v in sorted(counts.items())}


def simulate_alpha(mix: dict[str, float], true_alpha: float, n: int, rng: random.Random) -> float:
    labels, weights = list(mix), list(mix.values())
    ratings = []
    for _ in range(n):
        if rng.random() < true_alpha:
            y = rng.choices(labels, weights)[0]
            ratings.append([y, y])
        else:
            ratings.append(rng.choices(labels, weights, k=2))
    return krippendorff_alpha_nominal(ratings)


def gate_table(
    mix: dict[str, float], n_sim: int = 4000, seed: int = 42
) -> dict[str, dict[str, dict[str, float]]]:
    rng = random.Random(seed)
    table: dict[str, dict[str, dict[str, float]]] = {}
    for n in NS:
        table[str(n)] = {}
        for a in TRUE_ALPHAS:
            draws = sorted(simulate_alpha(mix, a, n, rng) for _ in range(n_sim))
            draws = [d for d in draws if d == d]  # drop NaN (degenerate draws)
            table[str(n)][f"{a:.2f}"] = {
                "p_pass": sum(d >= GATE for d in draws) / len(draws),
                "alpha_hat_p2_5": draws[int(0.025 * len(draws))],
                "alpha_hat_p97_5": draws[int(0.975 * len(draws)) - 1],
            }
    return table


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--spot-csv", type=Path, required=True)
    ap.add_argument("--n-sim", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    mix = class_mix(args.spot_csv)
    table = gate_table(mix, args.n_sim, args.seed)

    print(f"class mix ({len(mix)} classes): {mix}")
    print(f"P(point α ≥ {GATE}) by true α, and the 95% range of the estimate:")
    header = "  n   " + "".join(f"  α={a:.2f}" for a in TRUE_ALPHAS)
    print(header)
    for n, row in table.items():
        print(f"  {n:<4}" + "".join(f"  {row[f'{a:.2f}']['p_pass']:6.2f}" for a in TRUE_ALPHAS))
    for n, row in table.items():
        r = row["0.85"]
        print(
            f"  n={n}: if true α = 0.85, the estimate falls in "
            f"[{r['alpha_hat_p2_5']:.2f}, {r['alpha_hat_p97_5']:.2f}]"
        )
    if args.out:
        args.out.write_text(json.dumps({"class_mix": mix, "gate": GATE, "table": table}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
