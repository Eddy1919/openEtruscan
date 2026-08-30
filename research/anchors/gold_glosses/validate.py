#!/usr/bin/env python3
"""Validate gold_glosses.jsonl: schema, enums, NFC normalization, duplicates,
and overlap with the frozen rosetta benchmark. Exit non-zero on violations.

Overlap with the rosetta TEST split is not an error, but those records are
excluded from any new eval or training use (README rule 3); the report names
them so nobody wires them in by accident.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent.parent.parent
sys.path.insert(0, str(REPO / "eval/harness"))
from rosetta_eval_pairs import eval_pairs  # noqa: E402

REQUIRED = ["etr", "gloss_en", "lat", "source_type", "citation_primary",
            "citation_modern", "confidence", "notes", "adjudication"]
SOURCE_TYPES = {"ancient_gloss", "bilingual", "lexicon", "combinatory",
                "loanword", "numeral"}
CONFIDENCES = {"high", "medium", "low"}
STATUSES = {"seeded", "verified", "rejected"}


def main() -> int:
    path = HERE / "gold_glosses.jsonl"
    errors: list[str] = []
    records = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {lineno}: invalid JSON ({exc})")
            continue
        for field in REQUIRED:
            if field not in r:
                errors.append(f"line {lineno}: missing field {field!r}")
        if r.get("source_type") not in SOURCE_TYPES:
            errors.append(f"line {lineno}: bad source_type {r.get('source_type')!r}")
        if r.get("confidence") not in CONFIDENCES:
            errors.append(f"line {lineno}: bad confidence {r.get('confidence')!r}")
        adj = r.get("adjudication") or {}
        if adj.get("status") not in STATUSES:
            errors.append(f"line {lineno}: bad adjudication.status {adj.get('status')!r}")
        if adj.get("status") == "verified" and not (adj.get("by") and adj.get("date")):
            errors.append(f"line {lineno}: verified without by/date")
        etr = r.get("etr", "")
        if etr != unicodedata.normalize("NFC", etr).lower().strip():
            errors.append(f"line {lineno}: etr not NFC-lowercase-stripped: {etr!r}")
        records.append(r)

    dupes = [k for k, c in Counter((r["etr"], r["gloss_en"]) for r in records).items()
             if c > 1]
    for d in dupes:
        errors.append(f"duplicate (etr, gloss_en): {d}")

    test_etr = {p.etr for p in eval_pairs(min_confidence="low", split="test")}
    train_etr = {p.etr for p in eval_pairs(min_confidence="low", split="train")}
    overlap_test = sorted({r["etr"] for r in records} & test_etr)
    overlap_train = sorted({r["etr"] for r in records} & train_etr)

    by_status = Counter(r["adjudication"]["status"] for r in records)
    by_conf = Counter(r["confidence"] for r in records)
    by_type = Counter(r["source_type"] for r in records)
    print(f"records: {len(records)}")
    print(f"status: {dict(by_status)} | confidence: {dict(by_conf)}")
    print(f"source_type: {dict(by_type)}")
    print(f"rosetta TEST overlap (excluded from any future use): {overlap_test or 'none'}")
    print(f"rosetta TRAIN overlap (flag only): {overlap_train or 'none'}")

    if errors:
        print("\nVIOLATIONS:")
        for e in errors:
            print(f"  {e}")
        return 1
    print("schema OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
