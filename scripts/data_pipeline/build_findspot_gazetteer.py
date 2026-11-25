#!/usr/bin/env python3
"""Regenerate ``reference/findspot_gazetteer.csv``.

One row per distinct findspot string in the corpus: its role (findspot,
current location, both, object description, unknown), the place it names
(a key into ``reference/places.csv``), the precision of that mention and
the custody clause. Rows whose ``basis`` is ``manual`` are curator
decisions and survive regeneration unchanged; everything else is
recomputed from :func:`openetruscan.core.findspots.classify_findspot`.

Usage:
    # from the database
    DATABASE_URL=... python scripts/data_pipeline/build_findspot_gazetteer.py --from-db
    # from a JSON list of records (e.g. a /api/search snapshot)
    python scripts/data_pipeline/build_findspot_gazetteer.py --from-json records.json
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from openetruscan.core.findspots import (  # noqa: E402
    GAZETTEER_FIELDS,
    classify_findspot,
    load_gazetteer,
    load_places,
)


def _strings_from_db(url: str) -> collections.Counter[str]:
    from sqlalchemy import create_engine, text

    eng = create_engine(url)
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT COALESCE(e.findspot_source_text, i.findspot) AS f, COUNT(*) "
                "FROM inscriptions i LEFT JOIN inscription_edition e "
                "ON e.inscription_id = i.id GROUP BY 1"
            )
            if _has_edition_table(conn)
            else text("SELECT findspot, COUNT(*) FROM inscriptions GROUP BY 1")
        ).all()
    return collections.Counter({(f or "").strip(): n for f, n in rows if (f or "").strip()})


def _has_edition_table(conn) -> bool:  # type: ignore[no-untyped-def]
    from sqlalchemy import inspect

    return "inscription_edition" in inspect(conn).get_table_names()


def _strings_from_json(path: Path) -> collections.Counter[str]:
    records = json.loads(path.read_text(encoding="utf-8"))
    return collections.Counter(
        (r.get("findspot") or "").strip() for r in records if (r.get("findspot") or "").strip()
    )


def build(counts: collections.Counter[str], places_csv: Path, out: Path) -> dict[str, int]:
    places = load_places(places_csv)
    kinds = {k: p.kind for k, p in places.items()}
    previous = load_gazetteer(out)
    rows = []
    stats: collections.Counter[str] = collections.Counter()
    for s, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        prev = previous.get(s)
        c = prev if prev is not None and prev.basis == "manual" else classify_findspot(s, kinds)
        if c.place_key and c.place_key not in places:
            raise SystemExit(f"place key {c.place_key!r} for {s!r} is not in {places_csv}")
        rows.append(
            {
                "findspot": s,
                "count": n,
                "role": c.role,
                "place_key": c.place_key or "",
                "precision": c.precision or "",
                "current_location": c.current_location or "",
                "basis": c.basis,
                "note": c.note,
            }
        )
        stats[f"strings:{c.role}"] += 1
        stats[f"records:{c.role}"] += n
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=GAZETTEER_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return dict(stats)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-db", action="store_true", help="read findspots from DATABASE_URL")
    src.add_argument("--from-json", type=Path, help="JSON list of records with a findspot key")
    ap.add_argument("--places", type=Path, default=REPO / "reference/places.csv")
    ap.add_argument("--out", type=Path, default=REPO / "reference/findspot_gazetteer.csv")
    args = ap.parse_args()
    if args.from_db:
        import os

        url = os.environ.get("DATABASE_URL")
        if not url:
            raise SystemExit("DATABASE_URL is not set")
        counts = _strings_from_db(url)
    else:
        counts = _strings_from_json(args.from_json)
    stats = build(counts, args.places, args.out)
    for k in sorted(stats):
        print(f"{k:32} {stats[k]:>6}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
