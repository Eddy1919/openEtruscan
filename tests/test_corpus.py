"""Tests for the corpus module."""

import os
import tempfile
from pathlib import Path

from openetruscan.corpus import Corpus, Inscription, auto_flag_inscription


class TestCorpus:
    """Test corpus operations."""

    def setup_method(self):
        # Use temp database for each test
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.corpus = Corpus.load(self.db_path)

    def teardown_method(self):
        self.corpus.close()
        Path(self.db_path).unlink(missing_ok=True)

    def test_create_empty_corpus(self):
        assert self.corpus.count() == 0

    def test_add_inscription(self):
        insc = Inscription(id="TEST_001", raw_text="LARTHAL LECNES", findspot="Cerveteri")
        self.corpus.add(insc)
        assert self.corpus.count() == 1

    def test_auto_normalize_on_add(self):
        insc = Inscription(id="TEST_001", raw_text="LARTHAL")
        self.corpus.add(insc)
        results = self.corpus.search(text="larθal")
        assert len(results) == 1
        assert results.inscriptions[0].canonical == "larθal"

    def test_search_by_text(self):
        self.corpus.add(Inscription(id="T1", raw_text="Larθal Lecnes", findspot="Cerveteri"))
        self.corpus.add(Inscription(id="T2", raw_text="Arnθ Velchas", findspot="Tarquinia"))
        results = self.corpus.search(text="*lecnes*")
        assert len(results) == 1
        assert results.inscriptions[0].id == "T1"

    def test_search_by_findspot(self):
        self.corpus.add(Inscription(id="T1", raw_text="Larθal", findspot="Cerveteri"))
        self.corpus.add(Inscription(id="T2", raw_text="Arnθ", findspot="Tarquinia"))
        results = self.corpus.search(findspot="Cerveteri")
        assert len(results) == 1

    def test_search_by_date_range(self):
        self.corpus.add(Inscription(id="T1", raw_text="Larθal", date_approx=-400))
        self.corpus.add(Inscription(id="T2", raw_text="Arnθ", date_approx=-200))
        results = self.corpus.search(date_range=(-500, -300))
        assert len(results) == 1
        assert results.inscriptions[0].id == "T1"

    def test_export_csv(self):
        self.corpus.add(Inscription(id="T1", raw_text="Larθal", findspot="Cerveteri"))
        csv_out = self.corpus.export_all("csv")
        assert "Cerveteri" in csv_out
        assert "T1" in csv_out

    def test_export_json(self):
        self.corpus.add(Inscription(id="T1", raw_text="Larθal"))
        json_out = self.corpus.export_all("json")
        assert '"id": "T1"' in json_out

    def test_export_geojson(self):
        self.corpus.add(
            Inscription(
                id="T1",
                raw_text="Larθal",
                findspot_lat=42.0,
                findspot_lon=12.0,
            )
        )
        geojson = self.corpus.export_all("geojson")
        assert '"FeatureCollection"' in geojson

    def test_import_csv(self):
        csv_content = "id,text,findspot\nCSV_001,LARTHAL,Cerveteri\nCSV_002,ARNTH,Tarquinia\n"
        fd, tmp_csv_path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        tmp_csv = Path(tmp_csv_path)
        tmp_csv.write_text(csv_content)
        count = self.corpus.import_csv(tmp_csv)
        assert count == 2
        assert self.corpus.count() == 2
        tmp_csv.unlink()

    def test_date_display(self):
        insc = Inscription(id="T1", raw_text="X", date_approx=-350, date_uncertainty=25)
        assert insc.date_display() == "350 ± 25 BCE"

    def test_date_display_undated(self):
        insc = Inscription(id="T1", raw_text="X")
        assert insc.date_display() == "undated"


class TestProvenance:
    """Test provenance pipeline (quarantine, auto-flag, review)."""

    def setup_method(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.corpus = Corpus.load(self.db_path)

    def teardown_method(self):
        self.corpus.close()
        Path(self.db_path).unlink(missing_ok=True)

    def test_auto_flag_out_of_range_coords(self):
        insc = Inscription(
            id="FLAG1", raw_text="larθal", canonical="larθal",
            findspot_lat=-77.0, findspot_lon=166.0,  # Antarctica
        )
        flags = auto_flag_inscription(insc)
        assert any("lat_out_of_range" in f for f in flags)
        assert any("lon_out_of_range" in f for f in flags)

    def test_auto_flag_non_alphabet_chars(self):
        insc = Inscription(
            id="FLAG2", raw_text="larθal@#", canonical="larθal@#",
        )
        flags = auto_flag_inscription(insc)
        assert any("non_alphabet_chars" in f for f in flags)

    def test_auto_flag_clean_inscription(self):
        insc = Inscription(
            id="CLEAN", raw_text="larθal", canonical="larθal",
            findspot_lat=42.0, findspot_lon=12.0,
        )
        flags = auto_flag_inscription(insc)
        assert len(flags) == 0

    def test_review_quarantine_verify(self):
        insc = Inscription(
            id="Q1", raw_text="test", provenance_status="quarantined",
        )
        self.corpus.add(insc)
        success = self.corpus.review_quarantine("Q1", action="verify")
        assert success is True
        # Verify the status was updated
        results = self.corpus.search(provenance_status="verified")
        found = [i for i in results if i.id == "Q1"]
        assert len(found) == 1

    def test_review_quarantine_nonexistent(self):
        success = self.corpus.review_quarantine("NONEXIST")
        assert success is False

    def test_provenance_status_filter(self):
        self.corpus.add(Inscription(
            id="V1", raw_text="verified", provenance_status="verified",
        ))
        self.corpus.add(Inscription(
            id="Q1", raw_text="quarantined", provenance_status="quarantined",
        ))
        verified = self.corpus.search(provenance_status="verified")
        quarantined = self.corpus.search(provenance_status="quarantined")
        assert any(i.id == "V1" for i in verified)
        assert any(i.id == "Q1" for i in quarantined)
        assert not any(i.id == "Q1" for i in verified)

    def test_near_duplicate_detected(self):
        # Add an inscription, then check a near-duplicate against it
        self.corpus.add(Inscription(
            id="ORIG", raw_text="larθal spurinas lecnes",
            canonical="larθal spurinas lecnes",
        ))
        duplicate = Inscription(
            id="DUP", raw_text="larθal spurinas lecnes",
            canonical="larθal spurinas lecnes",
        )
        flags = auto_flag_inscription(duplicate, corpus=self.corpus)
        assert any("near_duplicate" in f for f in flags)
        assert any("ORIG" in f for f in flags)

    def test_distinct_text_not_flagged(self):
        self.corpus.add(Inscription(
            id="A", raw_text="larθal spurinas",
            canonical="larθal spurinas",
        ))
        different = Inscription(
            id="B", raw_text="ramθa matunai θana",
            canonical="ramθa matunai θana",
        )
        flags = auto_flag_inscription(different, corpus=self.corpus)
        assert not any("near_duplicate" in f for f in flags)

    def test_dedup_without_corpus_skips(self):
        insc = Inscription(id="X", raw_text="test", canonical="test")
        flags = auto_flag_inscription(insc)  # No corpus → no dedup
        assert not any("near_duplicate" in f for f in flags)
