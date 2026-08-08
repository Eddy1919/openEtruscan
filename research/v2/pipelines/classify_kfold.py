"""Stratified K-fold assignment over text groups — the v2.1 split shape.

Why this exists
---------------
The frozen holdout (classify_split.py) allocates 400+ of 712 silver labels
(56%+) to test. Three of the seven classes end up unlearnable by
construction — `commercial` 0 train / 2 test, `boundary` 1/9, `legal` 3/7 —
and `commercial` contributes a structural zero to every macro-F1 computed on
it (CHANGELOG, Known). K-fold uses every label for both training and
evaluation: each row is predicted exactly once, by a model that never saw
its text group in training, and the pooled predictions give one confusion
matrix over all 712 rows instead of a thin holdout.

Two properties the assignment guarantees:

1. **Group-atomic.** Rows sharing a normalized text (`text_key`) go to the
   same fold, so no fold's training data contains another fold's eval texts.
   This is the text-disjointness of Deviation §D, carried into CV.
2. **Stratified.** Within each label, groups are dealt round-robin across
   folds in deterministic shuffled order, so class proportions stay as even
   as group atomicity allows. A class with fewer groups than folds simply
   appears in fewer eval folds — its rows are still all evaluated exactly
   once, which is strictly more evaluation than the frozen holdout gives it.

This module only ASSIGNS folds; it does not train. Output is one JSONL, one
row per silver-labelled inscription: the classify_split.py row schema plus
`fold`. A trainer evaluates fold i by training on `fold != i`.

Status: v2.1 protocol candidate. The pre-registered v2.0 frozen holdout
remains the citable eval until a pre-registration amendment adopts this.

Usage
-----
    python -m research.v2.pipelines.classify_kfold \\
        --corpus research/data/openetruscan_clean.csv \\
        --silver research/data/openetruscan_labels.csv \\
        --out research/v2/data/classify_kfold_v2_1.jsonl \\
        --folds 5 --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

from research.v2.pipelines.classify_split import (
    CODEBOOK_VERSION,
    _load_corpus,
    _load_silver,
    _source_tag,
    text_key,
)


def assign_folds(
    silver: dict[str, dict[str, str]],
    corpus: dict[str, dict],
    n_folds: int,
    seed: int,
) -> dict[str, int]:
    """Return {inscription_id: fold} — group-atomic, label-stratified."""
    # Group silver ids by normalized text; pure-markup rows stay singletons.
    groups: dict[str, list[str]] = defaultdict(list)
    for insc_id in silver:
        key = text_key(corpus.get(insc_id, {}).get("canonical_transliterated", ""))
        groups[key or f"\0{insc_id}"].append(insc_id)

    # A group's stratum is its majority label (groups are overwhelmingly
    # label-pure; `mi` at 7×ownership/1×dedicatory is the known exception).
    def majority_label(ids: list[str]) -> str:
        return Counter(silver[i]["label"] for i in ids).most_common(1)[0][0]

    by_label: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    for key, ids in groups.items():
        by_label[majority_label(ids)].append((key, sorted(ids)))

    rng = random.Random(seed)
    fold_of: dict[str, int] = {}
    # Deal each label's groups round-robin, largest classes first so their
    # rotation dominates the balance; start offset varies per label so small
    # classes don't all pile onto fold 0.
    for offset, label in enumerate(sorted(by_label, key=lambda c: -len(by_label[c]))):
        entries = sorted(by_label[label])  # determinism before shuffle
        rng.shuffle(entries)
        for j, (_key, ids) in enumerate(entries):
            fold = (j + offset) % n_folds
            for insc_id in ids:
                fold_of[insc_id] = fold
    return fold_of


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", type=Path, action="append", required=True)
    ap.add_argument("--silver", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    silver = _load_silver(args.silver)
    corpus: dict[str, dict] = {}
    for path in args.corpus:
        for k, v in _load_corpus(path).items():
            corpus.setdefault(k, v)
    if not silver:
        print(f"ERROR: no silver labels in {args.silver}", file=sys.stderr)
        return 1

    fold_of = assign_folds(silver, corpus, args.folds, args.seed)

    # Guard: no normalized text may span folds.
    key_fold: dict[str, int] = {}
    for insc_id, fold in fold_of.items():
        key = text_key(corpus.get(insc_id, {}).get("canonical_transliterated", ""))
        if not key:
            continue
        if key in key_fold and key_fold[key] != fold:
            print(f"ERROR: text group {key!r} spans folds", file=sys.stderr)
            return 1
        key_fold[key] = fold

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        for insc_id in sorted(fold_of):
            row = corpus.get(insc_id, {})
            silver_row = silver[insc_id]
            f.write(
                json.dumps(
                    {
                        "id": insc_id,
                        "raw_text": row.get("raw_text", ""),
                        "canonical_transliterated": row.get("canonical_transliterated", ""),
                        "translation": row.get("translation", ""),
                        "silver_label": silver_row["label"],
                        "silver_confidence": silver_row["confidence"],
                        "silver_signal_source": silver_row["signal_source"],
                        "source_tag": _source_tag(insc_id),
                        "fold": fold_of[insc_id],
                        "n_folds": args.folds,
                        "split_seed": args.seed,
                        "codebook_version": CODEBOOK_VERSION,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    per_fold = Counter(fold_of.values())
    print(f"rows: {len(fold_of)}  folds: {dict(sorted(per_fold.items()))}", file=sys.stderr)
    per_class = defaultdict(Counter)
    for insc_id, fold in fold_of.items():
        per_class[silver[insc_id]["label"]][fold] += 1
    for label in sorted(per_class):
        print(f"  {label:<12} {dict(sorted(per_class[label].items()))}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
