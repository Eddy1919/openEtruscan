#!/usr/bin/env python3
"""
OpenEtruscan — Comprehensive Geotag Enrichment
================================================

Backfills findspot coordinates, Pleiades IDs, and PostGIS geometry
for all inscriptions in the live PostgreSQL database.

Strategies:
  A) CIE prefix → canonical findspot + coordinates
  B) Fuzzy Latin string matching for CIE verbose findspots
  C) Coordinate propagation from findspot name
  D) PostGIS geom column sync

Usage:
  source .venv/bin/activate  # or /tmp/oe_venv/bin/activate
  python scripts/update_geotags.py [--dry-run]
"""

import argparse
import json
import os
import re
import sys
import time
from urllib.request import urlopen, Request

import psycopg2
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://corpus_reader:etruscan_secret@127.0.0.1:5432/corpus",
)

# ═══════════════════════════════════════════════════════════════════════
# MASTER PLACE REGISTRY
# ═══════════════════════════════════════════════════════════════════════
# Each entry: canonical_name → (lat, lon, pleiades_id, tm_geo_id)
# Coordinates sourced from Pleiades JSON API + manual verification.
# TM GEO IDs from https://www.trismegistos.org/geo/

PLACES: dict[str, tuple[float, float, str, str | None]] = {
    # ── Major Etruscan cities ──
    "Arretium":       (43.4633, 11.8817, "413032", "20301"),   # Arezzo
    "Caere":          (42.0009, 12.1067, "422859", "19984"),   # Cerveteri
    "Clusium":        (43.0174, 11.9492, "413096", "20137"),   # Chiusi
    "Cortona":        (43.2754, 11.9858, "413106", "19837"),   # Cortona
    "Faesulae":       (43.8059, 11.2944, "413124", "20241"),   # Fiesole
    "Narce":          (42.2333, 12.4000, "413248", None),      # Narce
    "Perusia":        (43.1107, 12.3908, "413248", "19879"),   # Perugia
    "Piacenza":       (45.0522,  9.6930, "383741", "20445"),   # Placentia
    "Pisae":          (43.7228, 10.4017, "403253", "20218"),   # Pisa
    "Populonia":      (42.9883, 10.4936, "413169", "20274"),   # Populonia
    "Pyrgi":          (42.0098, 11.9676, "413182", None),      # S. Severa
    "Roma":           (41.8933, 12.4833, "423025", "562"),      # Rome
    "Rusellae":       (42.8240, 11.1595, "413288", "20271"),   # Roselle
    "Saturnia":       (42.6625, 11.5064, "413044", "20177"),   # Saturnia
    "Spina":          (44.6750, 12.1833, "393498", "20368"),   # Comacchio
    "Tarquinia":      (42.2488, 11.7553, "413332", "20002"),   # Tarquinia
    "Veii":           (42.0273, 12.3979, "423116", "19977"),   # Veio
    "Vetulonia":      (42.8524, 10.9746, "413381", "20270"),   # Vetulonia
    "Volaterrae":     (43.4015, 10.8619, "403292", "20287"),   # Volterra
    "Volsinii":       (42.6464, 11.9867, "413389", "20067"),   # Bolsena / Orvieto
    "Vulci":          (42.4212, 11.6323, "413393", "20069"),   # Vulci
    "Falerii":        (42.2981, 12.4219, "413125", "19949"),   # Civita Castellana

    # ── Ager (territory) entries — linked to parent city coords ──
    "Ager Caeretanus":      (42.0009, 12.1067, "422859", "19984"),
    "Ager Tarquiniensis":   (42.2488, 11.7553, "413332", "20002"),
    "Ager Veientanus":      (42.0273, 12.3979, "423116", "19977"),
    "Ager Clusinus":        (43.0174, 11.9492, "413096", "20137"),
    "Ager Faesulanus":      (43.8059, 11.2944, "413124", "20241"),
    "Ager Pisanus":         (43.7228, 10.4017, "403253", "20218"),
    "Ager Volaterranus":    (43.4015, 10.8619, "403292", "20287"),
    "Ager Volsiniensis":    (42.6464, 11.9867, "413389", "20067"),
    "Ager Volcentanus":     (42.4212, 11.6323, "413393", "20069"),
    "Ager Saenensis":       (43.3178, 11.3307, "413282", "20304"),  # Siena
    "Ager Capenas":         (42.1350, 12.5458, "413062", "19952"),  # Capena
    "Falerii et Ager Faliscus": (42.2981, 12.4219, "413125", "19949"),

    # ── Regions ──
    "Campania":  (40.8500, 14.2500, "442733", None),
    "Latium":    (41.8000, 12.7000, "422932", None),
    "Umbria":    (42.8000, 12.6000, "413356", None),
    "Liguria":   (44.3167, 8.3500,  "383627", None),
    "Lucania":   (40.3500, 15.8500, "442683", None),
    "Aemilia":   (44.5000, 11.3500, "383596", None),
    "Padana":    (45.0000, 10.5000, "393471", None),

    # ── Additional specific places from CIE data ──
    "Saena":                  (43.3178, 11.3307, "413282", "20304"),  # Siena
    "Florentia":              (43.7696, 11.2558, "413126", "20252"),  # Florence
    "Perugia":                (43.1107, 12.3908, "413248", "19879"),
    "Bettolle":               (43.2167, 11.8000, "413096", "20137"),  # near Clusium
    "Marciano":               (43.3000, 11.7833, "413032", "20301"),  # near Arretium
    "Lucignano":              (43.2833, 11.7500, "413096", "20137"),  # near Clusium
    "Poggio alle Mura":       (42.9167, 11.3333, "413381", "20270"),  # near Vetulonia
    "Isola d'Elba":           (42.7794, 10.2478, "413143", None),     # Elba
    "Bolsena":                (42.6464, 11.9867, "413389", "20067"),
    "Chianciano":             (43.0611, 11.8306, "413096", "20137"),  # near Clusium
    "Montepulciano":          (43.0939, 11.7828, "413096", "20137"),  # near Clusium
    "Orvieto":                (42.7185, 12.1117, "413389", "20067"),  # alt. for Volsinii
    "Siena":                  (43.3178, 11.3307, "413282", "20304"),
    "Arezzo":                 (43.4633, 11.8817, "413032", "20301"),
    "Volterra":               (43.4015, 10.8619, "403292", "20287"),
    "Chiusi":                 (43.0174, 11.9492, "413096", "20137"),
}

