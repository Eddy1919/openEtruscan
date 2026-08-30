#!/usr/bin/env python3
"""WP9c — gloss augmentation: free contrastive positives by paraphrasing the
ENGLISH side only (the Etruscan surface is data, never touched).

All transforms are meaning-preserving and rule-based (no external model):
  * possessive flip:   "the X of Y"  ->  "Y's X"
  * article drop:      remove standalone the/a/an
  * adjacent swap:     one random neighbouring word swap (word-order noise —
                       English encoders should not lean on rigid order here)
  * random deletion:   drop one non-first word (glosses ≥4 words only)
  * tight synonym map: jug->pitcher, tomb->grave, gave->gifted,
                       made->fashioned, urn->vessel, mirror->speculum

Reads the TRAIN part of out/contrastive_pairs.csv (split produced by
train_contrastive.py); emits up to 3 deduped variants per pair.

Output: out/gloss_augmented.csv  (surface, translation, op)
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
OUT = HERE / "out"
SEED = 20260830

SYNONYMS = {"jug": "pitcher", "tomb": "grave", "gave": "gifted",
            "made": "fashioned", "urn": "vessel", "mirror": "speculum"}
POSSESSIVE = re.compile(r"\bthe (\w+) of (\w+)\b")
ARTICLE = re.compile(r"\b(?:the|a|an)\s+")


def variants(gloss: str, rng: np.random.Generator) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []

    flipped = POSSESSIVE.sub(lambda m: f"{m.group(2)}'s {m.group(1)}", gloss, count=1)
    if flipped != gloss:
        out.append((flipped, "possessive_flip"))

    dropped = ARTICLE.sub("", gloss).strip()
    if dropped and dropped != gloss:
        out.append((dropped, "article_drop"))

    words = gloss.split()
    if len(words) >= 3:
        i = int(rng.integers(0, len(words) - 1))
        sw = words.copy()
        sw[i], sw[i + 1] = sw[i + 1], sw[i]
        if sw != words:
            out.append((" ".join(sw), "adjacent_swap"))

    if len(words) >= 4:
        j = int(rng.integers(1, len(words)))
        out.append((" ".join(words[:j] + words[j + 1:]), "random_deletion"))

    syn = " ".join(SYNONYMS.get(w, w) for w in words)
    if syn != gloss:
        out.append((syn, "synonym"))

    # dedupe, drop exact copies of the source, cap at 3
    seen, keep = {gloss}, []
    for g, op in out:
        g = " ".join(g.split())
        if g and g not in seen:
            seen.add(g)
            keep.append((g, op))
    return keep[:3]


def main() -> None:
    rng = np.random.default_rng(SEED)
    pairs = pd.read_csv(OUT / "contrastive_pairs.csv", dtype=str)
    train = pairs[pairs["part"] == "train"]

    rows = []
    for _, r in train.iterrows():
        for g, op in variants(r["translation"], rng):
            rows.append({"surface": r["surface"], "translation": g, "op": op})
    aug = pd.DataFrame(rows).drop_duplicates(subset=["surface", "translation"])
    aug.to_csv(OUT / "gloss_augmented.csv", index=False)
    print(f"train pairs {len(train)} -> augmented variants {len(aug)}")
    print(aug["op"].value_counts().to_dict())


if __name__ == "__main__":
    main()
