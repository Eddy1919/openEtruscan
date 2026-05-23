"""Classification metrics for Stream A.

All metrics consume a sequence of (gold_label, predicted_label) tuples. They
return floats so the bootstrap harness can wrap them directly.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

CLASSES: tuple[str, ...] = (
    "funerary",
    "ownership",
    "dedicatory",
    "votive",
    "legal",
    "boundary",
    "commercial",
)


def _per_class_prf(rows: Sequence[tuple[str, str]], cls: str) -> tuple[float, float, float]:
    tp = sum(1 for g, p in rows if g == cls and p == cls)
    fp = sum(1 for g, p in rows if g != cls and p == cls)
    fn = sum(1 for g, p in rows if g == cls and p != cls)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def macro_f1(rows: Sequence[tuple[str, str]]) -> float:
    """Unweighted mean of per-class F1 over the 7 classes."""
    return sum(_per_class_prf(rows, c)[2] for c in CLASSES) / len(CLASSES)


def accuracy(rows: Sequence[tuple[str, str]]) -> float:
    if not rows:
        return 0.0
    return sum(1 for g, p in rows if g == p) / len(rows)


def head2_f1(rows: Sequence[tuple[str, str]]) -> float:
    """F1 on the two head classes (funerary, ownership) only."""
    head = ("funerary", "ownership")
    f1s = [_per_class_prf(rows, c)[2] for c in head]
    return sum(f1s) / len(f1s)


def tail5_f1(rows: Sequence[tuple[str, str]]) -> float:
    """F1 on the five tail classes."""
    tail = tuple(c for c in CLASSES if c not in ("funerary", "ownership"))
    f1s = [_per_class_prf(rows, c)[2] for c in tail]
    return sum(f1s) / len(f1s)


def confusion_matrix(rows: Sequence[tuple[str, str]]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = {g: {p: 0 for p in CLASSES} for g in CLASSES}
    for gold, pred in rows:
        if gold in matrix and pred in matrix[gold]:
            matrix[gold][pred] += 1
    return matrix


def per_class_report(rows: Sequence[tuple[str, str]]) -> dict[str, dict[str, float]]:
    report: dict[str, dict[str, float]] = {}
    counts = Counter(g for g, _ in rows)
    for c in CLASSES:
        p, r, f = _per_class_prf(rows, c)
        report[c] = {
            "precision": p,
            "recall": r,
            "f1": f,
            "support": float(counts.get(c, 0)),
        }
    return report
