"""Response models shared across routers."""

from pydantic import BaseModel


class InscriptionModel(BaseModel):
    """Data model representing a single Etruscan inscription for API output."""

    id: str
    canonical: str
    phonetic: str
    old_italic: str
    raw_text: str
    findspot: str
    findspot_lat: float | None
    findspot_lon: float | None
    date_display: str
    date_approx: int | None = None
    date_uncertainty: int | None = None
    source: str | None = None
    notes: str | None = None
    medium: str
    object_type: str
    language: str
    classification: str
    gens: str | None = None
    pleiades_id: str | None = None
    geonames_id: str | None = None
    trismegistos_id: str | None = None
    eagle_id: str | None = None
    is_codex: bool = False
    provenance_status: str | None = "verified"
    source_code: str = "unknown"
    source_detail: str | None = None
    original_script_entry: str | None = None
    zotero_id: str | None = None
    zotero_bibliography: dict | None = None


class SearchResponse(BaseModel):
    """Response model for paginated search results."""

    total: int
    count: int
    results: list[InscriptionModel]


class StatsResponse(BaseModel):
    """Response model for corpus-wide statistical aggregations."""

    total_inscriptions: int


def _build_model(i) -> InscriptionModel:
    """Convert a domain Inscription object into a Pydantic InscriptionModel."""
    return InscriptionModel(
        id=i.id,
        canonical=i.canonical,
        phonetic=i.phonetic,
        old_italic=i.old_italic,
        raw_text=i.raw_text,
        findspot=i.findspot,
        findspot_lat=i.findspot_lat,
        findspot_lon=i.findspot_lon,
        date_display=i.date_display(),
        date_approx=i.date_approx,
        date_uncertainty=i.date_uncertainty,
        source=i.source,
        notes=i.notes,
        medium=i.medium,
        object_type=i.object_type,
        language=i.language,
        classification=i.classification,
        gens=None,
        pleiades_id=i.pleiades_id,
        geonames_id=i.geonames_id,
        trismegistos_id=i.trismegistos_id,
        eagle_id=i.eagle_id,
        is_codex=i.is_codex,
        provenance_status=i.provenance_status,
        source_code=i.source_code,
        source_detail=i.source_detail,
        original_script_entry=i.original_script_entry,
        zotero_id=i.zotero_id,
    )
