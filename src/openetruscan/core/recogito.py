"""
Recogito (https://recogito.pelagios.org) round-trip.

Recogito is Pelagios's collaborative annotation tool. This module lets the v2
LLM-jury adjudication queue go *out* to Recogito so human philologists can
adjudicate in the community's own tool, and lets Recogito's annotation export
come *back* in — harvesting two things:

  * **PLACE annotations** resolved to a Pleiades URI → findspot → Pleiades-ID
    links, which feed the same ``data/pleiades_mapping.yaml`` the place-axis
    pipeline writes (see ``docs/PELAGIOS.md``). Recogito becomes a second,
    human-curated source of place links.
  * **TAGS** on a row → the philologist's classification decision, folded back
    into the adjudication queue.

Recogito's annotation CSV export has shifted column names across versions, so
parsing is deliberately tolerant: headers are matched case-insensitively against
a set of aliases. Pure standard library — always importable and unit-tested.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

__all__ = [
    "RecogitoAnnotation",
    "parse_recogito_csv",
    "pleiades_id_from_uri",
    "extract_pleiades_links",
    "extract_tag_decisions",
    "build_upload_table",
]

# Header aliases (lower-cased) → canonical field. Covers Recogito 2 exports and
# minor naming drift.
_COLUMN_ALIASES = {
    "uuid": "uuid",
    "id": "uuid",
    "file": "file",
    "filename": "file",
    "document": "file",
    "type": "ann_type",
    "entity_type": "ann_type",
    "quote_transcription": "quote",
    "quote": "quote",
    "transcription": "quote",
    "label": "label",
    "tags": "tags",
    "comments": "comments",
    "comment": "comments",
    "uri": "uri",
    "place_uri": "uri",
    "match_uri": "uri",
    "lat": "lat",
    "latitude": "lat",
    "lng": "lng",
    "lon": "lng",
    "longitude": "lng",
    "verification_status": "verification_status",
    "status": "verification_status",
}

_PLEIADES_ID_RE = re.compile(r"pleiades\.stoa\.org/places/(\d+)")


@dataclass(frozen=True)
class RecogitoAnnotation:
    """One row of a Recogito annotation export, normalised."""

    uuid: str = ""
    file: str = ""
    ann_type: str = ""
    quote: str = ""
    label: str = ""
    tags: tuple[str, ...] = ()
    comments: str = ""
    uri: str = ""
    lat: float | None = None
    lng: float | None = None
    verification_status: str = ""

    @property
    def is_rejected(self) -> bool:
        return self.verification_status.strip().upper() in {"REJECTED", "NOT_IDENTIFIABLE"}


def _split_tags(raw: str) -> tuple[str, ...]:
    if not raw:
        return ()
    # Recogito joins tags with "|"; tolerate commas too.
    parts = re.split(r"[|,]", raw)
    return tuple(p.strip() for p in parts if p.strip())


def _to_float(raw: str) -> float | None:
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def parse_recogito_csv(text: str) -> list[RecogitoAnnotation]:
    """Parse a Recogito annotation CSV export into normalised annotations."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    # Map each present header to a canonical field name.
    colmap = {h: _COLUMN_ALIASES.get((h or "").strip().lower()) for h in reader.fieldnames}

    annotations: list[RecogitoAnnotation] = []
    for row in reader:
        values: dict[str, str] = {}
        for header, canonical in colmap.items():
            if canonical and canonical not in values:
                values[canonical] = (row.get(header) or "").strip()
        annotations.append(
            RecogitoAnnotation(
                uuid=values.get("uuid", ""),
                file=values.get("file", ""),
                ann_type=values.get("ann_type", ""),
                quote=values.get("quote", ""),
                label=values.get("label", ""),
                tags=_split_tags(values.get("tags", "")),
                comments=values.get("comments", ""),
                uri=values.get("uri", ""),
                lat=_to_float(values.get("lat", "")),
                lng=_to_float(values.get("lng", "")),
                verification_status=values.get("verification_status", ""),
            )
        )
    return annotations


def pleiades_id_from_uri(uri: str) -> str | None:
    """Extract the numeric Pleiades place id from a URI, or None."""
    if not uri:
        return None
    m = _PLEIADES_ID_RE.search(uri)
    return m.group(1) if m else None


def extract_pleiades_links(annotations: list[RecogitoAnnotation]) -> dict[str, str]:
    """
    Harvest findspot → Pleiades-ID links from PLACE annotations.

    Keyed by the annotated quote (the place surface form), valued by Pleiades id.
    Rejected annotations and non-Pleiades URIs are skipped. When the same quote
    appears more than once, the first non-rejected Pleiades match wins.
    """
    links: dict[str, str] = {}
    for ann in annotations:
        if ann.ann_type.strip().upper() != "PLACE" or ann.is_rejected:
            continue
        pid = pleiades_id_from_uri(ann.uri)
        key = ann.quote.strip()
        if pid and key and key not in links:
            links[key] = pid
    return links


def extract_tag_decisions(annotations: list[RecogitoAnnotation]) -> dict[str, list[str]]:
    """
    Harvest per-document tag sets (the philologist's classification decision).

    Returns ``{file: [tags...]}`` accumulating tags across all of a file's
    annotations, de-duplicated and order-preserving.
    """
    decisions: dict[str, list[str]] = {}
    for ann in annotations:
        if not ann.file or not ann.tags:
            continue
        bucket = decisions.setdefault(ann.file, [])
        for tag in ann.tags:
            if tag not in bucket:
                bucket.append(tag)
    return decisions


@dataclass
class UploadRow:
    """A queue item to send to Recogito as one CSV row."""

    id: str
    text: str
    extra: dict[str, str] = field(default_factory=dict)


def build_upload_table(rows: list[UploadRow], *, extra_columns: list[str] | None = None) -> str:
    """
    Build a Recogito tabular-import CSV from queue rows.

    Produces ``id, text[, <extra columns>]``. On upload the annotator points
    Recogito at the ``text`` column; the extra columns (e.g. the jury's proposed
    labels) ride along as context. Returns CSV text.
    """
    extra_columns = extra_columns or []
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["id", "text", *extra_columns])
    for row in rows:
        writer.writerow([row.id, row.text, *[row.extra.get(c, "") for c in extra_columns]])
    return out.getvalue()
