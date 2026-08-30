#!/usr/bin/env python3
"""Produce the v1.2 dataset export: v1.1 rows + the metadata columns the
published CSV has never carried.

Why: the offline search eval showed 28 of 74 frozen queries (place_pleiades,
place_findspot, chronology) are unanswerable from the published text-only
columns, and the graph/hyperbolic embedding blocks cannot be tested on real
geography. All of these columns already exist on the prod `inscriptions`
table; they were simply dropped at export (research/data/README.md,
"Columns this export does not carry").

Run against prod (read-only):

    DATABASE_URL=postgres://... python scripts/data_pipeline/export_v12_metadata.py \
        --grouped research/data/openetruscan_clean_grouped.csv \
        --bilinguals research/data/bilingual_annotations.csv \
        --output research/data/openetruscan_clean_v12.csv

Join contract: LEFT JOIN on `id` against the frozen v1.1 grouped CSV — row
count and row order of v1.1 are preserved byte-for-byte on the existing
columns, so v1.2 is a strict column superset and every published split or
dup_group stays valid.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

METADATA_COLS = [
    "findspot", "findspot_lat", "findspot_lon", "findspot_uncertainty_m",
    "object_type", "medium", "language", "script_system", "classification",
    "completeness", "pleiades_id", "trismegistos_id", "source_code",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grouped", type=Path, required=True,
                    help="frozen v1.1 openetruscan_clean_grouped.csv")
    ap.add_argument("--bilinguals", type=Path, default=None,
                    help="bilingual_annotations.csv to join (optional)")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        sys.exit("DATABASE_URL is required (read-only prod access)")

    import sqlalchemy as sa

    engine = sa.create_engine(db_url)
    cols = ", ".join(METADATA_COLS)
    with engine.connect() as conn:
        meta = pd.read_sql(sa.text(f"SELECT id, {cols} FROM inscriptions"), conn)

    base = pd.read_csv(args.grouped, dtype=str)
    n_base = len(base)
    out = base.merge(meta, on="id", how="left")
    assert len(out) == n_base, "join changed the row count — duplicate ids in prod?"

    if args.bilinguals is not None and args.bilinguals.exists():
        bil = pd.read_csv(args.bilinguals, dtype=str)
        bil = bil[bil["review_status"] == "id_confirmed"][
            ["corpus_id", "bilingual_ids", "latin_text", "bilingual_fixes"]
        ].rename(columns={"corpus_id": "id"})
        out = out.merge(bil, on="id", how="left")
        assert len(out) == n_base

    out.to_csv(args.output, index=False)
    covered = out["findspot"].fillna("").str.len().gt(0).sum()
    print(f"rows {len(out)} | findspot coverage {covered} "
          f"({100 * covered / len(out):.1f}%) | wrote {args.output}")
    print("next: sha256, update scripts/ops/fetch_data.py manifest, "
          "Zenodo new-version deposit (see research/data/DEPOSIT_v1.2.md)")


if __name__ == "__main__":
    main()
