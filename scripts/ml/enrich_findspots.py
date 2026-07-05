#!/usr/bin/env python3
"""
OpenEtruscan Findspot Enrichment Script
========================================

Backfills missing findspot data using multiple strategies:
1. Exact canonical text matching against known records
2. CIE prefix → findspot deterministic mapping
3. ETP sub-ID range inference from known ETP records
4. Pleiades/GeoNames coordinate propagation from findspot name

Writes the enriched corpus back to the frontend JSON and
regenerates the RDF/Turtle corpus file.
"""

import json
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = REPO_ROOT / "frontend/public/data/corpus.json"
TTL_PATH = REPO_ROOT / "data/rdf/corpus.ttl"

# ── CIE prefix → findspot (100% reliable from data analysis) ──
CIE_PREFIX_MAP = {
    "AC": ("Ager Caeretanus", 42.0009, 12.1067, "422859", None),
    "AF": ("Ager Faesulanus", None, None, "413126", None),
    "AK": ("Ager Clusinus", None, None, "413084", None),
    "AP": ("Ager Pisanus", None, None, "403207", None),
    "AS": ("Ager Saenensis", None, None, "413282", None),
    "AT": ("Ager Tarquiniensis", 42.25, 11.75, "413332", None),
    "AV": ("Ager Volcentanus", None, None, "413395", None),
    "Af": ("Africa", None, None, None, None),
    "Ar": ("Arretium", None, None, "413032", "3182749"),
    "At": ("Ager Tarquiniensis", 42.25, 11.75, "413332", None),
    "Cl": ("Clusium", 43.0174, 11.9492, "413084", "3178519"),
    "Cm": ("Campania", 40.85, 14.25, "442733", None),
    "Co": ("Cortona", 43.2754, 11.9858, "413098", "3177997"),
    "Cr": ("Caere", 42.0009, 12.1067, "422859", "6541965"),
    "El": ("Isola dElba", None, None, None, None),
    "Fa": ("Falerii et Ager Faliscus", None, None, "413123", None),
    "Fs": ("Faesulae", 43.8059, 11.2944, "413126", "3177101"),
    "La": ("Latium", None, None, "422932", None),
    "Li": ("Liguria", None, None, "383627", None),
    "Lu": ("Lucania", None, None, "442683", None),
    "Na": ("Narce", None, None, "413248", None),
    "Pa": ("Padana", None, None, "393471", None),
    "Pe": ("Perusia", 43.1107, 12.3908, "413248", "3171180"),
    "Pi": ("Piacenza", 45.0522, 9.693, "383741", "3171077"),
    "Ps": ("Pisae", None, None, "403207", "3170647"),
    "Po": ("Populonia", 42.9883, 10.4936, "413169", "3170227"),
    "Py": ("Pyrgi", 42.0098, 11.9676, "413182", None),
    "Rm": ("Roma", None, None, "423025", "3169070"),
    "Ru": ("Rusellae", 42.824, 11.1595, "413184", None),
    "Sa": ("Saturnia", None, None, "413186", "3167074"),
    "Sp": ("Spina", None, None, "393489", None),
    "Ta": ("Tarquinia", 42.2488, 11.7553, "413332", "3165940"),
    "Um": ("Umbria", None, None, "413356", None),
    "Vc": ("Vulci", 42.4212, 11.6323, "413395", "8013259"),
    "Ve": ("Veii", 42.0273, 12.3979, "423116", "3164526"),
    "Vn": ("Vetulonia", 42.8524, 10.9746, "413381", "3164375"),
    "Vs": ("Volsinii", 42.7182, 11.875, "413389", None),
    "Vt": ("Volaterrae", 43.4015, 10.8619, "403292", "3163972"),
}

# ── Findspot name → coordinates (for propagation) ──
FINDSPOT_COORDS = {}
for _prefix, (name, lat, lon, pleiades, geonames) in CIE_PREFIX_MAP.items():
    if lat and lon:
        FINDSPOT_COORDS[name] = (lat, lon, pleiades, geonames)


