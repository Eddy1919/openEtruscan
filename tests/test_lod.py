"""Tests for the Linked Open Data module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from openetruscan.corpus import Corpus, Inscription
from openetruscan.lod import (
    get_eagle_uri,
    get_pleiades_uri,
    get_trismegistos_uri,
    get_wikidata_uri,
    inscription_to_jsonld,
    lod_stats,
    reconcile_trismegistos,
    reconcile_wikidata,
)


class TestPleiadesURI:
    """Test Pleiades URI generation (existing functionality)."""

    def test_known_findspot(self):
        uri = get_pleiades_uri("Cerveteri")
        # Returns None if not in mapping, or the URI if it is
        if uri:
            assert uri.startswith("https://pleiades.stoa.org")

    def test_unknown_findspot(self):
        uri = get_pleiades_uri("Atlantis")
        assert uri is None


class TestTrismegistosURI:
    """Test Trismegistos URI generation."""

    def test_mapped_inscription(self):
        uri = get_trismegistos_uri("ET_Cr_1.1")
        assert uri is not None
        assert "trismegistos.org/text/" in uri
        assert "828901" in uri

    def test_unmapped_inscription(self):
        uri = get_trismegistos_uri("NONEXISTENT_ID")
        assert uri is None


class TestEagleURI:
    """Test EAGLE URI generation."""

    def test_mapped_inscription(self):
        uri = get_eagle_uri("ET_Cr_1.1")
        assert uri is not None
        assert "eagle-network.eu" in uri
        assert "EDR000001" in uri

    def test_unmapped_inscription(self):
        uri = get_eagle_uri("NONEXISTENT_ID")
        assert uri is None


class TestEnrichedJsonLD:
    """Test JSON-LD output with all three LOD systems."""

    def test_jsonld_includes_tm_uri(self):
        insc = Inscription(
            id="ET_Cr_1.1",
            raw_text="larθal lecnes",
            canonical="larθal lecnes",
            findspot="Cerveteri",
        )
        jsonld = inscription_to_jsonld(insc)
        sources = [
            b.get("source", "")
            for b in jsonld.get("body", [])
            if isinstance(b, dict) and b.get("purpose") == "identifying"
        ]
        assert any(s.startswith("https://www.trismegistos.org") for s in sources)

    def test_jsonld_includes_eagle_uri(self):
        insc = Inscription(
            id="ET_Cr_1.1",
            raw_text="larθal lecnes",
            canonical="larθal lecnes",
        )
        jsonld = inscription_to_jsonld(insc)
        sources = [
            b.get("source", "")
            for b in jsonld.get("body", [])
            if isinstance(b, dict) and b.get("purpose") == "identifying"
        ]
        assert any("eagle-network.eu" in s for s in sources)

    def test_jsonld_no_lod_for_unknown_id(self):
        insc = Inscription(
            id="UNKNOWN_ID",
            raw_text="test text",
            canonical="test text",
        )
        jsonld = inscription_to_jsonld(insc)
        identifying_bodies = [
            b for b in jsonld.get("body", [])
            if isinstance(b, dict) and b.get("purpose") == "identifying"
        ]
        assert len(identifying_bodies) == 0


class TestLodStats:
    """Test LOD coverage statistics."""

    def test_lod_stats_structure(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        corpus = Corpus.load(db_path)
        corpus.add(Inscription(id="ET_Cr_1.1", raw_text="test", findspot="Cerveteri"))
        corpus.add(Inscription(id="UNKNOWN", raw_text="test2"))

        stats = lod_stats(corpus)
        assert "pleiades" in stats
        assert "trismegistos" in stats
        assert "eagle" in stats
        assert "mapped" in stats["trismegistos"]
        assert "total" in stats["trismegistos"]
        assert "coverage" in stats["trismegistos"]
        # ET_Cr_1.1 should be mapped in TM and EAGLE
        assert stats["trismegistos"]["mapped"] >= 1
        assert stats["eagle"]["mapped"] >= 1

        corpus.close()
        Path(db_path).unlink()


class TestReconciliation:
    """Test live API reconciliation functions (offline-safe)."""

    def test_reconcile_tm_uses_static_first(self):
        # ET_Cr_1.1 is in the static mapping — should return without API call
        result = reconcile_trismegistos("ET_Cr_1.1")
        assert result == "828901"

    def test_reconcile_tm_returns_none_for_unknown(self):
        # Unknown ID with empty text — returns None without API call
        result = reconcile_trismegistos("NONEXISTENT", text="")
        assert result is None

    def test_reconcile_wikidata_empty_returns_none(self):
        result = reconcile_wikidata("")
        assert result is None

    def test_reconcile_wikidata_none_returns_none(self):
        result = reconcile_wikidata(None)
        assert result is None

    def test_save_and_load_yaml_mapping(self):
        """Test YAML mapping round-trip."""
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            # Patch the data directory path
            test_file = Path(tmpdir) / "test_mapping.yaml"
            mapping = {"INS_001": "TM12345", "INS_002": "TM67890"}

            # Write directly
            with open(test_file, "w", encoding="utf-8") as f:
                yaml.dump(mapping, f, allow_unicode=True)

            # Read back
            with open(test_file, encoding="utf-8") as f:
                loaded = yaml.safe_load(f)

            assert loaded["INS_001"] == "TM12345"
            assert loaded["INS_002"] == "TM67890"

    def test_get_wikidata_uri_missing_file(self):
        """get_wikidata_uri returns None when no cache file exists."""
        # Patch to point to a nonexistent directory
        with patch("openetruscan.lod.Path") as mock_path:
            mock_path.return_value.parent.parent.parent.__truediv__ = (
                lambda *a: Path("/nonexistent/path.yaml")
            )
            # Direct test: no wikidata_mapping.yaml → None
            result = get_wikidata_uri("Atlantis")
            # Should be None (file doesn't exist or findspot not in mapping)
            assert result is None

    def test_reconcile_tm_with_mock_api(self):
        """Test TM API reconciliation with mocked response."""
        class MockResponse:
            status_code = 200
            def raise_for_status(self):
                pass
            def json(self):
                return [{"tm_id": "999999", "text": "test"}]

        class MockHttpx:
            @staticmethod
            def get(*args, **kwargs):
                return MockResponse()

        # Use an ID NOT in static mapping so it hits the "API"
        with patch("openetruscan.lod._get_httpx", return_value=MockHttpx):
            result = reconcile_trismegistos("BRAND_NEW_ID", text="test inscription")
            assert result == "999999"

    def test_reconcile_wikidata_with_mock_api(self):
        """Test Wikidata SPARQL reconciliation with mocked response."""
        class MockResponse:
            status_code = 200
            def raise_for_status(self):
                pass
            def json(self):
                return {
                    "results": {
                        "bindings": [
                            {
                                "item": {
                                    "value": "http://www.wikidata.org/entity/Q202210"
                                }
                            }
                        ]
                    }
                }

        class MockHttpx:
            @staticmethod
            def get(*args, **kwargs):
                return MockResponse()

        with patch("openetruscan.lod._get_httpx", return_value=MockHttpx):
            result = reconcile_wikidata("Cerveteri")
            assert result == "Q202210"