# ═══════════════════════════════════════════════════════════════════════
# FUZZY LATIN VARIATION → CANONICAL PLACE
# ═══════════════════════════════════════════════════════════════════════
# CIE findspots use elaborate Latin provenance strings like
# "Clusii in agro" or "in museo publico Clusino (succ.) DA."
# We need deterministic substring matching.
#
# Order matters: more specific patterns first to avoid false matches.

LATIN_PATTERNS: list[tuple[str, str]] = [
    # Clusium / Chiusi variations (the biggest gap — ~900 records)
    ("Clusii",    "Clusium"),
    ("Clusino",   "Clusium"),
    ("Clusium",   "Clusium"),
    ("Chiusi",    "Clusium"),

    # Volaterrae / Volterra
    ("Volaterr",  "Volaterrae"),
    ("Volterra",  "Volaterrae"),

    # Tarquinia
    ("Tarquini",  "Tarquinia"),

    # Cortona
    ("Corton",    "Cortona"),

    # Perusia / Perugia
    ("Perusi",    "Perusia"),
    ("Perugia",   "Perusia"),

    # Vulci
    ("Vulci",     "Vulci"),
    ("Vulcent",   "Vulci"),

    # Caere / Cerveteri
    ("Caeret",    "Caere"),
    ("Caere",     "Caere"),
    ("Cerveteri", "Caere"),

    # Veii / Veio
    ("Veient",    "Veii"),
    ("Veii",      "Veii"),
    ("Veio",      "Veii"),

    # Arretium / Arezzo
    ("Arreti",    "Arretium"),
    ("Arezzo",    "Arretium"),

    # Faesulae / Fiesole
    ("Faesul",    "Faesulae"),
    ("Fiesole",   "Faesulae"),

    # Populonia
    ("Populoni",  "Populonia"),

    # Rusellae / Roselle
    ("Rusell",    "Rusellae"),
    ("Roselle",   "Rusellae"),

    # Vetulonia
    ("Vetulon",   "Vetulonia"),

    # Volsinii / Bolsena / Orvieto
    ("Volumni",   "Volsinii"),
    ("Volsini",   "Volsinii"),
    ("Bolsena",   "Volsinii"),
    ("Orvieto",   "Volsinii"),

    # Saturnia
    ("Saturni",   "Saturnia"),

    # Spina
    ("Spina",     "Spina"),

    # Narce
    ("Narce",     "Narce"),

    # Falerii
    ("Falisc",    "Falerii"),
    ("Faleri",    "Falerii"),

    # Roma
    ("Roma",      "Roma"),

    # Pyrgi / S. Severa
    ("Pyrgi",     "Pyrgi"),

    # Florence
    ("Florentin", "Florentia"),
    ("Firenze",   "Florentia"),

    # Saena / Siena
    ("SAENA",     "Saena"),
    ("Saena",     "Saena"),
    ("Siena",     "Saena"),

    # Specific archaeological sites
    ("Bettolle",          "Bettolle"),
    ("Marciano",          "Marciano"),
    ("Lucignano",         "Lucignano"),
    ("Poggio alle Mura",  "Poggio alle Mura"),
    ("Chianciano",        "Chianciano"),
    ("Montepulciano",     "Montepulciano"),
    ("Piacenza",          "Piacenza"),

    # Broader regional matches (last resort)
    ("Campania",  "Campania"),
    ("Lati",      "Latium"),
    ("Umbri",     "Umbria"),
    ("Liguri",    "Liguria"),
    ("Lucani",    "Lucania"),
    ("Padana",    "Padana"),
    ("Aemilia",   "Aemilia"),
    ("Elba",      "Isola d'Elba"),
]


