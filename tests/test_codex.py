"""Tests for Etruscan codex texts data and seeding."""

import os
import tempfile
from pathlib import Path

import yaml

from openetruscan.corpus import Corpus

CODEX_PATH = Path(__file__).parent.parent / "data" / "codex_texts.yaml"


class TestCodexData:
    """Test the codex_texts.yaml data file."""

    def test_codex_file_exists(self):
        assert CODEX_PATH.exists(), "codex_texts.yaml should exist in data/"

    def test_codex_has_six_texts(self):
        with open(CODEX_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert "texts" in data
        assert len(data["texts"]) == 7  # 6 texts but Pyrgi has A+B as separate entries

    def test_each_text_has_required_fields(self):
        with open(CODEX_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for text in data["texts"]:
            assert "id" in text
            assert "title" in text
            assert "classification" in text
            assert "sections" in text
            assert len(text["sections"]) > 0
            for section in text["sections"]:
                assert "id" in section
                assert "raw_text" in section
                assert len(section["raw_text"].strip()) > 0

    def test_liber_linteus_is_longest(self):
        with open(CODEX_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        ll = next(t for t in data["texts"] if t["id"] == "CODEX_LL")
        assert ll["word_count"] >= 1200
        assert ll["columns"] == 12

    def test_pyrgi_tablets_are_dedicatory(self):
        with open(CODEX_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        pyrgi_a = next(t for t in data["texts"] if t["id"] == "CODEX_PY_A")
        pyrgi_b = next(t for t in data["texts"] if t["id"] == "CODEX_PY_B")
        assert pyrgi_a["classification"] == "dedicatory"
        assert pyrgi_b["classification"] == "dedicatory"

    def test_legal_texts_classified(self):
        with open(CODEX_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        cp = next(t for t in data["texts"] if t["id"] == "CODEX_CP")
        tco = next(t for t in data["texts"] if t["id"] == "CODEX_TCo")
        assert cp["classification"] == "legal"
        assert tco["classification"] == "legal"


class TestCodexSeeding:
    """Test codex import into corpus."""

    def setup_method(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

    def teardown_method(self):
        Path(self.db_path).unlink(missing_ok=True)

    def test_seed_codex_imports_sections(self):
        """Test that seed_codex imports all sections."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        from seed_larth import seed_codex

        count = seed_codex(db_path=self.db_path)
        assert count >= 12  # At least 12 sections across 6 texts

        corpus = Corpus.load(self.db_path)
        assert corpus.count() >= 12

        # Search by direct ID
        all_results = corpus.search(limit=999)
        codex_ids = [i.id for i in all_results if i.id.startswith("CODEX_")]
        assert len(codex_ids) >= 12

        corpus.close()

    def test_codex_sections_have_metadata(self):
        """Verify codex sections retain scholarly metadata."""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        from seed_larth import seed_codex

        seed_codex(db_path=self.db_path)
        corpus = Corpus.load(self.db_path)

        all_results = corpus.search(limit=999)
        pyrgi = next((i for i in all_results if i.id == "CODEX_PY_A_1"), None)
        assert pyrgi is not None
        assert pyrgi.findspot == "Pyrgi"
        assert pyrgi.classification == "dedicatory"
        assert pyrgi.medium == "gold"
        assert pyrgi.provenance_status == "verified"
        assert pyrgi.date_approx == -500
        assert "Pallottino" in pyrgi.bibliography

        corpus.close()
