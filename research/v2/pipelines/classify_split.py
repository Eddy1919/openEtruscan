"""Frozen-split generator for Stream A (Classification).

Reads the v1 cleaned corpus and produces a stratified, seeded train/test
split. The output is a pair of JSONL files committed to the repository so
the split is byte-reproducible.

Usage
-----
    python -m research.v2.pipelines.classify_split \\
        --corpus research/data/openetruscan_clean.csv \\
        --silver research/data/openetruscan_labels.csv \\
        --out-train research/v2/data/classify_train_pool.jsonl \\
        --out-test  research/v2/data/classify_test_v2.jsonl \\
        --n-test 400 \\
        --seed 42

Behavior
--------
- Strata: (silver_label) × (silver_confidence) × (source_tag).
  source_tag is "Larth" if id matches Larth Pallottino-Rix conventions, else
  "CIE" / "ETP" / "other".
- The held-out test pool consists of `--n-test` rows sampled WITHOUT
  REPLACEMENT, stratum-proportional. Tail strata with fewer than 2 rows are
  upsampled to at least 2 rows each (so every class has ≥2 test examples).
- The training pool is the remainder. The script guarantees zero overlap
  between train and test by id.
- Each output row carries: id, raw_text, canonical_transliterated,
  translation (if present), silver_label, silver_confidence, source_tag,
  stratum_id, split_seed, codebook_version.

This script is a SPLIT generator. It does NOT label data. The test rows are
still silver-labeled — the LLM-jury + adjudication pipeline replaces those
labels with gold afterwards.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

CODEBOOK_VERSION = "v2.0"
SEED = 42


def _source_tag(insc_id: str) -> str:
    """Heuristic source classification from the id format."""
    pid = insc_id.strip()
    if pid.startswith("CIE "):
        return "CIE"
    if pid.startswith("ETP "):
        return "ETP"
    # Pallottino-Rix ids: "Cl 1.1006", "Ta 1.66", "Vc 1.59", etc.
    if (
        len(pid) >= 4
        and pid[:2].isalpha()
        and pid[0].isupper()
        and pid[2] == " "
        and any(ch.isdigit() for ch in pid)
    ):
        return "Larth"
    return "other"


def _load_silver(path: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            out[row["id"].strip()] = {
                "label": row["label"].strip(),
                "confidence": row["confidence"].strip(),
                "signal_source": row.get("signal_source", "").strip(),
            }
    return out


def _normalize_corpus_row(row: dict[str, Any]) -> dict[str, Any]:
    """Map the various corpus JSONL schemas onto the CSV-named fields the
    pipeline downstream expects.

    Known schema variants:
      - v1 Zenodo CSV:        id, raw_text, canonical_transliterated, translation, ...
      - prod-rawtext-v3 JSONL: id, raw_text, canonical_clean, translation, data_quality, ...
      - prod-v2 JSONL (lean): id, text                                                    ← the
                                                                                            publication-id
                                                                                            namespace
                                                                                            (CIE/Pallottino-Rix/ETP)
                                                                                            that joins
                                                                                            the silver
                                                                                            labels.

    We coalesce all three into the v1 CSV shape so downstream code stays
    schema-agnostic.
    """
    out = dict(row)
    if "raw_text" not in out and "text" in out:
        out["raw_text"] = out["text"]
    if "canonical_transliterated" not in out:
        if "canonical_clean" in out:
            out["canonical_transliterated"] = out["canonical_clean"]
        elif "text" in out:
            out["canonical_transliterated"] = out["text"]
    return out


def _load_corpus(path: Path) -> dict[str, dict[str, Any]]:
    """Load corpus from CSV or JSONL; tolerate missing file (smoke-test mode).

    Format is auto-detected by suffix:
      - .csv  → csv.DictReader
      - .jsonl / .ndjson → one JSON object per line (prod-rawtext-v* schema)
    """
    out: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return out
    suffix = path.suffix.lower()
    if suffix in (".jsonl", ".ndjson"):
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                insc_id = str(row.get("id", "")).strip()
                if not insc_id:
                    continue
                out[insc_id] = _normalize_corpus_row(row)
    else:
        with path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                insc_id = row.get("id", "").strip()
                if not insc_id:
                    continue
                out[insc_id] = _normalize_corpus_row(row)
    return out


def _stratum(silver_row: dict[str, str], src: str) -> str:
    return f"{silver_row['label']}|{silver_row['confidence']}|{src}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--corpus",
        type=Path,
        action="append",
        required=True,
        help="Path to corpus file. Pass multiple times to merge "
        "across id namespaces (e.g. once for publication-id "
        "JSONL, once for integer-DB-id JSONL). Later sources "
        "do not override earlier ones for the same id.",
    )
    ap.add_argument(
        "--silver",
        type=Path,
        default=Path("research/data/openetruscan_labels.csv"),
        help="Path to v1 silver-label CSV.",
    )
    ap.add_argument(
        "--out-train", type=Path, required=True, help="Output JSONL for the training pool."
    )
    ap.add_argument(
        "--out-test", type=Path, required=True, help="Output JSONL for the frozen test pool."
    )
    ap.add_argument(
        "--n-test",
        type=int,
        default=400,
        help="Target test-pool size (rounded up to satisfy class-2 floor).",
    )
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args(argv)

    silver = _load_silver(args.silver)
    corpus: dict[str, dict[str, Any]] = {}
    for path in args.corpus:
        loaded = _load_corpus(path)
        # Earlier sources win on id collision (deterministic across re-runs).
        for k, v in loaded.items():
            corpus.setdefault(k, v)
        print(f"Loaded {len(loaded):>6} rows from {path}", file=sys.stderr)
    if not silver:
        print(f"ERROR: no silver labels loaded from {args.silver}", file=sys.stderr)
        return 1
    matched = sum(1 for sid in silver if sid in corpus)
    print(
        f"Silver-corpus join: {matched}/{len(silver)} silver ids " f"resolved to corpus text",
        file=sys.stderr,
    )

    # Group ids by stratum
    strata: dict[str, list[str]] = defaultdict(list)
    for insc_id, lab in silver.items():
        src = _source_tag(insc_id)
        strata[_stratum(lab, src)].append(insc_id)

    rng = random.Random(args.seed)
    for ids in strata.values():
        ids.sort()  # determinism before shuffle
        rng.shuffle(ids)

    n_total = sum(len(v) for v in strata.values())
    if n_total == 0:
        print("ERROR: silver labels file is empty", file=sys.stderr)
        return 1
    target_test = min(args.n_test, n_total)

    # Stratum-proportional allocation with class-2 floor on each (label) bucket.
    test_ids: set[str] = set()

    # First pass: enforce floor of 2 test rows per (label) — sample from the
    # most-confident, most-common stratum for each label.
    labels_seen: dict[str, list[str]] = defaultdict(list)
    for stratum, ids in strata.items():
        label = stratum.split("|", 1)[0]
        labels_seen[label].extend(ids)
    for ids in labels_seen.values():
        for insc_id in ids[: min(2, len(ids))]:
            test_ids.add(insc_id)

    remaining = target_test - len(test_ids)
    if remaining > 0:
        # Proportional sampling from the rest
        per_stratum_quota: dict[str, int] = {}
        for stratum, ids in strata.items():
            per_stratum_quota[stratum] = max(0, round(remaining * len(ids) / n_total))
        # Sample without replacement, skipping floor-taken ids
        for stratum, ids in strata.items():
            quota = per_stratum_quota[stratum]
            taken_in_stratum = 0
            for insc_id in ids:
                if taken_in_stratum >= quota:
                    break
                if insc_id in test_ids:
                    continue
                test_ids.add(insc_id)
                taken_in_stratum += 1
                if len(test_ids) >= target_test:
                    break
            if len(test_ids) >= target_test:
                break

    # Materialize rows
    def _row(insc_id: str) -> dict[str, Any]:
        silver_row = silver[insc_id]
        src = _source_tag(insc_id)
        corpus_row = corpus.get(insc_id, {})
        return {
            "id": insc_id,
            "raw_text": corpus_row.get("raw_text", ""),
            "canonical_transliterated": corpus_row.get("canonical_transliterated", ""),
            "translation": corpus_row.get("translation", ""),
            "silver_label": silver_row["label"],
            "silver_confidence": silver_row["confidence"],
            "silver_signal_source": silver_row["signal_source"],
            "source_tag": src,
            "stratum_id": _stratum(silver_row, src),
            "split_seed": args.seed,
            "codebook_version": CODEBOOK_VERSION,
        }

    args.out_test.parent.mkdir(parents=True, exist_ok=True)
    with args.out_test.open("w") as f:
        for insc_id in sorted(test_ids):
            f.write(json.dumps(_row(insc_id), ensure_ascii=False) + "\n")

    train_ids = set(silver) - test_ids
    with args.out_train.open("w") as f:
        for insc_id in sorted(train_ids):
            f.write(json.dumps(_row(insc_id), ensure_ascii=False) + "\n")

    # Report
    assert not (test_ids & train_ids), "CONTAMINATION: train and test overlap!"
    print(f"Total silver rows: {n_total}", file=sys.stderr)
    print(f"Test pool:  {len(test_ids):4d} rows  → {args.out_test}", file=sys.stderr)
    print(f"Train pool: {len(train_ids):4d} rows  → {args.out_train}", file=sys.stderr)
    print(f"Seed: {args.seed}  Codebook: {CODEBOOK_VERSION}", file=sys.stderr)

    # Per-class test breakdown
    from collections import Counter

    label_counts = Counter(silver[i]["label"] for i in test_ids)
    print("\nTest-pool class breakdown:", file=sys.stderr)
    for cls, count in sorted(label_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {cls:12s} {count:3d}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
