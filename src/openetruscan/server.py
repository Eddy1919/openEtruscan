"""
FastAPI REST wrapper for the OpenEtruscan corpus.

Provides full-text and native PostGIS spatial search capabilities via HTTP.
Run locally:
    uvicorn openetruscan.server:app --reload
"""

import asyncio
import gc
import logging
import re
import resource
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
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
_GRAPH_BUILDING = False
START_TIME = datetime.utcnow()


def _ensure_graph():
    """Lazily build the FamilyGraph on first /clan request."""
    global family_graph, insc_to_gens, GRAPH_READY, _GRAPH_BUILDING
    if GRAPH_READY or _GRAPH_BUILDING:
        return
    _GRAPH_BUILDING = True
    try:
        logger.info("Building FamilyGraph on first request...")
        from openetruscan.prosopography import FamilyGraph

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
        gc.collect()
        family_graph = fg
        insc_to_gens = itg
        GRAPH_READY = True
        logger.info(
            "FamilyGraph ready — RSS %.0f MB",
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        )
    except Exception:
        logger.exception("Failed to build FamilyGraph")
        _GRAPH_BUILDING = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global corpus, START_TIME
    START_TIME = datetime.utcnow()
    corpus = Corpus.load()

    def prewarm():
        logger.info("Pre-warming cached endpoints...")
        _get_all_ids_cached()
        _get_stats_summary_cached()
        _get_stats_timeline_cached()
        _get_concordance_base_cached()
        _get_network_base_cached()
        logger.info("Pre-warming completed.")

    threading.Thread(target=prewarm, daemon=True).start()

    # FamilyGraph is built lazily on first /clan request to save memory
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
        date_approx=i.date_approx,
        date_uncertainty=i.date_uncertainty,
        source=i.source,
        notes=i.notes,
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
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for monitoring and load balancers."""
    uptime = (datetime.utcnow() - START_TIME).total_seconds()
    rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "status": "healthy" if corpus else "unhealthy",
        "version": __version__,
        "uptime_seconds": round(uptime, 2),
        "corpus_loaded": corpus is not None,
        "graph_ready": GRAPH_READY,
        "mem_rss_mb": round(rss_kb / 1024, 1),
        "timestamp": datetime.utcnow().isoformat(),
    }


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

# ── Known Etruscan Name Patterns (for /names/network) ──────────────────────
_KNOWN_NAMES = {
    "larθ", "laris", "aule", "vel", "arnθ", "θana", "larthi", "velia",
    "sethre", "marce", "avile", "lavtni", "ramtha", "fasti", "hasti",
    "tite", "caile", "larθi", "arnth", "thana", "lart", "lars",
    "arnt", "arn", "arath", "araθ", "veilia",
    "matunas", "velthur", "velθur", "cainei", "cai", "clan",
    "puia", "sec", "ati", "papa",
}


def _extract_names(canonical: str) -> list[str]:
    """Extract known Etruscan names from canonical inscription text."""
    import re as _re
    tokens = _re.split(r"[\s·.,:;]+", canonical.lower())
    found = []
    seen = set()
    for t in tokens:
        if len(t) >= 2 and t in _KNOWN_NAMES and t not in seen:
            found.append(t)
            seen.add(t)
    return found


# ── API Endpoints ───────────────────────────────────────────────────────────


@app.get("/corpus", response_model=list[InscriptionModel], tags=["Corpus"],
         deprecated=True)
@limiter.limit("10/minute")
def get_full_corpus(request: Request):
    """DEPRECATED — use /search with pagination instead."""
    results = corpus.search(limit=500)
    data = [_build_model(i) for i in results.inscriptions]
    return data


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
    offset: Annotated[
        int,
        Query(ge=0, description="Number of results to skip for pagination"),
    ] = 0,
    sort_by: Annotated[
        str,
        Query(description="Sort order (id, date, site, relevance)"),
    ] = "id",
):
    """Search by text, location, or metadata with pagination."""
    if text:
        text = _validate_alphanumeric(text, "text")
    if findspot:
        findspot = _validate_alphanumeric(findspot, "findspot")
    if language:
        language = _validate_alphanumeric(language, "language")
    if classification:
        classification = _validate_alphanumeric(classification, "classification")

    actual_sort = sort_by if sort_by in ["date", "site"] else "id"

    results = corpus.search(
        text=_clamp_text(text),
        findspot=findspot,
        language=language,
        classification=classification,
        limit=_clamp_limit(limit),
        offset=offset,
        sort_by=actual_sort,
    )
    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@app.get("/search/geo", response_model=SearchResponse, tags=["Search"])
@limiter.limit("30/minute")
def search_geo(
    request: Request,
    text: Annotated[
        str | None,
        Query(description="Text search", max_length=MAX_TEXT_LEN),
    ] = None,
    findspot: Annotated[
        str | None,
        Query(description="Findspot name", max_length=MAX_TEXT_LEN),
    ] = None,
    classification: Annotated[
        str | None,
        Query(description="Classification filter", max_length=50),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=5000, description="Max results"),
    ] = 2000,
):
    """Return only geotagged inscriptions (with coordinates)."""
    if text:
        text = _validate_alphanumeric(text, "text")
    if findspot:
        findspot = _validate_alphanumeric(findspot, "findspot")
    if classification:
        classification = _validate_alphanumeric(classification, "classification")

    results = corpus.search(
        text=_clamp_text(text),
        findspot=findspot,
        classification=classification,
        limit=min(limit, 5000),
        offset=0,
    )
    geo = [i for i in results.inscriptions if i.findspot_lat is not None]
    data = [_build_model(i) for i in geo]
    return {"total": len(data), "count": len(data), "results": data}


@app.get("/inscription/{inscription_id}", response_model=InscriptionModel,
         tags=["Corpus"])
@limiter.limit("120/minute")
def get_inscription(
    request: Request,
    inscription_id: Annotated[
        str,
        Path(description="ID of the inscription to retrieve"),
    ],
):
    """Fetch a single inscription by ID."""
    inscription_id = _validate_alphanumeric(inscription_id, "inscription_id")
    results = corpus.get_by_ids([inscription_id])
    if not results.inscriptions:
        raise HTTPException(status_code=404, detail="Inscription not found")
    return _build_model(results.inscriptions[0])


@lru_cache(maxsize=1)
def _get_all_ids_cached():
    results = corpus.search(limit=99999)
    return [i.id for i in results.inscriptions]


@app.get("/ids", tags=["Corpus"])
@limiter.limit("10/minute")
def get_all_ids(request: Request):
    """Return the list of all inscription IDs (lightweight, ~50KB)."""
    return _get_all_ids_cached()


@lru_cache(maxsize=1)
def _get_stats_summary_cached():
    results = corpus.search(limit=99999)
    all_insc = results.inscriptions
    total = len(all_insc)

    # Classification counts
    class_counts: dict[str, int] = {}
    site_counts: dict[str, int] = {}
    text_length_buckets: dict[str, int] = {"1-5": 0, "6-10": 0, "11-20": 0,
                                            "21-50": 0, "50+": 0}
    with_coords = 0
    pleiades_linked = 0
    classified = 0
    distinct_sites: set[str] = set()
    distinct_classifications: set[str] = set()

    for i in all_insc:
        cls = i.classification or "unknown"
        class_counts[cls] = class_counts.get(cls, 0) + 1
        if cls != "unknown":
            classified += 1
        distinct_classifications.add(cls)

        site = i.findspot or "Unknown"
        site_counts[site] = site_counts.get(site, 0) + 1
        if i.findspot:
            distinct_sites.add(i.findspot)

        if i.findspot_lat is not None:
            with_coords += 1
        if i.pleiades_id:
            pleiades_linked += 1

        clen = len(i.canonical)
        if clen <= 5:
            text_length_buckets["1-5"] += 1
        elif clen <= 10:
            text_length_buckets["6-10"] += 1
        elif clen <= 20:
            text_length_buckets["11-20"] += 1
        elif clen <= 50:
            text_length_buckets["21-50"] += 1
        else:
            text_length_buckets["50+"] += 1

    top_sites = sorted(site_counts.items(), key=lambda x: x[1],
                       reverse=True)[:20]

    return {
        "total": total,
        "with_coords": with_coords,
        "pleiades_linked": pleiades_linked,
        "classified": classified,
        "classification_counts": sorted(
            class_counts.items(), key=lambda x: x[1], reverse=True
        ),
        "top_sites": top_sites,
        "text_length_buckets": list(text_length_buckets.items()),
        "distinct_sites": sorted(distinct_sites),
        "distinct_classifications": sorted(distinct_classifications),
    }


@app.get("/stats/summary", tags=["Statistics"])
@limiter.limit("30/minute")
def stats_summary(request: Request):
    """Pre-computed corpus statistics for dashboard display."""
    return _get_stats_summary_cached()


@lru_cache(maxsize=1)
def _get_stats_timeline_cached():
    results = corpus.search(limit=99999)
    items = []
    for i in results.inscriptions:
        if i.date_approx is not None and i.findspot_lat is not None:
            items.append({
                "id": i.id,
                "findspot": i.findspot,
                "findspot_lat": i.findspot_lat,
                "findspot_lon": i.findspot_lon,
                "date_approx": i.date_approx,
                "classification": i.classification,
            })
    return {"total": len(items), "items": items}


@app.get("/stats/timeline", tags=["Statistics"])
@limiter.limit("30/minute")
def stats_timeline(request: Request):
    """Dated + geolocated inscriptions with minimal fields for timeline map."""
    return _get_stats_timeline_cached()


@lru_cache(maxsize=1)
def _get_concordance_base_cached():
    results = corpus.search(limit=99999)
    return [
        {"id": i.id, "lower": i.canonical.lower(), "original": i.canonical}
        for i in results.inscriptions
    ]


@app.get("/concordance", tags=["Search"])
@limiter.limit("30/minute")
def concordance_search(
    request: Request,
    q: Annotated[
        str,
        Query(description="Search term (min 2 chars)", min_length=2,
              max_length=MAX_TEXT_LEN),
    ],
    context: Annotated[
        int,
        Query(ge=10, le=100, description="Context characters"),
    ] = 40,
    limit: Annotated[
        int,
        Query(ge=1, le=5000, description="Max occurrences to return"),
    ] = 2000,
):
    """Server-side KWIC (Key Word In Context) concordance search."""
    q = _validate_alphanumeric(q, "q")
    q_lower = q.lower().strip()
    base_data = _get_concordance_base_cached()

    rows = []
    for insc in base_data:
        text = insc["lower"]
        start_pos = 0
        while True:
            idx = text.find(q_lower, start_pos)
            if idx == -1:
                break
            match_end = idx + len(q_lower)
            original = insc["original"]

            left_full = original[:idx]
            left = left_full[-context:] if len(left_full) > context else left_full

            right_full = original[match_end:]
            right = right_full[:context] if len(right_full) > context else right_full

            rows.append({
                "inscId": insc["id"],
                "left": left,
                "keyword": original[idx:match_end],
                "right": right,
            })
            if len(rows) >= limit:
                break
            start_pos = match_end
        if len(rows) >= limit:
            break

    unique = len({r["inscId"] for r in rows})
    return {"total": len(rows), "unique_inscriptions": unique, "rows": rows}


@lru_cache(maxsize=1)
def _get_network_base_cached():
    results = corpus.search(limit=99999)
    name_inscriptions: dict[str, set[str]] = {}
    co_occurrences: dict[str, int] = {}

    for insc in results.inscriptions:
        names = _extract_names(insc.canonical)
        for name in names:
            if name not in name_inscriptions:
                name_inscriptions[name] = set()
            name_inscriptions[name].add(insc.id)
        for i_idx in range(len(names)):
            for j_idx in range(i_idx + 1, len(names)):
                key = "|".join(sorted([names[i_idx], names[j_idx]]))
                co_occurrences[key] = co_occurrences.get(key, 0) + 1
    return name_inscriptions, co_occurrences


@app.get("/names/network", tags=["Prosopography"])
@limiter.limit("15/minute")
def names_network(
    request: Request,
    min_count: Annotated[
        int,
        Query(ge=1, le=100, description="Minimum attestations to include"),
    ] = 5,
):
    """Name co-occurrence network for prosopographic analysis."""
    name_inscriptions, co_occurrences = _get_network_base_cached()

    filtered = [
        (name, ids) for name, ids in name_inscriptions.items()
        if len(ids) >= min_count
    ]
    filtered.sort(key=lambda x: len(x[1]), reverse=True)
    name_set = {n for n, _ in filtered}

    nodes = [
        {"id": name, "count": len(ids), "inscriptions": sorted(ids)}
        for name, ids in filtered
    ]
    edges = []
    for key, weight in co_occurrences.items():
        a, b = key.split("|")
        if a in name_set and b in name_set and weight >= 2:
            edges.append({"source": a, "target": b, "weight": weight})

    return {"nodes": nodes, "edges": edges}


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
    _ensure_graph()
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

    # Targeted lookup: fetch only the IDs we need (not the entire corpus)
    results = corpus.get_by_ids(member_insc_ids)

    data = [_build_model(i) for i in results.inscriptions]
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

    search_kwargs: dict = {"language": language, "limit": 10000}
    if findspot:
        search_kwargs["findspot"] = findspot

    results_a = corpus.search(**search_kwargs)
    texts_a = [i.canonical for i in results_a.inscriptions if i.canonical]
    freq_a = letter_frequencies(texts_a, language=language)

    response: dict = {"primary": freq_a.to_dict(), "label_a": findspot or "All sites"}

    if findspot_b:
        search_kwargs_b: dict = {"language": language, "limit": 10000, "findspot": findspot_b}
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
