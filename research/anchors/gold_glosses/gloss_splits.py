"""Deterministic train / silver-eval assignment for gold-gloss records.

Single source of truth for which records the hybrid_embed WP10 models trained
on (`gg_train`) and which form the silver word-level eval (`gg_silver`).
`research/experiments/hybrid_embed/build_gloss_pairs.py` and
`verification_queue.py` both read it, so the worksheet a human verifies and
the split the models saw can't drift apart.

Rules (unchanged from WP10):
  * usable records: status llm_checked or verified (seeded and rejected stay out)
  * surfaces are compared after stripping a trailing hyphen; first record wins
  * sha1(surface) % 10 < 8 -> training bucket, else silver-eval bucket
  * training never takes a rosetta TEST word; the silver eval takes no rosetta
    word from either split
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

USABLE_STATUSES = frozenset({"llm_checked", "verified"})

GG_TRAIN = "gg_train"
GG_SILVER = "gg_silver"
ROSETTA_TEST = "rosetta_test"  # spoken for by the frozen benchmark
ROSETTA_TRAIN_OVERLAP = "rosetta_train_overlap"  # silver bucket, but a rosetta word
DUPLICATE_SURFACE = "duplicate_surface"
EMPTY = "empty"
NOT_USABLE = "not_usable"  # seeded or rejected


def clean_surface(etr: str) -> str:
    return etr.rstrip("-").strip()


def gloss_head(gloss_en: str) -> str:
    """First sense of a gloss, without parenthetical comments."""
    return gloss_en.split("(")[0].strip().rstrip(",;")


def in_train_bucket(surface: str) -> bool:
    return int(hashlib.sha1(surface.encode()).hexdigest(), 16) % 10 < 8


def assign_splits(
    records: Iterable[dict], test_etr: set[str], train_etr: set[str]
) -> dict[str, str]:
    """Map each record's raw `etr` to its split label, in file order."""
    out: dict[str, str] = {}
    seen: set[str] = set()
    for r in records:
        etr = r["etr"]
        if etr in out:
            raise ValueError(f"duplicate etr {etr!r}; validate.py requires one record per form")
        if r["adjudication"]["status"] not in USABLE_STATUSES:
            out[etr] = NOT_USABLE
            continue
        surface = clean_surface(etr)
        if not surface:
            out[etr] = EMPTY
            continue
        if surface in seen:
            out[etr] = DUPLICATE_SURFACE
            continue
        seen.add(surface)  # before the gloss check, as WP10 did
        if not gloss_head(r["gloss_en"]):
            out[etr] = EMPTY
            continue
        if surface in test_etr:
            out[etr] = ROSETTA_TEST
        elif in_train_bucket(surface):
            out[etr] = GG_TRAIN
        elif surface in train_etr:
            out[etr] = ROSETTA_TRAIN_OVERLAP
        else:
            out[etr] = GG_SILVER
    return out
