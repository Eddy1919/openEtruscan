"""Inscription records, search results, and the controlled vocabularies they use."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Classification constants
# ---------------------------------------------------------------------------

CLASSIFICATIONS = (
    "funerary",
    "votive",
    "legal",
    "commercial",
    "boundary",
    "ownership",
    "dedicatory",
    "unknown",
)

SCRIPT_SYSTEMS = ("old_italic", "latin", "greek", "other")
COMPLETENESS_VALUES = ("complete", "fragmentary", "illegible")

# Tiered provenance vocabulary. See migration `a1f2c3d4e5f6_provenance_integrity`
# for the rationale. The four values describe the *archaeological* status of an
# inscription, not the editorial status of its text:
#   - excavated:             documented stratigraphic recovery (curator-set).
#   - acquired_documented:   findspot named in the bibliography, no dig context.
#   - acquired_undocumented: no findspot recorded; "Discovery Vector".
#   - unknown:               not yet assessed.
PROVENANCE_STATUSES = (
    "excavated",
    "acquired_documented",
    "acquired_undocumented",
    "unknown",
)

# `has_provenance` (used as a /search facet) is True when the row sits in either
# tier that asserts a known archaeological location. Conservative on purpose —
# `acquired_documented` does NOT mean we know the dig context, only that we know
# *where* the object surfaced; that's already enough for spatial citation work.
PROVENANCE_KINDS_WITH_PROVENANCE = ("excavated", "acquired_documented")
PROVENANCE_KINDS_WITHOUT_PROVENANCE = ("acquired_undocumented", "unknown")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Inscription:
    """A single inscription record."""

    id: str
    raw_text: str
    canonical: str = ""
    phonetic: str = ""
    old_italic: str = ""
    findspot: str = ""
    findspot_lat: float | None = None
    findspot_lon: float | None = None
    findspot_uncertainty_m: int | None = None
    date_approx: int | None = None  # negative = BCE
    date_uncertainty: int | None = None  # +/- years
    medium: str = ""
    object_type: str = ""
    source: str = ""
    bibliography: str = ""
    notes: str = ""
    # Classification fields
    language: str = "etruscan"
    classification: str = "unknown"
    script_system: str = "old_italic"
    completeness: str = "complete"
    provenance_status: str | None = "unknown"
    provenance_flags: list[str] = field(default_factory=list)
    trismegistos_id: str | None = None
    eagle_id: str | None = None
    pleiades_id: str | None = None
    geonames_id: str | None = None
    zotero_id: str | None = None
    is_codex: bool = False
    source_code: str = "unknown"
    source_detail: str | None = None
    original_script_entry: str | None = None

    def date_display(self) -> str:
        """Human-readable date string."""
        if self.date_approx is None:
            return "undated"
        era = "BCE" if self.date_approx < 0 else "CE"
        year = abs(self.date_approx)
        if self.date_uncertainty:
            return f"{year} ± {self.date_uncertainty} {era}"
        return f"{year} {era}"

    def to_dict(self) -> dict:
        """Serialize the inscription to a dictionary for API and export formats."""
        return {
            "id": self.id,
            "raw_text": self.raw_text,
            "canonical": self.canonical,
            "phonetic": self.phonetic,
            "old_italic": self.old_italic,
            "findspot": self.findspot,
            "findspot_lat": self.findspot_lat,
            "findspot_lon": self.findspot_lon,
            "findspot_uncertainty_m": self.findspot_uncertainty_m,
            "date_approx": self.date_approx,
            "date_uncertainty": self.date_uncertainty,
            "medium": self.medium,
            "object_type": self.object_type,
            "source": self.source,
            "bibliography": self.bibliography,
            "notes": self.notes,
            "language": self.language,
            "classification": self.classification,
            "script_system": self.script_system,
            "completeness": self.completeness,
            "provenance_status": self.provenance_status,
            "provenance_flags": self.provenance_flags,
            "trismegistos_id": self.trismegistos_id,
            "eagle_id": self.eagle_id,
            "pleiades_id": self.pleiades_id,
            "geonames_id": self.geonames_id,
            "zotero_id": self.zotero_id,
            "is_codex": self.is_codex,
        }


@dataclass
class SearchResults:
    """Container for corpus search results."""

    inscriptions: list[Inscription] = field(default_factory=list)
    total: int = 0

    def __len__(self) -> int:
        """Return the number of inscriptions in the collection."""
        return len(self.inscriptions)

    def __iter__(self) -> Iterator[Inscription]:
        """Iterate over the inscriptions in the collection."""
        return iter(self.inscriptions)

    def export(self, fmt: str = "csv") -> str:
        """Export results to string in specified format."""
        if fmt == "csv":
            return self._to_csv()
        elif fmt == "json":
            data = [i.to_dict() for i in self.inscriptions]
            return json.dumps(data, ensure_ascii=False, indent=2)
        elif fmt == "jsonl":
            lines = [json.dumps(i.to_dict(), ensure_ascii=False) for i in self.inscriptions]
            return "\n".join(lines)
        elif fmt == "geojson":
            return self._to_geojson()
        else:
            raise ValueError(f"Unknown format: {fmt}. Use: csv, json, jsonl, geojson")

    def _to_csv(self) -> str:
        """Export the collection to a CSV string with standard header mapping."""
        import io

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "id",
                "canonical",
                "findspot",
                "date",
                "medium",
                "source",
                "language",
                "classification",
            ]
        )
        for i in self.inscriptions:
            writer.writerow(
                [
                    i.id,
                    i.canonical,
                    i.findspot,
                    i.date_display(),
                    i.medium,
                    i.source,
                    i.language,
                    i.classification,
                ]
            )
        return buf.getvalue()

    def _to_geojson(self) -> str:
        """Export the search results as a GeoJSON FeatureCollection for map rendering."""
        features = []
        for i in self.inscriptions:
            if i.findspot_lat is not None and i.findspot_lon is not None:
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [i.findspot_lon, i.findspot_lat],
                        },
                        "properties": {
                            "id": i.id,
                            "text": i.canonical,
                            "findspot": i.findspot,
                            "date": i.date_display(),
                            "language": i.language,
                            "classification": i.classification,
                        },
                    }
                )
        collection = {
            "type": "FeatureCollection",
            "features": features,
        }
        return json.dumps(collection, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dict_to_inscription(row: dict) -> Inscription:
    """Convert a PostgreSQL dict row to Inscription."""
    return Inscription(
        id=row["id"],
        raw_text=row["raw_text"],
        canonical=row["canonical"],
        phonetic=row["phonetic"],
        old_italic=row["old_italic"],
        findspot=row["findspot"],
        findspot_lat=row.get("findspot_lat"),
        findspot_lon=row.get("findspot_lon"),
        date_approx=row.get("date_approx"),
        date_uncertainty=row.get("date_uncertainty"),
        medium=row.get("medium", ""),
        object_type=row.get("object_type", ""),
        source=row.get("source", ""),
        bibliography=row.get("bibliography", ""),
        notes=row.get("notes", ""),
        language=row.get("language", "etruscan"),
        classification=row.get("classification", "unknown"),
        # NULL-safe: the DDL declares both NOT NULL, but rows read through
        # views or partial SELECTs may omit them. Fall back to the
        # Inscription dataclass defaults rather than passing None into a
        # str-typed field.
        script_system=row.get("script_system") or "old_italic",
        completeness=row.get("completeness") or "complete",
        provenance_status=row.get("provenance_status", "verified"),
        provenance_flags=(
            [] if not row.get("provenance_flags") else row["provenance_flags"].split(",")
        ),
        trismegistos_id=row.get("trismegistos_id"),
        eagle_id=row.get("eagle_id"),
        pleiades_id=row.get("pleiades_id"),
        geonames_id=row.get("geonames_id"),
        is_codex=row.get("is_codex", False),
    )


def _safe_float(val: str | None) -> float | None:
    """Safe conversion of string/none to float for coordinate and measurement fields."""
    if not val or val.strip() == "":
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _safe_int(val: str | None) -> int | None:
    """Safe conversion of string/none to integer for ID and year fields."""
    if not val or val.strip() == "":
        return None
    try:
        return int(float(val))
    except ValueError:
        return None
