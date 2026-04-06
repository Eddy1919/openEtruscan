"""
CLTK Language definition for Etruscan.

Follows the exact data model used in cltk.languages.glottolog.
Glottolog ID: etru1241
ISO 639-3:    ett
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

# ── Lightweight replicas of CLTK data types ──────────────────────────
#
# We define these locally so the module works WITHOUT cltk installed.
# When contributed upstream, these classes are imported from
# ``cltk.core.data_types``.
# ─────────────────────────────────────────────────────────────────────


@dataclass
class Identifier:
    """Represents a unique identifier for a language (e.g. Glottolog code)."""
    scheme: str
    value: str


@dataclass
class GeoPoint:
    """Represents a geographic coordinate (latitude, longitude)."""
    lat: float
    lon: float


@dataclass
class GeoArea:
    """Represents a geographic region defined by countries and centroids."""
    centroid: GeoPoint | None = None
    macroareas: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)


@dataclass
class Timespan:
    """Represents the historical temporal bounds of a language's usage."""
    start: str | None = None
    end: str | None = None
    note: str = ""


@dataclass
class Classification:
    """Represents the genealogical classification of a language in Glottolog."""
    level: str = "language"
    parent_glottocode: str = ""
    lineage: list[str] = field(default_factory=list)
    children_glottocodes: list[str] = field(default_factory=list)


@dataclass
class NameVariant:
    """Represents an alternative name for a language from a specific source."""
    value: str
    source: str
    script: str | None = None
    language: str | None = None


@dataclass
class Dialect:
    """Represents a specific sub-variety or dialect of a language."""
    glottolog_id: str
    language_code: str
    name: str
    status: str = "unknown"
    alt_names: list[NameVariant] = field(default_factory=list)
    identifiers: list[Identifier] = field(default_factory=list)
    geo: GeoArea | None = None
    timespan: Timespan | None = None
    scripts: list[Any] = field(default_factory=list)
    orthographies: list[Any] = field(default_factory=list)
    sources: list[Any] = field(default_factory=list)
    links: list[Any] = field(default_factory=list)


@dataclass
class Language:
    """The central data model for a language, following the CLTK standard."""
    name: str
    glottolog_id: str
    identifiers: list[Identifier] = field(default_factory=list)
    level: str = "language"
    status: str = "unknown"
    type: str | None = None
    geo: GeoArea | None = None
    timespan: Timespan | None = None
    classification: Classification | None = None
    family_id: str = ""
    parent_id: str = ""
    iso: str = ""
    iso_set: dict[str, str] = field(default_factory=dict)
    alt_names: list[NameVariant] = field(default_factory=list)
    scripts: list[Any] = field(default_factory=list)
    orthographies: list[Any] = field(default_factory=list)
    sources: list[Any] = field(default_factory=list)
    links: list[Any] = field(default_factory=list)
    dialects: list[Dialect] = field(default_factory=list)
    default_variety_id: str | None = None
    glottolog_version: str | None = None
    commit_sha: str = ""
    last_updated: date | None = None
    endangerment: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    dates: list[Any] = field(default_factory=list)
    newick: str | None = None


# ── Etruscan Language Definition ─────────────────────────────────────

ETRUSCAN_LANGUAGE = Language(
    name="Etruscan",
    glottolog_id="etru1241",
    identifiers=[
        Identifier(scheme="glottocode", value="etru1241"),
        Identifier(scheme="iso639-3", value="ett"),
    ],
    level="language",
    status="extinct",
    type=None,
    geo=GeoArea(
        centroid=GeoPoint(lat=42.75, lon=11.75),
        macroareas=["Eurasia"],
        countries=["IT"],
    ),
    timespan=Timespan(
        start=None,
        end=None,
        note="-0700-01-01/0100-01-01",
    ),
    classification=Classification(
        level="language",
        parent_glottocode="tyrs1239",
        lineage=["tyrs1239"],
        children_glottocodes=[],
    ),
    family_id="tyrs1239",
    parent_id="tyrs1239",
    iso="ett",
    iso_set={"639-3": "ett"},
    alt_names=[
        # Multitree / standard
        NameVariant(value="Etruscan", source="multitree"),
        NameVariant(value="Etruscan language", source="multitree"),
        # Lexvo — multilingual
        NameVariant(value="Etruscan", source="lexvo", language="en"),
        NameVariant(value="Étrusque", source="lexvo", language="fr"),
        NameVariant(value="Etruskische Sprache", source="lexvo", language="de"),
        NameVariant(value="Lingua etrusca", source="lexvo", language="it"),
        NameVariant(value="Idioma etrusco", source="lexvo", language="es"),
        NameVariant(value="Língua etrusca", source="lexvo", language="pt"),
        NameVariant(value="Этрусский язык", source="lexvo", language="ru"),
        NameVariant(value="Etruskiska", source="lexvo", language="sv"),
        NameVariant(value="Etruskisch", source="lexvo", language="nl"),
        NameVariant(value="Etruszk nyelv", source="lexvo", language="hu"),
        NameVariant(value="Język etruski", source="lexvo", language="pl"),
        NameVariant(value="エトルリア語", source="lexvo", language="ja"),
        NameVariant(value="伊特拉斯坎語", source="lexvo", language="zh"),
        # Glottolog scholarly
        NameVariant(value="Rasena", source="hhbib_lgcode"),
        NameVariant(value="Rasna", source="hhbib_lgcode"),
    ],
    scripts=[],
    orthographies=[],
    sources=[],
    links=[],
    dialects=[
        Dialect(
            glottolog_id="nort3230",
            language_code="nort3230",
            name="Northern Etruscan",
            status="unknown",
            alt_names=[
                NameVariant(value="Clusium", source="glottolog"),
                NameVariant(value="Perugia", source="glottolog"),
            ],
            identifiers=[
                Identifier(scheme="glottocode", value="nort3230"),
            ],
            geo=GeoArea(
                centroid=None,
                macroareas=["Eurasia"],
                countries=["IT"],
            ),
        ),
        Dialect(
            glottolog_id="sout3229",
            language_code="sout3229",
            name="Southern Etruscan",
            status="unknown",
            alt_names=[
                NameVariant(value="Caere", source="glottolog"),
                NameVariant(value="Tarquinia", source="glottolog"),
                NameVariant(value="Veii", source="glottolog"),
            ],
            identifiers=[
                Identifier(scheme="glottocode", value="sout3229"),
            ],
            geo=GeoArea(
                centroid=None,
                macroareas=["Eurasia"],
                countries=["IT"],
            ),
        ),
    ],
    default_variety_id=None,
    glottolog_version=None,
    commit_sha="",
    last_updated=date(2026, 3, 23),
    endangerment="extinct",
    latitude=42.75,
    longitude=11.75,
    dates=[],
    newick=None,
)
