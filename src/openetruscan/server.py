"""
FastAPI REST wrapper for the OpenEtruscan corpus.

Provides full-text and native PostGIS spatial search capabilities via HTTP.
Run locally:
    uvicorn openetruscan.server:app --reload
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from openetruscan.corpus import Corpus

logger = logging.getLogger("openetruscan")

# Global corpus and graph instances
corpus = None
family_graph = None
insc_to_gens = {}
GRAPH_READY = False


async def _build_graph_background():
    """Build the prosopographical graph in a background thread."""
    global family_graph, insc_to_gens, GRAPH_READY
    try:
        logger.info("Building FamilyGraph in background...")

        def _build():
            from openetruscan.prosopography import FamilyGraph

            fg = FamilyGraph.from_corpus(corpus)
            itg = {
                idx: p.gentilicium
                for p in fg.persons()
                for idx in p.inscription_ids
                if p.gentilicium
            }
            return fg, itg

        fg, itg = await asyncio.to_thread(_build)
        family_graph = fg
        insc_to_gens = itg
        GRAPH_READY = True
        logger.info("FamilyGraph generated successfully.")
    except Exception:
        logger.exception("Failed to build FamilyGraph")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global corpus
    corpus = Corpus.load()

    # Start graph generation in the background so API can accept connections instantly
    asyncio.create_task(_build_graph_background())

    yield
    if corpus:
        corpus.close()


# ── Rate Limiter ────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

app = FastAPI(
    title="OpenEtruscan Corpus API",
    description="REST API for querying the OpenEtruscan dataset.",
    version="0.4",
    lifespan=lifespan,
    docs_url="/docs" if os.getenv("ENABLE_DOCS", "0") == "1" else None,
    redoc_url=None,
)

# Attach rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ────────────────────────────────────────────────────────────────────
_ALLOWED_ORIGINS = [
    "https://openetruscan.com",
    "https://www.openetruscan.com",
    "https://eddy1919.github.io",
    "http://localhost",
    "http://localhost:80",
    "http://localhost:8000",
    "http://127.0.0.1",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Global Exception Handler ───────────────────────────────────────────────
@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ── Input Bounds ───────────────────────────────────────────────────────────
MAX_LIMIT = 500
MAX_RADIUS_KM = 500
MAX_TEXT_LEN = 200


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))


def _clamp_text(text: str | None) -> str | None:
    return text[:MAX_TEXT_LEN] if text else text


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
    pleiades_id: str | None = None
    geonames_id: str | None = None
    trismegistos_id: str | None = None
    eagle_id: str | None = None
    is_codex: bool = False
    provenance_status: str | None = "verified"


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
        pleiades_id=i.pleiades_id,
        geonames_id=i.geonames_id,
        trismegistos_id=i.trismegistos_id,
        eagle_id=i.eagle_id,
        is_codex=i.is_codex,
        provenance_status=i.provenance_status,
    )

@app.get("/corpus", response_model=list[InscriptionModel])
@limiter.limit("5/minute")
def get_full_corpus(request: Request):
    """Fetch the entire unified corpus asynchronously. High bandwidth endpoint."""
    results = corpus.search(limit=99999)
    return [_build_model(i) for i in results.inscriptions]


@app.get("/search", response_model=SearchResponse)
@limiter.limit("60/minute")
def search_corpus(
    request: Request,
    text: str | None = Query(
        None, description="Wildcard text search (e.g. *larth*)", max_length=MAX_TEXT_LEN
    ),
    findspot: str | None = Query(None, description="Findspot name", max_length=MAX_TEXT_LEN),
    language: str | None = Query(None, description="Language filter", max_length=50),
    classification: str | None = Query(None, description="Classification filter", max_length=50),
    limit: int = Query(100, ge=1, le=MAX_LIMIT),
):
    """Search by text, location, or metadata."""
    results = corpus.search(
        text=_clamp_text(text),
        findspot=findspot,
        language=language,
        classification=classification,
        limit=_clamp_limit(limit),
    )
    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@app.get("/radius", response_model=SearchResponse)
@limiter.limit("60/minute")
def search_by_radius(
    request: Request,
    lat: float = Query(..., description="Latitude of center point", ge=-90, le=90),
    lon: float = Query(..., description="Longitude of center point", ge=-180, le=180),
    radius_km: float = Query(50.0, description="Radius in kilometers", ge=0.1, le=MAX_RADIUS_KM),
    limit: int = Query(100, ge=1, le=MAX_LIMIT),
):
    """Search by spatial radius."""
    results = corpus.search_radius(lat=lat, lon=lon, radius_km=radius_km, limit=_clamp_limit(limit))
    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@app.get("/semantic-search", response_model=SearchResponse)
@limiter.limit("30/minute")
async def semantic_search(
    request: Request,
    q: str = Query(..., description="Query text to search for", max_length=MAX_TEXT_LEN),
    field: str = Query("emb_combined", description="Vector field to compare against"),
    limit: int = Query(20, ge=1, le=100),
):
    """Semantic pgvector search using Gemini text-embedding-004."""
    import requests

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500, detail="GEMINI_API_KEY not configured on server"
        )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={api_key}"
    payload = {"content": {"parts": [{"text": q[:2048]}]}}

    def _fetch_emb():
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()["embedding"]["values"]

    try:
        query_embedding = await asyncio.to_thread(_fetch_emb)
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        raise HTTPException(status_code=502, detail="Failed to embed query") from e

    try:
        results = corpus.semantic_search(
            query_embedding=query_embedding,
            field=field,
            limit=_clamp_limit(limit),
        )
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        raise HTTPException(
            status_code=500, detail="Database error during vector search"
        ) from e

    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@app.get("/inscriptions/{id}/genetics")
@limiter.limit("30/minute")
def get_genetic_matches(
    request: Request,
    id: str = Path(..., description="ID of the inscription to find genetic matches for"),
    limit: int = Query(5, ge=1, le=20),
):
    """Spatio-temporal matchmaking between inscriptions and archaeogenetic samples."""
    try:
        matches = corpus.find_genetic_matches(id, limit=limit)
        return {"total": len(matches), "inscription_id": id, "matches": matches}
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Genetics search failed: {e}")
        raise HTTPException(
            status_code=500, detail="Database error during genetics search"
        ) from e


@app.get("/clan/{gens}", response_model=SearchResponse)
@limiter.limit("30/minute")
def search_by_clan(request: Request, gens: str):
    """Prosopographical network search."""
    if not GRAPH_READY:
        raise HTTPException(
            status_code=503,
            detail="Prosopographical engine is initializing. Please try again in a minute.",
        )

    if len(gens) > MAX_TEXT_LEN:
        return {"total": 0, "count": 0, "results": []}

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
@limiter.limit("30/minute")
def frequency_analysis(
    request: Request,
    findspot: str | None = Query(None, description="Filter by findspot", max_length=MAX_TEXT_LEN),
    findspot_b: str | None = Query(
        None, description="Second findspot for comparison", max_length=MAX_TEXT_LEN
    ),
    date_from: int | None = Query(None, description="Date range start (BCE, positive int)"),
    date_to: int | None = Query(None, description="Date range end (BCE, positive int)"),
    language: str = Query("etruscan", description="Language adapter to use", max_length=50),
):
    """Letter frequency analysis, optionally comparing two sites (chi² test)."""
    from openetruscan.statistics import (
        compare_frequencies,
        letter_frequencies,
    )

    search_kwargs: dict = {"language": language, "limit": 999999}
    if findspot:
        search_kwargs["findspot"] = findspot

    results_a = corpus.search(**search_kwargs)
    texts_a = [i.canonical for i in results_a.inscriptions if i.canonical]
    freq_a = letter_frequencies(texts_a, language=language)

    response: dict = {"primary": freq_a.to_dict(), "label_a": findspot or "All sites"}

    if findspot_b:
        search_kwargs_b: dict = {"language": language, "limit": 999999, "findspot": findspot_b}
        results_b = corpus.search(**search_kwargs_b)
        texts_b = [i.canonical for i in results_b.inscriptions if i.canonical]
        freq_b = letter_frequencies(texts_b, language=language)
        comparison = compare_frequencies(freq_a, freq_b)
        response["secondary"] = freq_b.to_dict()
        response["label_b"] = findspot_b
        response["comparison"] = comparison.to_dict()

    return response


@app.get("/stats/clusters")
@limiter.limit("15/minute")
def dialect_clusters(
    request: Request,
    min_inscriptions: int = Query(5, description="Minimum inscriptions per site", ge=2, le=100),
    language: str = Query("etruscan", description="Language adapter", max_length=50),
):
    """Dialect clustering via Ward's hierarchical method with cosine distance."""
    from openetruscan.statistics import cluster_sites

    result = cluster_sites(corpus, language=language, min_inscriptions=min_inscriptions)
    return result.to_dict()


@app.get("/stats/date-estimate")
@limiter.limit("60/minute")
def date_estimate(
    request: Request,
    text: str = Query(..., description="Inscription text to analyze", max_length=MAX_TEXT_LEN),
    language: str = Query("etruscan", description="Language adapter", max_length=50),
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


# Static file serving removed — frontend is deployed on GitHub Pages.
# API-only server: all routes are under /search, /radius, /stats, etc.
