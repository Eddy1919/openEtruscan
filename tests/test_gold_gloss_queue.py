"""Tests for the gold-gloss verification worksheet and the shared split rules.

The worksheet is the only path by which a human verdict reaches
gold_glosses.jsonl, and its audit tier is the sample the llm_checked error
rate is estimated from. Both properties are pinned here:

  1. the shared split rules reproduce the WP10 split the models trained on,
  2. tiers and order don't move when verdicts land, gloss corrections included,
  3. `apply` writes nothing unless every filled row is valid, and is idempotent,
  4. `build` refuses to overwrite verdicts that were not applied yet,
  5. `report` counts a corrected gloss as an llm_checked error.
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

import pytest

pytest.importorskip("scipy")

REPO_ROOT = Path(__file__).resolve().parent.parent
GG_DIR = REPO_ROOT / "research/anchors/gold_glosses"
sys.path.insert(0, str(GG_DIR))

import gloss_splits  # noqa: E402
import verification_queue as vq  # noqa: E402


@pytest.fixture(scope="module")
def rosetta() -> tuple[set[str], set[str]]:
    return vq.rosetta_sets()


@pytest.fixture()
def records() -> list[dict]:
    return vq.load_records()


def test_splits_reproduce_wp10_counts(records, rosetta):
    # status-independent view: verdicts landing later must not break this test
    splits = vq.population_splits(records, *rosetta)
    counts = {label: list(splits.values()).count(label) for label in set(splits.values())}
    # WP10 (hybrid_embed/README.md): 221 training pairs, 71-item silver eval
    assert counts[gloss_splits.GG_TRAIN] == 221
    assert counts[gloss_splits.GG_SILVER] == 71


def test_verified_records_stay_usable(rosetta):
    rec = {"etr": "zzqa", "gloss_en": "test", "adjudication": {"status": "verified"}}
    assert gloss_splits.assign_splits([rec], *rosetta)["zzqa"] in {
        gloss_splits.GG_TRAIN,
        gloss_splits.GG_SILVER,
    }
    rec["adjudication"]["status"] = "rejected"
    assert gloss_splits.assign_splits([rec], *rosetta)["zzqa"] == gloss_splits.NOT_USABLE


def test_tiers_are_stable_under_verdicts(records, rosetta):
    before = [(t, r["etr"]) for t, r in vq.assign_tiers(records, *rosetta)]
    audit = [etr for t, etr in before if t == "audit"]
    seeded = [etr for t, etr in before if t == "seeded"]
    by_etr = {r["etr"]: r for r in records}
    for etr in audit[:3]:
        by_etr[etr]["adjudication"] = {"status": "rejected", "by": "t", "date": "2026-01-01"}
    for etr in audit[3:8] + seeded[:1]:
        by_etr[etr]["adjudication"] = {"status": "verified", "by": "t", "date": "2026-01-01"}
    by_etr[audit[3]]["gloss_en"] = "(divine name) Tinia"  # a correction with a comment first
    after = [(t, r["etr"]) for t, r in vq.assign_tiers(records, *rosetta)]
    assert after == before


def test_tiers_cover_every_record_once(records, rosetta):
    tiered = vq.assign_tiers(records, *rosetta)
    assert sorted(r["etr"] for _, r in tiered) == sorted(r["etr"] for r in records)
    assert sum(t == "audit" for t, _ in tiered) == vq.AUDIT_N


def _fill(worksheet: Path, fills: dict[str, dict[str, str]]) -> None:
    with worksheet.open() as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0])
    for row in rows:
        row.update(fills.get(row["etr"], {}))
    with worksheet.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def test_apply_round_trip(tmp_path, records, rosetta):
    glosses = tmp_path / "gold_glosses.jsonl"
    shutil.copy(vq.GLOSSES, glosses)
    worksheet = tmp_path / "queue.csv"
    assert vq.build(worksheet, records, *rosetta, force=False) == 0

    tiered = vq.assign_tiers(records, *rosetta)
    ok, bad = tiered[0][1]["etr"], tiered[1][1]["etr"]
    original = glosses.read_text()

    # one valid row plus one rejection without a reason: nothing may be written
    _fill(
        worksheet,
        {
            ok: {
                "verdict": "verified",
                "corrected_gloss": "corrected sense",
                "verified_by": "A. Philologist",
                "verified_date": "2026-11-24",
            },
            bad: {"verdict": "rejected", "verified_by": "A. P.", "verified_date": "2026-11-24"},
        },
    )
    assert vq.apply(worksheet, glosses) == 1
    assert glosses.read_text() == original

    _fill(worksheet, {bad: {"verifier_notes": "locus does not support the gloss"}})
    assert vq.apply(worksheet, glosses) == 0
    after = {r["etr"]: r for r in vq.load_records(glosses)}
    assert after[ok]["adjudication"] == {
        "status": "verified",
        "by": "A. Philologist",
        "date": "2026-11-24",
    }
    assert after[ok]["gloss_en"] == "corrected sense"
    assert "gloss corrected at verification (was:" in after[ok]["notes"]
    assert after[bad]["adjudication"]["status"] == "rejected"
    assert "rejected at verification: locus does not support" in after[bad]["notes"]
    # every other record is byte-identical
    before_lines = [ln for ln in original.splitlines() if json.loads(ln)["etr"] not in {ok, bad}]
    after_lines = [
        ln for ln in glosses.read_text().splitlines() if json.loads(ln)["etr"] not in {ok, bad}
    ]
    assert before_lines == after_lines


def test_apply_is_idempotent_and_build_accepts_applied_rows(
    tmp_path, records, rosetta, monkeypatch
):
    glosses = tmp_path / "gold_glosses.jsonl"
    shutil.copy(vq.GLOSSES, glosses)
    monkeypatch.setattr(vq, "GLOSSES", glosses)
    worksheet = tmp_path / "queue.csv"
    vq.build(worksheet, records, *rosetta, force=False)
    first = vq.assign_tiers(records, *rosetta)[0][1]["etr"]
    _fill(
        worksheet,
        {
            first: {
                "verdict": "verified",
                "verified_by": "A. P.",
                "verified_date": "2026-11-24",
                "verifier_notes": "ok",
            }
        },
    )
    # an unapplied verdict blocks a rebuild
    assert vq.build(worksheet, vq.load_records(glosses), *rosetta, force=False) == 1
    assert vq.apply(worksheet, glosses) == 0
    once = glosses.read_text()
    assert vq.apply(worksheet, glosses) == 0
    assert glosses.read_text() == once  # notes not appended twice
    # once applied, the same row no longer blocks a rebuild
    assert vq.build(worksheet, vq.load_records(glosses), *rosetta, force=False) == 0
    # a correction added after the verdict landed is neither skipped nor lost
    _fill(
        worksheet,
        {
            first: {
                "verdict": "verified",
                "corrected_gloss": "a later sense",
                "verified_by": "A. P.",
                "verified_date": "2026-11-24",
            }
        },
    )
    assert vq.apply(worksheet, glosses) == 1
    assert glosses.read_text() == once
    assert vq.build(worksheet, vq.load_records(glosses), *rosetta, force=False) == 1


def test_apply_rejects_a_correction_without_a_sense(tmp_path, records, rosetta):
    glosses = tmp_path / "gold_glosses.jsonl"
    shutil.copy(vq.GLOSSES, glosses)
    worksheet = tmp_path / "queue.csv"
    vq.build(worksheet, records, *rosetta, force=False)
    first = vq.assign_tiers(records, *rosetta)[0][1]["etr"]
    _fill(
        worksheet,
        {
            first: {
                "verdict": "verified",
                "corrected_gloss": "(uncertain)",
                "verified_by": "A. P.",
                "verified_date": "2026-11-24",
            }
        },
    )
    original = glosses.read_text()
    assert vq.apply(worksheet, glosses) == 1
    assert glosses.read_text() == original


def test_report_counts_corrections_as_errors(records, rosetta, capsys):
    audit = [r for t, r in vq.assign_tiers(records, *rosetta) if t == "audit"]
    done = {"by": "t", "date": "2026-01-01"}
    audit[0]["adjudication"] = {"status": "rejected", **done}
    audit[1]["adjudication"] = {"status": "verified", **done}
    audit[1]["notes"] = f"{vq.CORRECTION_NOTE} (was: x)"
    audit[2]["adjudication"] = {"status": "verified", **done}
    vq.report(records, *rosetta)
    out = capsys.readouterr().out
    assert "audit sample: 3/50 adjudicated" in out
    assert "error rate: 2/3" in out
    assert "1 rejected, 1 verified only after a gloss correction" in out


def test_duplicate_forms_fail_loudly(rosetta):
    recs = [
        {"etr": "zzqa", "gloss_en": "year", "adjudication": {"status": "llm_checked"}},
        {"etr": "zzqa", "gloss_en": "age", "adjudication": {"status": "llm_checked"}},
    ]
    with pytest.raises(ValueError, match="duplicate etr"):
        gloss_splits.assign_splits(recs, *rosetta)


def test_clopper_pearson_known_values():
    lo, hi = vq.clopper_pearson(0, 50)
    assert lo == 0.0
    assert hi == pytest.approx(0.0711, abs=1e-4)
    lo, hi = vq.clopper_pearson(5, 50)
    assert lo == pytest.approx(0.0333, abs=1e-3)
    assert hi == pytest.approx(0.2181, abs=1e-3)


def test_spotcheck_alpha_tracks_rho():
    """Under the simulation model, population α equals ρ (checked at large n)."""
    import random

    sys.path.insert(0, str(REPO_ROOT))
    from research.v2.eval import spotcheck_power as sp

    mix = {"a": 0.4, "b": 0.3, "c": 0.2, "d": 0.1}
    rng = random.Random(0)
    for rho in (0.6, 0.85):
        est = sum(sp.simulate_alpha(mix, rho, 2000, rng) for _ in range(5)) / 5
        assert est == pytest.approx(rho, abs=0.03)
