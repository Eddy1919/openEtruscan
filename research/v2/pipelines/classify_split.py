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
  between train and test both by id AND by normalized text (see below).
- Each output row carries: id, raw_text, canonical_transliterated,
  translation (if present), silver_label, silver_confidence, source_tag,
  stratum_id, split_seed, codebook_version.

Text-level disjointness
-----------------------
An id-only guard is not sufficient. The corpus holds 6,567 rows over 6,097
distinct `canonical_transliterated` values — 470 rows repeat a text that also
appears under a *different* id (`mi`, `suθina`, `aplu`, `alpan` and other short
formulaic items recur across genuinely distinct artifacts). An id-disjoint
split therefore still leaks: the model can see the exact test string, with the
same label, during training.

Measured on the frozen v2 split, which was generated before this guard existed:
25/400 test rows (6.2%) had a bracket-stripped twin in the train pool and 23 of
those twins carried the same label. The leak is not uniform — it concentrates in
short, high-frequency forms, which are also the rows an LLM jury most reliably
agrees on, so it is *enriched* in the unanimous candidate-gold set that carries
the published metric rather than diluted across the full test pool.

This generator therefore samples **text groups**, not rows: once a row enters
the test pool, every other silver-labelled row sharing its normalized text
follows it there. Groups are almost all singletons, so stratum proportions move
only slightly, but the test pool may finish a few rows above `--n-test`. The
run fails outright if any normalized text still appears on both sides.

This script is a SPLIT generator. It does NOT label data. The test rows are
still silver-labeled — the LLM-jury + adjudication pipeline replaces those
labels with gold afterwards.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

CODEBOOK_VERSION = "v2.0"
SEED = 42

# Leiden editorial markup and lacuna marks. Two rows that differ only in how an
# editor bracketed a restoration are the same string for leakage purposes:
# `la(u)tni`, `lautn(i)` and `laut(n)i` all reduce to `lautni`.
_MARKUP = re.compile(r"[\[\]<>{}()?\-–—]")
_WS = re.compile(r"\s+")


def text_key(text: str) -> str:
    """Normalized form used to detect the same inscription text across ids.

    Strips Leiden markup, collapses whitespace, and casefolds. Rows whose text
    is *entirely* markup normalize to the empty string; those must not be
    fused into one giant group, so callers fall back to a per-row unique key.
    """
    return _WS.sub(" ", _MARKUP.sub("", text)).strip().casefold()


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
    ap.add_argument(
        "--allow-empty-text",
        action="store_true",
        help="Permit emitting rows whose text fields are empty (smoke-test "
        "mode only). Without this flag the generator hard-fails if any "
        "silver id does not resolve to corpus text — the committed "
        "frozen split of 2026-05 was corrupted exactly this way (id-only "
        "rows emitted because the corpus file was missing).",
    )
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

    def _has_text(sid: str) -> bool:
        row = corpus.get(sid, {})
        return bool(
            (row.get("raw_text") or "").strip()
            or (row.get("canonical_transliterated") or "").strip()
        )

    matched = sum(1 for sid in silver if _has_text(sid))
    print(
        f"Silver-corpus join: {matched}/{len(silver)} silver ids resolved to corpus text",
        file=sys.stderr,
    )
    if matched < len(silver) and not args.allow_empty_text:
        missing = sorted(sid for sid in silver if not _has_text(sid))
        print(
            f"ERROR: {len(missing)} silver ids have no corpus text "
            f"(first few: {missing[:5]}). A frozen split must carry the text "
            f"the jury reads — refusing to emit id-only rows. Fetch the "
            f"corpus (see research/v2/data/README.md) or pass "
            f"--allow-empty-text for a smoke test.",
            file=sys.stderr,
        )
        return 1

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

    # Expand the test pool to whole text groups. Sampling picked individual
    # ids; any silver-labelled sibling sharing the same normalized text would
    # otherwise land in train and hand the model the answer.
    groups: dict[str, list[str]] = defaultdict(list)
    for insc_id in silver:
        key = text_key(corpus.get(insc_id, {}).get("canonical_transliterated", ""))
        # Empty key = text was entirely markup; keep those rows ungrouped.
        groups[key or f"\0{insc_id}"].append(insc_id)

    pulled = 0
    for insc_id in sorted(test_ids):
        key = text_key(corpus.get(insc_id, {}).get("canonical_transliterated", ""))
        for sibling in groups[key or f"\0{insc_id}"]:
            if sibling not in test_ids:
                test_ids.add(sibling)
                pulled += 1
    if pulled:
        print(
            f"Text-group expansion: pulled {pulled} sibling row(s) into test to "
            f"keep the split text-disjoint (test now {len(test_ids)})",
            file=sys.stderr,
        )

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

    # Contamination guard. An `assert` is the wrong tool here — `python -O`
    # strips it, and this is the check the frozen v2 split silently failed.
    if test_ids & train_ids:
        print(
            f"CONTAMINATION: {len(test_ids & train_ids)} ids in both pools.",
            file=sys.stderr,
        )
        return 1
    train_keys = {
        text_key(corpus.get(i, {}).get("canonical_transliterated", "")) for i in train_ids
    }
    train_keys.discard("")
    shared = sorted(
        k
        for k in (text_key(corpus.get(i, {}).get("canonical_transliterated", "")) for i in test_ids)
        if k and k in train_keys
    )
    if shared:
        print(
            f"CONTAMINATION: {len(shared)} test row(s) share normalized text with "
            f"the train pool (first few: {shared[:5]}). An id-disjoint split is "
            f"not enough — see 'Text-level disjointness' in this module's docstring.",
            file=sys.stderr,
        )
        return 1

    # Report
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
