"""Tests for the corpus module."""

import tempfile
from pathlib import Path

from openetruscan.corpus import Corpus, Inscription


class TestCorpus:
    """Test corpus operations."""

    def setup_method(self):
        # Use temp database for each test
        self.db_path = tempfile.mktemp(suffix=".db")
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
        tmp_csv = Path(tempfile.mktemp(suffix=".csv"))
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
