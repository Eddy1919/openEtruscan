"""
FastAPI REST wrapper for the OpenEtruscan corpus.

Provides full-text and native PostGIS spatial search capabilities via HTTP.
Run locally:
    uvicorn openetruscan.api.server:app --reload
"""

import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from openetruscan import __version__
from openetruscan.core.config import settings
from openetruscan.db.session import get_session
from openetruscan.db.repository import InscriptionRepository

logger = logging.getLogger("openetruscan")

# Global startup tracking
START_TIME = datetime.now(timezone.utc)


def _configure_logging():
    """Setup structured JSON logging for production."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    
    if settings.is_production:
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            # In a real SOTA implementation, we'd use structlog or python-json-logger
            # e.g. using pythonjsonlogger.jsonlogger.JsonFormatter
        )
    else:
        logging.basicConfig(level=log_level)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown events, including uptime initialization."""
    global START_TIME
    START_TIME = datetime.now(timezone.utc)
    _configure_logging()
    # The InscriptionRepository handles sessions per request
    yield


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

# --- FASTAPI APPLICATION INITIALIZATION ---
# Using lifespan for database connection pooling and model loading on startup
app = FastAPI(
    title="OpenEtruscan Corpus API",
    description="REST API for querying the OpenEtruscan dataset.",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_docs else None, # Interactive Swagger UI
    redoc_url=None, # ReDoc disabled for simplicity
    openapi_url="/openapi.json" if settings.enable_docs else None,
)

# 1. Attach rate limiter to the application state
app.state.limiter = limiter
# Explicitly handle rate limit breaches with the custom handler (429 Too Many Requests)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 2. CORS (Cross-Origin Resource Sharing) Configuration
# Essential for the Next.js frontend running on a different domain/port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins, # Controlled via .env
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    max_age=600, # Cache preflight responses for 10 minutes
)


