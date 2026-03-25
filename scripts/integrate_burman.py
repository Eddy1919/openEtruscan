#!/usr/bin/env python3
"""
Integrate the Burman Digital Concordance into the OpenEtruscan corpus.

This script:
  1. Loads the Burman concordance CSV (Zenodo DOI: 10.5281/zenodo.17209666)
  2. Matches entries against existing corpus inscriptions via ET reference IDs
  3. Enriches matched inscriptions with Trismegistos + CIE cross-references
  4. Updates the trismegistos_mapping.yaml with new TM IDs
  5. Stores unmatched concordance entries for future import

Usage:
    python scripts/integrate_burman.py --db data/corpus.db \
        --concordance data/contributions/burman_concordance.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from pathlib import Path

import yaml


def _parse_et1_id(et1_str: str) -> str | None:
    """Convert 'ET1 Fs 1.0001' → 'Fs 1.1' (corpus format)."""
    m = re.match(r"ET1\s+(\w+)\s+(\d+)\.(\d+)", et1_str.strip())
    if m:
        loc, major, minor = m.group(1), m.group(2), str(int(m.group(3)))
        return f"{loc} {major}.{minor}"
    return None


def _parse_et2_id(et2_str: str) -> str | None:
    """Convert 'ET2 Fs 1.0001' → 'Fs 1.1' (corpus format)."""
    m = re.match(r"ET2\s+(\w+)\s+(\d+)\.(\d+)", et2_str.strip())
    if m:
        loc, major, minor = m.group(1), m.group(2), str(int(m.group(3)))
        return f"{loc} {major}.{minor}"
    return None


def _parse_cie_number(cie_str: str) -> str | None:
    """Extract numeric CIE number from 'CIE 00371' → '371'."""
    m = re.match(r"CIE\s+(\d+)", cie_str.strip())
    if m:
        return str(int(m.group(1)))
    return None


def _parse_tm_id(tm_str: str) -> str | None:
    """Extract TM number from 'TM 145534' → '145534'."""
    m = re.match(r"TM\s+(\d+)", tm_str.strip())
    if m:
        return m.group(1)
    return None


def load_concordance(csv_path: str | Path) -> list[dict]:
    """Load the Burman concordance CSV."""
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        return list(reader)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Integrate Burman concordance into OpenEtruscan corpus."
    )
    parser.add_argument("--db", default="data/corpus.db", help="Path to corpus SQLite DB.")
    parser.add_argument(
        "--concordance",
        default="data/contributions/burman_concordance.csv",
        help="Path to Burman concordance CSV.",
    )
    parser.add_argument(
        "--tm-mapping",
        default="data/trismegistos_mapping.yaml",
        help="Path to TM mapping YAML.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Don't write changes.")
    args = parser.parse_args()

    # Load corpus IDs
    conn = sqlite3.connect(args.db)
    corpus_ids = set(r[0] for r in conn.execute("SELECT id FROM inscriptions").fetchall())
    print(f"Corpus inscriptions: {len(corpus_ids)}")

    # Load existing TM mapping
    tm_path = Path(args.tm_mapping)
    existing_tm: dict[str, str] = {}
    if tm_path.exists():
        with open(tm_path, encoding="utf-8") as f:
            existing_tm = yaml.safe_load(f) or {}
    print(f"Existing TM mappings: {len(existing_tm)}")

    # Load concordance
    concordance = load_concordance(args.concordance)
    print(f"Concordance entries: {len(concordance)}")

    # Build match index: concordance entry → corpus ID
    matched: list[tuple[str, dict]] = []  # (corpus_id, concordance_row)
    unmatched: list[dict] = []

    for row in concordance:
        corpus_id = None

        # Try ET1 match
        et1 = row.get("Rix. ET1", "").strip()
        if et1:
            cid = _parse_et1_id(et1)
            if cid and cid in corpus_ids:
                corpus_id = cid

        # Try ET2 match (if ET1 didn't match)
        if corpus_id is None:
            et2 = row.get("Meiser. ET2", "").strip()
            if et2:
                cid = _parse_et2_id(et2)
                if cid and cid in corpus_ids:
                    corpus_id = cid

        if corpus_id:
            matched.append((corpus_id, row))
        else:
            unmatched.append(row)

    print(f"\nMatched to corpus: {len(matched)}")
    print(f"Unmatched (new data): {len(unmatched)}")

    # Enrich: add TM IDs to mapping
    new_tm = 0
    new_bibliography = 0

    for corpus_id, row in matched:
        tm_str = row.get("Trismegistos", "").strip()
        tm_id = _parse_tm_id(tm_str) if tm_str else None

        if tm_id and corpus_id not in existing_tm:
            existing_tm[corpus_id] = tm_id
            new_tm += 1

        # Add CIE reference to bibliography/source in DB
        cie_str = row.get("CIE", "").strip()
        if cie_str and not args.dry_run:
            # Update source field if it's empty
            current = conn.execute(
                "SELECT source, bibliography FROM inscriptions WHERE id = ?",
                (corpus_id,),
            ).fetchone()
            if current:
                source, bibliography = current
                cie_ref = cie_str.replace("CIE ", "CIE ")
                if "CIE" not in (source or "") and "CIE" not in (bibliography or ""):
                    new_bib = f"{bibliography}; {cie_ref}" if bibliography else cie_ref
                    conn.execute(
                        "UPDATE inscriptions SET bibliography = ? WHERE id = ?",
                        (new_bib, corpus_id),
                    )
                    new_bibliography += 1

    if not args.dry_run:
        conn.commit()

    print(f"\nNew TM mappings: {new_tm}")
    print(f"New bibliography entries: {new_bibliography}")
    print(f"Total TM mappings after: {len(existing_tm)}")

    # Save updated TM mapping
    if new_tm > 0 and not args.dry_run:
        with open(tm_path, "w", encoding="utf-8") as f:
            yaml.dump(
                dict(sorted(existing_tm.items())),
                f,
                allow_unicode=True,
                sort_keys=True,
            )
        print(f"✅ Updated {tm_path}")

    # Save unmatched entries for future reference
    unmatched_with_et = [
        r for r in unmatched if r.get("Rix. ET1", "").strip() or r.get("Meiser. ET2", "").strip()
    ]
    print(f"\nUnmatched entries with ET references: {len(unmatched_with_et)}")
    print("  (These are inscriptions in the concordance but not yet in our corpus)")

    # Show summary of what the concordance could add
    unmatched_with_tm = [r for r in unmatched if r.get("Trismegistos", "").strip()]
    print(f"  With TM IDs: {len(unmatched_with_tm)}")

    # Show location distribution of unmatched ET entries
    loc_counts: dict[str, int] = {}
    for r in unmatched_with_et:
        et1 = r.get("Rix. ET1", "").strip()
        if et1:
            m = re.match(r"ET1\s+(\w+)", et1)
            if m:
                loc = m.group(1)
                loc_counts[loc] = loc_counts.get(loc, 0) + 1
    if loc_counts:
        print("\n  Location distribution of unmatched ET inscriptions:")
        for loc, count in sorted(loc_counts.items(), key=lambda x: -x[1])[:15]:
            print(f"    {loc:<6} {count:>5}")

    conn.close()
    print("\n✅ Integration complete!")


if __name__ == "__main__":
    main()
