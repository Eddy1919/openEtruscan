#!/usr/bin/env python3
"""
Build a local Pleiades gazetteer for findspot matching.

Downloads the public Pleiades **places** and **names** CSV dumps, filters to the
Etruria / central-Italy bounding box, and writes a compact JSON file that
``propose_pleiades_links.py`` consumes. Pulling the *names* dump (not just place
titles) is what lets us match ancient surface forms — "Tarchna", "Velch",
"Clevsin" — that never appear as the modern title.

Output schema (``data/pleiades_gazetteer.json``):

    [
      {"pleiades_id": "413047", "title": "Clusium",
       "names": ["Clusium", "Camars"], "lat": 43.0, "lon": 11.9},
      ...
    ]

Run:
    python scripts/data_pipeline/build_pleiades_gazetteer.py
    python scripts/data_pipeline/build_pleiades_gazetteer.py --bbox 40 45.5 9 14.5

Network access required. Re-run when you want a fresher gazetteer snapshot.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import urllib.request
from pathlib import Path

PLACES_URL = "https://atlantides.org/downloads/pleiades/dumps/pleiades-places-latest.csv.gz"
NAMES_URL = "https://atlantides.org/downloads/pleiades/dumps/pleiades-names-latest.csv.gz"

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "data" / "pleiades_gazetteer.json"

# Etruria + the Etruscan expansion sphere (Campania, Po valley) by default.
DEFAULT_BBOX = (40.0, 45.5, 9.0, 14.5)  # min_lat, max_lat, min_lon, max_lon

# Candidate name columns across dump versions; we read whichever are present.
_NAME_COLUMNS = ("nameAttested", "nameTransliterated", "nameRomanized", "title")


def _download_csv(url: str) -> list[dict[str, str]]:
    print(f"  downloading {url} ...")
    with urllib.request.urlopen(url) as resp:  # noqa: S310 (trusted Pleiades host)
        raw = gzip.decompress(resp.read()).decode("utf-8")
    return list(csv.DictReader(io.StringIO(raw)))


def _place_id_from_pid(pid: str) -> str:
    """Names-dump `pid` may be a bare id or a /places/<id> path; normalise it."""
    pid = (pid or "").strip().rstrip("/")
    return pid.rsplit("/", 1)[-1] if "/" in pid else pid


def build(bbox: tuple[float, float, float, float], output: Path) -> int:
    min_lat, max_lat, min_lon, max_lon = bbox

    print("Fetching Pleiades places...")
    places_rows = _download_csv(PLACES_URL)
    places: dict[str, dict] = {}
    for row in places_rows:
        try:
            lat = float(row["reprLat"])
            lon = float(row["reprLong"])
        except (ValueError, TypeError, KeyError):
            lat = lon = None  # keep place; some have names but no representative point
        if lat is not None and not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
            continue
        pid = (row.get("id") or "").strip()
        if not pid:
            continue
        title = (row.get("title") or "").strip()
        places[pid] = {
            "pleiades_id": pid,
            "title": title,
            "names": [title] if title else [],
            "lat": lat,
            "lon": lon,
        }
    print(f"  {len(places)} places inside bbox")

    print("Fetching Pleiades names (ancient + variant forms)...")
    names_rows = _download_csv(NAMES_URL)
    attached = 0
    for row in names_rows:
        pid = _place_id_from_pid(row.get("pid", ""))
        place = places.get(pid)
        if place is None:
            continue
        for col in _NAME_COLUMNS:
            for variant in (row.get(col) or "").split(","):
                variant = variant.strip()
                if variant and variant not in place["names"]:
                    place["names"].append(variant)
                    attached += 1
    print(f"  attached {attached} name variants")

    gazetteer = sorted(places.values(), key=lambda p: p["pleiades_id"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(gazetteer, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"Wrote {len(gazetteer)} places to {output}")
    return len(gazetteer)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a local Pleiades gazetteer JSON.")
    ap.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        metavar=("MIN_LAT", "MAX_LAT", "MIN_LON", "MAX_LON"),
        default=DEFAULT_BBOX,
        help="Bounding box to keep (default: Etruria + expansion sphere).",
    )
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()
    build(tuple(args.bbox), args.output)


if __name__ == "__main__":
    main()
