"""Tests for the adapter loader."""

from openetruscan.adapter import LanguageAdapter, list_available_adapters, load_adapter


class TestLoadAdapter:
    """Test YAML adapter loading."""

    def test_load_etruscan(self):
        adapter = load_adapter("etruscan")
        assert isinstance(adapter, LanguageAdapter)
        assert adapter.language_id == "etruscan"
        assert adapter.direction == "rtl"

    def test_alphabet_loaded(self):
        adapter = load_adapter("etruscan")
        assert len(adapter.alphabet) > 20
        assert "θ" in adapter.alphabet
        assert "a" in adapter.alphabet

    def test_equivalence_classes(self):
        adapter = load_adapter("etruscan")
        assert "aspirated_dental" in adapter.equivalence_classes

    def test_phonotactics(self):
        adapter = load_adapter("etruscan")
        assert "m" in adapter.phonotactics.forbidden_word_final

    def test_onomastics(self):
        adapter = load_adapter("etruscan")
        assert "larθ" in adapter.onomastics.known_praenomina["male"]

    def test_variant_resolution(self):
        adapter = load_adapter("etruscan")
        assert adapter.resolve_variant("th") == "θ"
        assert adapter.resolve_variant("TH") == "θ"
        assert adapter.resolve_variant("ph") == "φ"

    def test_unicode_conversion(self):
        adapter = load_adapter("etruscan")
        assert adapter.to_unicode("a") == "\U00010300"
        assert adapter.to_unicode("θ") == "\U00010308"

    def test_ipa_conversion(self):
        adapter = load_adapter("etruscan")
        assert adapter.to_ipa("θ") == "tʰ"
        assert adapter.to_ipa("a") == "a"

    def test_unicode_range_detection(self):
        adapter = load_adapter("etruscan")
        assert adapter.is_in_unicode_range("\U00010300")
        assert not adapter.is_in_unicode_range("A")

    def test_unknown_adapter_raises(self):
        try:
            load_adapter("klingon")
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError:
            pass

    def test_list_available(self):
        adapters = list_available_adapters()
        assert "etruscan" in adapters


class TestGentilicia:
    """Test that known name lists are populated."""

    def test_gentilicia_not_empty(self):
        adapter = load_adapter("etruscan")
        assert len(adapter.onomastics.known_gentilicia) > 10

    def test_praenomina_not_empty(self):
        adapter = load_adapter("etruscan")
        assert len(adapter.onomastics.known_praenomina["male"]) > 10
        assert len(adapter.onomastics.known_praenomina["female"]) > 5
