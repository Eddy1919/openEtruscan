#!/usr/bin/env python3
"""
Migrate OpenEtruscan corpus from SQLite to PostgreSQL (Cloud SQL).

Usage:
    python scripts/migrate_to_postgres.py \\
        --source data/corpus.db \\
        --target "postgresql://postgres:PASSWORD@IP/corpus"

Features:
    - Migrates all inscriptions with auto-classification
    - Creates read-only 'corpus_reader' user for public access
    - Shows classification distribution after migration
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openetruscan.corpus import (  # noqa: E402
    _COLUMNS,
    PostgresCorpus,
)

# ---------------------------------------------------------------------------
# Classification heuristics for Etruscan inscriptions
# ---------------------------------------------------------------------------

# Common Etruscan funerary terms (name suffixes, family markers)
FUNERARY_PATTERNS = re.compile(
    r"(clan|sec|puia|ati|zilath|avil|sval|lupu|suth|hinth|"
    r"clen|neft|lautni|etera)",
    re.IGNORECASE,
)

# Votive / dedicatory terms
VOTIVE_PATTERNS = re.compile(
    r"(turce|mlac|alpan|tinia|uni|menrva|turan|"
    r"fufluns|nethuns|sethlans|thesan)",
    re.IGNORECASE,
)

# Boundary markers
BOUNDARY_PATTERNS = re.compile(
    r"(tular|tularu|rasna|spura|mechi)",
    re.IGNORECASE,
)

# Ownership marks
OWNERSHIP_PATTERNS = re.compile(
    r"(mi\s|mini\s|mina\s)",
    re.IGNORECASE,
)

# Commercial / numerical
COMMERCIAL_PATTERNS = re.compile(
    r"(zathrum|ci|huth|mach|semph|thu|cezp)",
    re.IGNORECASE,
)


def classify_inscription(text: str) -> str:
    """
    Auto-classify an Etruscan inscription by keyword heuristics.

    Priority order: boundary > votive > ownership > commercial > funerary.
    Most unclassified texts default to funerary (majority of corpus).
    """
    if not text:
        return "unknown"

    canonical = text.lower().strip()

    if BOUNDARY_PATTERNS.search(canonical):
        return "boundary"
    if VOTIVE_PATTERNS.search(canonical):
        return "votive"
    if OWNERSHIP_PATTERNS.search(canonical):
        return "ownership"
    if COMMERCIAL_PATTERNS.search(canonical):
        return "commercial"
    if FUNERARY_PATTERNS.search(canonical):
        return "funerary"

    # Default: most Etruscan inscriptions are funerary
    # Only mark as unknown if very short or illegible
    if len(canonical) < 3:
        return "unknown"
    return "funerary"


def detect_completeness(text: str) -> str:
    """Detect if an inscription is fragmentary."""
    if not text:
        return "illegible"
    if "[" in text or "]" in text or "..." in text or "---" in text:
        return "fragmentary"
    return "complete"


def migrate(source_path: str, target_url: str) -> None:
    """Migrate SQLite corpus to PostgreSQL."""
    # Connect to source SQLite
    src = sqlite3.connect(source_path)
    src.row_factory = sqlite3.Row

    # Check source has data
    count = src.execute("SELECT COUNT(*) FROM inscriptions").fetchone()[0]
    if count == 0:
        print("Source database is empty. Nothing to migrate.")
        return

    print(f"Source: {source_path} ({count} inscriptions)")
    print(f"Target: {target_url.split('@')[1] if '@' in target_url else target_url}")

    # Connect to PostgreSQL
    pg = PostgresCorpus.from_url(target_url)
    print("Connected to PostgreSQL. Schema created.")

    # Read all source columns
    src_cursor = src.execute("PRAGMA table_info(inscriptions)")
    src_columns = [row[1] for row in src_cursor.fetchall()]

    # Migrate inscriptions
    rows = src.execute("SELECT * FROM inscriptions").fetchall()
    migrated = 0
    classifications: dict[str, int] = {}

    for row in rows:
        canonical = row["canonical"]
        raw_text = row["raw_text"]

        # Auto-classify
        classification = classify_inscription(canonical or raw_text)
        completeness = detect_completeness(canonical or raw_text)

        # Build values tuple matching _COLUMNS order
        values = (
            row["id"],
            row["raw_text"],
            row["canonical"],
            row["phonetic"],
            row["old_italic"],
            row["findspot"],
            row["findspot_lat"],
            row["findspot_lon"],
            row["date_approx"],
            row["date_uncertainty"],
            row["medium"],
            row["object_type"],
            row["source"],
            row["bibliography"],
            row["notes"],
            (
                row["language"]
                if "language" in src_columns
                else "etruscan"
            ),
            classification,
            (
                row["script_system"]
                if "script_system" in src_columns
                else "old_italic"
            ),
            completeness,
        )

        # Insert into PostgreSQL
        cols = ", ".join(_COLUMNS)
        placeholders = ", ".join(["%s"] * len(_COLUMNS))
        conflict_updates = ", ".join(
            f"{c} = EXCLUDED.{c}" for c in _COLUMNS if c != "id"
        )
        sql = (
            f"INSERT INTO inscriptions ({cols}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT (id) DO UPDATE SET {conflict_updates}"
        )

        with pg._conn.cursor() as cur:
            cur.execute(sql, values)

        classifications[classification] = (
            classifications.get(classification, 0) + 1
        )
        migrated += 1

        if migrated % 500 == 0:
            pg._conn.commit()
            print(f"  Migrated {migrated}/{count}...")

    pg._conn.commit()
    print(f"\nMigrated {migrated} inscriptions.")

    # Show classification distribution
    print("\nClassification distribution:")
    for cls_name, cls_count in sorted(
        classifications.items(), key=lambda x: -x[1],
    ):
        pct = cls_count / migrated * 100
        bar = "#" * int(pct / 2)
        print(f"  {cls_name:15s} {cls_count:5d} ({pct:5.1f}%) {bar}")

    # Create read-only user
    print("\nCreating read-only user 'corpus_reader'...")
    # Note: Use a strong password in production or read from env
    pg.create_readonly_user("openetruscan_readonly_user_pass")
    print("Done. Public read-only access configured.")

    # Final count check
    pg_count = pg.count()
    print(f"\nPostgreSQL count: {pg_count}")
    assert pg_count == count, (
        f"Count mismatch: SQLite={count}, PostgreSQL={pg_count}"
    )
    print("Migration verified.")

    src.close()
    pg.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate OpenEtruscan corpus to PostgreSQL",
    )
    parser.add_argument(
        "--source",
        default="src/openetruscan/data/corpus.db",
        help="Path to source SQLite database",
    )
    parser.add_argument(
        "--target",
        required=True,
        help="PostgreSQL connection URL",
    )
    args = parser.parse_args()

    if not Path(args.source).exists():
        print(f"Error: Source database not found: {args.source}")
        sys.exit(1)

    migrate(args.source, args.target)


if __name__ == "__main__":
    main()
