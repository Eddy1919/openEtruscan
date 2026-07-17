"""Pin the normalizer's output on the shared golden fixture.

tests/fixtures/normalizer_golden.json is the cross-implementation parity
contract: the same file is consumed by the TypeScript engine's vitest suite
in the openEtruscan-frontend repo (lib/__fixtures__/). The Python package is
the source of truth — regenerate the fixture from here (never hand-edit) and
copy it to the frontend when normalization behavior changes deliberately.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openetruscan import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "normalizer_golden.json"
CASES = json.loads(FIXTURE.read_text())


@pytest.mark.parametrize("case", CASES, ids=[c["input"] for c in CASES])
def test_golden(case):
    result = normalize(case["input"])
    got = result.to_dict()
    for field, expected in case["expected"].items():
        assert got[field] == expected, (
            f"{field} drifted for {case['input']!r} — if this change is "
            f"deliberate, regenerate the fixture AND sync it to the frontend"
        )
