#!/usr/bin/env python3
"""
Merge Larth (Vico & Spanakis 2023) metadata into the normalized CSV.

Joins three columns from Larth onto the openetruscan_normalized CSV
by inscription ID:
  - translation  (English gloss)
  - year_from    (date range start, BCE/CE — Larth uses negative for BCE)
  - year_to      (date range end)

Larth has duplicate IDs (7,139 rows / 4,712 unique IDs) — we take the
first non-empty value per field. Rows with no Larth match get empty
strings (the openetruscan corpus has 1,855 CIE-only rows that Larth
never had).

Output column order is content-first, metadata-second, filtering-knobs-last:
  id, raw_text, canonical_transliterated, canonical_italic,
  canonical_words_only, translation, year_from, year_to,
  intact_token_ratio, data_quality

If the Larth CSV is not present, this script will download it from
the upstream GitHub repo.
"""
from __future__ import annotations

import argparse
import csv
import sys
import urllib.request
from pathlib import Path

LARTH_URL = (
    "https://raw.githubusercontent.com/GianlucaVico/Larth-Etruscan-NLP/"
    "main/Data/Etruscan.csv"
)

OUTPUT_COLS = [
    "id", "raw_text", "canonical_transliterated", "canonical_italic",
    "canonical_words_only", "translation", "year_from", "year_to",
    "intact_token_ratio", "data_quality",
]


def ensure_larth(path: Path) -> None:
    if path.exists():
        return
    print(f"Downloading Larth from {LARTH_URL}", file=sys.stderr)
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(LARTH_URL) as r:
        path.write_bytes(r.read())


def build_larth_index(path: Path) -> dict[str, dict[str, str]]:
    """ID → {translation, year_from, year_to}, taking first non-empty."""
    index: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = (row.get("ID") or "").strip()
            if not sid:
                continue
            entry = index.setdefault(sid, {})
            for src, dst in [
                ("Translation", "translation"),
                ("Year - From", "year_from"),
                ("Year - To", "year_to"),
            ]:
                v = (row.get(src) or "").strip()
                if v and not entry.get(dst):
                    entry[dst] = v
    return index


def merge(larth_path: Path, norm_path: Path, out_path: Path) -> dict[str, int]:
    larth = build_larth_index(larth_path)
    counts = {"id_in_larth": 0, "got_translation": 0, "got_year": 0,
              "cie_only": 0, "total": 0}
    with norm_path.open() as fin, out_path.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=OUTPUT_COLS,
                                quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for row in reader:
            counts["total"] += 1
            sid = row["id"].strip()
            entry = larth.get(sid, {})
            row["translation"] = entry.get("translation", "")
            row["year_from"] = entry.get("year_from", "")
            row["year_to"] = entry.get("year_to", "")
            if sid in larth:
                counts["id_in_larth"] += 1
                if row["translation"]:
                    counts["got_translation"] += 1
                if row["year_from"] or row["year_to"]:
                    counts["got_year"] += 1
            else:
                counts["cie_only"] += 1
            writer.writerow({k: row.get(k, "") for k in OUTPUT_COLS})
    return counts


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--larth", type=Path,
                   default=Path("/tmp/larth_etruscan.csv"))
    p.add_argument("--normalized", type=Path,
                   default=Path("/home/edoardo/Documents/openEtruscan/"
                                "openetruscan_normalized.csv"))
    p.add_argument("--output", type=Path,
                   default=Path("/home/edoardo/Documents/openEtruscan/"
                                "openetruscan_clean.csv"))
    args = p.parse_args()

    ensure_larth(args.larth)
    if not args.normalized.exists():
        print(f"normalized csv not found: {args.normalized}", file=sys.stderr)
        return 2

    c = merge(args.larth, args.normalized, args.output)
    t = c["total"]
    print(f"wrote {t:,} rows to {args.output}", file=sys.stderr)
    print(f"  ID found in Larth        : {c['id_in_larth']:,}  ({100*c['id_in_larth']/t:.1f}%)",
          file=sys.stderr)
    print(f"  CIE-only (no Larth row)  : {c['cie_only']:,}  ({100*c['cie_only']/t:.1f}%)",
          file=sys.stderr)
    print(f"  got translation column   : {c['got_translation']:,}  ({100*c['got_translation']/t:.1f}%)",
          file=sys.stderr)
    print(f"  got year_from / year_to  : {c['got_year']:,}  ({100*c['got_year']/t:.1f}%)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
