"""
PeriodO (https://perio.do) period linking — the *time* axis of the Pelagios triad.

Pelagios links the past through place **and time**. The corpus already carries a
signed-year estimate per inscription (``date_approx``; negative = BCE) and a
feature-based period classifier (``openetruscan.core.statistics``). This module
turns either of those into a stable PeriodO period URI so the LOD feed can be
joined on chronology the same way it is joined on Pleiades places.

We link against one coherent authority — the MAPPA Lab Tuscany data model
(PeriodO authority ``p03dzfb``) — whose Etruscan-era periods *tile* the timeline
without gaps or overlaps and are spatially scoped to Tuscany/Etruria. Linking by
the actual year (interval containment) is the primary, most defensible path;
mapping the coarse archaic/classical/late label is a fallback for rows that have
a period label but no numeric estimate.

URIs are the canonical PeriodO ARKs (``http://n2t.net/ark:/99152/<id>``); the IDs
and date bounds below were pulled from the live PeriodO dataset and verified to
resolve. Pure standard library — always importable and unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "PeriodoPeriod",
    "PERIODO_BASE",
    "ETRUSCAN_PERIODS",
    "period_for_year",
    "period_for_label",
    "periodo_uri_for_year",
    "periodo_uri_for_label",
]

PERIODO_BASE = "http://n2t.net/ark:/99152/"


@dataclass(frozen=True)
class PeriodoPeriod:
    """One PeriodO period definition. Years are signed (negative = BCE)."""

    periodo_id: str
    label: str
    label_en: str
    start_year: int  # earliest year, signed (e.g. -580)
    stop_year: int  # latest year, signed (e.g. -481)

    @property
    def uri(self) -> str:
        return f"{PERIODO_BASE}{self.periodo_id}"

    def contains(self, year: int) -> bool:
        return self.start_year <= year <= self.stop_year


# MAPPA Lab Tuscany authority (p03dzfb). These four tile the Etruscan era and are
# what the corpus's date estimates fall into. Ordered earliest → latest.
ETRUSCAN_PERIODS: tuple[PeriodoPeriod, ...] = (
    PeriodoPeriod("p03dzfbxvz2", "Età orientalizzante", "Orientalizing period", -720, -581),
    PeriodoPeriod("p03dzfbdcxr", "Età etrusca arcaica", "Archaic Etruscan Age", -580, -481),
    PeriodoPeriod("p03dzfb58xf", "Età etrusca classica", "Classical Etruscan Age", -480, -324),
    PeriodoPeriod("p03dzfbq5p5", "Età etrusca ellenistica", "Hellenistic Etruscan Age", -323, -90),
)

# Umbrella period spanning the whole Etruscan civilisation, used as a fallback
# when a year sits just outside the tiled sub-periods but still in the era.
ETRUSCAN_UMBRELLA = PeriodoPeriod("p03dzfbsj3d", "Età Etrusca", "Etruscan Civilization", -720, -90)

# Coarse statistics-module labels → the representative tiled period. Used only
# when there's a label but no numeric date.
_LABEL_TO_ID = {
    "archaic": "p03dzfbdcxr",
    "classical": "p03dzfb58xf",
    "late": "p03dzfbq5p5",
}
_PERIODS_BY_ID = {p.periodo_id: p for p in (*ETRUSCAN_PERIODS, ETRUSCAN_UMBRELLA)}


def period_for_year(year: int | None) -> PeriodoPeriod | None:
    """
    Most specific Etruscan-era PeriodO period containing ``year``.

    Falls back to the umbrella "Età Etrusca" period if the year is within the era
    but outside the tiled sub-periods. Returns None for years outside the era or
    for None input.
    """
    if year is None:
        return None
    for period in ETRUSCAN_PERIODS:
        if period.contains(year):
            return period
    if ETRUSCAN_UMBRELLA.contains(year):
        return ETRUSCAN_UMBRELLA
    return None


def period_for_label(label: str | None) -> PeriodoPeriod | None:
    """Map a coarse archaic/classical/late label to its representative period."""
    if not label:
        return None
    pid = _LABEL_TO_ID.get(label.strip().lower())
    return _PERIODS_BY_ID.get(pid) if pid else None


def periodo_uri_for_year(year: int | None) -> str | None:
    period = period_for_year(year)
    return period.uri if period else None


def periodo_uri_for_label(label: str | None) -> str | None:
    period = period_for_label(label)
    return period.uri if period else None
