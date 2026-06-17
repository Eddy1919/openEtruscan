#!/usr/bin/env python3
"""
Import a Recogito annotation export and harvest two things.

1. **Place links** — PLACE annotations resolved to a Pleiades URI become
   findspot → Pleiades-ID proposals, written in the same queue format
   propose_pleiades_links.py emits, so they flow through the existing
   review_pleiades_links.py HITL step into data/pleiades_mapping.yaml. Recogito
   thus becomes a second, human-curated source of place links.
2. **Classification decisions** — per-document TAGS become the philologist's
   adjudication decision, written as a CSV (id, decision_tags).

    python scripts/research/import_recogito.py \
        --export /tmp/recogito_annotations.csv \
        --links-out data/pleiades_link_queue.jsonl \
        --decisions-out /tmp/adjudicated.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from openetruscan.core.recogito import (  # noqa: E402
    extract_pleiades_links,
    extract_tag_decisions,
    parse_recogito_csv,
)

PLEIADES_PLACE_URI = "https://pleiades.stoa.org/places/{}"


def write_link_queue(path: Path, links: dict[str, str]) -> int:
    """Append Recogito-harvested place links as pending review rows."""
    with path.open("a", encoding="utf-8") as f:
        for findspot, pid in links.items():
            f.write(
                json.dumps(
                    {
                        "findspot": findspot,
                        "status": "pending",
                        "source": "recogito",
                        "candidates": [
                            {
                                "pleiades_id": pid,
                                "title": "",
                                "score": 1.0,
                                "matched_name": findspot,
                                "uri": PLEIADES_PLACE_URI.format(pid),
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    return len(links)


def write_decisions(path: Path, decisions: dict[str, list[str]]) -> int:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "decision_tags"])
        for file_id, tags in decisions.items():
            writer.writerow([file_id, "|".join(tags)])
    return len(decisions)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--export", type=Path, required=True, help="Recogito annotation CSV export.")
    ap.add_argument(
        "--links-out", type=Path, help="Append harvested place links here (queue JSONL)."
    )
    ap.add_argument("--decisions-out", type=Path, help="Write classification decisions CSV here.")
    args = ap.parse_args()

    annotations = parse_recogito_csv(args.export.read_text(encoding="utf-8"))
    print(f"Parsed {len(annotations)} annotations.")

    links = extract_pleiades_links(annotations)
    decisions = extract_tag_decisions(annotations)
    print(f"Harvested {len(links)} place links, {len(decisions)} document decisions.")

    if args.links_out and links:
        n = write_link_queue(args.links_out, links)
        print(f"Appended {n} place links to {args.links_out}")
        print("Review them: python scripts/data_pipeline/review_pleiades_links.py")
    if args.decisions_out and decisions:
        n = write_decisions(args.decisions_out, decisions)
        print(f"Wrote {n} decisions to {args.decisions_out}")


if __name__ == "__main__":
    main()
