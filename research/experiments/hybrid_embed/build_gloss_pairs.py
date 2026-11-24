#!/usr/bin/env python3
"""WP10 prep: turn research/anchors/gold_glosses/gold_glosses.jsonl into
training pairs and a silver word-level eval.

Tiers and guards (implemented in research/anchors/gold_glosses/gloss_splits.py,
shared with the human verification worksheet):
  * status llm_checked or verified records are used (seeded and rejected stay out)
  * training additions exclude every Etruscan word in the frozen rosetta
    TEST split (leak guard, as everywhere in this experiment)
  * the silver eval excludes every rosetta word from BOTH splits, so it
    measures only new items and stays independent of the frozen benchmark
  * split is deterministic (sha1 of the etr form): ~80% train / 20% silver
    eval

Outputs: out/gg_train_pairs.csv   (surface, translation), training tier
         out/gg_silver_eval.csv   (surface, translation), silver eval
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
REPO = HERE.parent.parent.parent
OUT = HERE / "out"
sys.path.insert(0, str(REPO / "eval/harness"))
sys.path.insert(0, str(REPO / "research/anchors/gold_glosses"))
from gloss_splits import (  # noqa: E402
    GG_SILVER,
    GG_TRAIN,
    USABLE_STATUSES,
    assign_splits,
    clean_surface,
    gloss_head,
)
from rosetta_eval_pairs import eval_pairs  # noqa: E402


def main() -> None:
    records = [
        json.loads(ln)
        for ln in (REPO / "research/anchors/gold_glosses/gold_glosses.jsonl")
        .read_text()
        .splitlines()
        if ln.strip()
    ]
    checked = [r for r in records if r["adjudication"]["status"] in USABLE_STATUSES]

    test_etr = {p.etr for p in eval_pairs(min_confidence="low", split="test")}
    train_etr = {p.etr for p in eval_pairs(min_confidence="low", split="train")}
    splits = assign_splits(records, test_etr, train_etr)

    train_rows, silver_rows = [], []
    for r in checked:
        row = {
            "surface": clean_surface(r["etr"]),
            "translation": gloss_head(r["gloss_en"]),
            "confidence": r["confidence"],
        }
        if splits[r["etr"]] == GG_TRAIN:
            train_rows.append(row)
        elif splits[r["etr"]] == GG_SILVER:
            silver_rows.append(row)

    pd.DataFrame(train_rows).to_csv(OUT / "gg_train_pairs.csv", index=False)
    pd.DataFrame(silver_rows).to_csv(OUT / "gg_silver_eval.csv", index=False)
    print(
        f"usable {len(checked)} | train pairs {len(train_rows)} | "
        f"silver eval {len(silver_rows)} | rosetta-test excluded {len(test_etr)}"
    )


if __name__ == "__main__":
    main()
