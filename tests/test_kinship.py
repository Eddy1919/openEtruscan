"""Tests for the kinship reconciliation engine.

KinshipReconciler only talks to the database through ``corpus._conn.cursor()``,
so these tests drive it with an in-memory fake connection: no Postgres needed,
and the conflict-detection logic is exercised deterministically.
"""

from openetruscan.core.kinship import KinshipReconciler, _epigraphic_conflicts


class _FakeCursor:
    """Returns canned rows keyed on which table the executed SQL touches."""

    def __init__(self, rows_by_table):
        self._rows_by_table = rows_by_table
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        if "genetic_samples" in query:
            self._rows = self._rows_by_table.get("genetic_samples", [])
        elif "relationships" in query:
            self._rows = self._rows_by_table.get("relationships", [])
        else:
            self._rows = []

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows_by_table):
        self._rows_by_table = rows_by_table

    def cursor(self):
        return _FakeCursor(self._rows_by_table)


class _FakeCorpus:
    def __init__(self, rows_by_table):
        self._conn = _FakeConn(rows_by_table)


class TestEpigraphicConflicts:
    """Unit tests for the pure conflict-detection helper."""

    def test_no_conflict_for_distinct_pairs(self):
        links = [
            ("P1", "P2", "CHILD_OF"),
            ("P1", "P3", "PUIA_OF"),
        ]
        assert _epigraphic_conflicts(links) == []

    def test_duplicate_same_type_is_not_a_conflict(self):
        links = [
            ("P1", "P2", "CHILD_OF"),
            ("P1", "P2", "CHILD_OF"),
        ]
        assert _epigraphic_conflicts(links) == []

    def test_clan_membership_rows_are_skipped(self):
        # related_person_id IS NULL for clan-membership rows (see the
        # relationships CHECK constraint); they must not count as pairs.
        links = [
            ("P1", None, "MEMBER_OF"),
            ("P1", None, "CHILD_OF"),
        ]
        assert _epigraphic_conflicts(links) == []

    def test_conflicting_types_for_same_pair_are_flagged(self):
        links = [
            ("P1", "P2", "CHILD_OF"),
            ("P1", "P2", "PUIA_OF"),
            ("P3", "P4", "CHILD_OF"),
        ]
        conflicts = _epigraphic_conflicts(links)
        assert len(conflicts) == 1
        assert conflicts[0]["person_a"] == "P1"
        assert conflicts[0]["person_b"] == "P2"
        assert conflicts[0]["relationship_types"] == ["CHILD_OF", "PUIA_OF"]


class TestAuditKinship:
    """End-to-end audit_kinship over the fake connection."""

    def test_clean_tomb_reports_no_conflicts(self):
        corpus = _FakeCorpus(
            {
                "genetic_samples": [
                    ("S1", "R1b", "H1", "male"),
                    ("S2", "R1b", "H2", "male"),
                ],
                "relationships": [
                    ("P1", "P2", "CHILD_OF"),
                ],
            }
        )
        report = KinshipReconciler(corpus).audit_kinship("Tomba dei Scudi")

        assert report["tomb_id"] == "Tomba dei Scudi"
        assert report["potential_conflicts"] == []
        # Shared Y-haplogroup R1b → one paternal biological link
        assert any(
            link["type"] == "paternal" and link["marker"] == "R1b"
            for link in report["biological_links"]
        )
        assert report["epigraphic_links"] == [("P1", "P2", "CHILD_OF")]

    def test_contradictory_epigraphic_claims_are_flagged(self):
        corpus = _FakeCorpus(
            {
                "genetic_samples": [],
                "relationships": [
                    ("P1", "P2", "CHILD_OF"),
                    ("P1", "P2", "PUIA_OF"),
                ],
            }
        )
        report = KinshipReconciler(corpus).audit_kinship("Tomba Golini")

        assert len(report["potential_conflicts"]) == 1
        conflict = report["potential_conflicts"][0]
        assert (conflict["person_a"], conflict["person_b"]) == ("P1", "P2")
        assert conflict["relationship_types"] == ["CHILD_OF", "PUIA_OF"]
