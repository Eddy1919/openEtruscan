#!/usr/bin/env python3
"""
Human-in-the-loop review of proposed findspot → Pleiades links.

Walks the queue produced by ``propose_pleiades_links.py``. For each findspot it
shows the ranked Pleiades candidates; the reviewer accepts one, rejects all, or
skips. Accepted links are appended to ``data/pleiades_mapping.yaml`` — the same
file ``openetruscan.api.lod.get_pleiades_uri`` reads — so every approval
immediately becomes Pelagios-emittable linked data.

The queue is rewritten on quit with the unreviewed rows, so the loop is
resumable. Approved/rejected rows drop out.

    python scripts/data_pipeline/review_pleiades_links.py

Keys:  [1..N] accept that candidate   [n] none/reject   [s] skip   [q] save & quit
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_QUEUE = REPO_ROOT / "data" / "pleiades_link_queue.jsonl"
DEFAULT_MAPPING = REPO_ROOT / "data" / "pleiades_mapping.yaml"


def load_queue(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def write_queue(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def append_mapping(path: Path, findspot: str, pleiades_id: str) -> None:
    """Append/update one findspot→id entry, preserving existing content."""
    existing = {}
    if path.exists():
        existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    existing[findspot] = str(pleiades_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(existing, allow_unicode=True, sort_keys=True), encoding="utf-8")


def main() -> None:
    queue_path = DEFAULT_QUEUE
    mapping_path = DEFAULT_MAPPING

    rows = [r for r in load_queue(queue_path) if r.get("status") == "pending"]
    if not rows:
        print(f"No pending rows in {queue_path}. Nothing to review.")
        return

    print("=" * 60)
    print(" FINDSPOT → PLEIADES REVIEW")
    print(f" {len(rows)} findspots pending")
    print(" [1..N] accept candidate  [n] reject  [s] skip  [q] save & quit")
    print("=" * 60)

    remaining: list[dict] = []
    approved = rejected = 0

    for i, row in enumerate(rows):
        findspot = row["findspot"]
        candidates = row.get("candidates", [])
        print(f"\n[{i + 1}/{len(rows)}] findspot: {findspot!r}")
        if not candidates:
            print("   (no candidate places above threshold)")
        for n, c in enumerate(candidates, start=1):
            print(
                f"   {n}. {c['title']}  (score {c['score']}, "
                f"matched {c['matched_name']!r})  {c['uri']}"
            )

        choice = input("   > ").strip().lower()
        if choice == "q":
            remaining.extend(rows[i:])
            break
        if choice == "s":
            remaining.append(row)
            continue
        if choice == "n" or choice == "":
            rejected += 1
            continue
        if choice.isdigit() and 1 <= int(choice) <= len(candidates):
            picked = candidates[int(choice) - 1]
            append_mapping(mapping_path, findspot, picked["pleiades_id"])
            print(f"   ✓ linked {findspot!r} → {picked['title']} ({picked['pleiades_id']})")
            approved += 1
        else:
            print("   ? unrecognised — skipping this one")
            remaining.append(row)

    write_queue(queue_path, remaining)
    print(f"\nDone. Approved {approved}, rejected {rejected}, {len(remaining)} left in queue.")
    if approved:
        print(f"Updated {mapping_path}. These now emit as Pelagios place links.")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nInterrupted — queue left unchanged from last save.")
        sys.exit(130)
