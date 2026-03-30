"""
FastAPI REST wrapper for the OpenEtruscan corpus.

Provides full-text and native PostGIS spatial search capabilities via HTTP.
Run locally:
    uvicorn openetruscan.server:app --reload
"""

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from openetruscan import __version__
from openetruscan.config import settings
from openetruscan.corpus import Corpus

logger = logging.getLogger("openetruscan")

# Global corpus and graph instances
corpus = None
family_graph = None
insc_to_gens = {}
GRAPH_READY = False
START_TIME = datetime.utcnow()


async def _build_graph_background():
    """Build the prosopographical graph in a background thread."""
    global family_graph, insc_to_gens, GRAPH_READY
    try:
        logger.info("Building FamilyGraph in background...")

        def _build():
            from openetruscan.prosopography import FamilyGraph
            from openetruscan.corpus import Corpus

            bg_corpus = Corpus.load()
            try:
                fg = FamilyGraph.from_corpus(bg_corpus)
                itg = {
                    idx: p.gentilicium
                    for p in fg.persons()
                    for idx in p.inscription_ids
                    if p.gentilicium
                }
            finally:
                bg_corpus.close()
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
    global corpus, START_TIME
    START_TIME = datetime.utcnow()
    corpus = Corpus.load()

    # Start graph generation in the background so API can accept connections instantly
    asyncio.create_task(_build_graph_background())

    yield
    if corpus:
        corpus.close()


# ── Rate Limiter ────────────────────────────────────────────────────────────
def _get_rate_limit_key(request: Request) -> str:
    """Get rate limit key with path awareness."""
    client = get_remote_address(request)
    return f"{client}:{request.url.path}"


limiter = Limiter(
    key_func=_get_rate_limit_key,
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
    strategy="fixed-window",
)

app = FastAPI(
    title="OpenEtruscan Corpus API",
    description="REST API for querying the OpenEtruscan dataset.",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)

# Attach rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    max_age=600,
)

# ── Security Headers ───────────────────────────────────────────────────────
@ app.middleware("http")
async def _add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response


# ── Global Exception Handler ───────────────────────────────────────────────
@ app.exception_handler(Exception)
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
MAX_GENS_LEN = 100


# ── Validators ─────────────────────────────────────────────────────────────
def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))


def _clamp_text(text: str | None) -> str | None:
    return text[:MAX_TEXT_LEN] if text else text


def _validate_alphanumeric(text: str, field_name: str) -> str:
    """Validate text contains only alphanumeric chars, spaces, and common punctuation."""
    if not text:
        return text
    # Allow letters, numbers, spaces, and common punctuation for ancient texts
    if not re.match(r"^[\w\s\-\.\,\;\:\'\"\*\?\[\]\(\)/\\]*$", text, re.UNICODE):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} contains invalid characters",
        )
    return text


# ── Pydantic Models ────────────────────────────────────────────────────────
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


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    corpus_loaded: bool
    graph_ready: bool
    timestamp: str


class StatsResponse(BaseModel):
    total_inscriptions: int


class ErrorResponse(BaseModel):
    detail: str


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


# ── Health Endpoint ────────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint for monitoring and load balancers."""
    uptime = (datetime.utcnow() - START_TIME).total_seconds()
    return HealthResponse(
        status="healthy" if corpus else "unhealthy",
        version=__version__,
        uptime_seconds=round(uptime, 2),
        corpus_loaded=corpus is not None,
        graph_ready=GRAPH_READY,
        timestamp=datetime.utcnow().isoformat(),
    )


@app.get("/ready", tags=["Health"])
async def readiness_check():
    """Readiness probe for Kubernetes."""
    if corpus is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Corpus not loaded",
        )
    return {"status": "ready"}


@app.get("/live", tags=["Health"])
async def liveness_check():
    """Liveness probe for Kubernetes."""
    return {"status": "alive"}


