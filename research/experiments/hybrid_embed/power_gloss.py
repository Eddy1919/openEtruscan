#!/usr/bin/env python3
"""WP11: how many verified gloss items would it take to certify the WP10 effect?

Reads the trained towers, recomputes per-item ranks on the 71-item silver eval
(the only gold-gloss items no gold-gloss model trained on), and turns the
observed effect into sample sizes:

  * vs chance:   one-sided exact binomial on p@10 against K/|pool|
  * vs baseline: one-sided exact McNemar on paired p@10 hits (gg vs v1)
                 and a one-sided paired sign-flip test on reciprocal rank

Power is simulated by resampling items from the observed per-item joint
distribution (all four frozen+gold-gloss seeds pooled against v1), so the
discordance structure is the measured one. Because 71 items pin the effect
loosely, the script also reports n for a grid of assumed effects.

Assumption stated in the output: the candidate pool stays the size it is now
(chance fixed). A larger eval with a larger pool lowers chance and, likely,
p@10 with it.

Usage: python power_gloss.py
Output: out/power_gloss.json
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import stats

from eval_contrastive import Towers
from evaluate import K, OUT, l2

BASELINE = "v1"
GG_SEEDS = ["frozen_gg", "frozen_gg_s101", "frozen_gg_s202", "frozen_gg_s303"]
ALPHA = 0.05
TARGET_POWER = 0.80
N_SIM = 4000
N_GRID = [71, 150, 250, 319, 500, 800, 1200, 2000, 3000]
SEED = 20261124


def per_item_ranks(towers: Towers, pairs: list[tuple[str, str]], pool: list[str]) -> np.ndarray:
    cand = l2(towers.eng(pool))
    idx = {g: i for i, g in enumerate(pool)}
    q = l2(towers.etr([e for e, _ in pairs]))
    sims = q @ cand.T
    gold = np.array([idx[g] for _, g in pairs])
    gold_sim = sims[np.arange(len(pairs)), gold]
    # rank = 1 + number of candidates scoring strictly higher than the gold one
    return 1 + (sims > gold_sim[:, None]).sum(axis=1)


def binom_power(p1: float, p0: float, n: int, rng: np.random.Generator) -> float:
    """Exact one-sided binomial test of H0: p <= p0, simulated at true p1."""
    # critical count: smallest c with P(X >= c | p0) <= ALPHA
    c = int(stats.binom.isf(ALPHA, n, p0)) + 1
    hits = rng.binomial(n, p1, size=N_SIM)
    return float((hits >= c).mean())


def mcnemar_power(b_rate: float, c_rate: float, n: int, rng: np.random.Generator) -> float:
    """Exact one-sided McNemar (gg-only hits vs v1-only hits), simulated."""
    disc = rng.multinomial(n, [b_rate, c_rate, 1 - b_rate - c_rate], size=N_SIM)
    b, c = disc[:, 0], disc[:, 1]
    m = b + c
    pvals = np.where(m > 0, stats.binom.sf(b - 1, np.maximum(m, 1), 0.5), 1.0)
    return float((pvals < ALPHA).mean())


def signflip_power(diffs: np.ndarray, n: int, rng: np.random.Generator, n_sim: int = 600) -> float:
    """One-sided paired test on per-item differences, items resampled from `diffs`.

    Uses the large-sample normal approximation to the sign-flip null
    (mean / (sd/sqrt(n))), which is accurate for n >= 71 here.
    """
    rejects = 0
    for _ in range(n_sim):
        d = rng.choice(diffs, size=n, replace=True)
        sd = d.std(ddof=1)
        if sd == 0:
            continue
        z = d.mean() / (sd / np.sqrt(n))
        rejects += z > stats.norm.isf(ALPHA)
    return rejects / n_sim


def n_for_power(curve: dict[int, float]) -> int | None:
    for n in sorted(curve):
        if curve[n] >= TARGET_POWER:
            return n
    return None


def main() -> None:
    rng = np.random.default_rng(SEED)
    silver = pd.read_csv(OUT / "gg_silver_eval.csv", dtype=str)
    train_g = pd.read_csv(OUT / "gg_train_pairs.csv", dtype=str)
    pairs = list(zip(silver["surface"], silver["translation"], strict=True))
    pool = sorted(set(silver["translation"]) | set(train_g["translation"]))
    chance = K / len(pool)

    ranks = {
        tag: per_item_ranks(Towers("" if tag == BASELINE else f"_{tag}"), pairs, pool)
        for tag in [BASELINE, *GG_SEEDS]
    }
    hits = {t: (r <= K).astype(float) for t, r in ranks.items()}
    rr = {t: 1.0 / r for t, r in ranks.items()}

    base_hit, base_rr = hits[BASELINE], rr[BASELINE]
    gg_hit = np.stack([hits[t] for t in GG_SEEDS])  # [seeds, items]
    gg_rr = np.stack([rr[t] for t in GG_SEEDS])

    p_gg = float(gg_hit.mean())
    p_base = float(base_hit.mean())
    # discordance pooled over seeds: b = gg hit & v1 miss, c = v1 hit & gg miss
    b_rate = float(((gg_hit == 1) & (base_hit == 0)).mean())
    c_rate = float(((gg_hit == 0) & (base_hit == 1)).mean())
    rr_diffs = (gg_rr - base_rr).ravel()

    observed = {
        "n_items": len(pairs),
        "pool": len(pool),
        "chance_p_at_10": chance,
        "p_at_10": {t: float(h.mean()) for t, h in hits.items()},
        "mrr": {t: float(r.mean()) for t, r in rr.items()},
        "gg_seed_mean_p_at_10": p_gg,
        "discordance_gg_only": b_rate,
        "discordance_v1_only": c_rate,
        "mean_rr_diff_gg_minus_v1": float(rr_diffs.mean()),
        # what the 71 items say today
        "binom_p_gg_vs_chance_at_71": float(
            stats.binom.sf(round(p_gg * len(pairs)) - 1, len(pairs), chance)
        ),
    }

    curves = {"vs_chance_binomial": {}, "vs_v1_mcnemar": {}, "vs_v1_rr_signflip": {}}
    for n in N_GRID:
        curves["vs_chance_binomial"][n] = binom_power(p_gg, chance, n, rng)
        curves["vs_v1_mcnemar"][n] = mcnemar_power(b_rate, c_rate, n, rng)
        curves["vs_v1_rr_signflip"][n] = signflip_power(rr_diffs, n, rng)

    # sensitivity: n needed vs chance for assumed true p@10, pool fixed
    assumed = {}
    for p1 in [0.05, 0.06, 0.08, 0.10, 0.15, 0.20]:
        curve = {n: binom_power(p1, chance, n, rng) for n in N_GRID}
        assumed[f"{p1:.2f}"] = n_for_power(curve)

    out = {
        "assumptions": {
            "alpha_one_sided": ALPHA,
            "target_power": TARGET_POWER,
            "pool_size_fixed": True,
            "effect_source": "items resampled from the observed 71-item joint "
            "distribution, four frozen+gold-gloss seeds pooled against v1",
        },
        "observed": observed,
        "power_curves": curves,
        "n_for_80pct_power": {k: n_for_power(v) for k, v in curves.items()},
        "n_for_80pct_power_vs_chance_by_assumed_p_at_10": assumed,
    }
    (OUT / "power_gloss.json").write_text(json.dumps(out, indent=2))

    print(f"pool {len(pool)} | chance p@10 {chance:.3f} | n items {len(pairs)}")
    print(f"p@10: v1 {p_base:.3f} | gg seed mean {p_gg:.3f}")
    print(f"discordance: gg-only {b_rate:.3f}  v1-only {c_rate:.3f}")
    print(f"mean RR diff gg-v1: {rr_diffs.mean():+.4f}")
    print(f"binomial p (gg vs chance) at n=71: {observed['binom_p_gg_vs_chance_at_71']:.3f}")
    print("power by n:")
    for n in N_GRID:
        print(
            f"  n={n:5d}  vs-chance {curves['vs_chance_binomial'][n]:.2f}  "
            f"McNemar {curves['vs_v1_mcnemar'][n]:.2f}  "
            f"RR sign-flip {curves['vs_v1_rr_signflip'][n]:.2f}"
        )
    print("n for 80% power:", out["n_for_80pct_power"])
    print("n for 80% power vs chance, by assumed true p@10:", assumed)


if __name__ == "__main__":
    main()
