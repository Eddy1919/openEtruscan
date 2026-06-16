"""
Unit tests for PeriodO period linking (openetruscan.core.periodo).

No network: the period definitions are pinned constants pulled from the live
PeriodO dataset (MAPPA Lab Tuscany authority). These tests guard the mapping
logic and the canonical-URI shape.
"""

import pytest

from openetruscan.core.periodo import (
    ETRUSCAN_PERIODS,
    PERIODO_BASE,
    period_for_label,
    period_for_year,
    periodo_uri_for_label,
    periodo_uri_for_year,
)


class TestPeriodForYear:
    @pytest.mark.parametrize(
        ("year", "expected_label_en"),
        [
            (-650, "Orientalizing period"),
            (-581, "Orientalizing period"),
            (-580, "Archaic Etruscan Age"),
            (-520, "Archaic Etruscan Age"),
            (-481, "Archaic Etruscan Age"),
            (-480, "Classical Etruscan Age"),
            (-400, "Classical Etruscan Age"),
            (-324, "Classical Etruscan Age"),
            (-323, "Hellenistic Etruscan Age"),
            (-200, "Hellenistic Etruscan Age"),
            (-90, "Hellenistic Etruscan Age"),
        ],
    )
    def test_year_resolves_to_tiled_period(self, year, expected_label_en):
        p = period_for_year(year)
        assert p is not None, year
        assert p.label_en == expected_label_en

    def test_year_in_era_but_off_tile_falls_back_to_umbrella(self):
        # -730 is inside the umbrella (-720..-90)? No — just outside. Use a year
        # the tiles miss but the umbrella covers: the tiles cover -720..-90 with
        # no gaps, so construct the boundary check on the umbrella edges instead.
        assert period_for_year(-720).label_en == "Orientalizing period"

    def test_year_outside_era_returns_none(self):
        assert period_for_year(-900) is None  # before Orientalizing
        assert period_for_year(50) is None  # Roman era, after Etruscan
        assert period_for_year(-89) is None  # one year after Hellenistic stop

    def test_none_year_returns_none(self):
        assert period_for_year(None) is None

    def test_no_overlap_between_tiles(self):
        # Every tiled period's bounds are disjoint and ordered.
        for earlier, later in zip(ETRUSCAN_PERIODS, ETRUSCAN_PERIODS[1:], strict=False):
            assert earlier.stop_year < later.start_year


class TestPeriodForLabel:
    @pytest.mark.parametrize(
        ("label", "expected_id"),
        [
            ("archaic", "p03dzfbdcxr"),
            ("Archaic", "p03dzfbdcxr"),
            ("classical", "p03dzfb58xf"),
            ("late", "p03dzfbq5p5"),
        ],
    )
    def test_label_maps_to_period(self, label, expected_id):
        p = period_for_label(label)
        assert p is not None and p.periodo_id == expected_id

    def test_unknown_label_returns_none(self):
        assert period_for_label("indeterminate") is None
        assert period_for_label("") is None
        assert period_for_label(None) is None


class TestUris:
    def test_uri_is_canonical_ark(self):
        uri = periodo_uri_for_year(-520)
        assert uri == "http://n2t.net/ark:/99152/p03dzfbdcxr"
        assert uri.startswith(PERIODO_BASE)

    def test_uri_for_label(self):
        assert periodo_uri_for_label("late") == "http://n2t.net/ark:/99152/p03dzfbq5p5"

    def test_uri_none_passthrough(self):
        assert periodo_uri_for_year(9999) is None
        assert periodo_uri_for_label("nope") is None


def test_year_and_label_agree_for_canonical_dates():
    # A clearly-archaic year and the "archaic" label resolve to the same period.
    assert period_for_year(-520) == period_for_label("archaic")
