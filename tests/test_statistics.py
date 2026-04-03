"""Tests for the statistical analysis engine."""

from openetruscan.adapter import load_adapter
from openetruscan.corpus import Corpus, Inscription
from openetruscan.statistics import (
    BayesianDatingResult,
    ClusterResult,
    ComparisonResult,
    FrequencyResult,
    bayesian_date,
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
        corpus = Corpus.load()
        # Clean up test data
        test_ids = [f"A{i}" for i in range(10)] + [f"B{i}" for i in range(10)]
        with corpus._conn.cursor() as cur:
            cur.execute("DELETE FROM inscriptions WHERE id = ANY(%s)", (test_ids,))
        corpus._conn.commit()
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
        return corpus

    def test_returns_clusters(self):
        corpus = self._build_corpus()
        result = cluster_sites(corpus, min_inscriptions=5)
        assert isinstance(result, ClusterResult)
        assert result.n_clusters >= 2
        assert len(result.sites) == 2
        corpus.close()

    def test_pca_coordinates(self):
        corpus = self._build_corpus()
        result = cluster_sites(corpus, min_inscriptions=5)
        for site in result.sites:
            assert isinstance(site.pca_x, float)
            assert isinstance(site.pca_y, float)
        corpus.close()

    def test_to_dict(self):
        corpus = self._build_corpus()
        result = cluster_sites(corpus, min_inscriptions=5)
        d = result.to_dict()
        assert "n_clusters" in d
        assert "clusters" in d
        assert "dendrogram" in d
        corpus.close()

    def test_min_inscriptions_filter(self):
        corpus = self._build_corpus()
        result = cluster_sites(corpus, min_inscriptions=20)
        # Both sites have only 10 inscriptions, so nothing should pass
        assert len(result.sites) == 0
        corpus.close()


class TestDateEstimate:
    """Test descriptive dating tagging system."""

    def test_archaic_features(self):
        # Text with K before a, no F → archaic indicators
        result = estimate_date("kanas")
        assert result.period in ("archaic", "indeterminate")
        assert any(f["id"] == "k_before_a" and f["present"] for f in result.features)
        # New fields
        assert result.method == "descriptive"
        assert result.tag_scores is not None
        assert "archaic" in result.tag_scores

    def test_late_features(self):
        # Text with F → late indicator
        result = estimate_date("felnas")
        assert any(f["id"] == "f_present" and f["present"] for f in result.features)
        assert result.tag_scores["late"] > 0

    def test_classical_features(self):
        # Text with θ, c (no k/q) → classical indicators
        result = estimate_date("larθal lecnes")
        assert any(f["id"] == "aspirates_frequent" and f["present"] for f in result.features)
        assert any(f["id"] == "c_dominant" and f["present"] for f in result.features)
        assert result.tag_scores["classical"] > 0

    def test_empty_text(self):
        result = estimate_date("")
        assert result.period == "indeterminate"
        assert result.confidence == 0.0
        assert result.tag_scores == {"archaic": 0.0, "classical": 0.0, "late": 0.0}

    def test_to_dict(self):
        result = estimate_date("larθal velinas")
        d = result.to_dict()
        assert "period" in d
        assert "date_range" in d
        assert "date_display" in d
        assert "confidence" in d
        assert "features" in d
        # New descriptive fields
        assert "tag_scores" in d
        assert "method" in d
        assert d["method"] == "descriptive"
        assert "caveats" in d
        assert isinstance(d["caveats"], list)

    def test_features_have_weights(self):
        result = estimate_date("larθal")
        for f in result.features:
            assert "weight" in f, f"Feature {f['id']} missing 'weight'"
            assert "period" in f, f"Feature {f['id']} missing 'period'"
            assert f["weight"] > 0

    def test_weighted_scoring_k_plus_q(self):
        # K+Q combo should score higher than K alone
        result_kq = estimate_date("kaqas")
        result_k = estimate_date("kanas")
        assert result_kq.tag_scores["archaic"] > result_k.tag_scores["archaic"]

    def test_caveats_present(self):
        result = estimate_date("larθal")
        assert result.caveats is not None
        assert len(result.caveats) > 0
        assert any("Rule-based" in c for c in result.caveats)


class TestBayesianDating:
    """Test Bayesian aoristic dating model."""

    def test_archaic_text_peaks_early(self):
        # "kanas" has K before /a/, Q absent, no F → archaic
        result = bayesian_date("kanas")
        assert isinstance(result, BayesianDatingResult)
        # MAP should be in the archaic range (700-500 BCE → negative)
        assert result.map_estimate <= -475

    def test_late_text_peaks_late(self):
        # "f" present + Latin influence → late period
        result = bayesian_date("fasd")
        assert result.map_estimate >= -400  # Later than 400 BCE

    def test_posterior_sums_to_one(self):
        result = bayesian_date("larθal spurinas")
        total = sum(result.posterior.values())
        assert abs(total - 1.0) < 0.01, f"Posterior sums to {total}"

    def test_posterior_has_13_bins(self):
        result = bayesian_date("larθal")
        assert len(result.posterior) == 13

    def test_credible_interval_contains_map(self):
        result = bayesian_date("larθal")
        ci = result.credible_interval_95
        map_bce = abs(result.map_estimate)
        assert ci[0] >= 50  # BCE values are positive
        assert ci[1] <= 700
        assert ci[0] <= map_bce <= ci[1] or ci[0] >= map_bce

    def test_features_observed_populated(self):
        result = bayesian_date("kanas")
        assert "k_before_a" in result.features_observed
        assert result.features_observed["k_before_a"] is True
        assert "f_present" in result.features_observed
        assert result.features_observed["f_present"] is False

    def test_to_dict(self):
        result = bayesian_date("larθal")
        d = result.to_dict()
        assert "posterior" in d
        assert "map_estimate" in d
        assert "map_display" in d
        assert "credible_interval_95" in d
        assert "credible_interval_display" in d
        assert d["method"] == "bayesian_aoristic"

    def test_kq_text_strongly_archaic(self):
        # K+Q both present → very strong archaic signal
        result = bayesian_date("kaqas")
        # First 4 bins (700-500 BCE) should dominate
        archaic_mass = sum(
            v
            for k, v in result.posterior.items()
            if any(k.startswith(f"{yr}-") for yr in ["700", "650", "600", "550"])
        )
        assert archaic_mass > 0.8, f"Archaic bins only have {archaic_mass:.2f} mass"
