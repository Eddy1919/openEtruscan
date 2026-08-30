#!/usr/bin/env python3
"""WP10 eval — word-level gloss retrieval on (a) the 71-item silver eval
(held-out gold_glosses records, no rosetta overlap) and (b) the frozen
rosetta gloss test (n=22), for one or more trained tags.

Candidate pool for the silver eval: every distinct gloss string across
gg_train + gg_silver (~250+) — a much harder pool than rosetta's 60.

Usage: python eval_gloss_silver.py --tags v1 frozen_aug_mined frozen_gg ...
Output: out/gloss_silver_results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from evaluate import OUT, REPO, K, l2
from eval_contrastive import Towers

sys.path.insert(0, str(REPO / "eval/harness"))
from rosetta_eval_pairs import eval_pairs  # noqa: E402


def rank_metrics(towers: Towers, pairs: list[tuple[str, str]],
                 candidates: list[str]) -> dict:
    cand_vecs = l2(towers.eng(candidates))
    cand_idx = {g: i for i, g in enumerate(candidates)}
    p1 = p10 = 0
    rr = []
    for etr, gloss in pairs:
        ev = l2(towers.etr([etr]))[0]
        order = np.argsort(-(cand_vecs @ ev))
        rank = int(np.where(order == cand_idx[gloss])[0][0]) + 1
        p1 += int(rank == 1)
        p10 += int(rank <= K)
        rr.append(1.0 / rank)
    n = len(pairs)
    return {"n": n, "candidates": len(candidates),
            "p_at_1": p1 / n, "p_at_10": p10 / n, "mrr": float(np.mean(rr)),
            "chance_p_at_10": K / len(candidates)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", nargs="+", required=True)
    args = ap.parse_args()

    silver = pd.read_csv(OUT / "gg_silver_eval.csv", dtype=str)
    train_g = pd.read_csv(OUT / "gg_train_pairs.csv", dtype=str)
    silver_pairs = list(zip(silver["surface"], silver["translation"]))
    pool = sorted(set(silver["translation"]) | set(train_g["translation"]))

    ros_test = eval_pairs(split="test")
    ros_all = eval_pairs(min_confidence="low", split=None)
    ros_pairs = [(p.etr, p.gloss.lower()) for p in ros_test]
    ros_pool = sorted({p.gloss.lower() for p in ros_all})

    results = {}
    for tag in args.tags:
        sfx = "" if tag == "v1" else f"_{tag}"
        towers = Towers(sfx)
        results[tag] = {
            "silver_gloss_71": rank_metrics(towers, silver_pairs, pool),
            "rosetta_gloss_22": rank_metrics(towers, ros_pairs, ros_pool),
        }
        s, r = results[tag]["silver_gloss_71"], results[tag]["rosetta_gloss_22"]
        print(f"{tag:20} silver p@10 {s['p_at_10']:.3f} mrr {s['mrr']:.3f} "
              f"(chance {s['chance_p_at_10']:.3f}) | rosetta p@10 {r['p_at_10']:.3f}")

    (OUT / "gloss_silver_results.json").write_text(json.dumps(results, indent=2))
    print("saved out/gloss_silver_results.json")


if __name__ == "__main__":
    main()
