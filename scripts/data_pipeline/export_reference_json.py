#!/usr/bin/env python3
"""Write the frontend's copies of the reference tables.

The site reads place labels, ET text classes and ET region codes from
``lib/reference/{places,rixClasses,etRegions}.json`` in the frontend repo.
They are generated from ``reference/*.csv`` here; edit the CSVs and re-run.

Usage:
    python scripts/data_pipeline/export_reference_json.py \\
        --out ../openEtruscan-frontend/lib/reference
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "reference"
COMMENT = (
    "Generated from openetruscan/reference/*.csv by the edition-layer backfill tooling; "
    "edit the CSVs, not this file."
)


def _rows(name: str) -> list[dict[str, str]]:
    with open(REFERENCE / name, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def places() -> dict[str, Any]:
    return {
        r["key"]: {
            "pleiadesId": r["pleiades_id"],
            "en": r["label_en"],
            "it": r["label_it"],
            "kind": r["kind"],
            "lat": float(r["lat"]),
            "lon": float(r["lon"]),
        }
        for r in _rows("places.csv")
    }


def rix_classes() -> dict[str, Any]:
    return {
        r["class"]: {
            "en": r["label_en"],
            "it": r["label_it"],
            "siteLabel": r["site_label"] or None,
            "source": r["source"],
            "confidence": r["confidence"],
        }
        for r in _rows("rix_text_classes.csv")
    }


def et_regions() -> dict[str, Any]:
    return {
        r["code"]: {
            "label": r["label"],
            "placeKey": r["place_key"] or None,
            "precision": r["precision"] or None,
            "confidence": r["confidence"],
        }
        for r in _rows("et_regions.csv")
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True, help="frontend lib/reference directory")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for name, data in (
        ("places.json", places()),
        ("rixClasses.json", rix_classes()),
        ("etRegions.json", et_regions()),
    ):
        path = args.out / name
        path.write_text(
            json.dumps({"_comment": COMMENT, "data": data}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {path} ({len(data)} entries)")


if __name__ == "__main__":
    main()
