#!/usr/bin/env python3
"""Add `dup_group_id` / `dup_group_size` columns to a corpus CSV.

Why these columns exist
-----------------------
The published corpus holds 6,567 rows over 6,097 distinct
`canonical_transliterated` values. The repeats are usually *correct* — `mi`
("I am") really is carved on eight different artifacts — so the deposit must
not be deduplicated (that would destroy the artifact record). But repeated
texts mean row-level random train/test splits leak: the same string, with the
same label, lands on both sides under different ids. That leak contaminated
the frozen v2 classification split (PRE_REGISTRATION.md Deviation §D).

`dup_group_id` makes the leak preventable by any downstream consumer, not
just this repository's own pipeline: split on groups, not rows. Grouping is
by the same normalization the split generator uses (`text_key`: Leiden
markup stripped, whitespace collapsed, casefolded), so `la(u)tni`,
`lautn(i)` and `laut(n)i` share a group. The id is the first 12 hex chars of
the SHA-256 of the normalized text — stable across row order, corpus
version, and file encoding. Rows whose text is entirely editorial markup
(`[---]`, `[?]`) normalize to the empty string and get a per-row group of
size 1 rather than being fused into one blob.

Usage
-----
    python scripts/data_pipeline/add_dup_group_id.py \\
        --input research/data/openetruscan_clean.csv \\
        --output research/data/openetruscan_clean_grouped.csv

The output is byte-identical to the input except for the two appended
columns, so checksums of the underlying 10 columns are preserved by
projection. Intended for the next Zenodo deposit revision.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from research.v2.pipelines.classify_split import text_key  # noqa: E402


def group_id(normalized: str, row_id: str) -> str:
    """Stable group identifier: hash of the normalized text.

    Empty normalization (pure-markup rows) falls back to the row id so those
    rows stay singletons instead of forming one giant false group.
    """
    basis = normalized if normalized else f"\0row:{row_id}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument(
        "--text-column",
        default="canonical_transliterated",
        help="Column holding the text to group on.",
    )
    args = ap.parse_args(argv)

    with args.input.open(newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or args.text_column not in reader.fieldnames:
            print(
                f"ERROR: column {args.text_column!r} not in {args.input}",
                file=sys.stderr,
            )
            return 1
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    keys = [
        group_id(text_key(r[args.text_column]), r.get("id", str(i))) for i, r in enumerate(rows)
    ]
    sizes = Counter(keys)

    out_fields = fieldnames + ["dup_group_id", "dup_group_size"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        for row, key in zip(rows, keys, strict=True):
            row["dup_group_id"] = key
            row["dup_group_size"] = str(sizes[key])
            writer.writerow(row)

    n_groups = len(sizes)
    n_multi = sum(1 for v in sizes.values() if v > 1)
    n_rows_in_multi = sum(v for v in sizes.values() if v > 1)
    print(f"rows: {len(rows)}  groups: {n_groups}", file=sys.stderr)
    print(
        f"multi-row groups: {n_multi}  rows in them: {n_rows_in_multi}  "
        f"excess rows (leak surface): {n_rows_in_multi - n_multi}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