# ── API Endpoints ───────────────────────────────────────────────────────────
@app.get("/corpus", response_model=list[InscriptionModel], tags=["Corpus"])
@limiter.limit("5/minute")
def get_full_corpus(request: Request):
    """Fetch the entire unified corpus asynchronously. High bandwidth endpoint."""
    results = corpus.search(limit=99999)
    return [_build_model(i) for i in results.inscriptions]


@app.get("/search", response_model=SearchResponse, tags=["Search"])
@limiter.limit("60/minute")
def search_corpus(
    request: Request,
    text: Annotated[
        str | None,
        Query(
            description="Wildcard text search (e.g. *larth*)",
            max_length=MAX_TEXT_LEN,
        ),
    ] = None,
    findspot: Annotated[
        str | None,
        Query(description="Findspot name", max_length=MAX_TEXT_LEN),
    ] = None,
    language: Annotated[
        str | None,
        Query(description="Language filter", max_length=50),
    ] = None,
    classification: Annotated[
        str | None,
        Query(description="Classification filter", max_length=50),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=MAX_LIMIT, description="Maximum number of results"),
    ] = 100,
):
    """Search by text, location, or metadata."""
    # Validate and sanitize inputs
    if text:
        text = _validate_alphanumeric(text, "text")
    if findspot:
        findspot = _validate_alphanumeric(findspot, "findspot")
    if language:
        language = _validate_alphanumeric(language, "language")
    if classification:
        classification = _validate_alphanumeric(classification, "classification")

    results = corpus.search(
        text=_clamp_text(text),
        findspot=findspot,
        language=language,
        classification=classification,
        limit=_clamp_limit(limit),
    )
    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@app.get("/radius", response_model=SearchResponse, tags=["Search"])
@limiter.limit("60/minute")
def search_by_radius(
    request: Request,
    lat: Annotated[
        float,
        Query(description="Latitude of center point", ge=-90, le=90),
    ],
    lon: Annotated[
        float,
        Query(description="Longitude of center point", ge=-180, le=180),
    ],
    radius_km: Annotated[
        float,
        Query(
            description="Radius in kilometers",
            ge=0.1,
            le=MAX_RADIUS_KM,
        ),
    ] = 50.0,
    limit: Annotated[
        int,
        Query(ge=1, le=MAX_LIMIT),
    ] = 100,
):
    """Search by spatial radius."""
    results = corpus.search_radius(
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        limit=_clamp_limit(limit),
    )
    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@app.get("/semantic-search", response_model=SearchResponse, tags=["Search"])
@limiter.limit("30/minute")
async def semantic_search(
    request: Request,
    q: Annotated[
        str,
        Query(description="Query text to search for", max_length=MAX_TEXT_LEN),
    ],
    field: Annotated[
        str,
        Query(
            description="Vector field to compare against",
            pattern="^(emb_text|emb_context|emb_combined)$",
        ),
    ] = "emb_combined",
    limit: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 20,
):
    """Semantic pgvector search using Gemini text-embedding-004."""
    import requests

    # Validate query
    q = _validate_alphanumeric(q, "q")

    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GEMINI_API_KEY not configured on server",
        )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={settings.gemini_api_key}"
    payload = {"content": {"parts": [{"text": q[:2048]}]}}

    def _fetch_emb():
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()["embedding"]["values"]

    try:
        query_embedding = await asyncio.to_thread(_fetch_emb)
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to embed query",
        ) from e

    try:
        results = corpus.semantic_search(
            query_embedding=query_embedding,
            field=field,
            limit=_clamp_limit(limit),
        )
    except NotImplementedError as e:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error during vector search",
        ) from e

    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@app.get("/inscriptions/{id}/genetics", tags=["Genetics"])
@limiter.limit("30/minute")
def get_genetic_matches(
    request: Request,
    id: Annotated[
        str,
        Path(description="ID of the inscription to find genetic matches for"),
    ],
    limit: Annotated[
        int,
        Query(ge=1, le=20),
    ] = 5,
):
    """Spatio-temporal matchmaking between inscriptions and archaeogenetic samples."""
    # Validate ID
    id = _validate_alphanumeric(id, "id")

    try:
        matches = corpus.find_genetic_matches(id, limit=limit)
        return {"total": len(matches), "inscription_id": id, "matches": matches}
    except NotImplementedError as e:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Genetics search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error during genetics search",
        ) from e


