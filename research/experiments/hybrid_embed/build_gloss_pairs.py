#!/usr/bin/env python3
"""WP10 prep — turn research/anchors/gold_glosses/gold_glosses.jsonl into
training pairs and a silver word-level eval.

Tiers and guards:
  * only status=llm_checked records are used (seeded stays out)
  * training additions exclude every Etruscan word in the frozen rosetta
    TEST split (leak guard, as everywhere in this experiment)
  * the silver eval excludes every rosetta word from BOTH splits, so it
    measures only new items and stays independent of the frozen benchmark
  * split is deterministic (sha1 of the etr form): ~80% train / 20% silver
    eval

Outputs: out/gg_train_pairs.csv   (surface, translation)  — training tier
         out/gg_silver_eval.csv   (surface, translation)  — silver eval
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
REPO = HERE.parent.parent.parent
OUT = HERE / "out"
sys.path.insert(0, str(REPO / "eval/harness"))
from rosetta_eval_pairs import eval_pairs  # noqa: E402


def clean_surface(etr: str) -> str:
    return etr.rstrip("-").strip()


def main() -> None:
    records = [json.loads(l) for l in
               (REPO / "research/anchors/gold_glosses/gold_glosses.jsonl")
               .read_text().splitlines() if l.strip()]
    checked = [r for r in records if r["adjudication"]["status"] == "llm_checked"]

    test_etr = {p.etr for p in eval_pairs(min_confidence="low", split="test")}
    train_etr = {p.etr for p in eval_pairs(min_confidence="low", split="train")}

    train_rows, silver_rows = [], []
    seen = set()
    for r in checked:
        etr = clean_surface(r["etr"])
        if not etr or etr in seen:
            continue
        seen.add(etr)
        gloss = r["gloss_en"].split("(")[0].strip().rstrip(",;")
        if not gloss:
            continue
        h = int(hashlib.sha1(etr.encode()).hexdigest(), 16) % 10
        if h < 8:  # train candidate
            if etr not in test_etr:
                train_rows.append({"surface": etr, "translation": gloss,
                                   "confidence": r["confidence"]})
        else:      # silver-eval candidate
            if etr not in test_etr and etr not in train_etr:
                silver_rows.append({"surface": etr, "translation": gloss,
                                    "confidence": r["confidence"]})

    pd.DataFrame(train_rows).to_csv(OUT / "gg_train_pairs.csv", index=False)
    pd.DataFrame(silver_rows).to_csv(OUT / "gg_silver_eval.csv", index=False)
    print(f"llm_checked {len(checked)} | train pairs {len(train_rows)} | "
          f"silver eval {len(silver_rows)} | rosetta-test excluded {len(test_etr)}")


if __name__ == "__main__":
    main()
