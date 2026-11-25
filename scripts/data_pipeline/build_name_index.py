#!/usr/bin/env python3
"""Fill ``name_attestations`` (migration ``k6a7b8c9d0e1``), the Name Index.

Reads every record's ``canonical`` text and indexes its personal names word
by word with :mod:`openetruscan.core.onomastics`: praenomina from
``reference/praenomina.csv`` (spellings and case forms grouped under one
lemma), abbreviated praenomina inside a naming formula, and the family name
that follows a praenomen. Each row carries its basis and confidence; only
listed praenomina are ``high``.

Dry run by default; ``--apply`` replaces this script's rows in one
transaction, so re-running is safe.

Usage:
    DATABASE_URL=postgresql://… python scripts/data_pipeline/build_name_index.py \\
        --report-dir research/results/name_index           # dry run
    DATABASE_URL=… python scripts/data_pipeline/build_name_index.py --apply
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from openetruscan.core.onomastics import (  # noqa: E402
    GOLD_GLOSSES,
    REFERENCE,
    NameLexicon,
    NameToken,
    index_corpus,
    load_lexicon,
)

SCRIPT_TAG = "build_name_index"


@dataclass
class Plan:
    names: dict[str, list[NameToken]]
    stats: collections.Counter[str] = field(default_factory=collections.Counter)
    lemmas: list[dict[str, Any]] = field(default_factory=list)


def build_plan(records: list[tuple[str, str]], lex: NameLexicon) -> Plan:
    plan = Plan(index_corpus(records, lex))
    s = plan.stats
    s["records"] = len(records)
    s["records_with_a_name"] = len(plan.names)
    by_lemma: dict[tuple[str, str], dict[str, Any]] = {}
    for rid, names in plan.names.items():
        for n in names:
            s["names"] += 1
            s[f"names:{n.name_type}"] += 1
            s[f"names_via:{n.basis}"] += 1
            entry = by_lemma.setdefault(
                (n.name_type, n.lemma),
                {
                    "lemma": n.lemma,
                    "name_type": n.name_type,
                    "gender": n.gender or "",
                    "confidence": n.confidence,
                    "attestations": 0,
                    "forms": collections.Counter(),
                    "records": set(),
                },
            )
            entry["attestations"] += 1
            entry["forms"][n.form] += 1
            entry["records"].add(rid)
    for e in by_lemma.values():
        e["records"] = len(e["records"])
        e["forms"] = " | ".join(f for f, _ in e["forms"].most_common())
    plan.lemmas = sorted(
        by_lemma.values(), key=lambda e: (-e["attestations"], e["name_type"], e["lemma"])
    )
    s["distinct_lemmas"] = len(plan.lemmas)
    s["distinct_lemmas:praenomen"] = sum(1 for e in plan.lemmas if e["name_type"] == "praenomen")
    s["distinct_lemmas:gentilicium"] = sum(
        1 for e in plan.lemmas if e["name_type"] == "gentilicium"
    )
    s["lemmas_attested_twice_or_more"] = sum(1 for e in plan.lemmas if e["attestations"] >= 2)
    return plan


def read_records(conn) -> list[tuple[str, str]]:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    rows = conn.execute(text("SELECT id, canonical FROM inscriptions ORDER BY id"))
    return [(r[0], r[1] or "") for r in rows]


def apply_plan(conn, plan: Plan) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    conn.execute(text("DELETE FROM name_attestations WHERE source = :s"), {"s": SCRIPT_TAG})
    rows = [
        {
            "inscription_id": rid,
            "position": n.position,
            "form": n.form,
            "lemma": n.lemma,
            "name_type": n.name_type,
            "gender": n.gender,
            "basis": n.basis,
            "confidence": n.confidence,
            "source": SCRIPT_TAG,
        }
        for rid, names in plan.names.items()
        for n in names
    ]
    if rows:
        conn.execute(
            text(
                "INSERT INTO name_attestations (inscription_id, position, form, lemma, "
                "name_type, gender, basis, confidence, source) VALUES (:inscription_id, "
                ":position, :form, :lemma, :name_type, :gender, :basis, :confidence, :source)"
            ),
            rows,
        )


def write_reports(plan: Plan, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    with open(outdir / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(dict(sorted(plan.stats.items())), fh, indent=1)
        fh.write("\n")
    with open(outdir / "names.csv", "w", encoding="utf-8", newline="") as fh:
        cols = ["lemma", "name_type", "gender", "confidence", "attestations", "records", "forms"]
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(plan.lemmas)


def make_engine(url: str):
    """Sync engine for the backfill, with batched executemany on psycopg2.

    psycopg2 sends an executemany as one round trip per row, about 99 ms each
    from a laptop to Neon. ``values_plus_batch`` sends 100 statements per round
    trip. That mode leaves ``rowcount`` empty after a batched UPDATE or DELETE;
    apply_plan reads no rowcount.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    kwargs: dict[str, Any] = {}
    if make_url(url).get_driver_name() == "psycopg2":
        kwargs["executemany_mode"] = "values_plus_batch"
    return create_engine(url, **kwargs)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write to the database")
    ap.add_argument("--praenomina", type=Path, default=REFERENCE / "praenomina.csv")
    ap.add_argument("--glosses", type=Path, default=GOLD_GLOSSES)
    ap.add_argument("--report-dir", type=Path, default=None)
    args = ap.parse_args()
    lex = load_lexicon(args.praenomina, args.glosses)

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    engine = make_engine(url)
    with engine.begin() as conn:
        plan = build_plan(read_records(conn), lex)
        if args.apply:
            apply_plan(conn, plan)
    for k, v in sorted(plan.stats.items()):
        print(f"{k:42} {v:>7}")
    if args.report_dir:
        write_reports(plan, args.report_dir)
        print(f"reports in {args.report_dir}")
    print("applied" if args.apply else "dry run: nothing written (use --apply)")


if __name__ == "__main__":
    main()
