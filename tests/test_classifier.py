"""Tests for the inscription classifier."""

from openetruscan.classifier import ClassificationResult, InscriptionClassifier


class TestKeywordFallback:
    """Test keyword-based classification (fallback mode)."""

    def setup_method(self):
        self.clf = InscriptionClassifier()

    def test_funerary_keywords(self):
        result = self.clf.predict("suθi larθal lecnes")
        assert isinstance(result, ClassificationResult)
        assert result.label == "funerary"
        assert result.method == "keyword_fallback"

    def test_votive_keywords(self):
        result = self.clf.predict("turce alpan fleres")
        assert result.label == "votive"

    def test_boundary_keywords(self):
        result = self.clf.predict("tular rasna spura")
        assert result.label == "boundary"

    def test_ownership_keywords(self):
        result = self.clf.predict("mi mulu")
        assert result.label == "ownership"

    def test_unknown_text(self):
        result = self.clf.predict("larθal velinas")
        assert result.label == "unknown"

    def test_to_dict(self):
        result = self.clf.predict("suθi larθal")
        d = result.to_dict()
        assert "label" in d
        assert "probabilities" in d
        assert "method" in d
        assert d["method"] == "keyword_fallback"

    def test_probabilities_are_normalised(self):
        result = self.clf.predict("turce alpan")
        if result.label != "unknown":
            total = sum(result.probabilities.values())
            assert abs(total - 1.0) < 0.01


class TestMLMode:
    """Test ML training (with synthetic data)."""

    def test_train_below_threshold_stays_fallback(self):
        clf = InscriptionClassifier()
        # Under 500 samples → should stay in fallback
        clf.train(["text"] * 100, ["funerary"] * 100)
        result = clf.predict("suθi")
        assert result.method == "keyword_fallback"

    def test_result_dataclass(self):
        result = ClassificationResult(
            label="funerary",
            probabilities={"funerary": 0.8, "votive": 0.2},
            method="ml",
        )
        d = result.to_dict()
        assert d["label"] == "funerary"
        assert d["method"] == "ml"
        assert abs(d["probabilities"]["funerary"] - 0.8) < 0.001
