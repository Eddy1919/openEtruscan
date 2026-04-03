"""Tests for the corpus module."""

from openetruscan.corpus import Corpus, Inscription, auto_flag_inscription

_TEST_INSCRIPTIONS_TABLE = "test_inscriptions"


class TestCorpus:
    """Test corpus operations."""

    def setup_method(self):
        # Connect to PG but use savepoint-level isolation
        self.corpus = Corpus.load()
        # Clear only test data at start (idempotent)
        with self.corpus._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM inscriptions WHERE id LIKE 'TEST_%'"
                " OR id LIKE 'T_' OR id LIKE 'T%' AND length(id) <= 3"
            )
        self.corpus._conn.commit()

    def teardown_method(self):
        # Clean up test data
        with self.corpus._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM inscriptions WHERE id LIKE 'TEST_%' OR id LIKE 'T_' "
                "OR id IN ('T1','T2','CSV_001','CSV_002')"
            )
        self.corpus._conn.commit()

    def test_add_inscription(self):
        insc = Inscription(
            id="TEST_001",
            raw_text="LARTHAL LECNES",
            canonical="larthal lecnes",
            findspot="Cerveteri",
        )
        self.corpus.add(insc)
        results = self.corpus.search(text="larthal")
        found = [i for i in results if i.id == "TEST_001"]
        assert len(found) >= 1

    def test_auto_normalize_on_add(self):
        insc = Inscription(id="TEST_001", raw_text="LARTHAL", canonical="larthal")
        self.corpus.add(insc)
        results = self.corpus.search(text="larthal")
        found = [i for i in results if i.id == "TEST_001"]
        assert len(found) >= 1

    def test_search_by_findspot(self):
        self.corpus.add(
            Inscription(id="T1", raw_text="Larθal", canonical="larθal", findspot="Cerveteri")
        )
        self.corpus.add(
            Inscription(id="T2", raw_text="Arnθ", canonical="arnθ", findspot="Tarquinia")
        )
        results = self.corpus.search(findspot="Cerveteri")
        found = [i for i in results if i.id == "T1"]
        assert len(found) >= 1

    def test_search_by_date_range(self):
        self.corpus.add(
            Inscription(id="T1", raw_text="Larθal", canonical="larθal", date_approx=-400)
        )
        self.corpus.add(Inscription(id="T2", raw_text="Arnθ", canonical="arnθ", date_approx=-200))
        results = self.corpus.search(date_range=(-500, -300))
        found = [i for i in results if i.id == "T1"]
        assert len(found) >= 1

    def test_date_display(self):
        insc = Inscription(id="T1", raw_text="X", date_approx=-350, date_uncertainty=25)
        assert insc.date_display() == "350 ± 25 BCE"

    def test_date_display_undated(self):
        insc = Inscription(id="T1", raw_text="X")
        assert insc.date_display() == "undated"


class TestProvenance:
    """Test provenance pipeline (quarantine, auto-flag, review)."""

    def setup_method(self):
        self.corpus = Corpus.load()
        with self.corpus._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM inscriptions WHERE id IN "
                "('FLAG1','FLAG2','CLEAN','Q1','V1','ORIG','DUP','A','B','X')"
            )
        self.corpus._conn.commit()

    def teardown_method(self):
        with self.corpus._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM inscriptions WHERE id IN "
                "('FLAG1','FLAG2','CLEAN','Q1','V1','ORIG','DUP','A','B','X')"
            )
        self.corpus._conn.commit()

    def test_auto_flag_out_of_range_coords(self):
        insc = Inscription(
            id="FLAG1",
            raw_text="larθal",
            canonical="larθal",
            findspot_lat=-77.0,
            findspot_lon=166.0,  # Antarctica
        )
        flags = auto_flag_inscription(insc)
        assert any("lat_out_of_range" in f for f in flags)
        assert any("lon_out_of_range" in f for f in flags)

    def test_auto_flag_non_alphabet_chars(self):
        insc = Inscription(
            id="FLAG2",
            raw_text="larθal@#",
            canonical="larθal@#",
        )
        flags = auto_flag_inscription(insc)
        assert any("non_alphabet_chars" in f for f in flags)

    def test_auto_flag_clean_inscription(self):
        insc = Inscription(
            id="CLEAN",
            raw_text="larθal",
            canonical="larθal",
            findspot_lat=42.0,
            findspot_lon=12.0,
        )
        flags = auto_flag_inscription(insc)
        assert len(flags) == 0

    def test_review_quarantine_verify(self):
        insc = Inscription(
            id="Q1",
            raw_text="test",
            provenance_status="quarantined",
        )
        self.corpus.add(insc)
        success = self.corpus.review_quarantine("Q1", action="verify")
        assert success is True
        results = self.corpus.search(provenance_status="verified")
        found = [i for i in results if i.id == "Q1"]
        assert len(found) == 1

    def test_review_quarantine_nonexistent(self):
        success = self.corpus.review_quarantine("NONEXIST")
        assert success is False

    def test_provenance_status_filter(self):
        self.corpus.add(
            Inscription(
                id="V1",
                raw_text="verified",
                provenance_status="verified",
            )
        )
        self.corpus.add(
            Inscription(
                id="Q1",
                raw_text="quarantined",
                provenance_status="quarantined",
            )
        )
        verified = self.corpus.search(provenance_status="verified")
        quarantined = self.corpus.search(provenance_status="quarantined")
        assert any(i.id == "V1" for i in verified)
        assert any(i.id == "Q1" for i in quarantined)

    def test_near_duplicate_detected(self):
        self.corpus.add(
            Inscription(
                id="ORIG",
                raw_text="larθal spurinas lecnes",
                canonical="larθal spurinas lecnes",
            )
        )
        duplicate = Inscription(
            id="DUP",
            raw_text="larθal spurinas lecnes",
            canonical="larθal spurinas lecnes",
        )
        flags = auto_flag_inscription(duplicate, corpus=self.corpus)
        assert any("near_duplicate" in f for f in flags)
        assert any("ORIG" in f for f in flags)

    def test_distinct_text_not_flagged(self):
        self.corpus.add(
            Inscription(
                id="A",
                raw_text="larθal spurinas",
                canonical="larθal spurinas",
            )
        )
        different = Inscription(
            id="B",
            raw_text="ramθa matunai θana",
            canonical="ramθa matunai θana",
        )
        flags = auto_flag_inscription(different, corpus=self.corpus)
        assert not any("near_duplicate" in f for f in flags)

    def test_dedup_without_corpus_skips(self):
        insc = Inscription(id="X", raw_text="test", canonical="test")
        flags = auto_flag_inscription(insc)  # No corpus → no dedup
        assert not any("near_duplicate" in f for f in flags)
