#!/usr/bin/env python3
"""Step 1 — build the cleaned training/index tables for the hybrid embedding
experiment.

Input : research/data/openetruscan_clean_grouped.csv (Zenodo v1.1.0)
Output: research/experiments/hybrid_embed/out/index.csv   (every retrievable row)
        research/experiments/hybrid_embed/out/train.csv   (deduped Etruscan-only
                                                           training rows)
        research/experiments/hybrid_embed/out/prepare_stats.json

Cleaning rules (see research/data/README.md, "What the tiers do not filter"):
  * keep data_quality == "clean"
  * drop rows whose transliteration is majority-uppercase — this removes both
    the ~525 Latin-orthography CIE rows and the retrograde-OCR junk, neither
    of which is Etruscan text the model should learn
  * training set is deduplicated on dup_group_id (one representative per
    group, longest text wins) so repeated formulae don't dominate the loss
    and group-level held-out splits cannot leak
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
REPO = HERE.parent.parent.parent
OUT = HERE / "out"

LEIDEN = re.compile(r"[\[\]<>{}()?]|---+")
SEP = re.compile(r"[:·•|/\\.\s]+")


def surface_text(row) -> str:
    """Best trainable surface form: words-only when present, else the
    transliteration with Leiden markup stripped."""
    words = row["canonical_words_only"]
    if isinstance(words, str) and words.strip():
        return words.strip()
    text = row["canonical_transliterated"]
    if not isinstance(text, str):
        return ""
    return " ".join(t for t in SEP.split(LEIDEN.sub(" ", text)) if t).strip()


def uppercase_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(c.isupper() for c in letters) / len(letters)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    df = pd.read_csv(REPO / "research/data/openetruscan_clean_grouped.csv")
    n_total = len(df)

    df = df[df["data_quality"] == "clean"].copy()
    n_clean = len(df)

    df["surface"] = df.apply(surface_text, axis=1)
    df = df[df["surface"].str.len() > 0]

    df["upper_ratio"] = df["canonical_transliterated"].fillna("").map(uppercase_ratio)
    latin_mask = df["upper_ratio"] > 0.5
    n_latin_like = int(latin_mask.sum())
    df = df[~latin_mask].copy()

    index_cols = ["id", "surface", "canonical_transliterated", "translation",
                  "dup_group_id", "dup_group_size", "intact_token_ratio"]
    df[index_cols].to_csv(OUT / "index.csv", index=False)

    # one representative per duplicate group; longest surface keeps the most
    # attested material
    train = (
        df.assign(_len=df["surface"].str.len())
        .sort_values("_len", ascending=False)
        .drop_duplicates("dup_group_id")
        .drop(columns="_len")
    )
    train[index_cols].to_csv(OUT / "train.csv", index=False)

    stats = {
        "rows_published": n_total,
        "rows_clean": n_clean,
        "rows_dropped_majority_uppercase": n_latin_like,
        "rows_index": len(df),
        "rows_train_deduped": len(train),
        "dup_groups_in_index": int(df["dup_group_id"].nunique()),
        "rows_with_translation": int(df["translation"].notna().sum()),
    }
    (OUT / "prepare_stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
