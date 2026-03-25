#!/usr/bin/env python3
"""
Seed the OpenEtruscan corpus from the Larth dataset.

Downloads and imports 7,139 Etruscan inscriptions from:
    Vico & Spanakis (2023). "Larth: Dataset and Machine Translation for Etruscan."
    Ancient Language Processing Workshop (ALP2023).
    https://github.com/GianlucaVico/Larth-Etruscan-NLP

Usage:
    python scripts/seed_larth.py
    python scripts/seed_larth.py --db-path data/corpus.db
    python scripts/seed_larth.py --csv-path /path/to/local/Etruscan.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import urllib.request
from pathlib import Path

import yaml

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openetruscan.corpus import Corpus, Inscription
from openetruscan.normalizer import normalize

LARTH_URL = (
    "https://raw.githubusercontent.com/GianlucaVico/Larth-Etruscan-NLP/main/Data/Etruscan.csv"
)

# Known Etruscan cities → approximate coordinates (WGS84)
CITY_COORDS: dict[str, tuple[float, float]] = {
    "Caere": (42.0009, 12.1067),
    "Tarquinii": (42.2488, 11.7553),
    "Ager Tarquiniensis": (42.25, 11.75),
    "Vulci": (42.4212, 11.6323),
    "Volsinii": (42.7182, 11.8750),
    "Clusium": (43.0174, 11.9492),
    "Perusia": (43.1107, 12.3908),
    "Cortona": (43.2754, 11.9858),
    "Arretium": (43.4613, 11.8802),
    "Volaterrae": (43.4015, 10.8619),
    "Vetulonia": (42.8524, 10.9746),
    "Populonia": (42.9883, 10.4936),
    "Rusellae": (42.8240, 11.1595),
    "Faesulae": (43.8059, 11.2944),
    "Veii": (42.0273, 12.3979),
    "Campania": (40.85, 14.25),
    "Orvieto": (42.7182, 12.1122),
    "Chiusi": (43.0174, 11.9492),
    "Cerveteri": (42.0009, 12.1067),
    "Tarquinia": (42.2488, 11.7553),
    "Perugia": (43.1107, 12.3908),
    "Volterra": (43.4015, 10.8619),
    "Bolsena": (42.6455, 11.9864),
    "Arezzo": (43.4613, 11.8802),
    "Sovana": (42.6594, 11.6478),
    "Tuscania": (42.4181, 11.8709),
    "Norchia": (42.3406, 11.9403),
    "Musarna": (42.4431, 11.8686),
    "Blera": (42.2744, 12.0285),
    "San Giovenale": (42.2333, 11.9167),
    "Pyrgi": (42.0098, 11.9676),
    "Piacenza": (45.0522, 9.6930),
}


def clean_etruscan_text(raw: str) -> tuple[str, bool]:
    """Clean raw Etruscan text from the Larth dataset.

    Returns (cleaned_text, has_interpuncts).
    The boolean indicates whether the source used ':' interpuncts
    (epigraphic word dividers carved on the original stone).
    """
    text = raw.strip()
    # Detect epigraphic interpuncts before removing them
    has_interpuncts = ":" in text
    # Remove word boundary markers
    text = text.replace(" : ", " ")
    text = text.replace(":", " ")
    # Remove editorial markers
    text = text.replace(" | ", " ")
    text = text.replace("|", " ")
    # Collapse whitespace
    text = " ".join(text.split())
    return text.strip(), has_interpuncts


def parse_date(year_from: str, year_to: str) -> tuple[int | None, int | None]:
    """Parse date range from Larth format to (approx, uncertainty)."""
    try:
        y_from = int(float(year_from)) if year_from else None
        y_to = int(float(year_to)) if year_to else None
    except (ValueError, TypeError):
        return None, None

    if y_from is not None and y_to is not None:
        # Larth uses positive numbers for BCE dates (e.g., 400 = 400 BCE)
        # Convert to our convention: negative = BCE
        approx = -((y_from + y_to) // 2)
        uncertainty = abs(y_from - y_to) // 2
        return approx, uncertainty if uncertainty > 0 else None
    elif y_from is not None:
        return -y_from, None
    return None, None


def get_coords(city: str) -> tuple[float | None, float | None]:
    """Look up approximate coordinates for a city."""
    if not city:
        return None, None
    city_clean = city.strip()
    if city_clean in CITY_COORDS:
        return CITY_COORDS[city_clean]
    # Try partial match
    for known_city, coords in CITY_COORDS.items():
        if known_city.lower() in city_clean.lower() or city_clean.lower() in known_city.lower():
            return coords
    return None, None


def download_larth(url: str = LARTH_URL) -> str:
    """Download the Larth CSV from GitHub."""
    print("📥 Downloading Larth dataset from GitHub...")
    req = urllib.request.Request(url, headers={"User-Agent": "OpenEtruscan/0.1"})
    with urllib.request.urlopen(req) as response:
        data = response.read().decode("utf-8")
    print(f"   Downloaded {len(data):,} bytes")
    return data


def seed_corpus(csv_data: str, db_path: str = "data/corpus.db") -> int:
    """Import Larth CSV into the OpenEtruscan corpus."""
    corpus = Corpus.load(db_path)

    reader = csv.DictReader(io.StringIO(csv_data))
    count = 0
    skipped = 0

    for row in reader:
        raw_text = row.get("Etruscan", "").strip()
        if not raw_text:
            skipped += 1
            continue

        clean_text, has_interpuncts = clean_etruscan_text(raw_text)
        if not clean_text:
            skipped += 1
            continue

        inscription_id = row.get("ID", f"LARTH_{count:05d}").strip()
        city = row.get("City", "").strip()
        translation = row.get("Translation", "").strip()
        year_from = row.get("Year - From", "")
        year_to = row.get("Year - To", "")

        date_approx, date_uncertainty = parse_date(year_from, year_to)
        lat, lon = get_coords(city)

        # Normalize the text
        try:
            result = normalize(clean_text)
        except Exception as e:
            print(f"   ⚠️  Failed to normalize '{clean_text}': {e}")
            skipped += 1
            continue

        # Build notes: translation + interpunct metadata
        notes_parts = []
        if translation:
            notes_parts.append(translation)
        if has_interpuncts:
            notes_parts.append("[interpuncts in source]")
        notes = "; ".join(notes_parts)

        inscription = Inscription(
            id=inscription_id,
            raw_text=raw_text,
            canonical=result.canonical,
            phonetic=result.phonetic,
            old_italic=result.old_italic,
            findspot=city,
            findspot_lat=lat,
            findspot_lon=lon,
            date_approx=date_approx,
            date_uncertainty=date_uncertainty,
            medium="",
            object_type="",
            source="Larth (Vico & Spanakis, 2023)",
            bibliography=(
                "Vico, G., & Spanakis, G. (2023). "
                "Larth: Dataset and Machine Translation "
                "for Etruscan. ALP2023."
            ),
            notes=notes,
        )
        corpus.add(inscription)
        count += 1

        if count % 1000 == 0:
            print(f"   📝 Imported {count:,} inscriptions...")

    corpus.close()
    print(f"\n✅ Seeded {count:,} inscriptions (skipped {skipped})")
    print(f"   Database: {db_path}")
    return count


def seed_codex(db_path: str = "data/corpus.db") -> int:
    """
    Import the 6 major Etruscan codex texts from codex_texts.yaml.

    Each text's sections are imported as individual inscriptions with
    full scholarly metadata and provenance_status='verified'.
    """
    codex_path = Path(__file__).parent.parent / "data" / "codex_texts.yaml"
    if not codex_path.exists():
        print("⚠️  codex_texts.yaml not found")
        return 0

    with open(codex_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "texts" not in data:
        print("⚠️  No texts found in codex_texts.yaml")
        return 0

    corpus = Corpus.load(db_path)
    count = 0

    for text_entry in data["texts"]:
        title = text_entry.get("title", "")
        sections = text_entry.get("sections", [])

        if not sections:
            continue

        for section in sections:
            section_id = section["id"]
            raw_text = section.get("raw_text", "").strip()
            if not raw_text:
                continue

            # Normalize
            try:
                result = normalize(raw_text)
            except Exception as e:
                print(f"   ⚠️  Failed to normalize '{section_id}': {e}")
                continue

            lat = text_entry.get("findspot_lat")
            lon = text_entry.get("findspot_lon")

            inscription = Inscription(
                id=section_id,
                raw_text=raw_text,
                canonical=result.canonical,
                phonetic=result.phonetic,
                old_italic=result.old_italic,
                findspot=text_entry.get("findspot", ""),
                findspot_lat=lat,
                findspot_lon=lon,
                date_approx=text_entry.get("date_approx"),
                date_uncertainty=text_entry.get("date_uncertainty"),
                medium=text_entry.get("medium", ""),
                object_type=text_entry.get("object_type", ""),
                source=text_entry.get("source", ""),
                bibliography=text_entry.get("bibliography", ""),
                notes=f"{title}: {section.get('label', '')}. {text_entry.get('notes', '')}",
                language="etruscan",
                classification=text_entry.get("classification", "unknown"),
                script_system=text_entry.get("script_system", "old_italic"),
                completeness=text_entry.get("completeness", "complete"),
                provenance_status="verified",
            )
            corpus.add(inscription)
            count += 1
            print(f"   📜 {section_id}: {title} — {section.get('label', '')}")

    corpus.close()
    print(f"\n✅ Seeded {count} codex sections")
    print(f"   Database: {db_path}")
    return count


def main():
    parser = argparse.ArgumentParser(description="Seed OpenEtruscan corpus from Larth dataset")
    parser.add_argument("--db-path", default="data/corpus.db", help="Path to corpus database")
    parser.add_argument("--csv-path", default=None, help="Path to local CSV (skips download)")
    parser.add_argument("--codex", action="store_true", help="Also import codex texts")
    parser.add_argument(
        "--codex-only",
        action="store_true",
        help="Import ONLY codex texts (skip Larth download)",
    )
    args = parser.parse_args()

    if args.codex_only:
        print("📚 Importing Etruscan codex texts...")
        seed_codex(db_path=args.db_path)
    else:
        if args.csv_path:
            csv_data = Path(args.csv_path).read_text(encoding="utf-8")
        else:
            csv_data = download_larth()

        seed_corpus(csv_data, db_path=args.db_path)

        if args.codex:
            print("\n📚 Importing Etruscan codex texts...")
            seed_codex(db_path=args.db_path)

    # Show a sample query
    print("\n🔍 Sample query:")
    corpus = Corpus.load(args.db_path)
    results = corpus.search(limit=3)
    for insc in results:
        print(f"   {insc.id}: {insc.canonical} ({insc.findspot}, {insc.date_display()})")
    corpus.close()


if __name__ == "__main__":
    main()
