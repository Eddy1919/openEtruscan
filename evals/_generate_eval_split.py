#!/usr/bin/env python3
"""Generate the deterministic train/test split for rosetta_eval_pairs.py.

This script was run ONCE to produce the split assignments that are now
hardcoded in ``rosetta_eval_pairs.py``. It is kept in the repo for
reproducibility — anyone can verify the split by running::

    python evals/_generate_eval_split.py

and comparing the output to the ``split`` values in ``rosetta_eval_pairs.py``.

Algorithm
---------
1. Group all 61 pairs by (category, confidence) strata.
2. Within each stratum, shuffle deterministically with seed=20260510.
3. Assign floor(n × 22/61) pairs to test (min 1 per stratum).
4. Distribute remaining test slots to the largest strata until
   exactly 22 test pairs are reached.
5. Remaining pairs go to train (39).

This yields train=39, test=22 with every category having ≥1 pair in
both splits.
"""

from __future__ import annotations

import math
import random
import sys
from collections import defaultdict
from pathlib import Path

# Import the pairs without the split field (we're generating it).
sys.path.insert(0, str(Path(__file__).parent))

SEED = 20260510
TARGET_TEST = 22
TOTAL = 61


def main() -> None:
    from rosetta_eval_pairs import EVAL_PAIRS

    # Group by (category, confidence)
    strata: dict[tuple[str, str], list[int]] = defaultdict(list)
    for idx, pair in enumerate(EVAL_PAIRS):
        strata[(pair.category, pair.confidence)].append(idx)

    rng = random.Random(SEED)

    # Pass 1: floor allocation
    test_allocations: dict[tuple[str, str], int] = {}
    for key, indices in sorted(strata.items()):
        n_test = max(1, math.floor(len(indices) * TARGET_TEST / TOTAL))
        test_allocations[key] = n_test

    # Pass 2: distribute remaining test slots
    total_test = sum(test_allocations.values())
    if total_test < TARGET_TEST:
        deficit = TARGET_TEST - total_test
        sorted_keys = sorted(strata.keys(), key=lambda k: (-len(strata[k]), k))
        for key in sorted_keys:
            if deficit <= 0:
                break
            if test_allocations[key] < len(strata[key]) - 1:
                test_allocations[key] += 1
                deficit -= 1

    # Generate assignments
    split_map: dict[int, str] = {}
    for key, indices in sorted(strata.items()):
        shuffled = list(indices)
        rng.shuffle(shuffled)
        n_test = test_allocations[key]
        for i, idx in enumerate(shuffled):
            split_map[idx] = "test" if i < n_test else "train"

    # Report
    train_count = sum(1 for v in split_map.values() if v == "train")
    test_count = sum(1 for v in split_map.values() if v == "test")
    print(f"train={train_count} test={test_count}")

    cat_splits: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for idx, pair in enumerate(EVAL_PAIRS):
        cat_splits[pair.category][split_map[idx]] += 1

    for cat, splits in sorted(cat_splits.items()):
        print(f"  {cat}: train={splits.get('train', 0)} test={splits.get('test', 0)}")

    print()
    for idx in sorted(split_map.keys()):
        pair = EVAL_PAIRS[idx]
        print(f'  {idx:2d} {pair.etr:12s} → {pair.lat:14s} [{pair.category:10s} {pair.confidence:6s}] {split_map[idx]}')


if __name__ == "__main__":
    main()