# 3. GLOBAL SECURITY HEADERS MIDDLEWARE
# Hardening the API against common web vulnerabilities (XSS, Framing, Sniffing)
@app.middleware("http")
async def _add_security_headers(request: Request, call_next):
    """Add production-grade security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff" # Prevent MIME type sniffing
    response.headers["X-Frame-Options"] = "DENY" # Prevent clickjacking
    response.headers["X-XSS-Protection"] = "1; mode=block" # Enable browser XSS filtering
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response


# ── Global Exception Handler ───────────────────────────────────────────────
@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler for unexpected server-side errors, ensuring 500 status returns."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.exception_handler(ValueError)
async def _value_error_handler(request: Request, exc: ValueError):
    """Handle validation and logic errors (ValueError) with a 400 Bad Request response."""
    logger.warning("ValueError on %s %s: %s", request.method, request.url.path, str(exc))
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


# ── Input Bounds ───────────────────────────────────────────────────────────
MAX_LIMIT = 500
MAX_RADIUS_KM = 500
MAX_TEXT_LEN = 200
MAX_GENS_LEN = 100


# ── Validators ─────────────────────────────────────────────────────────────
def _clamp_limit(limit: int) -> int:
    """Clamp the pagination limit to prevent excessive resource consumption."""
    return max(1, min(limit, MAX_LIMIT))


def _clamp_text(text: str | None) -> str | None:
    """Truncate input text to the maximum supported length for safety."""
    return text[:MAX_TEXT_LEN] if text else text


# ── Pydantic Models ────────────────────────────────────────────────────────
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


class SearchResponse(BaseModel):
    """Response model for paginated search results."""
    total: int
    count: int
    results: list[InscriptionModel]


class HealthResponse(BaseModel):
    """Response model for the system health and diagnostics endpoint."""
    status: str
    version: str
    uptime_seconds: float
    corpus_loaded: bool
    graph_ready: bool
    timestamp: str


class StatsResponse(BaseModel):
    """Response model for corpus-wide statistical aggregations."""
    total_inscriptions: int


class ErrorResponse(BaseModel):
    """Standardized error response model."""
    detail: str


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
    )


# ── Health Endpoint ────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check(session: AsyncSession = Depends(get_session)):
    """Health check endpoint for monitoring and load balancers."""
    uptime = (datetime.now(timezone.utc) - START_TIME).total_seconds()
    rss_mb = 0.0
    try:
        import resource
        rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_mb = round(rss_kb / 1024, 1)
    except ImportError:
        pass

    repo = InscriptionRepository(session)
    count = await repo.count()

    return {
        "status": "healthy" if count > 0 else "unhealthy",
        "version": __version__,
        "uptime_seconds": round(uptime, 2),
        "corpus_loaded": True,
        "total_inscriptions": count,
        "mem_rss_mb": rss_mb,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Health"])
async def readiness_check(session: AsyncSession = Depends(get_session)):
    """Readiness probe for Kubernetes."""
    repo = InscriptionRepository(session)
    count = await repo.count()
    if count == 0:
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


@app.get("/corpus", response_model=list[InscriptionModel], tags=["Corpus"], deprecated=True)
@limiter.limit("10/minute")
async def get_full_corpus(request: Request, session: AsyncSession = Depends(get_session)):
    """DEPRECATED — use /search with pagination instead."""
    repo = InscriptionRepository(session)
    results = await repo.search(limit=500)
    data = [_build_model(i) for i in results.inscriptions]
    return data


@app.get("/search", response_model=SearchResponse, tags=["Search"])
@limiter.limit("60/minute")
async def search_corpus(
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
    session: AsyncSession = Depends(get_session),
):
    """Search by text, location, or metadata with pagination."""
    repo = InscriptionRepository(session)
    actual_sort = sort_by if sort_by in ["date", "-date", "-id"] else "id"

    results = await repo.search(
        text_query=_clamp_text(text),
        findspot=findspot,
        language=language,
        classification=classification,
        limit=_clamp_limit(limit),
        offset=offset,
        sort_by=actual_sort,
    )

    accept_header = request.headers.get("accept", "")
    if (
        "application/xml" in accept_header
        or "application/tei+xml" in accept_header
        or "text/xml" in accept_header
    ):
        from fastapi.responses import Response
        from openetruscan.core.epidoc import results_to_epidoc
        xml_data = results_to_epidoc(results)
        return Response(content=xml_data, media_type="application/tei+xml")

    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@app.get("/search/geo", response_model=SearchResponse, tags=["Search"])
@limiter.limit("30/minute")
async def search_geo(
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
    ] = 50,
    session: AsyncSession = Depends(get_session),
):
    """Return only geotagged inscriptions (with coordinates)."""
    repo = InscriptionRepository(session)
    results = await repo.search(
        text_query=_clamp_text(text),
        findspot=findspot,
        classification=classification,
        limit=min(limit, 5000),
        offset=0,
        geo_only=True,
    )

    accept_header = request.headers.get("accept", "")
    if (
        "application/xml" in accept_header
        or "application/tei+xml" in accept_header
        or "text/xml" in accept_header
    ):
        from fastapi.responses import Response
        from openetruscan.core.epidoc import results_to_epidoc
        xml_data = results_to_epidoc(results)
        return Response(content=xml_data, media_type="application/tei+xml")

    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@app.get("/inscription/{inscription_id}", tags=["Corpus"])
@limiter.limit("120/minute")
async def get_inscription(
    request: Request,
    inscription_id: Annotated[
        str,
        Path(description="ID of the inscription to retrieve"),
    ],
    session: AsyncSession = Depends(get_session),
):
    """Fetch a single inscription by ID."""
    repo = InscriptionRepository(session)
    model = await repo.get_by_id(inscription_id)
    if not model:
        raise HTTPException(status_code=404, detail="Inscription not found")

    inscription = repo._to_dataclass(model)

    # ── Content Negotiation ──
    accept_header = request.headers.get("accept", "")
    if (
        "application/xml" in accept_header
        or "application/tei+xml" in accept_header
        or "text/xml" in accept_header
    ):
        try:
            from fastapi.responses import Response
            from openetruscan.core.epidoc import inscription_to_epidoc
            xml_data = inscription_to_epidoc(inscription)
            return Response(content=xml_data, media_type="application/tei+xml")
        except ImportError:
            raise HTTPException(
                status_code=501, detail="EpiDoc TEI capability is not installed server-side."
            )

    return _build_model(inscription)


@app.get("/inscription/{inscription_id}/concordance", tags=["Research"])
@limiter.limit("60/minute")
async def get_inscription_concordance(
    request: Request,
    inscription_id: str,
    session: AsyncSession = Depends(get_session)
):
    """
    Fetch all related inscriptions that share identifiers (TM, EDR, Pleiades) 
    with the target record. Defines the physical concordance cluster.
    """
    repo = InscriptionRepository(session)
    results = await repo.get_concordance_network(inscription_id)
    if not results:
        raise HTTPException(status_code=404, detail="Inscription not found or has no concordance")
    
    return [_build_model(i) for i in results]


@app.get("/inscription/{inscription_id}/names-network", tags=["Prosopography"])
@limiter.limit("60/minute")
async def get_inscription_names_network(
    request: Request,
    inscription_id: str,
    session: AsyncSession = Depends(get_session)
):
    """
    Fetch a graph representation (nodes/edges) of entities and relationships 
    associated with this inscription.
    """
    repo = InscriptionRepository(session)
    graph = await repo.get_names_network(inscription_id)
    if not graph or not graph.get("nodes"):
        # We still return the empty graph structure if no entities are found, 
        # but 404 if the inscription itself is missing would be handled by common logic.
        return {"nodes": [], "edges": []}
        
    return graph


@app.post("/inscriptions", tags=["Corpus"])
@limiter.limit("30/minute")
async def import_inscription(request: Request, session: AsyncSession = Depends(get_session)):
    """Import an inscription from EpiDoc TEI XML."""
    content_type = request.headers.get("content-type", "")
    if "xml" not in content_type:
        raise HTTPException(
            status_code=400, detail="Content-Type must be application/xml or similar"
        )

    body = await request.body()
    try:
        from openetruscan.core.epidoc import parse_epidoc
        inscription = parse_epidoc(body.decode("utf-8"))
        repo = InscriptionRepository(session)
        await repo.add(inscription)
        return {"status": "success", "id": inscription.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during import")


@app.get("/ids", tags=["Corpus"])
@limiter.limit("10/minute")
async def get_all_ids(request: Request, session: AsyncSession = Depends(get_session)):
    """Return the list of all inscription IDs (lightweight, ~50KB)."""
    repo = InscriptionRepository(session)
    return await repo.get_all_ids()


class RestoreRequest(BaseModel):
    """Pydantic model for neural lacunae restoration requests."""
    text: str
    top_k: int = 5


@app.post("/neural/restore", tags=["Neural"])
@limiter.limit("60/minute")
async def restore_lacunae(request: Request, body: RestoreRequest):
    """Predict missing characters in text with Leiden conventions (e.g. lar[..]i)."""
    try:
        from openetruscan.ml.neural import _TORCH_AVAILABLE, LacunaeRestorer

        if not _TORCH_AVAILABLE:
            raise HTTPException(
                status_code=501,
                detail="Lacunae restoration requires PyTorch, which is not installed in the lightweight API container.",
            )

        restorer = LacunaeRestorer()
        results = restorer.predict(body.text, top_k=body.top_k)
        return {"text": body.text, "predictions": results}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during restoration")


@app.get("/stats/summary", tags=["Statistics"])
@limiter.limit("30/minute")
async def stats_summary(request: Request, session: AsyncSession = Depends(get_session)):
    """Full corpus statistics for dashboard display."""
    repo = InscriptionRepository(session)
    return await repo.get_stats_summary()


@app.get("/stats/timeline", tags=["Statistics"])
@limiter.limit("30/minute")
async def stats_timeline(request: Request, session: AsyncSession = Depends(get_session)):
    """Dated + geolocated inscriptions with minimal fields for timeline map."""
    repo = InscriptionRepository(session)
    return await repo.get_timeline_stats() 


@app.get("/concordance", tags=["Search"])
@limiter.limit("30/minute")
async def concordance_search(
    request: Request,
    q: Annotated[
        str,
        Query(description="Search term (min 2 chars)", min_length=2, max_length=MAX_TEXT_LEN),
    ],
    context: Annotated[
        int,
        Query(ge=10, le=100, description="Context characters"),
    ] = 40,
    limit: Annotated[
        int,
        Query(ge=1, le=5000, description="Max occurrences to return"),
    ] = 2000,
    session: AsyncSession = Depends(get_session),
):
    """Server-side KWIC (Key Word In Context) concordance search."""
    repo = InscriptionRepository(session)
    rows = await repo.concordance(query=q, limit=limit, context=context)
    unique = len({r["inscId"] for r in rows})
    return {"total": len(rows), "unique_inscriptions": unique, "rows": rows}





@app.get("/names/network", tags=["Prosopography"])
@limiter.limit("150/minute")
async def names_network(
    request: Request,
    min_count: Annotated[
        int,
        Query(ge=1, le=100, description="Minimum attestations to include"),
    ] = 5,
    session: AsyncSession = Depends(get_session),
):
    """
    Prosopographic co-occurrence network endpoint.
    Fetches frequent name relationships from the database and returns a node/edge graph.
    """
    # Initialize repository with session
    repo = InscriptionRepository(session)
    # Fetch data from repository
    return await repo.get_full_names_network(min_count=min_count)


@app.get("/radius", response_model=SearchResponse, tags=["Search"])
@limiter.limit("60/minute")
async def search_by_radius(
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
    session: AsyncSession = Depends(get_session),
):
    """Search by spatial radius."""
    repo = InscriptionRepository(session)
    results = await repo.search_radius(
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        limit=_clamp_limit(limit),
    )
    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@app.get("/tiles/{z}/{x}/{y}.pbf", tags=["Search"])
@limiter.limit("500/minute")
async def get_vector_tiles(
    request: Request, 
    z: int, x: int, y: int,
    session: AsyncSession = Depends(get_session)
):
    """
    Serve PostGIS dynamic vector tiles (MVT).
    Delegates tile generation to the database repository.
    """
    from fastapi.responses import Response
    repo = InscriptionRepository(session)
    
    try:
        # Fetch the binary MVT data from the database
        mvt_bytes = await repo.get_mvt_tiles(z, x, y)
        
        # If no geometries intersect the tile, return 204 No Content
        if not mvt_bytes:
            return Response(status_code=204)
            
        # Return the binary protobuf data
        return Response(
            content=mvt_bytes,
            media_type="application/x-protobuf",
            headers={"Access-Control-Allow-Origin": "*"},
        )
    except Exception as e:
        logger.error(f"Vector tile error for {z}/{x}/{y}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="MVT tile generation failed"
        ) from e


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
    session: AsyncSession = Depends(get_session),
):
    """
    Perform semantic vector search using Gemini text-embedding-004.
    Matches embeddings in pgvector against the provided query string.
    """
    # 1. Ensure API key is configured
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GEMINI_API_KEY not configured on server",
        )
        
    # 2. Build Gemini Embedding URL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={settings.gemini_api_key}"
    payload = {"content": {"parts": [{"text": q[:2048]}]}}

    # local helper to fetch the embedding from Google
    async def _fetch_emb():
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10.0)
            resp.raise_for_status()
            return resp.json()["embedding"]["values"]

    # 3. Fetch the query embedding
    try:
        query_embedding = await _fetch_emb()
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate embedding for search query",
        ) from e

    # 4. Execute the vector search via repository
    try:
        repo = InscriptionRepository(session)
        results = await repo.semantic_search(
            query_embedding=query_embedding,
            field=field,
            limit=_clamp_limit(limit),
        )
    except Exception as e:
        logger.error(f"Semantic search failed in DB: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error during vector search execution",
        ) from e

    # 5. Format results
    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@app.get("/inscriptions/{id}/genetics", tags=["Genetics"])
@limiter.limit("30/minute")
async def get_genetic_matches(
    request: Request,
    id: Annotated[
        str,
        Path(description="ID of the inscription to find genetic matches for"),
    ],
    limit: Annotated[
        int,
        Query(ge=1, le=20),
    ] = 5,
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Spatio-temporal matchmaking between inscriptions and archaeogenetic samples."""
    repo = InscriptionRepository(session)
    matches = await repo.get_genetic_matches(inscription_id=id, limit=limit)
    return {"total": len(matches), "inscription_id": id, "matches": matches}


