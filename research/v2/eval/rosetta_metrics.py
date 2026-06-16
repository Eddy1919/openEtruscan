"""Rosetta-eval-v2 metrics.

Inputs: a list of "scored retrieval" records. Each record is

    {
      "etruscan_word": "...",
      "gold_equivalent": "...",
      "gold_category": "kinship",
      "top_k_predictions": ["..", "..", ...],   # length ≥ K
    }

The metrics consume such records and return floats so the bootstrap harness
can wrap them.
"""

from __future__ import annotations

import json
from pathlib import Path
from collections.abc import Sequence


def precision_at_k(rows: Sequence[dict], k: int) -> float:
    if not rows:
        return 0.0
    hits = 0
    for row in rows:
        topk = row.get("top_k_predictions", [])[:k]
        if row["gold_equivalent"] in topk:
            hits += 1
    return hits / len(rows)


def reciprocal_rank(rows: Sequence[dict]) -> float:
    if not rows:
        return 0.0
    total = 0.0
    for row in rows:
        try:
            idx = row.get("top_k_predictions", []).index(row["gold_equivalent"])
            total += 1.0 / (idx + 1)
        except ValueError:
            continue
    return total / len(rows)


def load_semantic_fields(path: Path) -> dict[str, set[str]]:
    """Load the frozen semantic-field vocabularies."""
    data = json.loads(path.read_text())
    return {cat: set(words) for cat, words in data.items()}


def make_semantic_field_pk(semantic_fields: dict[str, set[str]], k: int):
    """Return a metric_fn that does P@k under the semantic-field relaxation.

    A retrieval hit iff any token in top_k appears in the gold-pair's
    semantic-field vocabulary. The semantic_fields dict is frozen at the
    freeze commit — it does NOT get edited based on observed misses.
    """

    def metric(rows: Sequence[dict]) -> float:
        if not rows:
            return 0.0
        hits = 0
        for row in rows:
            cat = row.get("gold_category", "")
            vocab = semantic_fields.get(cat, set())
            if not vocab:
                # No vocabulary for this category — fall back to exact match
                if row["gold_equivalent"] in row.get("top_k_predictions", [])[:k]:
                    hits += 1
                continue
            topk = set(row.get("top_k_predictions", [])[:k])
            if topk & vocab:
                hits += 1
        return hits / len(rows)

    return metric
