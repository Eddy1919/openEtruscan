#!/usr/bin/env python3
"""Build ``reference/places.csv`` from a Pleiades places dump.

The findspot gazetteer (``reference/findspot_gazetteer.csv``) and the ET
region table (``reference/et_regions.csv``) refer to places by a short key
(``clusium``, ``ager_faliscus``). This script resolves each key to its
Pleiades place and copies the representative point and title out of the
dump, so no coordinate in the repo is typed by hand.

Usage:
    curl -LO https://atlantides.org/downloads/pleiades/dumps/pleiades-places-latest.csv.gz
    python scripts/data_pipeline/build_reference_places.py \
        --places pleiades-places-latest.csv.gz --out reference/places.csv
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import sys
from pathlib import Path

#: (key, Pleiades id, English label, Italian label, kind)
#: kind is the precision a bare mention of the place carries: ``city`` for a
#: settlement, ``site`` for a sanctuary or necropolis, ``region`` for a
#: Pleiades region.
PLACES: tuple[tuple[str, str, str, str, str], ...] = (
    ("adria", "393436", "Adria (Atria)", "Adria", "city"),
    ("ager_faliscus", "532728731", "Ager Faliscus", "Agro falisco", "region"),
    ("aemilia", "393372", "Aemilia", "Emilia", "region"),
    ("arretium", "413032", "Arretium (Arezzo)", "Arezzo", "city"),
    ("asciano", "413035", "Asciano", "Asciano", "city"),
    ("blera", "413054", "Blera", "Blera", "city"),
    ("caere", "422859", "Caere (Cerveteri)", "Cerveteri", "city"),
    ("campania", "432742", "Campania", "Campania", "region"),
    ("capena", "413062", "Capena", "Capena", "city"),
    ("capua", "432754", "Capua", "Capua", "city"),
    ("castiglione_del_lago", "413071", "Castiglione del Lago", "Castiglione del Lago", "site"),
    ("cetona", "232079422", "Cetona", "Cetona", "city"),
    ("clusium", "413096", "Clusium (Chiusi)", "Chiusi", "city"),
    ("cortona", "413106", "Cortona", "Cortona", "city"),
    ("cosa", "413107", "Cosa", "Cosa", "city"),
    ("etruria", "413122", "Etruria", "Etruria", "region"),
    ("faesulae", "413124", "Faesulae (Fiesole)", "Fiesole", "city"),
    ("falerii", "413125", "Falerii", "Falerii", "city"),
    (
        "falerii_veteres",
        "413126",
        "Falerii Veteres (Civita Castellana)",
        "Civita Castellana",
        "city",
    ),
    ("felsina", "393421", "Felsina/Bononia (Bologna)", "Bologna", "city"),
    ("ferentium", "413132", "Ferentium", "Ferento", "city"),
    ("florentia", "413138", "Florentia (Florence)", "Firenze", "city"),
    ("fratte", "432845", "Fratte", "Fratte", "site"),
    ("graviscae", "413157", "Graviscae", "Gravisca", "site"),
    ("heba", "413164", "Heba", "Heba", "city"),
    ("horta", "413172", "Horta (Orte)", "Orte", "city"),
    ("kainua", "393448", "Kainua (Marzabotto)", "Marzabotto", "city"),
    ("latium", "432900", "Latium", "Lazio", "region"),
    ("musarna", "413217", "Musarna", "Musarna", "city"),
    ("narce", "413133", "Narce (Pleiades: Fescennium)", "Narce", "city"),
    ("nepet", "413224", "Nepet (Nepi)", "Nepi", "city"),
    ("nola", "432981", "Nola", "Nola", "city"),
    ("orcla", "413233", "Orcla (Norchia)", "Norchia", "site"),
    ("perusia", "413248", "Perusia (Perugia)", "Perugia", "city"),
    ("pisae", "403253", "Pisae (Pisa)", "Pisa", "city"),
    ("placentia", "383741", "Placentia (Piacenza)", "Piacenza", "city"),
    ("poggio_civitate", "413216", "Poggio Civitate (Murlo)", "Poggio Civitate (Murlo)", "site"),
    ("pontecagnano", "442728", "Pontecagnano", "Pontecagnano", "city"),
    ("populonia", "403212", "Populonia", "Populonia", "city"),
    ("pyrgi", "433061", "Pyrgi", "Pyrgi", "site"),
    ("rusellae", "413288", "Rusellae (Roselle)", "Roselle", "city"),
    ("saena", "413293", "Saena (Siena)", "Siena", "city"),
    ("sarteano", "413307", "Sarteano", "Sarteano", "city"),
    ("saturnia", "413044", "Saturnia", "Saturnia", "city"),
    ("spina", "393498", "Spina", "Spina", "city"),
    ("suana", "413323", "Suana (Sovana)", "Sovana", "city"),
    ("sutrium", "413328", "Sutrium (Sutri)", "Sutri", "city"),
    ("tarquinii", "413332", "Tarquinii (Tarquinia)", "Tarquinia", "city"),
    ("tuscana", "413356", "Tuscana (Tuscania)", "Tuscania", "city"),
    ("veii", "423116", "Veii", "Veio", "city"),
    ("vetulonia", "403291", "Vetulonia", "Vetulonia", "city"),
    ("visentium", "413386", "Visentium", "Bisenzio", "city"),
    ("volaterrae", "403292", "Volaterrae (Volterra)", "Volterra", "city"),
    ("volsinii", "413389", "Volsinii (Bolsena)", "Bolsena", "city"),
    ("volsinii_veteres", "413373", "Velzna/Volsinii Veteres (Orvieto)", "Orvieto", "city"),
    ("vulci", "413393", "Vulci", "Vulci", "city"),
)

FIELDS = ("key", "pleiades_id", "label_en", "label_it", "kind", "pleiades_title", "lat", "lon")


def build(places_dump: Path, out: Path) -> int:
    wanted = {pid: (key, en, it, kind) for key, pid, en, it, kind in PLACES}
    csv.field_size_limit(sys.maxsize)
    found: dict[str, dict[str, str]] = {}
    with gzip.open(places_dump, "rb") as raw:
        for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8")):
            if row["id"] in wanted:
                found[row["id"]] = row
    missing = sorted(set(wanted) - set(found))
    if missing:
        raise SystemExit(f"Pleiades ids not in dump: {missing}")
    rows = []
    for key, pid, en, it, kind in PLACES:
        r = found[pid]
        rows.append(
            {
                "key": key,
                "pleiades_id": pid,
                "label_en": en,
                "label_it": it,
                "kind": kind,
                "pleiades_title": r["title"],
                "lat": f"{float(r['reprLat']):.5f}",
                "lon": f"{float(r['reprLong']):.5f}",
            }
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--places", type=Path, required=True, help="pleiades-places-latest.csv.gz")
    ap.add_argument("--out", type=Path, default=Path("reference/places.csv"))
    args = ap.parse_args()
    n = build(args.places, args.out)
    print(f"wrote {n} places to {args.out}")


if __name__ == "__main__":
    main()
