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


def _patched_query(monkeypatch, responses: dict[str, list[str]]):
    """Patch run_rosetta_eval._query_neighbours to return canned responses
    keyed on the queried Etruscan word. ``None`` ⇒ transport failure;
    ``[]`` ⇒ source word OOV.
    """

    def fake(api_url, word, from_lang, to_lang, k, **_kw):
        return responses.get(word, [])

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
            return ["filius"]

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

        def fake_get_vocab(api_url, to_lang):
            return ["other", "unrelated", "fanu", "fanaticus"]

        monkeypatch.setattr(run_rosetta_eval, "_get_vocab", fake_get_vocab)

        report = run_rosetta_eval.evaluate(
            api_url="https://test", pairs=pairs, pace=False, baseline="levenshtein"
        )
        assert report["n_evaluated"] == 1
        assert report["n_skipped"] == 0
        assert report["precision_at_k"][1] == 1.0
        assert report["per_pair"][0]["rank_of_expected"] == 1


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
