"""Tests for the Rosetta cross-language eval harness.

The harness hits a live API endpoint (``/neural/rosetta``) — these
tests use ``respx`` (httpx's mock library) where available, and fall
back to monkey-patching when not, so the test suite never touches
prod and never depends on the DB being populated.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the eval helpers importable — same path the script uses.
sys.path.insert(0, str(Path(__file__).parent.parent / "evals"))

from rosetta_eval_pairs import EvalPair  # noqa: E402

import run_rosetta_eval  # noqa: E402


# ---------------------------------------------------------------------------
# Eval pair sanity
# ---------------------------------------------------------------------------


class TestEvalPairs:
    def test_min_pair_count(self):
        from rosetta_eval_pairs import EVAL_PAIRS

        assert len(EVAL_PAIRS) >= 60

    def test_every_pair_has_a_category(self):
        from rosetta_eval_pairs import EVAL_PAIRS, VALID_CATEGORIES

        for p in EVAL_PAIRS:
            assert p.category in VALID_CATEGORIES, (
                f"{p.etr}→{p.lat} category={p.category!r} not in {VALID_CATEGORIES}"
            )

    def test_eval_pairs_filter_by_confidence(self):
        from rosetta_eval_pairs import eval_pairs

        all_pairs = eval_pairs(min_confidence="low", split=None)
        med = eval_pairs(min_confidence="medium", split=None)
        high = eval_pairs(min_confidence="high", split=None)
        assert len(all_pairs) >= len(med) >= len(high)
        assert all(p.confidence == "high" for p in high)
        assert all(p.confidence in {"high", "medium"} for p in med)

    def test_split_balance(self):
        """Each category has ≥1 train AND ≥1 test example."""
        from rosetta_eval_pairs import EVAL_PAIRS
        from collections import defaultdict

        cat_splits = defaultdict(lambda: defaultdict(int))
        for p in EVAL_PAIRS:
            cat_splits[p.category][p.split] += 1

        for cat, splits in cat_splits.items():
            assert splits.get("train", 0) >= 1, f"{cat} has no train pairs"
            assert splits.get("test", 0) >= 1, f"{cat} has no test pairs"

    def test_no_overlap(self):
        """train ∩ test = ∅ on the (etr, lat) key."""
        from rosetta_eval_pairs import EVAL_PAIRS

        train_keys = {(p.etr, p.lat) for p in EVAL_PAIRS if p.split == "train"}
        test_keys = {(p.etr, p.lat) for p in EVAL_PAIRS if p.split == "test"}
        overlap = train_keys & test_keys
        assert overlap == set(), f"Overlap: {overlap}"

    def test_split_size(self):
        """len(test) ∈ [20, 24] and len(train) ∈ [38, 42]."""
        from rosetta_eval_pairs import EVAL_PAIRS

        train = [p for p in EVAL_PAIRS if p.split == "train"]
        test = [p for p in EVAL_PAIRS if p.split == "test"]
        assert 38 <= len(train) <= 42, f"train={len(train)}"
        assert 20 <= len(test) <= 24, f"test={len(test)}"


# ---------------------------------------------------------------------------
# Harness math (precision@k computation)
# ---------------------------------------------------------------------------


def _patched_query(monkeypatch, responses: dict[str, list | None]):
    """Patch run_rosetta_eval._query_neighbours to return canned responses
    keyed on the queried Etruscan word. ``None`` ⇒ transport failure;
    ``[]`` ⇒ source word OOV.
    """

    def fake(api_url, word, from_lang, to_lang, k, **_kw):
        res = responses.get(word, [])
        if res is None:
            return None
        if not res:
            return []
        if isinstance(res[0], str):
            # Auto-generate fake decreasing cosines
            return [(w, 0.9 - i * 0.01) for i, w in enumerate(res)]
        return res

    monkeypatch.setattr(run_rosetta_eval, "_query_neighbours", fake)


class TestEvaluate:
    """End-to-end tests of the evaluate() function with mocked HTTP."""

    def test_perfect_recall(self, monkeypatch):
        """If every expected target sits at rank 1, every precision@k = 1.0."""
        pairs = [
            EvalPair("clan", "filius", "son", "high", "test", "kinship"),
            EvalPair("avil", "annus", "year", "high", "test", "time"),
        ]
        _patched_query(
            monkeypatch,
            {
                "clan": ["filius", "filium", "puer"],
                "avil": ["annus", "annorum", "anni"],
            },
        )

        report = run_rosetta_eval.evaluate(
            api_url="https://test", pairs=pairs, pace=False,
        )
        assert report["n_evaluated"] == 2
        assert report["n_skipped"] == 0
        for k, v in report["precision_at_k"].items():
            assert v == pytest.approx(1.0), f"precision@{k}={v} should be 1.0"

    def test_partial_recall_at_different_k(self, monkeypatch):
        """Target at rank 4 contributes to @5 and @10 but not @1 or @3."""
        pairs = [
            EvalPair("clan", "filius", "son", "high", "test", "kinship"),
        ]
        _patched_query(
            monkeypatch,
            {"clan": ["puer", "homo", "vir", "filius", "natus"]},
        )

        report = run_rosetta_eval.evaluate(
            api_url="https://test", pairs=pairs, pace=False,
        )
        assert report["precision_at_k"][1] == 0.0
        assert report["precision_at_k"][3] == 0.0
        assert report["precision_at_k"][5] == 1.0
        assert report["precision_at_k"][10] == 1.0
        assert report["per_pair"][0]["rank_of_expected"] == 4

    def test_target_not_in_top_k(self, monkeypatch):
        """Misses count toward n_evaluated but not toward any precision@k."""
        pairs = [EvalPair("clan", "filius", "son", "high", "test", "kinship")]
        _patched_query(
            monkeypatch,
            {"clan": ["completely", "unrelated", "words"]},
        )

        report = run_rosetta_eval.evaluate(
            api_url="https://test", pairs=pairs, pace=False,
        )
        assert report["n_evaluated"] == 1
        assert report["per_pair"][0]["rank_of_expected"] is None
        assert all(v == 0.0 for v in report["precision_at_k"].values())

    def test_oov_source_is_skipped_not_failed(self, monkeypatch):
        """Empty neighbours list = source word has no stored vector. The
        denominator should drop, not the numerator."""
        pairs = [
            EvalPair("clan", "filius", "son", "high", "test", "kinship"),
            EvalPair("zilθ", "praetor", "magistrate", "high", "test", "civic"),
        ]
        _patched_query(
            monkeypatch,
            {
                "clan": ["filius"],
                # zilθ omitted ⇒ default `[]` ⇒ OOV
            },
        )

        report = run_rosetta_eval.evaluate(
            api_url="https://test", pairs=pairs, pace=False,
        )
        assert report["n_evaluated"] == 1
        assert report["n_skipped"] == 1
        # Precision@k computed over n_evaluated only — single hit / single
        # evaluated → 1.0, not 0.5.
        assert report["precision_at_k"][1] == pytest.approx(1.0)

    def test_transport_failure_counts_as_failed_not_skipped(self, monkeypatch):
        """``None`` from _query_neighbours = transport error / 5xx, distinct
        from "the endpoint succeeded but returned no neighbours"."""
        pairs = [
            EvalPair("clan", "filius", "son", "high", "test", "kinship"),
            EvalPair("avil", "annus", "year", "high", "test", "time"),
        ]

        def fake(api_url, word, from_lang, to_lang, k, **_kw):
            if word == "avil":
                return None  # transport failure
            return [("filius", 0.9)]

        monkeypatch.setattr(run_rosetta_eval, "_query_neighbours", fake)

        report = run_rosetta_eval.evaluate(
            api_url="https://test", pairs=pairs, pace=False,
        )
        assert report["n_evaluated"] == 1
        assert report["n_skipped"] == 0
        assert report["n_failed"] == 1

    def test_per_category_breakdown(self, monkeypatch):
        pairs = [
            EvalPair("clan", "filius", "son", "high", "test", "kinship"),
            EvalPair("apa", "pater", "father", "high", "test", "kinship"),
            EvalPair("tinia", "iuppiter", "Jupiter", "high", "test", "theonym"),
        ]
        _patched_query(
            monkeypatch,
            {
                "clan": ["filius"],
                "apa": ["fratres"],          # miss
                "tinia": ["iuppiter"],
            },
        )

        report = run_rosetta_eval.evaluate(
            api_url="https://test", pairs=pairs, pace=False,
        )
        assert report["by_category"]["kinship"]["n"] == 2
        assert report["by_category"]["kinship"]["precision_at_k"][1] == 0.5
        assert report["by_category"]["theonym"]["n"] == 1
        assert report["by_category"]["theonym"]["precision_at_k"][1] == 1.0


    def test_levenshtein_baseline_self_match(self, monkeypatch):
        """The Levenshtein baseline should rank an exact match first."""
        pairs = [EvalPair("fanu", "fanu", "sanctuary", "high", "test", "religious")]

        def fake_get_vocab(api_url, to_lang, **_kw):
            return ["other", "unrelated", "fanu", "fanaticus"]

        monkeypatch.setattr(run_rosetta_eval, "_get_vocab", fake_get_vocab)

        report = run_rosetta_eval.evaluate(
            api_url="https://test", pairs=pairs, pace=False, baseline="levenshtein"
        )
        assert report["n_evaluated"] == 1
        assert report["n_skipped"] == 0
        assert report["precision_at_k"][1] == 1.0
        assert report["per_pair"][0]["rank_of_expected"] == 1


    def test_levenshtein_pipeline_end_to_end(self, monkeypatch):
        """Test Levenshtein integration with coverage_at_threshold."""
        pairs = [EvalPair("fanu", "fanu", "sanctuary", "high", "test", "religious")]

        def fake_get_vocab(api_url, to_lang, **_kw):
            return ["other", "unrelated", "fanu", "fanaticus"]

        monkeypatch.setattr(run_rosetta_eval, "_get_vocab", fake_get_vocab)

        report = run_rosetta_eval.evaluate(
            api_url="https://test", pairs=pairs, pace=False, baseline="levenshtein"
        )
        assert report["n_evaluated"] == 1
        assert "coverage_at_threshold" in report
        assert 0.5 in report["coverage_at_threshold"]
        assert report["coverage_at_threshold"][0.5] >= 0.0
# ---------------------------------------------------------------------------
# Random baseline (analytical)
# ---------------------------------------------------------------------------


class TestRandomBaseline:
    """Verify _random_baseline_metrics matches hand-computed expectations."""

    def test_strict_and_field_at_known_values(self, monkeypatch):
        """With vocab_size=1000, field_size=10, k=5:
        strict = 5/1000 = 0.005
        field  = 1 - C(990,5)/C(1000,5) ≈ 0.0491
        """
        import math
        from unittest.mock import patch
        
        monkeypatch.setattr(run_rosetta_eval, "_get_vocab", lambda *args: ["x"] * 1000)

        # Use a valid category but override the field to exactly 10 members.
        fake_fields = {"kinship": set(f"word{i}" for i in range(10))}
        pairs = [
            EvalPair("a", "b", "test", "high", "ref", "kinship"),
            EvalPair("c", "d", "test", "high", "ref", "kinship"),
        ]

        with patch.object(run_rosetta_eval, "LATIN_SEMANTIC_FIELDS", fake_fields):
            result = run_rosetta_eval._random_baseline_metrics("https://test", pairs)

        # strict@5 = 5/1000 = 0.005
        assert result["precision_at_k"][5] == pytest.approx(0.005)

        # field@5 = 1 - C(990,5)/C(1000,5)
        expected_field = 1.0 - math.comb(990, 5) / math.comb(1000, 5)
        assert result["precision_at_k_semantic_field"][5] == pytest.approx(
            expected_field, rel=1e-6
        )
        # Sanity: field > strict (semantic field is broader)
        assert result["precision_at_k_semantic_field"][5] > result["precision_at_k"][5]

    def test_random_baseline_via_evaluate(self):
        """--baseline=random through evaluate() produces correct report shape."""
        pairs = [
            EvalPair("clan", "filius", "son", "high", "test", "kinship"),
            EvalPair("avil", "annus", "year", "high", "test", "time"),
        ]
        report = run_rosetta_eval.evaluate(
            api_url="https://test", pairs=pairs, pace=False, baseline="random",
        )
        assert report["n_evaluated"] == 2
        assert report["n_skipped"] == 0
        assert report["n_failed"] == 0
        # strict@10 for vocab=100000 is 10/100000 = 0.0001
        assert report["precision_at_k"][10] == pytest.approx(1e-4)
        # field must be strictly greater than strict
        assert report["precision_at_k_semantic_field"][10] > report["precision_at_k"][10]

    def test_coverage_metric(self, monkeypatch):
        """Coverage tracks the fraction of eval pairs whose top-1 hit has a
        cosine above 0.5, 0.7, 0.85."""
        pairs = [
            EvalPair("p1", "w", "t", "high", "test", "kinship"),  # hits 0.9
            EvalPair("p2", "w", "t", "high", "test", "kinship"),  # hits 0.8
            EvalPair("p3", "w", "t", "high", "test", "kinship"),  # hits 0.6
            EvalPair("p4", "w", "t", "high", "test", "kinship"),  # hits 0.4
            EvalPair("p5", "w", "t", "high", "test", "kinship"),  # OOV (skipped)
            EvalPair("p6", "w", "t", "high", "test", "kinship"),  # Failed
        ]
        _patched_query(
            monkeypatch,
            {
                "p1": [("w", 0.90)],
                "p2": [("w", 0.80)],
                "p3": [("w", 0.60)],
                "p4": [("w", 0.40)],
                "p5": [],
                "p6": None,
            },
        )
        report = run_rosetta_eval.evaluate(
            api_url="https://test", pairs=pairs, pace=False,
        )
        assert report["n_evaluated"] == 4
        cov = report["coverage_at_threshold"]
        assert cov[0.85] == 1 / 4  # only p1 >= 0.85
        assert cov[0.70] == 2 / 4  # p1, p2 >= 0.70
        assert cov[0.50] == 3 / 4  # p1, p2, p3 >= 0.50



# ---------------------------------------------------------------------------
# Gate parsing
# ---------------------------------------------------------------------------


class TestEvaluateGates:
    def _report(self):
        # Hand-built report mimicking the evaluate() shape.
        return {
            "precision_at_k": {1: 0.5, 3: 0.7, 5: 0.85, 10: 0.95},
            "by_category": {
                "kinship": {
                    "precision_at_k": {1: 0.6, 3: 0.8, 5: 0.9, 10: 1.0},
                    "n": 9, "median_rank": 1,
                },
            },
        }

    def test_pass_when_all_thresholds_met(self):
        ok, failures = run_rosetta_eval._evaluate_gates(
            self._report(), "precision_at_5=0.40,precision_at_10=0.50",
        )
        assert ok
        assert failures == []

    def test_fail_when_threshold_missed(self):
        ok, failures = run_rosetta_eval._evaluate_gates(
            self._report(), "precision_at_1=0.99",
        )
        assert not ok
        assert "precision_at_1" in failures[0]

    def test_unknown_metric_fails_loudly(self):
        ok, failures = run_rosetta_eval._evaluate_gates(
            self._report(), "fake_metric=0.5",
        )
        assert not ok
        assert "unknown gate metric" in failures[0]

    def test_per_category_gate_works(self):
        ok, _ = run_rosetta_eval._evaluate_gates(
            self._report(), "kinship_precision_at_5=0.85",
        )
        assert ok

    def test_per_category_gate_can_fail(self):
        ok, failures = run_rosetta_eval._evaluate_gates(
            self._report(), "kinship_precision_at_1=0.99",
        )
        assert not ok
        assert "kinship_precision_at_1" in failures[0]


# ---------------------------------------------------------------------------
# Frozen benchmark presets (T1.5)
# ---------------------------------------------------------------------------


class TestBenchmarkPreset:
    """The --benchmark switch must lock split/min_confidence/category to a
    pinned tuple so that two runs of the same label are directly comparable.

    These tests guard the *contract* of the rosetta-eval-v1 spec: any change
    that moves the pinned values is a benchmark-breaking change and must
    rename the label (rosetta-eval-v2).
    """

    def test_rosetta_eval_v1_is_registered(self):
        assert "rosetta-eval-v1" in run_rosetta_eval.BENCHMARK_PRESETS

    def test_rosetta_eval_v1_pinned_values(self):
        preset = run_rosetta_eval.BENCHMARK_PRESETS["rosetta-eval-v1"]
        assert preset["split"] == "test"
        assert preset["min_confidence"] == "medium"
        assert preset["category"] is None

    def test_benchmark_locks_split_and_min_confidence(self, monkeypatch, capsys):
        """--benchmark=rosetta-eval-v1 --split=train should override back to test.

        Drives main() through a mocked HTTP layer; we only care that the
        resulting run uses the test split, not the user-supplied train.
        """
        # Stub _query_neighbours so we don't hit the network.
        monkeypatch.setattr(
            run_rosetta_eval, "_query_neighbours",
            lambda *args, **kwargs: [("dummy", 0.5)],
        )
        monkeypatch.setattr(run_rosetta_eval, "PER_REQUEST_DELAY_S", 0.0)

        # main() parses argv and prints "Split: test (N pairs)" — assert N matches
        # the test-split count, not the train-split count.
        rc = run_rosetta_eval.main([
            "--api-url", "https://test",
            "--benchmark", "rosetta-eval-v1",
            "--split", "train",          # should be overridden
            "--min-confidence", "low",   # should be overridden
            "--no-pace",
            "--json",
        ])
        assert rc == 0

        err = capsys.readouterr().err
        assert "Benchmark: rosetta-eval-v1" in err
        assert "WARN" in err  # the override warning fires
        # Expected test-split count is in [20, 24] per the T1.3 contract.
        # Match the "Split: test (N pairs)" line.
        import re
        m = re.search(r"Split: test \((\d+) pairs\)", err)
        assert m is not None, f"split line not found in stderr: {err!r}"
        n_pairs = int(m.group(1))
        assert 20 <= n_pairs <= 24, (
            f"benchmark used wrong split: got {n_pairs} pairs, expected 20-24 (test)"
        )

    def test_benchmark_does_not_warn_when_defaults_match(self, monkeypatch, capsys):
        """No override warning if the user didn't pass conflicting flags."""
        monkeypatch.setattr(
            run_rosetta_eval, "_query_neighbours",
            lambda *args, **kwargs: [("dummy", 0.5)],
        )
        monkeypatch.setattr(run_rosetta_eval, "PER_REQUEST_DELAY_S", 0.0)

        rc = run_rosetta_eval.main([
            "--api-url", "https://test",
            "--benchmark", "rosetta-eval-v1",
            "--no-pace",
            "--json",
        ])
        assert rc == 0
        err = capsys.readouterr().err
        assert "Benchmark: rosetta-eval-v1" in err
        # No WARN line because we didn't pass any overrides.
        assert "WARN" not in err