# ═══════════════════════════════════════════════════════════════════════
# CIE PREFIX → CANONICAL PLACE (for records with no findspot at all)
# ═══════════════════════════════════════════════════════════════════════

CIE_PREFIX_MAP: dict[str, str] = {
    "AC": "Ager Caeretanus",
    "AF": "Ager Faesulanus",
    "AK": "Ager Clusinus",
    "AP": "Ager Pisanus",
    "AS": "Ager Saenensis",
    "AT": "Ager Tarquiniensis",
    "AV": "Ager Volcentanus",
    "Af": "Campania",         # Africa records — minimal
    "Ar": "Arretium",
    "At": "Ager Tarquiniensis",
    "Cl": "Clusium",
    "Cm": "Campania",
    "Co": "Cortona",
    "Cr": "Caere",
    "El": "Isola d'Elba",
    "Fa": "Falerii",
    "Fs": "Faesulae",
    "La": "Latium",
    "Li": "Liguria",
    "Lu": "Lucania",
    "Na": "Narce",
    "Pa": "Padana",
    "Pe": "Perusia",
    "Pi": "Piacenza",
    "Ps": "Pisae",
    "Po": "Populonia",
    "Py": "Pyrgi",
    "Rm": "Roma",
    "Ru": "Rusellae",
    "Sa": "Saturnia",
    "Sp": "Spina",
    "Ta": "Tarquinia",
    "Um": "Umbria",
    "Vc": "Vulci",
    "Ve": "Veii",
    "Vn": "Vetulonia",
    "Vs": "Volsinii",
    "Vt": "Volaterrae",
}


