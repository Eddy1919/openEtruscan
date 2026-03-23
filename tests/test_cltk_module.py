"""Tests for the CLTK integration module."""

import pytest

from openetruscan.cltk_module import EtruscanPipeline, ETRUSCAN_LANGUAGE
from openetruscan.cltk_module.language import Language
from openetruscan.cltk_module.pipeline import EtruscanWord, EtruscanDoc


class TestLanguageDefinition:
    """Verify the Etruscan Language follows CLTK conventions."""

    def test_glottolog_id(self):
        assert ETRUSCAN_LANGUAGE.glottolog_id == "etru1241"

    def test_iso_code(self):
        assert ETRUSCAN_LANGUAGE.iso == "ett"
        assert ETRUSCAN_LANGUAGE.iso_set == {"639-3": "ett"}

    def test_family(self):
        assert ETRUSCAN_LANGUAGE.family_id == "tyrs1239"

    def test_status(self):
        assert ETRUSCAN_LANGUAGE.status == "extinct"

    def test_geo(self):
        assert ETRUSCAN_LANGUAGE.geo is not None
        assert ETRUSCAN_LANGUAGE.geo.centroid.lat == pytest.approx(42.75)
        assert ETRUSCAN_LANGUAGE.geo.countries == ["IT"]

    def test_dialects(self):
        names = [d.name for d in ETRUSCAN_LANGUAGE.dialects]
        assert "Northern Etruscan" in names
        assert "Southern Etruscan" in names

    def test_alt_names_multilingual(self):
        italian = [n for n in ETRUSCAN_LANGUAGE.alt_names if n.language == "it"]
        assert any("etrusca" in n.value.lower() for n in italian)


class TestPipeline:
    """Test the full Etruscan NLP pipeline."""

    @pytest.fixture
    def pipe(self):
        return EtruscanPipeline("etruscan")

    def test_tokenize(self, pipe):
        tokens = pipe.tokenize("mi larθal lecnes")
        assert tokens == ["mi", "larθal", "lecnes"]

    def test_tokenize_strips_editorial(self, pipe):
        tokens = pipe.tokenize("[mi] larθal (lecnes)")
        assert tokens == ["mi", "larθal", "lecnes"]

    def test_analyze_returns_doc(self, pipe):
        doc = pipe.analyze("mi larθal lecnes")
        assert isinstance(doc, EtruscanDoc)
        assert doc.raw == "mi larθal lecnes"
        assert doc.language == "ett"

    def test_analyze_word_count(self, pipe):
        doc = pipe.analyze("mi larθal lecnes")
        assert len(doc.words) == 3

    def test_normalized(self, pipe):
        doc = pipe.analyze("mi larθal lecnes")
        # All words should have non-empty normalized forms
        for word in doc.words:
            assert word.normalized

    def test_phonetic(self, pipe):
        doc = pipe.analyze("mi larθal lecnes")
        for word in doc.words:
            assert word.phonetic

    def test_old_italic(self, pipe):
        doc = pipe.analyze("mi")
        assert doc.words[0].old_italic

    def test_tokens_property(self, pipe):
        doc = pipe.analyze("mi larθal lecnes")
        assert doc.tokens == ["mi", "larθal", "lecnes"]

    def test_normalized_text_property(self, pipe):
        doc = pipe.analyze("mi larθal")
        assert isinstance(doc.normalized_text, str)
        assert len(doc.normalized_text) > 0

    def test_repr(self, pipe):
        r = repr(pipe)
        assert "EtruscanPipeline" in r
        assert "etruscan" in r


class TestNER:
    """Test Named Entity Recognition via onomastic lexicon."""

    @pytest.fixture
    def pipe(self):
        return EtruscanPipeline("etruscan")

    def test_entities_property(self, pipe):
        doc = pipe.analyze("larθ velchas")
        # entities is a list (may or may not have matches depending on data)
        assert isinstance(doc.entities, list)

    def test_word_repr(self):
        w = EtruscanWord(
            string="larθ",
            normalized="larθ",
            phonetic="larθ",
            old_italic="𐌋𐌀𐌓𐌈",
            ner_tag="PRAENOMEN",
        )
        assert "PRAENOMEN" in repr(w)

    def test_word_repr_no_ner(self):
        w = EtruscanWord(
            string="mi",
            normalized="mi",
            phonetic="mi",
            old_italic="𐌌𐌉",
        )
        assert "PRAENOMEN" not in repr(w)
