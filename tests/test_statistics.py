"""Tests for the statistical analysis engine."""

import tempfile
from pathlib import Path

from openetruscan.adapter import load_adapter
from openetruscan.corpus import Corpus, Inscription
from openetruscan.statistics import (
    ClusterResult,
    ComparisonResult,
    FrequencyResult,
    cluster_sites,
    compare_frequencies,
    estimate_date,
    letter_frequencies,
)


class TestLetterFrequency:
    """Test letter frequency analysis."""

    def test_basic_counts(self):
        adapter = load_adapter("etruscan")
        result = letter_frequencies(["aaa bbb"], adapter)
        assert isinstance(result, FrequencyResult)
        # 'a' should have count 3
        assert result.counts.get("a", 0) == 3

    def test_excludes_spaces(self):
        adapter = load_adapter("etruscan")
        result = letter_frequencies(["a e c"], adapter)
        # spaces should not be counted, but a, e, c are in the alphabet
        assert result.total_chars == 3

    def test_excludes_unknown_chars(self):
        adapter = load_adapter("etruscan")
        result = letter_frequencies(["a@e#c"], adapter)
        assert result.total_chars == 3

    def test_multiple_texts(self):
        adapter = load_adapter("etruscan")
        result = letter_frequencies(["aaa", "bbb"], adapter)
        assert result.inscription_count == 2
        assert result.counts.get("a", 0) == 3
        assert result.counts.get("b", 0) == 0  # 'b' not in Etruscan alphabet

    def test_empty_input(self):
        adapter = load_adapter("etruscan")
        result = letter_frequencies([], adapter)
        assert result.total_chars == 0
        assert result.inscription_count == 0

    def test_to_dict(self):
        adapter = load_adapter("etruscan")
        result = letter_frequencies(["larθal"], adapter)
        d = result.to_dict()
        assert "letters" in d
        assert "total_chars" in d
        assert isinstance(d["letters"], list)

    def test_frequencies_sum_to_one(self):
        adapter = load_adapter("etruscan")
        result = letter_frequencies(["larθal velinas"], adapter)
        total = sum(result.frequencies.values())
        assert abs(total - 1.0) < 0.001


class TestCompareFrequencies:
    """Test chi-squared comparison."""

    def test_identical_distributions(self):
        adapter = load_adapter("etruscan")
        freq = letter_frequencies(["larθal"], adapter)
        result = compare_frequencies(freq, freq)
        assert isinstance(result, ComparisonResult)
        # Same distribution → not significant
        assert result.p_value >= 0.05

    def test_different_distributions(self):
        adapter = load_adapter("etruscan")
        # Very different character compositions
        freq_a = letter_frequencies(["a" * 100], adapter)
        freq_b = letter_frequencies(["l" * 100], adapter)
        result = compare_frequencies(freq_a, freq_b)
        # Should detect a significant difference
        assert result.significant is True
        assert result.effect_size > 0

    def test_to_dict(self):
        adapter = load_adapter("etruscan")
        freq = letter_frequencies(["larθ"], adapter)
        result = compare_frequencies(freq, freq)
        d = result.to_dict()
        assert "chi2" in d
        assert "p_value" in d
        assert "significant" in d
        assert "effect_size" in d


class TestClusterSites:
    """Test dialect clustering."""

    def _build_corpus(self):
        db_path = tempfile.mktemp(suffix=".db")
        corpus = Corpus.load(db_path)
        # Two distinct "dialect" groups
        for i in range(10):
            corpus.add(
                Inscription(
                    id=f"A{i}",
                    raw_text="larθal velinas",
                    findspot="Cerveteri",
                    language="etruscan",
                )
            )
            corpus.add(
                Inscription(
                    id=f"B{i}",
                    raw_text="θana matunai",
                    findspot="Tarquinia",
                    language="etruscan",
                )
            )
        return corpus, db_path

    def test_returns_clusters(self):
        corpus, db_path = self._build_corpus()
        result = cluster_sites(corpus, min_inscriptions=5)
        assert isinstance(result, ClusterResult)
        assert result.n_clusters >= 2
        assert len(result.sites) == 2
        corpus.close()
        Path(db_path).unlink()

    def test_pca_coordinates(self):
        corpus, db_path = self._build_corpus()
        result = cluster_sites(corpus, min_inscriptions=5)
        for site in result.sites:
            assert isinstance(site.pca_x, float)
            assert isinstance(site.pca_y, float)
        corpus.close()
        Path(db_path).unlink()

    def test_to_dict(self):
        corpus, db_path = self._build_corpus()
        result = cluster_sites(corpus, min_inscriptions=5)
        d = result.to_dict()
        assert "n_clusters" in d
        assert "clusters" in d
        assert "dendrogram" in d
        corpus.close()
        Path(db_path).unlink()

    def test_min_inscriptions_filter(self):
        corpus, db_path = self._build_corpus()
        result = cluster_sites(corpus, min_inscriptions=20)
        # Both sites have only 10 inscriptions, so nothing should pass
        assert len(result.sites) == 0
        corpus.close()
        Path(db_path).unlink()


class TestDateEstimate:
    """Test dating heuristics."""

    def test_archaic_features(self):
        # Text with K before a, no F → archaic indicators
        result = estimate_date("kanas")
        assert result.period in ("archaic", "indeterminate")
        assert any(f["id"] == "k_before_a" and f["present"] for f in result.features)

    def test_late_features(self):
        # Text with F → late indicator
        result = estimate_date("felnas")
        assert any(f["id"] == "f_present" and f["present"] for f in result.features)

    def test_classical_features(self):
        # Text with θ, c (no k/q) → classical indicators
        result = estimate_date("larθal lecnes")
        assert any(f["id"] == "aspirates_frequent" and f["present"] for f in result.features)
        assert any(f["id"] == "c_dominant" and f["present"] for f in result.features)

    def test_empty_text(self):
        result = estimate_date("")
        assert result.period == "indeterminate"
        assert result.confidence == 0.0

    def test_to_dict(self):
        result = estimate_date("larθal velinas")
        d = result.to_dict()
        assert "period" in d
        assert "date_range" in d
        assert "date_display" in d
        assert "confidence" in d
        assert "features" in d
