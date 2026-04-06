"""Tests for the normalizer engine."""

from openetruscan.adapter import load_adapter
from openetruscan.normalizer import NormResult, detect_source_system, normalize


class TestDetectSourceSystem:
    """Test automatic source system detection."""

    def setup_method(self):
        self.adapter = load_adapter("etruscan")

    def test_detect_cie_all_uppercase(self):
        assert detect_source_system("LARTHAL", self.adapter) == "cie"

    def test_detect_philological_theta(self):
        assert detect_source_system("Larθal", self.adapter) == "philological"

    def test_detect_philological_phi(self):
        assert detect_source_system("φulenas", self.adapter) == "philological"

    def test_detect_unicode_old_italic(self):
        assert detect_source_system("𐌓𐌀𐌓𐌈", self.adapter) == "unicode"

    def test_detect_latex(self):
        assert detect_source_system("Lar\\d{h}al", self.adapter) == "latex"

    def test_detect_web_safe_default(self):
        assert detect_source_system("Larthal", self.adapter) == "web_safe"


class TestNormalize:
    """Test the normalize function across input systems."""

    def test_cie_input(self):
        result = normalize("LARTHAL")
        assert isinstance(result, NormResult)
        assert "larθal" in result.canonical or "larthal" in result.canonical

    def test_philological_input(self):
        result = normalize("Larθal")
        assert result.canonical == "larθal"

    def test_preserves_spaces(self):
        result = normalize("LARTH LECNES")
        assert " " in result.canonical

    def test_multiple_words(self):
        result = normalize("Larθal Lecnes")
        assert len(result.tokens) == 2

    def test_empty_string(self):
        result = normalize("")
        assert result.canonical == ""
        assert result.confidence == 1.0

    def test_confidence_decreases_with_warnings(self):
        # Input with unknown characters should lower confidence
        result = normalize("Lar@al")
        assert result.confidence < 1.0

    def test_to_dict(self):
        result = normalize("Larθal")
        d = result.to_dict()
        assert "canonical" in d
        assert "phonetic" in d
        assert "old_italic" in d
        assert "source_system" in d

    def test_source_system_reported(self):
        result = normalize("LARTHAL")
        assert result.source_system == "cie"

    def test_phonetic_output(self):
        result = normalize("Larθal")
        assert "tʰ" in result.phonetic

    def test_old_italic_output(self):
        result = normalize("Larθal")
        # Should contain Old Italic characters
        for char in result.old_italic:
            if char != " ":
                assert ord(char) >= 0x10300 or not char.isalpha()


class TestRoundTrip:
    """Test that normalizing different inputs gives consistent output."""

    def test_cie_and_philological_match(self):
        """CIE 'TH' and philological 'θ' should produce the same canonical form."""
        result_cie = normalize("LARTHAL")
        result_phil = normalize("Larθal")
        assert result_cie.canonical == result_phil.canonical

    def test_old_italic_roundtrip(self):
        """Normalizing the Old Italic output should give the same canonical."""
        result1 = normalize("Larθal")
        result2 = normalize(result1.old_italic)
        assert result1.canonical == result2.canonical
