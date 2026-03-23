"""
FastAPI REST wrapper for the OpenEtruscan corpus.

Provides full-text and native PostGIS spatial search capabilities via HTTP.
Run locally:
    uvicorn openetruscan.server:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from openetruscan.corpus import Corpus

# Global corpus and graph instances (loaded on startup)
corpus = None
family_graph = None
insc_to_gens = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global corpus, family_graph, insc_to_gens
    # If DATABASE_URL is set, Corpus.load() connects to PostgreSQL automatically.
    # Otherwise, it falls back to the local SQLite offline copy.
    corpus = Corpus.load()

    # Initialize the Prosopographical Network Engine
    from openetruscan.prosopography import FamilyGraph

    family_graph = FamilyGraph.from_corpus(corpus)

    # Build reverse lookup for instant UI badge population
    insc_to_gens = {
        idx: p.gentilicium
        for p in family_graph.persons()
        for idx in p.inscription_ids
        if p.gentilicium
    }

    yield
    if corpus:
        corpus.close()


app = FastAPI(
    title="OpenEtruscan Corpus API",
    description="REST API for querying the OpenEtruscan dataset.",
    version="0.3",
    lifespan=lifespan,
)

# Allow CORS for static GitHub Pages frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InscriptionModel(BaseModel):
    id: str
    canonical: str
    phonetic: str
    old_italic: str
    raw_text: str
    findspot: str
    findspot_lat: float | None
    findspot_lon: float | None
    date_display: str
    medium: str
    object_type: str
    language: str
    classification: str
    gens: str | None = None


class SearchResponse(BaseModel):
    total: int
    count: int
    results: list[InscriptionModel]


def _build_model(i) -> InscriptionModel:
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
        medium=i.medium,
        object_type=i.object_type,
        language=i.language,
        classification=i.classification,
        gens=insc_to_gens.get(i.id),
    )


@app.get("/search", response_model=SearchResponse)
def search_corpus(
    text: str | None = Query(None, description="Wildcard text search (e.g. *larth*)"),
    findspot: str | None = Query(None, description="Findspot name"),
    language: str | None = Query(None, description="Language filter"),
    classification: str | None = Query(None, description="Classification filter"),
    limit: int = 100,
):
    """Search by text, location, or metadata."""
    results = corpus.search(
        text=text,
        findspot=findspot,
        language=language,
        classification=classification,
        limit=limit,
    )
    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@app.get("/radius", response_model=SearchResponse)
def search_by_radius(
    lat: float = Query(..., description="Latitude of center point"),
    lon: float = Query(..., description="Longitude of center point"),
    radius_km: float = Query(50.0, description="Radius in kilometers"),
    limit: int = 100,
):
    """Search by spatial radius."""
    results = corpus.search_radius(lat=lat, lon=lon, radius_km=radius_km, limit=limit)
    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@app.get("/clan/{gens}", response_model=SearchResponse)
def search_by_clan(gens: str):
    """Prosopographical network search."""
    clan_info = family_graph.clan(gens)
    if not clan_info:
        return {"total": 0, "count": 0, "results": []}

    member_insc_ids = []
    for member in clan_info.members:
        member_insc_ids.extend(member.inscription_ids)

    results = corpus.search(limit=99999)
    id_set = set(member_insc_ids)
    matching = [i for i in results.inscriptions if i.id in id_set]

    data = [_build_model(i) for i in matching]
    return {"total": len(data), "count": len(data), "results": data}


@app.get("/stats")
def corpus_stats():
    """Get corpus counts."""
    return {"total_inscriptions": corpus.count()}


# ── Statistical Analysis Endpoints ──────────────────────────────────────────


@app.get("/stats/frequency")
def frequency_analysis(
    findspot: str | None = Query(None, description="Filter by findspot"),
    findspot_b: str | None = Query(None, description="Second findspot for comparison"),
    date_from: int | None = Query(None, description="Date range start (BCE, positive int)"),
    date_to: int | None = Query(None, description="Date range end (BCE, positive int)"),
    language: str = Query("etruscan", description="Language adapter to use"),
):
    """Letter frequency analysis, optionally comparing two sites (chi² test)."""
    from openetruscan.statistics import (
        compare_frequencies,
        letter_frequencies,
    )

    results_a = corpus.search(
        findspot=findspot,
        language=language,
        date_from=-date_from if date_from else None,
        date_to=-date_to if date_to else None,
        limit=999999,
    )
    texts_a = [i.canonical for i in results_a.inscriptions if i.canonical]
    freq_a = letter_frequencies(texts_a, language=language)

    response: dict = {"primary": freq_a.to_dict(), "label_a": findspot or "All sites"}

    if findspot_b:
        results_b = corpus.search(
            findspot=findspot_b,
            language=language,
            date_from=-date_from if date_from else None,
            date_to=-date_to if date_to else None,
            limit=999999,
        )
        texts_b = [i.canonical for i in results_b.inscriptions if i.canonical]
        freq_b = letter_frequencies(texts_b, language=language)
        comparison = compare_frequencies(freq_a, freq_b)
        response["secondary"] = freq_b.to_dict()
        response["label_b"] = findspot_b
        response["comparison"] = comparison.to_dict()

    return response


@app.get("/stats/clusters")
def dialect_clusters(
    min_inscriptions: int = Query(5, description="Minimum inscriptions per site"),
    language: str = Query("etruscan", description="Language adapter"),
):
    """Dialect clustering via Ward's hierarchical method with cosine distance."""
    from openetruscan.statistics import cluster_sites

    result = cluster_sites(corpus, language=language, min_inscriptions=min_inscriptions)
    return result.to_dict()


@app.get("/stats/date-estimate")
def date_estimate(
    text: str = Query(..., description="Inscription text to analyze"),
    language: str = Query("etruscan", description="Language adapter"),
):
    """Estimate chronological period from orthographic features."""
    from openetruscan.statistics import estimate_date

    result = estimate_date(text, language=language)
    return result.to_dict()


@app.get("/pelagios.jsonld")
def pelagios_feed():
    """Pelagios-compatible JSON-LD feed for Linked Open Data."""

    from fastapi.responses import Response

    from openetruscan.lod import corpus_to_pelagios_jsonld

    jsonld = corpus_to_pelagios_jsonld(corpus)
    return Response(
        content=jsonld,
        media_type="application/ld+json",
    )


@app.get("/pleiades-stats")
def pleiades_coverage():
    """Pleiades coverage statistics."""
    from openetruscan.lod import pleiades_stats

    stats = pleiades_stats(corpus)
    total = corpus.count()
    linked = sum(stats.values())
    return {
        "total_inscriptions": total,
        "linked_to_pleiades": linked,
        "coverage_pct": round(linked / total * 100, 1) if total else 0,
        "places": [{"pleiades_uri": uri, "count": count} for uri, count in stats.items()],
    }