@app.get("/clan/{gens}", response_model=SearchResponse, tags=["Prosopography"])
@limiter.limit("30/minute")
def search_by_clan(
    request: Request,
    gens: Annotated[
        str,
        Path(description="Gentilicium (clan name) to search for"),
    ],
):
    """Prosopographical network search by clan/gens."""
    if not GRAPH_READY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prosopographical engine is initializing. Please try again in a minute.",
        )

    # Validate gens - allow letters, spaces, and hyphens
    if not re.match(r"^[\w\s\-]+$", gens, re.UNICODE):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gens contains invalid characters",
        )

    if len(gens) > MAX_GENS_LEN:
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


@app.get("/stats", response_model=StatsResponse, tags=["Statistics"])
def corpus_stats():
    """Get corpus counts."""
    return StatsResponse(total_inscriptions=corpus.count())


# ── Statistical Analysis Endpoints ──────────────────────────────────────────


@app.get("/stats/frequency", tags=["Statistics"])
@limiter.limit("30/minute")
def frequency_analysis(
    request: Request,
    findspot: Annotated[
        str | None,
        Query(description="Filter by findspot", max_length=MAX_TEXT_LEN),
    ] = None,
    findspot_b: Annotated[
        str | None,
        Query(description="Second findspot for comparison", max_length=MAX_TEXT_LEN),
    ] = None,
    date_from: Annotated[
        int | None,
        Query(description="Date range start (BCE, positive int)"),
    ] = None,
    date_to: Annotated[
        int | None,
        Query(description="Date range end (BCE, positive int)"),
    ] = None,
    language: Annotated[
        str,
        Query(description="Language adapter to use", max_length=50),
    ] = "etruscan",
):
    """Letter frequency analysis, optionally comparing two sites (chi² test)."""
    from openetruscan.statistics import (
        compare_frequencies,
        letter_frequencies,
    )

    # Validate inputs
    if findspot:
        findspot = _validate_alphanumeric(findspot, "findspot")
    if findspot_b:
        findspot_b = _validate_alphanumeric(findspot_b, "findspot_b")
    language = _validate_alphanumeric(language, "language")

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


@app.get("/stats/clusters", tags=["Statistics"])
@limiter.limit("15/minute")
def dialect_clusters(
    request: Request,
    min_inscriptions: Annotated[
        int,
        Query(description="Minimum inscriptions per site", ge=2, le=100),
    ] = 5,
    language: Annotated[
        str,
        Query(description="Language adapter", max_length=50),
    ] = "etruscan",
):
    """Dialect clustering via Ward's hierarchical method with cosine distance."""
    from openetruscan.statistics import cluster_sites

    language = _validate_alphanumeric(language, "language")

    result = cluster_sites(corpus, language=language, min_inscriptions=min_inscriptions)
    return result.to_dict()


@app.get("/stats/date-estimate", tags=["Statistics"])
@limiter.limit("60/minute")
def date_estimate(
    request: Request,
    text: Annotated[
        str,
        Query(description="Inscription text to analyze", max_length=MAX_TEXT_LEN),
    ],
    language: Annotated[
        str,
        Query(description="Language adapter", max_length=50),
    ] = "etruscan",
):
    """Estimate chronological period from orthographic features."""
    from openetruscan.statistics import estimate_date

    text = _validate_alphanumeric(text, "text")
    language = _validate_alphanumeric(language, "language")

    result = estimate_date(text, language=language)
    return result.to_dict()


@app.get("/pelagios.jsonld", tags=["Linked Data"])
def pelagios_feed():
    """Pelagios-compatible JSON-LD feed for Linked Open Data."""
    from fastapi.responses import Response

    from openetruscan.lod import corpus_to_pelagios_jsonld

    jsonld = corpus_to_pelagios_jsonld(corpus)
    return Response(
        content=jsonld,
        media_type="application/ld+json",
    )


@app.get("/pleiades-stats", tags=["Linked Data"])
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