def resolve_findspot(findspot_str: str) -> str | None:
    """Match a raw Latin findspot string to a canonical place name."""
    if not findspot_str:
        return None
    for pattern, canonical in LATIN_PATTERNS:
        if pattern in findspot_str:
            return canonical
    return None


def get_cie_prefix(inscription_id: str) -> str:
    """Extract the CIE 2-letter prefix from an ID like 'Cr 2.20'."""
    parts = inscription_id.split()
    if len(parts) >= 2 and not parts[0][0].isdigit() and len(parts[0]) == 2:
        return parts[0]
    return ""


def main():
    parser = argparse.ArgumentParser(description="Enrich geotags in PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # ── Stats before ──
    cur.execute("SELECT COUNT(*) FROM inscriptions")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM inscriptions WHERE findspot_lat IS NOT NULL")
    coords_before = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM inscriptions WHERE pleiades_id IS NOT NULL")
    pleiades_before = cur.fetchone()[0]

    print(f"{'='*60}")
    print(f"OpenEtruscan — Geotag Enrichment")
    print(f"{'='*60}")
    print(f"Total inscriptions: {total}")
    print(f"With coordinates:   {coords_before}")
    print(f"With Pleiades ID:   {pleiades_before}")
    print()

    updates = []  # (id, findspot, lat, lon, pleiades_id, tm_geo_id)

    # ── Strategy A: Fill findspot from CIE prefix for empty records ──
    cur.execute("""SELECT id, findspot FROM inscriptions
                   WHERE findspot IS NULL OR findspot = ''""")
    no_findspot_rows = cur.fetchall()
    prefix_filled = 0

    for row_id, _ in no_findspot_rows:
        prefix = get_cie_prefix(row_id)
        canonical = CIE_PREFIX_MAP.get(prefix)
        if canonical and canonical in PLACES:
            lat, lon, pleiades_id, tm_geo = PLACES[canonical]
            updates.append((row_id, canonical, lat, lon, pleiades_id, tm_geo))
            prefix_filled += 1

    print(f"[Strategy A] CIE prefix → findspot: {prefix_filled} records")

    # ── Strategy B: Fuzzy Latin matching for existing findspot strings ──
    cur.execute("""SELECT id, findspot FROM inscriptions
                   WHERE findspot IS NOT NULL AND findspot != ''
                   AND findspot_lat IS NULL""")
    need_coords_rows = cur.fetchall()
    fuzzy_filled = 0

    for row_id, findspot in need_coords_rows:
        # First check if exact name is in PLACES
        if findspot in PLACES:
            lat, lon, pleiades_id, tm_geo = PLACES[findspot]
            updates.append((row_id, findspot, lat, lon, pleiades_id, tm_geo))
            fuzzy_filled += 1
            continue

        # Fuzzy Latin matching
        canonical = resolve_findspot(findspot)
        if canonical and canonical in PLACES:
            lat, lon, pleiades_id, tm_geo = PLACES[canonical]
            # Keep the original findspot string, just add coordinates
            updates.append((row_id, None, lat, lon, pleiades_id, tm_geo))
            fuzzy_filled += 1

    print(f"[Strategy B] Fuzzy Latin matching: {fuzzy_filled} records")

    # ── Strategy C: Coordinate propagation for records that have
    #    findspot but missing pleiades_id ──
    cur.execute("""SELECT id, findspot FROM inscriptions
                   WHERE findspot IS NOT NULL AND findspot != ''
                   AND findspot_lat IS NOT NULL
                   AND pleiades_id IS NULL""")
    need_pleiades_rows = cur.fetchall()
    pleiades_filled = 0

    for row_id, findspot in need_pleiades_rows:
        if findspot in PLACES:
            _, _, pleiades_id, tm_geo = PLACES[findspot]
            if pleiades_id:
                updates.append((row_id, None, None, None, pleiades_id, tm_geo))
                pleiades_filled += 1
            continue

        canonical = resolve_findspot(findspot)
        if canonical and canonical in PLACES:
            _, _, pleiades_id, tm_geo = PLACES[canonical]
            if pleiades_id:
                updates.append((row_id, None, None, None, pleiades_id, tm_geo))
                pleiades_filled += 1

    print(f"[Strategy C] Pleiades ID fill: {pleiades_filled} records")
    print(f"\nTotal updates to apply: {len(updates)}")

    if args.dry_run:
        print("\n[DRY RUN] No changes written.")
        # Show sample
        for u in updates[:20]:
            print(f"  {u[0]:30s} → findspot={u[1] or '(keep)':20s} lat={u[2]} lon={u[3]} pleiades={u[4]}")
        if len(updates) > 20:
            print(f"  ... and {len(updates) - 20} more")
        conn.close()
        return

    # ── Apply updates ──
    print("\nApplying updates...")
    applied = 0
    for row_id, findspot, lat, lon, pleiades_id, tm_geo in updates:
        parts = []
        params = []

        if findspot is not None:
            parts.append("findspot = %s")
            params.append(findspot)
        if lat is not None:
            parts.append("findspot_lat = %s")
            params.append(lat)
            parts.append("findspot_lon = %s")
            params.append(lon)
            parts.append(
                "geom = ST_SetSRID(ST_MakePoint(%s, %s), 4326)"
            )
            params.extend([lon, lat])
        if pleiades_id is not None:
            parts.append("pleiades_id = %s")
            params.append(pleiades_id)
        if tm_geo is not None:
            # We'll store TM geo IDs in the notes or a dedicated column
            # For now, skip if no column exists
            pass

        if not parts:
            continue

        params.append(row_id)
        sql = f"UPDATE inscriptions SET {', '.join(parts)} WHERE id = %s"
        cur.execute(sql, params)
        applied += 1

    # ── Also sync geom for any records that already have lat/lon but no geom ──
    cur.execute("""
        UPDATE inscriptions
        SET geom = ST_SetSRID(ST_MakePoint(findspot_lon, findspot_lat), 4326)
        WHERE findspot_lat IS NOT NULL
          AND findspot_lon IS NOT NULL
          AND geom IS NULL
    """)
    geom_synced = cur.rowcount

    conn.commit()

    # ── Stats after ──
    cur.execute("SELECT COUNT(*) FROM inscriptions WHERE findspot_lat IS NOT NULL")
    coords_after = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM inscriptions WHERE pleiades_id IS NOT NULL")
    pleiades_after = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM inscriptions WHERE geom IS NOT NULL")
    geom_after = cur.fetchone()[0]

    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    print(f"  Updates applied:    {applied}")
    print(f"  PostGIS geom synced: {geom_synced}")
    print(f"  Coordinates:  {coords_before} → {coords_after} (+{coords_after - coords_before})")
    print(f"  Pleiades IDs: {pleiades_before} → {pleiades_after} (+{pleiades_after - pleiades_before})")
    print(f"  PostGIS geom: {geom_after}")
    print(f"\n  Coverage: {coords_after}/{total} ({coords_after/total*100:.1f}%)")

    # Show top findspot distribution
    cur.execute("""
        SELECT findspot, COUNT(*) as cnt
        FROM inscriptions
        WHERE findspot IS NOT NULL AND findspot != ''
        GROUP BY findspot ORDER BY cnt DESC LIMIT 15
    """)
    print(f"\nTop 15 findspots:")
    for fs, cnt in cur.fetchall():
        cur2 = conn.cursor()
        cur2.execute(
            "SELECT COUNT(*) FROM inscriptions WHERE findspot = %s AND findspot_lat IS NOT NULL",
            (fs,)
        )
        has = cur2.fetchone()[0]
        status = "✅" if has == cnt else f"⚠️ {has}/{cnt}"
        print(f"  {status} {fs:40s} {cnt}")

    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
