#!/usr/bin/env python3
"""
Ingest Archaeogenetic Sample Metadata (AADR / Posth 2021) into the OpenEtruscan Corpus.

It supports parsing standard tab-separated (.tsv) or comma-separated (.csv) files.
It looks for fields representing latitude, longitude, date, and haplogroups, and injects
them into the `genetic_samples` schema using PostGIS/SQLite mapping.
"""

import argparse
import csv
import logging
import sys
from pathlib import Path

from openetruscan.corpus import Corpus, GeneticSample

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ingest_genetics")


def parse_date(date_str: str) -> tuple[int | None, int | None]:
    """Parse dates like '400 BCE', '-400', '400', '800-400 BCE' into approx and uncertainty."""
    if not date_str or date_str.lower() in ["..", "nodate", "nan"]:
        return None, None

    date_str = date_str.strip().upper()
    try:
        # AADR format uses mean in years BCE/CE or BP
        if "BCE" in date_str:
            val = date_str.replace("BCE", "").strip()
            if "-" in val:
                parts = val.split("-")
                mean = -(int(parts[0]) + int(parts[1])) // 2
                unc = abs(int(parts[0]) - int(parts[1])) // 2
                return mean, unc
            return -int(val), 0
        if "CE" in date_str:
            val = date_str.replace("CE", "").strip()
            return int(val), 0

        # Raw integer
        return int(float(date_str)), 0
    except (ValueError, TypeError):
        return None, None


def sniff_columns(headers: list[str]) -> dict[str, str]:
    """Dynamically map known AADR or generic column names to our schema."""
    mapping = {}
    for h in headers:
        hl = h.lower()
        if ("id" in hl or "index" in hl or "sample" in hl) and "id" not in mapping:
            mapping["id"] = h
        if "lat" in hl:
            mapping["lat"] = h
        if "lon" in hl or "long" in hl:
            mapping["lon"] = h
        if "date" in hl and "mean" in hl or "date" in hl and "date" not in mapping:
            mapping["date"] = h
        if "y haplogroup" in hl or "y-haplo" in hl or "y_haplo" in hl:
            mapping["y_haplo"] = h
        if "mt haplogroup" in hl or "mt-haplo" in hl or "mt_haplo" in hl:
            mapping["mt_haplo"] = h
        if "locality" in hl or "site" in hl or "findspot" in hl:
            mapping["findspot"] = h
        if "publication" in hl or "source" in hl:
            mapping["source"] = h

    return mapping


def ingest_genetics(file_path: Path, delimiter: str = "\t"):
    """Parse the TSV/CSV and ingest into the corpus."""
    corpus = Corpus.load()
    logger.info(f"Connected to database natively: {type(corpus).__name__}")

    count = 0
    with file_path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        headers = reader.fieldnames or []
        mapping = sniff_columns(headers)

        if "id" not in mapping:
            logger.error("Could not identify an ID column in the dataset. Exiting.")
            sys.exit(1)

        logger.info(f"Using column mapping: {mapping}")

        for row in reader:
            sample_id = row.get(mapping.get("id", ""), "").strip()
            if not sample_id:
                continue

            lat_str = row.get(mapping.get("lat", ""), "").strip()
            lon_str = row.get(mapping.get("lon", ""), "").strip()

            try:
                lat = float(lat_str) if lat_str and lat_str != ".." else None
                lon = float(lon_str) if lon_str and lon_str != ".." else None
            except ValueError:
                lat, lon = None, None

            # Filter solely to Italy coordinates roughly if not filtering by publication
            if lat and lon and not (35.0 <= lat <= 48.0 and 5.0 <= lon <= 19.0):
                continue  # Skip non-Italian/Etruscan macro-region samples

            date_str = row.get(mapping.get("date", ""), "").strip()
            date_approx, date_uncert = parse_date(date_str)

            source = row.get(mapping.get("source", ""), "").strip()

            sample = GeneticSample(
                id=sample_id,
                findspot=row.get(mapping.get("findspot", ""), "").strip(),
                findspot_lat=lat,
                findspot_lon=lon,
                date_approx=date_approx,
                date_uncertainty=date_uncert,
                y_haplogroup=row.get(mapping.get("y_haplo", ""), "").strip(),
                mt_haplogroup=row.get(mapping.get("mt_haplo", ""), "").strip(),
                source=source,
                notes=f"Auto-ingested via scripts/ingest_genetics.py from {file_path.name}",
            )

            corpus.add_genetic_sample(sample)
            count += 1

            if count % 100 == 0:
                logger.info(f"Ingested {count} genetic samples so far...")

    logger.info(f"Successfully ingested {count} genetic samples.")
    corpus.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Archaeogenetic Data")
    parser.add_argument(
        "file",
        type=Path,
        help="Path to the TSV or CSV genetics dataset (AADR format supported)",
    )
    parser.add_argument("--csv", action="store_true", help="Parse as CSV instead of TSV")
    args = parser.parse_args()

    delim = "," if args.csv else "\t"
    ingest_genetics(args.file, delimiter=delim)
