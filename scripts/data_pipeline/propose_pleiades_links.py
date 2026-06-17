#!/usr/bin/env python3
"""
Propose findspot → Pleiades links for human review.

Reads the local gazetteer built by ``build_pleiades_gazetteer.py``, gathers the
corpus findspot strings that don't yet have a Pleiades link, fuzzy-matches each
against the gazetteer (see ``openetruscan.core.gazetteer``), and writes a review
queue. ``review_pleiades_links.py`` then walks that queue with a human.

Findspot sources (pick one):
  --findspots-file PATH   newline-delimited findspot strings (offline; testable)
  --from-db               distinct `inscriptions.findspot` where pleiades_id IS NULL
                          (needs DATABASE_URL)

Findspots already present in ``data/pleiades_mapping.yaml`` are skipped, so the
queue only ever contains *new* work.

    python scripts/data_pipeline/propose_pleiades_links.py --from-db
    python scripts/data_pipeline/propose_pleiades_links.py \
        --findspots-file /tmp/findspots.txt --threshold 0.84
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from openetruscan.core.gazetteer import (  # noqa: E402
    GazetteerPlace,
    propose_links,
)

DEFAULT_GAZETTEER = REPO_ROOT / "data" / "pleiades_gazetteer.json"
DEFAULT_MAPPING = REPO_ROOT / "data" / "pleiades_mapping.yaml"
DEFAULT_QUEUE = REPO_ROOT / "data" / "pleiades_link_queue.jsonl"


def load_gazetteer(path: Path) -> list[GazetteerPlace]:
    if not path.exists():
        sys.exit(f"Gazetteer not found: {path}\nRun build_pleiades_gazetteer.py first.")
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [
        GazetteerPlace(
            pleiades_id=r["pleiades_id"],
            title=r.get("title", ""),
            names=tuple(r.get("names", ())),
            lat=r.get("lat"),
            lon=r.get("lon"),
        )
        for r in rows
    ]


def load_existing_mapping(path: Path) -> set[str]:
    if not path.exists():
        return set()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k) for k, v in raw.items() if v}


def findspots_from_file(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip()]


async def findspots_from_db() -> list[str]:
    from sqlalchemy import text

    from openetruscan.db.session import get_engine

    _, session_maker = get_engine()
    async with session_maker() as session:
        result = await session.execute(
            text(
                "SELECT DISTINCT findspot FROM inscriptions "
                "WHERE findspot IS NOT NULL AND findspot <> '' "
                "AND pleiades_id IS NULL ORDER BY findspot"
            )
        )
        return [row[0] for row in result.fetchall()]


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--findspots-file", type=Path, help="Newline-delimited findspots.")
    src.add_argument("--from-db", action="store_true", help="Pull unlinked findspots from the DB.")
    ap.add_argument("--gazetteer", type=Path, default=DEFAULT_GAZETTEER)
    ap.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    ap.add_argument("--output", type=Path, default=DEFAULT_QUEUE)
    ap.add_argument("--threshold", type=float, default=0.84, help="Min match score (default 0.84).")
    ap.add_argument("--top-k", type=int, default=3, help="Max candidates per findspot.")
    ap.add_argument(
        "--include-empty",
        action="store_true",
        help="Also queue findspots with no candidate (so reviewers can mark 'no place').",
    )
    args = ap.parse_args()

    gazetteer = load_gazetteer(args.gazetteer)
    already = load_existing_mapping(args.mapping)

    if args.from_db:
        findspots = asyncio.run(findspots_from_db())
    else:
        findspots = findspots_from_file(args.findspots_file)

    todo = [fs for fs in dict.fromkeys(findspots) if fs not in already]
    print(f"{len(findspots)} findspots, {len(todo)} need linking ({len(already)} already mapped).")

    proposals = propose_links(todo, gazetteer, threshold=args.threshold, top_k=args.top_k)

    written = 0
    with args.output.open("w", encoding="utf-8") as f:
        for p in proposals:
            if not p.candidates and not args.include_empty:
                continue
            f.write(
                json.dumps(
                    {
                        "findspot": p.findspot,
                        "status": "pending",
                        "candidates": [
                            {
                                "pleiades_id": c.pleiades_id,
                                "title": c.title,
                                "score": c.score,
                                "matched_name": c.matched_name,
                                "uri": c.uri,
                            }
                            for c in p.candidates
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            written += 1

    matched = sum(1 for p in proposals if p.candidates)
    print(f"Proposed candidates for {matched}/{len(todo)} findspots.")
    print(f"Wrote {written} queue rows to {args.output}")
    print("Next: python scripts/data_pipeline/review_pleiades_links.py")


if __name__ == "__main__":
    main()
