"""Invariant tests for the research/v2 science harness.

The v2.0.2 lacuna retraction (PRE_REGISTRATION.md Deviation §B) was caused by
a scorer bug — empty API responses counted as hallucinations. In a tiny-n
field one harness bug is a paper-level event, so the invariants that fix was
built on are pinned here permanently:

  1. no_parse / empty responses are NEVER scored as hallucinations,
  2. API errors are missing data, not model abstentions, and never
     contribute to candidate-gold unanimity,
  3. the frozen-split generator refuses to emit text-less rows,
  4. bootstrap statistics are seed-stable,
  5. the two Krippendorff α implementations agree,
  6. the committed evidence files match what the published tables claim.

research/ is an importable package (it ships __init__.py) but lives outside
the installed src/ tree, so the repo root is put on sys.path explicitly —
same approach as test_llm_extract_anchors.py uses for scripts/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from research.v2.eval import bootstrap, lacuna_metrics  # noqa: E402
from research.v2.pipelines import classify_adjudicate, classify_split  # noqa: E402


def _lacuna_row(**overrides):
    row = {
        "id": "x1",
        "model": "m",
        "gold_lacuna": "a",
        "masked": "mi [?] avil",
        "restored_lacuna": "a",
        "restored_full": "mi a avil",
        "hallucinated": False,
        "no_parse": False,
    }
    row.update(overrides)
    return row


class TestNoParseNeverHallucination:
    """The exact bug behind the retracted Finding C, pinned forever."""

    def test_answered_drops_no_parse_rows(self):
        rows = [_lacuna_row(), _lacuna_row(id="x2", no_parse=True, hallucinated=True)]
        kept = lacuna_metrics.answered(rows)
        assert [r["id"] for r in kept] == ["x1"]

    def test_hallucination_rate_excludes_no_parse(self):
        # 1 honest row + 9 no_parse rows flagged hallucinated=True: under the
        # buggy v2.0.2 scorer this read 0.9; the correct rate over answered
        # rows is 0.0.
        rows = [_lacuna_row()] + [
            _lacuna_row(id=f"e{i}", no_parse=True, hallucinated=True) for i in range(9)
        ]
        assert lacuna_metrics.hallucination_rate(lacuna_metrics.answered(rows)) == 0.0

    def test_dirty_gold_is_filtered(self):
        # Trailing dash markers ("more destroyed text continues") and
        # editorial digits are unscoreable and must not enter denominators.
        rows = [
            _lacuna_row(),
            _lacuna_row(id="d1", gold_lacuna="reri---"),
            _lacuna_row(id="d2", gold_lacuna="a2"),
            _lacuna_row(id="d3", gold_lacuna=""),
        ]
        assert [r["id"] for r in lacuna_metrics.filter_clean(rows)] == ["x1"]


class TestApiErrorIsMissingData:
    """classify_jury writes label='api_error' on transport failure; the
    adjudicator must treat it as missing data, never as an abstention."""

    def _jury(self, *labels, confidence="high"):
        return [
            {"model": f"m{i}", "label": lab, "confidence": confidence, "rationale": ""}
            for i, lab in enumerate(labels)
        ]

    def test_unanimous_clean_panel_promotes(self):
        disposition, summary = classify_adjudicate.classify_row(
            self._jury("funerary", "funerary", "funerary")
        )
        assert disposition == "candidate_gold"
        assert summary["n_api_error"] == 0

    def test_api_error_blocks_candidate_gold(self):
        # 2-of-2 agreement over an incomplete panel is not unanimity.
        disposition, summary = classify_adjudicate.classify_row(
            self._jury("funerary", "funerary", "api_error")
        )
        assert disposition == "queue"
        assert summary["n_api_error"] == 1

    def test_all_api_error_routes_to_queue(self):
        disposition, summary = classify_adjudicate.classify_row(
            self._jury("api_error", "api_error", "api_error")
        )
        assert disposition == "queue"
        assert summary["n_raters"] == 0

    def test_api_error_is_not_an_unsure_vote(self):
        # unsure + unsure + api_error is NOT "all raters unsure".
        disposition, _ = classify_adjudicate.classify_row(
            self._jury("unsure", "unsure", "api_error")
        )
        assert disposition == "all_unsure"  # the two real raters were unsure


class TestSplitGeneratorRefusesEmptyText:
    def test_missing_corpus_hard_fails(self, tmp_path):
        silver = tmp_path / "silver.csv"
        silver.write_text(
            "id,label,confidence,signal_source\n"
            "A1,funerary,high,keyword\n"
            "A2,ownership,medium,keyword\n"
        )
        rc = classify_split.main(
            [
                "--corpus",
                str(tmp_path / "does_not_exist.csv"),
                "--silver",
                str(silver),
                "--out-train",
                str(tmp_path / "train.jsonl"),
                "--out-test",
                str(tmp_path / "test.jsonl"),
                "--n-test",
                "1",
            ]
        )
        assert rc == 1
        assert not (tmp_path / "test.jsonl").exists()

    def test_allow_empty_text_flag_permits_smoke_runs(self, tmp_path):
        silver = tmp_path / "silver.csv"
        silver.write_text("id,label,confidence,signal_source\nA1,funerary,high,keyword\n")
        rc = classify_split.main(
            [
                "--corpus",
                str(tmp_path / "does_not_exist.csv"),
                "--silver",
                str(silver),
                "--out-train",
                str(tmp_path / "train.jsonl"),
                "--out-test",
                str(tmp_path / "test.jsonl"),
                "--n-test",
                "1",
                "--allow-empty-text",
            ]
        )
        assert rc == 0

    def test_text_bearing_corpus_passes_and_is_deterministic(self, tmp_path):
        silver = tmp_path / "silver.csv"
        silver.write_text(
            "id,label,confidence,signal_source\n"
            + "".join(f"A{i},funerary,high,keyword\n" for i in range(10))
        )
        corpus = tmp_path / "corpus.csv"
        corpus.write_text(
            "id,raw_text,canonical_transliterated,translation\n"
            + "".join(f"A{i},mi avil {i},mi avil {i},\n" for i in range(10))
        )
        outs = []
        for run in ("a", "b"):
            args = [
                "--corpus",
                str(corpus),
                "--silver",
                str(silver),
                "--out-train",
                str(tmp_path / f"train_{run}.jsonl"),
                "--out-test",
                str(tmp_path / f"test_{run}.jsonl"),
                "--n-test",
                "4",
                "--seed",
                "42",
            ]
            assert classify_split.main(args) == 0
            outs.append((tmp_path / f"test_{run}.jsonl").read_text())
        assert outs[0] == outs[1], "same seed must produce byte-identical splits"
        rows = [json.loads(line) for line in outs[0].splitlines()]
        assert all(r["raw_text"].strip() for r in rows)


class TestBootstrapStability:
    @staticmethod
    def _mean(rows):
        return sum(rows) / len(rows) if rows else 0.0

    def test_same_seed_same_ci(self):
        values = [1.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 0.0, 1.0, 1.0]
        a = bootstrap.bootstrap_ci(values, self._mean, n_resamples=2000, seed=42)
        b = bootstrap.bootstrap_ci(values, self._mean, n_resamples=2000, seed=42)
        assert (a.point, a.ci_low, a.ci_high) == (b.point, b.ci_low, b.ci_high)

    def test_paired_bootstrap_identical_metrics_is_null(self):
        values = [1.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.0]
        res = bootstrap.paired_bootstrap(values, self._mean, self._mean, n_resamples=2000, seed=42)
        assert res.delta_point == 0.0
        assert res.p_value > 0.05

    def test_paired_bootstrap_detects_dominance(self):
        # rows are (a_score, b_score) pairs; metric_a/metric_b project them.
        rows = [(1.0, 0.0)] * 30
        res = bootstrap.paired_bootstrap(
            rows,
            lambda rs: self._mean([r[0] for r in rs]),
            lambda rs: self._mean([r[1] for r in rs]),
            n_resamples=2000,
            seed=42,
        )
        assert res.delta_point == 1.0
        assert res.p_value < 0.05


class TestKrippendorffAlpha:
    def test_perfect_agreement_is_one(self):
        ratings = [["a", "a", "a"], ["b", "b", "b"], ["a", "a", "a"]]
        assert bootstrap.krippendorff_alpha_nominal(ratings) == pytest.approx(1.0)

    def test_handoff_implementation_agrees_with_eval_implementation(self):
        # compute_alpha.py is the dependency-free copy shipped to the
        # philologists; it must return the same α as the eval module.
        import importlib.util

        path = REPO_ROOT / "research/v2/handoff/v2.0-etr/compute_alpha.py"
        spec = importlib.util.spec_from_file_location("compute_alpha", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        ratings = [
            ["funerary", "funerary", "ownership"],
            ["votive", "votive", "votive"],
            ["funerary", "ownership", None],
            ["boundary", "boundary", "boundary"],
            ["ownership", "ownership", "ownership"],
        ]
        assert mod.krippendorff_alpha_nominal(ratings) == pytest.approx(
            bootstrap.krippendorff_alpha_nominal(ratings)
        )


class TestCommittedEvidencePins:
    """The tracked evidence under research/v2/ must keep matching the
    published tables. If these fail, either the evidence or the docs drifted."""

    RESULTS = REPO_ROOT / "research/v2/results/lacuna"
    DATA = REPO_ROOT / "research/v2/data"

    def test_v2_0_3_raw_jury_shape(self):
        rows = [
            json.loads(line)
            for line in (self.RESULTS / "lacuna_jury_raw_v2_0_3_rerun.jsonl").open()
        ]
        assert len(rows) == 210  # 3 raters x 70 unique tasks
        keys = {(r["model"], r["key"]) for r in rows}
        assert len(keys) == 210, "duplicate (model, task) pairs in the evidence file"
        assert {r["model"] for r in rows} == {
            "claude-opus-4-8",
            "gemini-3.1-pro-preview",
            "gemini-3.5-flash",
        }

    def test_v2_0_3_metrics_match_published_tables(self):
        d = json.loads((self.RESULTS / "lacuna_v2_0_3.json").read_text())
        pm = d["per_model"]
        assert pm["claude-opus-4-8"]["span_exact_match"]["point"] == pytest.approx(0.288, abs=5e-4)
        assert pm["gemini-3.1-pro-preview"]["span_exact_match"]["point"] == pytest.approx(
            0.258, abs=5e-4
        )
        assert pm["gemini-3.5-flash"]["hallucination_rate"]["point"] == pytest.approx(
            0.545, abs=5e-4
        )
        assert pm["gemini-3.1-pro-preview"]["hallucination_rate"]["point"] == pytest.approx(
            0.161, abs=5e-4
        )
        assert d["seed"] == 42
        assert d["n_resamples"] == 10_000

    def test_frozen_split_carries_text_and_preregistered_n(self):
        rows = [json.loads(line) for line in (self.DATA / "classify_test_v2.jsonl").open()]
        assert len(rows) == 400, "pre-registered test-pool size"
        assert all(
            (r["raw_text"] or "").strip() or (r["canonical_transliterated"] or "").strip()
            for r in rows
        ), "frozen split must carry the text the jury reads"
        assert all(r["split_seed"] == 42 for r in rows)

    def test_frozen_split_contains_the_jury_handoff_ids(self):
        import csv

        split_ids = {
            str(json.loads(line)["id"]) for line in (self.DATA / "classify_test_v2.jsonl").open()
        }
        handoff = REPO_ROOT / "research/v2/handoff/v2.0-etr/adjudication_queue.csv"
        queue_ids = {row["id"] for row in csv.DictReader(handoff.open())}
        assert queue_ids <= split_ids, "the jury's adjudication queue must be a subset"

    def test_no_train_test_contamination(self):
        test_ids = {
            str(json.loads(line)["id"]) for line in (self.DATA / "classify_test_v2.jsonl").open()
        }
        train_ids = {
            str(json.loads(line)["id"]) for line in (self.DATA / "classify_train_pool.jsonl").open()
        }
        assert not (test_ids & train_ids)