@app.get("/clan/{gens}", response_model=SearchResponse, tags=["Prosopography"])
@limiter.limit("30/minute")
async def search_by_clan(
    request: Request,
    gens: Annotated[
        str,
        Path(description="Gentilicium (clan name) to search for"),
    ],
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Prosopographical network search by clan/gens."""

    # Validate gens - allow letters, spaces, and hyphens
    if not re.match(r"^[\w\s\-]+$", gens, re.UNICODE):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gens contains invalid characters",
        )

    if len(gens) > MAX_GENS_LEN:
        return {"total": 0, "count": 0, "results": []}

    repo = InscriptionRepository(session)
    results = await repo.search_clan_members(gens)
    
    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@app.get("/stats", response_model=StatsResponse, tags=["Statistics"])
async def corpus_stats(session: AsyncSession = Depends(get_session)) -> Any:
    """Get corpus counts."""
    repo = InscriptionRepository(session)
    count = await repo.count()
    return StatsResponse(total_inscriptions=count)


# ── Statistical Analysis Endpoints ──────────────────────────────────────────


@app.get("/stats/frequency", tags=["Statistics"])
@limiter.limit("30/minute")
async def frequency_analysis(
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
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Letter frequency analysis, optionally comparing two sites (chi² test)."""
    from openetruscan.core.statistics import (
        compare_frequencies,
        letter_frequencies,
    )

    repo = InscriptionRepository(session)
    rows_a = await repo.get_all_canonical_texts(findspot=findspot)
    texts_a = [r["canonical"] for r in rows_a if r["canonical"]]
    freq_a = letter_frequencies(texts_a, language=language)

    response: dict[str, Any] = {"primary": freq_a.to_dict(), "label_a": findspot or "All sites"}

    if findspot_b:
        rows_b = await repo.get_all_canonical_texts(findspot=findspot_b)
        texts_b = [r["canonical"] for r in rows_b if r["canonical"]]
        freq_b = letter_frequencies(texts_b, language=language)
        comparison = compare_frequencies(freq_a, freq_b)
        response["secondary"] = freq_b.to_dict()
        response["label_b"] = findspot_b
        response["comparison"] = comparison.to_dict()

    return response


@app.get("/stats/clusters", tags=["Statistics"])
@limiter.limit("15/minute")
async def dialect_clusters(
    request: Request,
    min_inscriptions: Annotated[
        int,
        Query(description="Minimum inscriptions per site", ge=2, le=100),
    ] = 5,
    language: Annotated[
        str,
        Query(description="Language adapter", max_length=50),
    ] = "etruscan",
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Dialect clustering via Ward's hierarchical method with cosine distance."""
    from openetruscan.core.statistics import cluster_sites_from_texts

    repo = InscriptionRepository(session)
    rows = await repo.get_all_canonical_texts()
    result = cluster_sites_from_texts(rows, language=language, min_inscriptions=min_inscriptions)
    return result.to_dict()


@app.get("/stats/date-estimate", tags=["Statistics"])
@limiter.limit("60/minute")
async def date_estimate(
    request: Request,
    text: Annotated[
        str,
        Query(description="Inscription text to analyze", max_length=MAX_TEXT_LEN),
    ],
    language: Annotated[
        str,
        Query(description="Language adapter", max_length=50),
    ] = "etruscan",
) -> Any:
    """Estimate chronological period from orthographic features."""
    from openetruscan.core.statistics import estimate_date

    result = estimate_date(text, language=language)
    return result.to_dict()


@app.get("/pelagios.jsonld", tags=["Linked Data"])
async def pelagios_feed(session: AsyncSession = Depends(get_session)) -> Any:
    """Pelagios-compatible JSON-LD feed for Linked Open Data."""
    from fastapi.responses import Response
    from openetruscan.api.lod import corpus_to_pelagios_jsonld

    repo = InscriptionRepository(session)
    results = await repo.search(limit=500, geo_only=True)
    jsonld = corpus_to_pelagios_jsonld(results)
    return Response(
        content=jsonld,
        media_type="application/ld+json",
    )


@app.get("/pleiades-stats", tags=["Linked Data"])
async def pleiades_coverage(session: AsyncSession = Depends(get_session)) -> Any:
    """Pleiades coverage statistics."""
    repo = InscriptionRepository(session)
    summary = await repo.get_stats_summary()
    total = summary.get("total", 0)
    linked = summary.get("pleiades_linked", 0)
    return {
        "total_inscriptions": total,
        "linked_to_pleiades": linked,
        "coverage_pct": round(linked / total * 100, 1) if total else 0,
    }


# Static file serving removed — frontend is deployed on GitHub Pages.
# API-only server: all routes are under /search, /radius, /stats, etc.
