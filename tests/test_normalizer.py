"""Tests for the normalizer engine."""

from openetruscan.core.adapter import load_adapter
from openetruscan.core.normalizer import NormResult, detect_source_system, normalize


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


class TestLeidenApparatus:
    """Leiden editorial markup is parsed out, never folded into the text."""

    def test_supplied_brackets_stripped(self):
        result = normalize("[larθ]al")
        assert result.canonical == "larθal"
        assert len(result.apparatus) == 1
        span = result.apparatus[0]
        assert span.kind == "supplied"
        assert (span.start, span.end) == (0, 4)
        assert result.canonical[span.start : span.end] == "larθ"
        assert span.source == "[larθ]"

    def test_digraph_inside_supplied_span_remaps(self):
        """CIE 'TH' collapses to one θ; the span must shrink with it."""
        result = normalize("[TH]ANCVIL")
        assert result.canonical.startswith("θ")
        span = result.apparatus[0]
        assert span.kind == "supplied"
        assert (span.start, span.end) == (0, 1)
        assert result.canonical[span.start : span.end] == "θ"

    def test_span_boundary_mid_digraph_widens_with_warning(self):
        """A bracket splitting 'TH' cannot split the folded θ: snap outward."""
        result = normalize("[T]HANCVIL")
        span = result.apparatus[0]
        assert (span.start, span.end) == (0, 1)
        assert result.canonical[span.start : span.end] == "θ"
        assert any("widened" in w for w in result.warnings)

    def test_no_markup_leaks_into_any_representation(self):
        result = normalize("mi [lar]θ̣al (clan) [...] śuθi")
        markup = set("[]()̣")
        for text in (result.canonical, result.phonetic, result.old_italic, *result.tokens):
            assert not markup & set(text), f"markup leaked into {text!r}"
        kinds = [s.kind for s in result.apparatus]
        assert kinds == ["supplied", "unclear", "expansion", "gap"]

    def test_gap_recorded_with_warning(self):
        result = normalize("mi [...] lar")
        gap = next(s for s in result.apparatus if s.kind == "gap")
        assert gap.start == gap.end
        assert any("unrestorable gap of width 3" in w for w in result.warnings)

    def test_clean_input_has_empty_apparatus(self):
        result = normalize("Larθal")
        assert result.apparatus == ()

    def test_apparatus_serialized_in_to_dict(self):
        result = normalize("[larθ]al")
        d = result.to_dict()
        assert d["apparatus"] == [{"kind": "supplied", "start": 0, "end": 4, "source": "[larθ]"}]


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
