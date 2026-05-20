"""Train-set lemma exclusion verifier for Rosetta-eval-v2.

Given:
  --eval     a JSONL of Rosetta pairs (the frozen test set)
  --corpus   a CSV of training inscriptions (the prod corpus snapshot)

This script:
1. Extracts every distinct Etruscan lemma from the eval pairs.
2. Tokenizes every training inscription's `canonical_transliterated` field.
3. For each lemma, lists training rows that contain it (whole-token match).
4. Writes a JSONL of inscriptions to exclude, plus a contamination report.

The exclusion list is consumed by the fine-tuning pipeline:

    python -m openetruscan.ml.finetune \\
        --exclude research/v2/data/rosetta_train_exclusions.jsonl \\
        ...

A model trained without honoring this list is disqualified from
Rosetta-eval-v2 results.

Token matching is intentionally simple: whitespace split + strip of Leiden
brackets `[]<>{}()` and trailing punctuation. Etruscan canonical
transliteration is whitespace-tokenized in the corpus, so this matches
exactly.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterator

LEIDEN_PUNCT = re.compile(r"[\[\]\{\}\(\)\<\>•·\.,;:?!]")


def _normalize_token(tok: str) -> str:
    """Strip editorial markup and punctuation; lowercase."""
    return LEIDEN_PUNCT.sub("", tok).strip().lower()


def tokenize(text: str) -> list[str]:
    return [t for t in (_normalize_token(p) for p in (text or "").split()) if t]


def iter_pairs(path: Path) -> Iterator[dict]:
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def iter_corpus(path: Path) -> Iterator[tuple[str, str]]:
    if not path.exists():
        return
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            insc_id = row.get("id", "").strip()
            text = row.get("canonical_transliterated", "")
            if insc_id:
                yield insc_id, text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--eval", type=Path, required=True,
                    help="Rosetta-eval-v2 frozen test JSONL.")
    ap.add_argument("--corpus", type=Path, required=True,
                    help="Cleaned-corpus CSV (training data source).")
    ap.add_argument("--out-exclusions", type=Path, required=True,
                    help="JSONL of inscriptions to exclude from training.")
    ap.add_argument("--out-report", type=Path, required=True,
                    help="JSON report: contamination counts per lemma.")
    args = ap.parse_args(argv)

    pairs = list(iter_pairs(args.eval))
    if not pairs:
        print(f"ERROR: empty eval file {args.eval}", file=sys.stderr)
        return 1
    eval_lemmas: set[str] = set()
    for p in pairs:
        word = _normalize_token(p.get("etruscan_word", ""))
        if word:
            eval_lemmas.add(word)

    contamination: dict[str, set[str]] = defaultdict(set)
    inscription_to_lemmas: dict[str, set[str]] = defaultdict(set)
    n_corpus = 0
    for insc_id, text in iter_corpus(args.corpus):
        n_corpus += 1
        toks = set(tokenize(text))
        hits = toks & eval_lemmas
        if hits:
            for lemma in hits:
                contamination[lemma].add(insc_id)
                inscription_to_lemmas[insc_id].add(lemma)

    args.out_exclusions.parent.mkdir(parents=True, exist_ok=True)
    with args.out_exclusions.open("w") as f:
        for insc_id in sorted(inscription_to_lemmas):
            f.write(json.dumps({
                "id": insc_id,
                "contaminating_lemmas": sorted(inscription_to_lemmas[insc_id]),
            }, ensure_ascii=False) + "\n")

    report = {
        "n_eval_pairs": len(pairs),
        "n_unique_eval_lemmas": len(eval_lemmas),
        "n_corpus_rows": n_corpus,
        "n_excluded_inscriptions": len(inscription_to_lemmas),
        "contamination_per_lemma": {
            lemma: len(ids) for lemma, ids in sorted(contamination.items())
        },
        "lemmas_with_zero_corpus_hits": sorted(eval_lemmas - set(contamination)),
    }
    args.out_report.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    print(f"Eval lemmas:          {len(eval_lemmas)}", file=sys.stderr)
    print(f"Corpus rows:          {n_corpus}", file=sys.stderr)
    print(f"Contaminated rows:    {len(inscription_to_lemmas)}", file=sys.stderr)
    print(f"  → excluded from training in {args.out_exclusions}", file=sys.stderr)
    pct = 100.0 * len(inscription_to_lemmas) / n_corpus if n_corpus else 0.0
    print(f"  ({pct:.1f}% of corpus)", file=sys.stderr)

    if not contamination:
        print("WARN: zero contamination found. Verify the eval file is non-empty",
              "and the corpus path is correct.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