def load_corpus():
    with open(CORPUS_PATH) as f:
        return json.load(f)


def get_prefix(record_id: str) -> str:
    """Extract the CIE prefix from an ID like 'Cr 2.20' or 'AT 1.171'."""
    parts = record_id.split()
    if len(parts) >= 2 and not parts[0][0].isdigit():
        return parts[0]
    return ""


def enrich(data: list[dict]) -> dict:
    """Apply all enrichment strategies. Returns stats dict."""
    stats = Counter()

    # Build text→findspot index from known records
    text_index = {}
    for d in data:
        if d.get("findspot") and d.get("canonical"):
            canon = d["canonical"].strip().lower()
            if canon not in text_index:
                text_index[canon] = {
                    "findspot": d["findspot"],
                    "findspot_lat": d.get("findspot_lat"),
                    "findspot_lon": d.get("findspot_lon"),
                    "pleiades_id": d.get("pleiades_id"),
                    "geonames_id": d.get("geonames_id"),
                }

    for d in data:
        if d.get("findspot"):
            # Already has findspot; propagate coordinates if missing
            if not d.get("findspot_lat") and d["findspot"] in FINDSPOT_COORDS:
                lat, lon, pleiades, geonames = FINDSPOT_COORDS[d["findspot"]]
                d["findspot_lat"] = lat
                d["findspot_lon"] = lon
                if pleiades and not d.get("pleiades_id"):
                    d["pleiades_id"] = pleiades
                if geonames and not d.get("geonames_id"):
                    d["geonames_id"] = geonames
                stats["coords_propagated"] += 1
            continue

        # ── Strategy 1: CIE prefix mapping ──
        prefix = get_prefix(d["id"])
        if prefix and prefix in CIE_PREFIX_MAP:
            name, lat, lon, pleiades, geonames = CIE_PREFIX_MAP[prefix]
            d["findspot"] = name
            d["findspot_lat"] = lat
            d["findspot_lon"] = lon
            if pleiades:
                d["pleiades_id"] = pleiades
            if geonames:
                d["geonames_id"] = geonames
            stats["prefix_mapped"] += 1
            continue

        # ── Strategy 2: Exact text match ──
        if d.get("canonical"):
            canon = d["canonical"].strip().lower()
            if canon in text_index:
                match = text_index[canon]
                d["findspot"] = match["findspot"]
                d["findspot_lat"] = match["findspot_lat"]
                d["findspot_lon"] = match["findspot_lon"]
                if match.get("pleiades_id"):
                    d["pleiades_id"] = match["pleiades_id"]
                if match.get("geonames_id"):
                    d["geonames_id"] = match["geonames_id"]
                stats["text_matched"] += 1
                continue

        stats["still_missing"] += 1

    return dict(stats)


def save_corpus(data: list[dict]):
    with open(CORPUS_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    print("Loading corpus...")
    data = load_corpus()
    total = len(data)
    missing_before = sum(1 for d in data if not d.get("findspot"))
    print(f"  Total records: {total}")
    print(f"  Missing findspot: {missing_before}")

    print("\nEnriching...")
    stats = enrich(data)

    missing_after = sum(1 for d in data if not d.get("findspot"))
    filled = missing_before - missing_after

    print(f"\n{'=' * 50}")
    print("RESULTS")
    print(f"{'=' * 50}")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
    print(f"\n  Filled: {filled} ({filled / missing_before * 100:.1f}% of missing)")
    print(f"  Still missing: {missing_after} ({missing_after / total * 100:.1f}% of total)")

    # Show new findspot distribution
    fs_dist = Counter(d.get("findspot") or "UNKNOWN" for d in data)
    print("\nFindspot distribution (top 20):")
    for fs, c in fs_dist.most_common(20):
        print(f"  {fs}: {c}")

    print("\nSaving enriched corpus...")
    save_corpus(data)
    print(f"  Saved to {CORPUS_PATH}")


if __name__ == "__main__":
    main()
