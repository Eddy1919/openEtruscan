"""Measure train/test text-level contamination in a frozen classification split.

An id-disjoint split is not a clean split. Where one inscription text carries
several ids — `mi`, `suθina`, `aplu` and other short formulaic items recur
across genuinely distinct artifacts — the model can meet the exact test string,
under its own label, during training.

This tool reports that overlap so the number is measured rather than assumed.
`classify_split.py` now prevents the leak at generation time; this exists to
audit splits frozen before that guard, and to keep the figure honest in CI.

Usage
-----
    python -m research.v2.eval.split_contamination \\
        --train research/v2/data/classify_train_pool.jsonl \\
        --test  research/v2/data/classify_test_v2.jsonl \\
        --queue research/v2/handoff/v2.0-etr/adjudication_queue.csv

Exit status is 1 when any leak is found. It is a manual audit tool; the
committed split's disjointness is separately pinned by classify_split.py's
own guard and by tests/test_v2_harness.py. Pass `--expect N` to accept a
known, documented leak of exactly N rows (the superseded v2.0.2 split was
25; see PRE_REGISTRATION.md Deviation D).

The `--queue` argument is optional and answers a sharper question than the
headline percentage. The published metric is computed on the *unanimous*
candidate-gold subset, not the full test pool, so what matters is whether the
leak concentrates there. The adjudication queue holds the rows the jury did
NOT agree on. Leaked rows landing in the queue at below their expected rate
means they are enriched in the unanimous set that carries the metric.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from research.v2.pipelines.classify_split import text_key


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _tokens(text: str) -> list[str]:
    for sep in ":.•·|/,":
        text = text.replace(sep, " ")
    return text.split()


def find_leaks(train: list[dict[str, Any]], test: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Test rows whose normalized text also appears in the train pool."""
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in train:
        key = text_key(row.get("canonical_transliterated", ""))
        if key:
            by_key[key].append(row)

    leaks = []
    for row in test:
        key = text_key(row.get("canonical_transliterated", ""))
        twins = by_key.get(key) if key else None
        if not twins:
            continue
        label = row.get("silver_label", "")
        leaks.append(
            {
                "id": row.get("id", ""),
                "text": row.get("canonical_transliterated", ""),
                "label": label,
                "twin_ids": [t.get("id", "") for t in twins],
                "same_label": any(t.get("silver_label") == label for t in twins),
                "single_token": len(_tokens(row.get("canonical_transliterated", ""))) == 1,
            }
        )
    return leaks


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--train", type=Path, required=True)
    ap.add_argument("--test", type=Path, required=True)
    ap.add_argument(
        "--queue",
        type=Path,
        help="Adjudication-queue CSV (jury non-unanimous rows), for the "
        "enrichment check described in this module's docstring.",
    )
    ap.add_argument(
        "--expect",
        type=int,
        help="Accept exactly this many leaked rows and exit 0. For splits "
        "with a known, documented leak.",
    )
    args = ap.parse_args(argv)

    train, test = _load_jsonl(args.train), _load_jsonl(args.test)
    leaks = find_leaks(train, test)
    n = len(leaks)

    print(f"train={len(train)}  test={len(test)}")
    print(
        f"leaked test rows (normalized text also in train): {n}/{len(test)} "
        f"({100 * n / len(test):.1f}%)"
        if test
        else "empty test pool"
    )
    if not n:
        print("clean: no text-level overlap")
        return 0

    same = sum(1 for leak in leaks if leak["same_label"])
    single = sum(1 for leak in leaks if leak["single_token"])
    print(f"  ...twin carries the same label (free correct answer): {same}")
    print(f"  ...single-token rows: {single} ({100 * single / n:.0f}%)")

    print("\nper class (leaked / test n):")
    test_n = Counter(r.get("silver_label", "") for r in test)
    leak_n = Counter(leak["label"] for leak in leaks)
    for label, total in test_n.most_common():
        got = leak_n.get(label, 0)
        print(f"  {label:<12}{got:>4} /{total:>4}   {100 * got / total:>5.1f}%")

    if args.queue and args.queue.exists():
        queue_ids = {r["id"] for r in csv.DictReader(args.queue.open())}
        in_queue = sum(1 for leak in leaks if leak["id"] in queue_ids)
        expected = n * len(queue_ids) / len(test)
        print(
            f"\nenrichment check: {in_queue} leaked row(s) fell in the "
            f"{len(queue_ids)}-row non-unanimous queue; {expected:.1f} expected "
            f"if the leak were spread evenly."
        )
        if in_queue < expected:
            print(
                "  => the leak is concentrated in the rows the jury agreed on, "
                "i.e. enriched in the candidate-gold set that carries the "
                "published metric."
            )

    print("\nleaked rows:")
    for leak in sorted(leaks, key=lambda x: x["text"]):
        mark = "=" if leak["same_label"] else "~"
        print(
            f"  {leak['id']:>10}  {leak['text'][:34]:<34} {mark}{leak['label']:<12} "
            f"twins={leak['twin_ids'][:3]}"
        )

    if args.expect is not None and n == args.expect:
        print(f"\nleak of {n} matches the documented --expect value; exiting 0.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
