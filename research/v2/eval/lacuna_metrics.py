"""Lacuna-restoration metrics for Stream C.

Inputs: a list of records each shaped like

    {
      "id": "...",
      "gold_lacuna": "papas",
      "restored_lacuna": "papan",
      "hallucinated": False,
      "width": 5,
      "width_bucket": "w4_6",
    }

These records are produced by `pipelines/lacuna_jury.py`. Each metric
function returns a float so the bootstrap harness can wrap it directly.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

BUCKETS = ("w1", "w2_3", "w4_6", "w7_plus")

# Trailing-dash markers: editor convention for "more destroyed text continues
# here". Anything containing `---` (or 2+ consecutive dashes) is unscoreable
# because the gold itself encodes uncertainty about what's missing.
_HAS_DASH_MARKER = re.compile(r"-{2,}")

# Arabic digits in gold are editorial line-number annotations, not actual
# Etruscan characters. Etruscan numerals are Roman-style letters.
_HAS_DIGITS = re.compile(r"\d")


def is_clean_gold(row: dict) -> bool:
    """Return True iff the row's gold_lacuna is suitable for scoring.

    Excluded:
      - gold containing `---` (unknown continuation marker)
      - gold containing Arabic digits (editorial line/section markers)
      - gold that is empty
    Catches the v2.0 mining false-positives surfaced on 2026-05-20.
    """
    gold = (row.get("gold_lacuna") or "").strip()
    if not gold:
        return False
    if _HAS_DASH_MARKER.search(gold):
        return False
    if _HAS_DIGITS.search(gold):
        return False
    return True


def filter_clean(rows: Sequence[dict]) -> list[dict]:
    """Drop rows whose gold isn't suitable for scoring (see is_clean_gold)."""
    return [r for r in rows if is_clean_gold(r)]


def char_acc_top1(rows: Sequence[dict]) -> float:
    """Mean per-row character accuracy on the lacuna span."""
    if not rows:
        return 0.0
    totals = 0.0
    for row in rows:
        gold = row.get("gold_lacuna", "")
        pred = row.get("restored_lacuna", "")
        if not gold:
            continue
        n = max(len(gold), 1)
        matches = sum(1 for i in range(min(len(gold), len(pred))) if gold[i] == pred[i])
        totals += matches / n
    return totals / len(rows)


def span_exact_match(rows: Sequence[dict]) -> float:
    if not rows:
        return 0.0
    hits = sum(1 for r in rows if r.get("restored_lacuna", "") == r.get("gold_lacuna", ""))
    return hits / len(rows)


def hallucination_rate(rows: Sequence[dict]) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if r.get("hallucinated")) / len(rows)


def char_acc_top3(rows: Sequence[dict]) -> float:
    """Per-row char accuracy where a position is a hit if any of top-3 matches.

    "Top-3" means: per row, restored_lacuna or any of the (up to three)
    restored_alternates is checked at each position. The position scores 1 if
    any of those candidates' char-at-position matches gold's char.
    """
    if not rows:
        return 0.0
    totals = 0.0
    for row in rows:
        gold = row.get("gold_lacuna", "")
        if not gold:
            continue
        cands = [row.get("restored_lacuna", "")]
        cands.extend(row.get("restored_alternates", [])[:2])
        n = max(len(gold), 1)
        matches = 0
        for i, ch in enumerate(gold):
            if any(i < len(c) and c[i] == ch for c in cands):
                matches += 1
        totals += matches / n
    return totals / len(rows)


def per_bucket_breakdown(rows: Sequence[dict]) -> dict[str, dict[str, float]]:
    """Return per-width-bucket metrics."""
    out: dict[str, dict[str, float]] = {}
    for bucket in BUCKETS:
        sub = [r for r in rows if r.get("width_bucket") == bucket]
        out[bucket] = {
            "n": float(len(sub)),
            "char_acc_top1": char_acc_top1(sub),
            "char_acc_top3": char_acc_top3(sub),
            "span_exact": span_exact_match(sub),
            "hallucination_rate": hallucination_rate(sub),
        }
    return out
