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
import asyncio
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import secrets
from fastapi.middleware.cors import CORSMiddleware
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


security_scheme = HTTPBearer()


def verify_admin(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)):
    """Verifies that mutational operations are using the core ADMIN_TOKEN.

    If ``settings.admin_token`` is not configured this returns 503 (not 500):
    "the admin write surface is intentionally disabled" is an operational
    state, not a server bug. /health surfaces the same condition under
    ``checks.admin_token_configured`` so the gap is visible before someone
    tries to call an admin endpoint.
    """
    if not settings.admin_token:
        raise HTTPException(
            status_code=503,
            detail=(
                "Admin write endpoints are disabled because ADMIN_TOKEN is not "
                "configured on this deployment. See docs/internal/SECRETS.md."
            ),
        )
    if not secrets.compare_digest(credentials.credentials, settings.admin_token):
        raise HTTPException(status_code=403, detail="Invalid or missing admin credentials")
    return credentials


def _configure_logging():
    """Setup structured JSON logging for production."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    if settings.is_production:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            # In a real SOTA implementation, we'd use structlog or python-json-logger
            # e.g. using pythonjsonlogger.jsonlogger.JsonFormatter
        )
    else:
        logging.basicConfig(level=log_level)


def _maybe_install_otel(app: FastAPI) -> None:
    """Wire OpenTelemetry tracing if the optional packages are installed.

    The instrumentation is opt-in via ``[telemetry]`` extra so the prod
    container only pays the import cost when intended (~30 MB on disk and a
    handful of milliseconds at startup). When ``OTEL_EXPORTER_OTLP_ENDPOINT``
    is set we ship spans to a collector (Cloud Trace via the ops agent's OTLP
    receiver, or any OpenTelemetry collector). Without it, tracing is enabled
    in-memory only — useful for local debugging via ``otel-cli``.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    except ImportError:
        # Optional. Production prefers explicit dep install; dev runs without.
        return

    resource = Resource.create({
        "service.name": "openetruscan-api",
        "service.version": __version__,
    })
    provider = TracerProvider(resource=resource)

    import os as _os
    endpoint = _os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        except ImportError:
            pass

    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/health,/ready,/live")
    AsyncPGInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown events, including uptime initialization."""
    global START_TIME
    START_TIME = datetime.now(timezone.utc)
    _configure_logging()
    _maybe_install_otel(app)

    # Shared httpx client for outbound calls (Gemini embeddings, etc.).
    # Opening one per-request was the previous pattern and showed up in latency under load.
    import httpx

    app.state.http = httpx.AsyncClient(timeout=10.0)

    # Lazily-loaded ByT5/CharMLM lacunae restorer. Holding a single instance on
    # app.state lets `predict()` reuse the model after the first call instead of
    # re-instantiating (and re-building the dummy model) on every request.
    app.state.lacunae = None  # constructed on first /neural/restore call

    import collections
    app.state.query_embedding_cache = collections.OrderedDict()

    try:
        yield
    finally:
        await app.state.http.aclose()


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
    docs_url="/docs" if settings.enable_docs else None,  # Interactive Swagger UI
    redoc_url=None,  # ReDoc disabled for simplicity
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
    allow_origins=settings.cors_origins,  # Controlled via .env
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    # Tightened from "*". With allow_credentials=True, "*" expands to a generous
    # CSRF surface; list only the headers the frontend actually sends.
    allow_headers=["Accept", "Content-Type", "Authorization"],
    max_age=600,  # Cache preflight responses for 10 minutes
)


# 3. GLOBAL SECURITY HEADERS MIDDLEWARE
# Hardening the API against common web vulnerabilities (XSS, Framing, Sniffing)
@app.middleware("http")
async def _add_security_headers(request: Request, call_next):
    """Add production-grade security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"  # Prevent MIME type sniffing
    response.headers["X-Frame-Options"] = "DENY"  # Prevent clickjacking
    response.headers["X-XSS-Protection"] = "1; mode=block"  # Enable browser XSS filtering
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
        content={
            "type": "about:blank",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "Internal server error",
            "instance": request.url.path
        },
        media_type="application/problem+json"
    )


@app.exception_handler(ValueError)
async def _value_error_handler(request: Request, exc: ValueError):
    """Handle validation and logic errors (ValueError) with a 400 Bad Request response."""
    logger.warning("ValueError on %s %s: %s", request.method, request.url.path, str(exc))
    return JSONResponse(
        status_code=400,
        content={
            "type": "about:blank",
            "title": "Bad Request",
            "status": 400,
            "detail": str(exc),
            "instance": request.url.path
        },
        media_type="application/problem+json"
    )


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Format standard HTTP exceptions to RFC 7807."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": "about:blank",
            "title": "HTTP Error",
            "status": exc.status_code,
            "detail": str(exc.detail),
            "instance": request.url.path
        },
        media_type="application/problem+json"
    )


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    """Format FastAPI validation errors to RFC 7807."""
    return JSONResponse(
        status_code=422,
        content={
            "type": "about:blank",
            "title": "Unprocessable Entity",
            "status": 422,
            "detail": "Request validation failed",
            "errors": exc.errors(),
            "instance": request.url.path
        },
        media_type="application/problem+json"
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
    source_code: str = "unknown"
    source_detail: str | None = None
    original_script_entry: str | None = None


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
        source_code=i.source_code,
        source_detail=i.source_detail,
        original_script_entry=i.original_script_entry,
    )


# ── Health Endpoint ────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check(request: Request, session: AsyncSession = Depends(get_session)):
    """Deep health check.

    Returns 200 with `status: healthy` only when every dependency the public
    surface actually needs is reachable. A 503 is preferable to a green check
    while the DB is gone.
    """
    import asyncio

    uptime = (datetime.now(timezone.utc) - START_TIME).total_seconds()

    rss_mb = 0.0
    try:
        import resource

        rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_mb = round(rss_kb / 1024, 1)
    except ImportError:
        pass

    async def probe_db():
        try:
            t0 = datetime.now(timezone.utc)
            count = await InscriptionRepository(session).count()
            ms = (datetime.now(timezone.utc) - t0).total_seconds() * 1000
            return {"ok": count > 0, "count": count, "latency_ms": round(ms, 1)}
        except Exception as e:
            return {"ok": False, "error": type(e).__name__}

    async def probe_fuseki():
        # Side-channel: nginx routes /sparql -> http://fuseki:3030/openetruscan/sparql.
        # We hit the internal hostname directly so a public outage does not affect this.
        try:
            client = request.app.state.http
            t0 = datetime.now(timezone.utc)
            resp = await client.get(
                "http://fuseki:3030/openetruscan/sparql",
                params={"query": "SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o } LIMIT 1"},
                timeout=2.0,
            )
            ms = (datetime.now(timezone.utc) - t0).total_seconds() * 1000
            return {"ok": resp.status_code == 200, "latency_ms": round(ms, 1)}
        except Exception as e:
            return {"ok": False, "error": type(e).__name__}

    db_result, fuseki_result = await asyncio.gather(probe_db(), probe_fuseki())

    deps_ok = db_result["ok"]  # fuseki failure is degraded, not down
    status_code = 200 if deps_ok else 503

    body = {
        "status": "healthy" if deps_ok else "unhealthy",
        "version": __version__,
        "uptime_seconds": round(uptime, 2),
        "mem_rss_mb": rss_mb,
        "checks": {
            "db": db_result,
            "fuseki": fuseki_result,
            "gemini_configured": bool(settings.gemini_api_key),
            "admin_token_configured": bool(settings.admin_token),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(content=body, status_code=status_code)


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

# /corpus was deprecated in v0.3 in favour of /search with pagination. Removed
# in this branch — there are no remaining callers in the frontend or the
# documented client examples. /search?limit=500 is the drop-in replacement.


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
    provenance: Annotated[
        str | None,
        Query(
            description=(
                "Filter by provenance tier: excavated, acquired_documented, "
                "acquired_undocumented, unknown"
            ),
            pattern="^(excavated|acquired_documented|acquired_undocumented|unknown)$",
        ),
    ] = None,
    has_provenance: Annotated[
        bool | None,
        Query(
            description=(
                "Restrict to inscriptions with (true) or without (false) a known findspot. "
                "Useful for citation contexts: pass `true` to omit unprovenanced material."
            ),
        ),
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
        provenance=provenance,
        has_provenance=has_provenance,
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
    provenance: Annotated[
        str | None,
        Query(
            description="Provenance tier filter",
            pattern="^(excavated|acquired_documented|acquired_undocumented|unknown)$",
        ),
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
        provenance=provenance,
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


def _inscription_jsonld(inscription) -> dict:
    """Render an inscription as Schema.org / Pelagios-flavoured JSON-LD."""
    base = "https://api.openetruscan.com"
    iri = f"{base}/inscription/{inscription.id}"
    place = (
        {
            "@type": "Place",
            "name": inscription.findspot,
            **(
                {"geo": {"@type": "GeoCoordinates",
                         "latitude": inscription.findspot_lat,
                         "longitude": inscription.findspot_lon}}
                if inscription.findspot_lat is not None
                and inscription.findspot_lon is not None
                else {}
            ),
        }
        if inscription.findspot
        else None
    )
    same_as = []
    if inscription.trismegistos_id:
        same_as.append(f"https://www.trismegistos.org/text/{inscription.trismegistos_id}")
    if inscription.pleiades_id:
        same_as.append(f"https://pleiades.stoa.org/places/{inscription.pleiades_id}")
    if inscription.eagle_id:
        same_as.append(f"https://www.edr-edr.it/edr_programmi/res_complex_comune.php?do=show&id_nr={inscription.eagle_id}")

    payload = {
        "@context": [
            "http://www.w3.org/ns/anno.jsonld",
            {"schema": "http://schema.org/", "lawd": "http://lawd.info/ontology/"},
        ],
        "@id": iri,
        "@type": ["lawd:Inscription", "schema:CreativeWork"],
        "schema:identifier": inscription.id,
        "schema:text": inscription.canonical,
        "schema:alternativeHeadline": inscription.raw_text,
        "lawd:foundAt": place,
        "schema:dateCreated": (
            f"-{abs(inscription.date_approx):04d}"
            if inscription.date_approx and inscription.date_approx < 0
            else (str(inscription.date_approx) if inscription.date_approx else None)
        ),
        "schema:about": inscription.classification,
        "schema:inLanguage": inscription.language,
        "schema:license": "https://creativecommons.org/publicdomain/zero/1.0/",
    }
    if same_as:
        payload["schema:sameAs"] = same_as
    return payload


def _inscription_turtle(inscription) -> str:
    """Render an inscription as RDF/Turtle. Lossy but stable."""
    lines = [
        "@prefix lawd: <http://lawd.info/ontology/> .",
        "@prefix schema: <http://schema.org/> .",
        "@prefix dcterms: <http://purl.org/dc/terms/> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "",
        f"<https://api.openetruscan.com/inscription/{inscription.id}> a lawd:Inscription ;",
        f'    schema:identifier "{inscription.id}" ;',
        f'    schema:text """{(inscription.canonical or "").replace(chr(34), chr(92) + chr(34))}""" ;',
        f'    schema:inLanguage "{inscription.language}" ;',
        f'    schema:about "{inscription.classification}"',
    ]
    if inscription.findspot:
        lines.append(
            f'    ; lawd:foundAt [ a schema:Place ; schema:name "{inscription.findspot}" ]'
        )
    lines.append("    .")
    return "\n".join(lines) + "\n"


def _negotiate(request: Request) -> str:
    """Return the canonical media type to render for this request.

    Honours both the ``Accept`` header and the ``?format=`` query string. The
    query string wins (handier for sharable links / curl). Supported keys:

      - ``html`` / ``application/json``  → default JSON for the API and the
        front-end (returned as the standard Pydantic InscriptionModel).
      - ``jsonld`` / ``application/ld+json`` → Schema.org + Pelagios LAWD.
      - ``turtle`` / ``text/turtle`` → RDF/Turtle.
      - ``tei`` / ``application/tei+xml``  → EpiDoc XML.
    """
    fmt = request.query_params.get("format", "").lower()
    if fmt in {"jsonld", "json-ld"}:
        return "application/ld+json"
    if fmt in {"turtle", "ttl", "rdf"}:
        return "text/turtle"
    if fmt in {"tei", "epidoc", "xml"}:
        return "application/tei+xml"
    if fmt in {"json", "html"}:
        return "application/json"
    accept = request.headers.get("accept", "")
    if "application/ld+json" in accept:
        return "application/ld+json"
    if "text/turtle" in accept:
        return "text/turtle"
    if any(t in accept for t in ("application/tei+xml", "application/xml", "text/xml")):
        return "application/tei+xml"
    return "application/json"


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
    """Fetch a single inscription by ID with content negotiation.

    Each inscription is a citable resource; serve it in the format the caller
    asks for (JSON for the frontend, JSON-LD for linked-data aggregators,
    Turtle for triple stores, EpiDoc TEI for philological tooling). All four
    variants point at the same canonical IRI via ``Link: rel="alternate"``
    headers so the URL itself stays stable across formats.
    """
    repo = InscriptionRepository(session)
    model = await repo.get_by_id(inscription_id)
    if not model:
        raise HTTPException(status_code=404, detail="Inscription not found")

    inscription = repo._to_dataclass(model)
    media = _negotiate(request)

    base = f"https://api.openetruscan.com/inscription/{inscription_id}"
    alt_links = ", ".join(
        f'<{base}?format={fmt}>; rel="alternate"; type="{mt}"'
        for fmt, mt in (
            ("json", "application/json"),
            ("jsonld", "application/ld+json"),
            ("turtle", "text/turtle"),
            ("tei", "application/tei+xml"),
        )
    )
    headers = {
        "Link": alt_links,
        "Vary": "Accept",
    }

    from fastapi.responses import JSONResponse, Response

    if media == "application/ld+json":
        return JSONResponse(
            _inscription_jsonld(inscription),
            media_type="application/ld+json",
            headers=headers,
        )
    if media == "text/turtle":
        return Response(
            content=_inscription_turtle(inscription),
            media_type="text/turtle; charset=utf-8",
            headers=headers,
        )
    if media == "application/tei+xml":
        try:
            from openetruscan.core.epidoc import inscription_to_epidoc

            xml_data = inscription_to_epidoc(inscription)
            return Response(
                content=xml_data,
                media_type="application/tei+xml",
                headers=headers,
            )
        except ImportError:
            raise HTTPException(
                status_code=501, detail="EpiDoc TEI capability is not installed server-side."
            )

    # JSON default — emit Pydantic via JSONResponse so the Link header lands.
    return JSONResponse(
        _build_model(inscription).model_dump(),
        headers=headers,
    )


@app.get("/inscription/{inscription_id}/concordance", tags=["Research"])
@limiter.limit("60/minute")
async def get_inscription_concordance(
    request: Request, inscription_id: str, session: AsyncSession = Depends(get_session)
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
    request: Request, inscription_id: str, session: AsyncSession = Depends(get_session)
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


# In-memory idempotency store for /inscriptions POST. The endpoint runs at
# 30/minute on a single VM instance and the import flow is admin-only, so a
# process-local TTL cache is the right level of complexity. Once the API moves
# to Cloud Run (multi-instance), this will need to migrate to Redis or a
# `idempotency_keys` table — see ROADMAP.md.
_IDEMPOTENCY_TTL_SECONDS = 24 * 3600
_IDEMPOTENCY_CACHE: dict[str, tuple[float, dict]] = {}


def _idempotency_get(key: str) -> dict | None:
    """Return a cached response for `key` if present and unexpired."""
    import time

    record = _IDEMPOTENCY_CACHE.get(key)
    if record is None:
        return None
    expires_at, payload = record
    if time.time() > expires_at:
        _IDEMPOTENCY_CACHE.pop(key, None)
        return None
    return payload


def _idempotency_put(key: str, payload: dict) -> None:
    import time

    _IDEMPOTENCY_CACHE[key] = (time.time() + _IDEMPOTENCY_TTL_SECONDS, payload)
    # Cheap eviction: if the cache grows beyond a sane bound, drop the oldest
    # 25% of entries. Importing inscriptions is rare, so this rarely fires.
    if len(_IDEMPOTENCY_CACHE) > 1024:
        items = sorted(_IDEMPOTENCY_CACHE.items(), key=lambda kv: kv[1][0])
        for k, _ in items[: len(items) // 4]:
            _IDEMPOTENCY_CACHE.pop(k, None)


@app.post("/inscriptions", tags=["Corpus"])
@limiter.limit("30/minute")
async def import_inscription(
    request: Request,
    _auth: HTTPAuthorizationCredentials = Depends(verify_admin),
    session: AsyncSession = Depends(get_session),
):
    """Import an inscription from EpiDoc TEI XML.

    Supports the ``Idempotency-Key`` header (RFC draft `idempotency-header`).
    A client retrying after a network blip can safely re-POST the same body
    with the same key; the second call returns the cached response without
    re-running the EpiDoc parse and the upsert.
    """
    content_type = request.headers.get("content-type", "")
    if "xml" not in content_type:
        raise HTTPException(
            status_code=400, detail="Content-Type must be application/xml or similar"
        )

    idempotency_key = request.headers.get("idempotency-key")
    if idempotency_key:
        cached = _idempotency_get(idempotency_key)
        if cached is not None:
            return cached

    body = await request.body()
    try:
        from openetruscan.core.epidoc import parse_epidoc

        inscription = parse_epidoc(body.decode("utf-8"))
        repo = InscriptionRepository(session)
        await repo.add(inscription)
        response = {"status": "success", "id": inscription.id}
        if idempotency_key:
            _idempotency_put(idempotency_key, response)
        return response
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
    model_uri: str = "local://default"


@app.post("/neural/restore", tags=["Neural"])
@limiter.limit("60/minute")
async def restore_lacunae(
    request: Request,
    body: RestoreRequest,
    _auth: HTTPAuthorizationCredentials = Depends(verify_admin),
):
    """Predict missing characters in text with Leiden conventions (e.g. lar[..]i).

    Two modes:
      * **Remote** — if ``settings.byt5_service_url`` is set we proxy the request
        to a dedicated Cloud Run service (`services/byt5-restorer/`). This is
        the production mode: the API container stays small and inference
        autoscales to zero between calls.
      * **In-process** — fallback when no service URL is configured. Loads the
        torch model lazily and offloads inference to a worker thread.
    """
    if settings.byt5_service_url:
        client = request.app.state.http
        try:
            resp = await client.post(
                f"{settings.byt5_service_url.rstrip('/')}/restore",
                json={"text": body.text, "top_k": body.top_k},
                timeout=30.0,
            )
            resp.raise_for_status()
            return {"text": body.text, "predictions": resp.json().get("predictions", [])}
        except httpx.HTTPStatusError as e:
            # The remote service is up but rejected the call — surface its status.
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.HTTPError as e:
            # Connection / timeout. 502 is the right shape for "we couldn't reach
            # an upstream we depend on".
            raise HTTPException(status_code=502, detail=f"ByT5 service unreachable: {e}")

    try:
        from openetruscan.ml.neural import _TORCH_AVAILABLE, LacunaeRestorer

        if not _TORCH_AVAILABLE:
            raise HTTPException(
                status_code=501,
                detail="Lacunae restoration requires PyTorch, which is not installed in the lightweight API container.",
            )

        import asyncio

        registry = getattr(request.app.state, "lacunae_registry", {})
        restorer = registry.get(body.model_uri)
        if restorer is None:
            # First-time model load is also CPU-bound and >5 s; offload it.
            restorer = await asyncio.to_thread(LacunaeRestorer, model_uri=body.model_uri)
            registry[body.model_uri] = restorer
            request.app.state.lacunae_registry = registry

        # Inference is CPU-bound torch — running it directly blocks the event
        # loop and starves every other request. Offload to the default thread
        # pool, matching the pattern used by /search/hybrid's reranker.
        results = await asyncio.to_thread(restorer.predict, body.text, top_k=body.top_k)
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
    """Full corpus statistics for dashboard display, including the provenance breakdown."""
    repo = InscriptionRepository(session)
    return await repo.get_stats_summary()


@app.get("/stats/provenance", tags=["Statistics"])
@limiter.limit("60/minute")
async def stats_provenance(request: Request, session: AsyncSession = Depends(get_session)):
    """
    Honest provenance breakdown of the corpus.

    Returns the per-tier counts plus the share of the corpus that has a
    documented findspot vs. is unprovenanced. Citation tooling (and the
    homepage) should consume this rather than the headline `total` so users
    can distinguish "philologically attested" from "archaeologically located".
    """
    repo = InscriptionRepository(session)
    summary = await repo.get_stats_summary()
    return summary["provenance"]


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
    request: Request, z: int, x: int, y: int, session: AsyncSession = Depends(get_session)
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="MVT tile generation failed"
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

    # 2. Build Gemini Embedding request. The API key goes in the x-goog-api-key
    # header rather than the URL query string so it does not leak into nginx
    # access logs, browser referrers, or proxy caches.
    url = "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent"
    payload = {"content": {"parts": [{"text": q[:2048]}]}}
    headers = {"x-goog-api-key": settings.gemini_api_key}

    # 3. Fetch from cache or Gemini API
    cache = getattr(request.app.state, "query_embedding_cache", None)
    if cache is not None and q in cache:
        query_embedding = cache[q]
        cache.move_to_end(q)
    else:
        try:
            client = request.app.state.http
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            query_embedding = resp.json()["embedding"]["values"]
            if cache is not None:
                cache[q] = query_embedding
                if len(cache) > 1000:
                    cache.popitem(last=False)
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


@app.get("/inscriptions/{id}/genetics", tags=["Genetics"], include_in_schema=False)
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
@limiter.limit("5/minute")
async def pelagios_feed(request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    """Pelagios-compatible JSON-LD feed for Linked Open Data."""
    from fastapi.responses import Response
    from openetruscan.api.lod import corpus_to_pelagios_jsonld

    repo = InscriptionRepository(session)
    # Reconciled to the actual 6633 corpus rows, no longer artificially constrained to 500 geo-only
    results = await repo.search(limit=10000, geo_only=False)
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


# ── Newly Exponentiated Endpoints ──────────────────────────────────────────


@app.get("/export/epidoc", tags=["Export"])
@limiter.limit("5/minute")
async def export_epidoc_bulk(request: Request, session: AsyncSession = Depends(get_session)):
    """Stream the entire corpus as a multi-document EpiDoc XML response."""
    from fastapi.responses import StreamingResponse
    from openetruscan.core.epidoc import inscription_to_epidoc

    repo = InscriptionRepository(session)

    async def _xml_generator():
        yield '<?xml version="1.0" encoding="UTF-8"?>\n'
        yield '<TEI xmlns="http://www.tei-c.org/ns/1.0">\n'
        yield "<text><body>\n"

        offset = 0
        batch_size = 200
        while True:
            # We must use await since repo.search is async
            results = await repo.search(limit=batch_size, offset=offset)
            if not results.inscriptions:
                break
            for insc in results.inscriptions:
                # We yield the inner <TEI> as part of a collection, but simplified.
                fragment = inscription_to_epidoc(insc)
                # Strip XML decl and TEI wrap for the bulk stream (simplified wrapping)
                fragment = fragment.replace('<?xml version="1.0" encoding="UTF-8"?>\n', "")
                yield fragment + "\n"
            offset += batch_size

        yield "</body></text></TEI>\n"

    return StreamingResponse(_xml_generator(), media_type="application/tei+xml")


@app.get("/inscriptions/{inscription_id}/validate", tags=["Corpus"])
@limiter.limit("30/minute")
async def validate_inscription_flags(
    request: Request, inscription_id: str, session: AsyncSession = Depends(get_session)
):
    """Auto-detect potential issues (OCR, out-of-range, etc) in an inscription."""
    from openetruscan.core.corpus import auto_flag_inscription

    repo = InscriptionRepository(session)

    model = await repo.get_by_id(inscription_id)
    if not model:
        raise HTTPException(status_code=404, detail="Inscription not found")

    insc_data = repo._to_dataclass(model)
    flags = auto_flag_inscription(insc_data)

    return {"id": inscription_id, "flags": flags, "is_valid": len(flags) == 0}


@app.get("/stats/bayesian-date", tags=["Statistics"])
@limiter.limit("30/minute")
async def bayesian_date_estimate(
    request: Request,
    text: Annotated[
        str,
        Query(description="Inscription text to date probabilistically", max_length=MAX_TEXT_LEN),
    ],
    language: Annotated[
        str,
        Query(description="Language adapter", max_length=50),
    ] = "etruscan",
):
    """Estimate inscription date using Bayesian inference over time bins."""
    from openetruscan.core.statistics import bayesian_date

    result = bayesian_date(text, language=language)
    return result.to_dict()


_FAMILY_GRAPH_CACHE = None
_FAMILY_GRAPH_LOCK = None


async def _get_family_graph(repo: InscriptionRepository, language: str = "etruscan") -> Any:
    """Returns a cached FamilyGraph, building it once upon first request."""
    global _FAMILY_GRAPH_CACHE, _FAMILY_GRAPH_LOCK
    
    if _FAMILY_GRAPH_CACHE is not None:
        return _FAMILY_GRAPH_CACHE
        
    if _FAMILY_GRAPH_LOCK is None:
        _FAMILY_GRAPH_LOCK = asyncio.Lock()
        
    async with _FAMILY_GRAPH_LOCK:
        if _FAMILY_GRAPH_CACHE is None:
            _FAMILY_GRAPH_CACHE = await _build_family_graph(repo, language)
        return _FAMILY_GRAPH_CACHE


async def _build_family_graph(repo: InscriptionRepository, language: str = "etruscan") -> Any:
    """Async wrapper to build the FamilyGraph from the Async InscriptionRepository."""
    from openetruscan.core.prosopography import FamilyGraph, Person, parse_name
    from openetruscan.core.adapter import load_adapter

    graph = FamilyGraph()
    person_id = 0
    batch_size = 500
    offset = 0
    adapter = load_adapter(language)

    while True:
        results = await repo.search(limit=batch_size, offset=offset)
        if not results.inscriptions:
            break

        for inscription in results.inscriptions:
            if not inscription.canonical.strip():
                continue

            formula = parse_name(inscription.canonical, language=language, adapter=adapter)
            person = Person(
                id=f"P{person_id:05d}",
                name_formula=formula,
                inscription_ids=[inscription.id],
                findspots=[inscription.findspot] if inscription.findspot else [],
            )
            graph.add_person(person)
            person_id += 1

        offset += batch_size

    return graph


@app.get("/prosopography/export", tags=["Prosopography"])
@limiter.limit("5/minute")
async def export_prosopography(
    request: Request,
    fmt: Annotated[
        str,
        Query(description="Export format: json, graphml, csv, neo4j"),
    ] = "json",
    session: AsyncSession = Depends(get_session),
):
    """Export the entire prosopographical FamilyGraph."""
    from fastapi.responses import Response

    repo = InscriptionRepository(session)
    graph = await _get_family_graph(repo)

    try:
        content = graph.export(fmt=fmt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    media_types = {
        "json": "application/json",
        "csv": "text/csv",
        "graphml": "application/xml",
        "neo4j": "text/plain",
    }

    return Response(content=content, media_type=media_types.get(fmt, "text/plain"))


@app.get("/prosopography/persons/search", tags=["Prosopography"])
@limiter.limit("30/minute")
async def search_prosopography_persons(
    request: Request,
    gens: str | None = None,
    praenomen: str | None = None,
    gender: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Search for specific named persons in the prosopographical network."""
    repo = InscriptionRepository(session)
    graph = await _get_family_graph(repo)

    persons = graph.search_persons(gens=gens, praenomen=praenomen, gender=gender)

    # Manually serialize persons since the method returns Person objects directly
    return [
        {
            "id": p.id,
            "name": p.name_formula.canonical,
            "gender": p.gender,
            "praenomen": p.praenomen,
            "gentilicium": p.gentilicium,
            "patronymic": p.name_formula.patronymic(),
            "findspots": p.findspots,
            "inscription_ids": p.inscription_ids,
        }
        for p in persons
    ]


@app.get("/prosopography/clans/{gens}/related", tags=["Prosopography"])
@limiter.limit("30/minute")
async def related_clans(request: Request, gens: str, session: AsyncSession = Depends(get_session)):
    """Find clans strictly related to the target clan via co-occurrence."""
    repo = InscriptionRepository(session)
    graph = await _get_family_graph(repo)

    related = graph.related_clans(gens)
    return {"clan": gens, "related_clans": related}


@app.get("/admin/validate-pleiades", tags=["Admin"])
@limiter.limit("10/minute")
async def admin_validate_pleiades(request: Request, session: AsyncSession = Depends(get_session)):
    """Administrative audit endpoint for Pleiades identifier alignments."""
    repo = InscriptionRepository(session)
    return await repo.validate_pleiades_ids()


# ── Data sources ────────────────────────────────────────────────────────────


class PromoteProvenanceRequest(BaseModel):
    new_status: str
    bibliography: str | None = None
    notes: str | None = None
    reviewed_by: str = "admin"


class PromoteProvenanceResponse(BaseModel):
    status: str
    inscription_id: str
    old_status: str
    new_status: str
    audit_id: int


class ProvenanceAuditEntry(BaseModel):
    id: int
    old_status: str | None
    new_status: str
    notes: str | None
    created_by: str | None
    created_at: str | None


class ProvenanceHistoryResponse(BaseModel):
    inscription_id: str
    audits: list[ProvenanceAuditEntry]


@app.post(
    "/inscription/{inscription_id}/promote-provenance",
    tags=["Admin"],
    response_model=PromoteProvenanceResponse,
)
@limiter.limit("30/minute")
async def promote_provenance(
    request: Request,
    inscription_id: str,
    payload: PromoteProvenanceRequest,
    _auth: HTTPAuthorizationCredentials = Depends(verify_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Promote an inscription's provenance tier and write an audit row.

    This is the primary curatorial endpoint for upgrading provenance status
    (e.g. ``unprovenanced`` → ``acquired_documented`` → ``excavated``).
    Every call produces a ``provenance_audits`` row for the chain of evidence.
    """
    from openetruscan.core.corpus import PROVENANCE_STATUSES

    if payload.new_status not in PROVENANCE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"new_status must be one of {PROVENANCE_STATUSES}",
        )

    repo = InscriptionRepository(session)
    insc = await repo.get_by_id(inscription_id)
    if not insc:
        raise HTTPException(status_code=404, detail="Inscription not found")

    old_status = insc.provenance_status or "unknown"
    insc.provenance_status = payload.new_status

    from openetruscan.db.models import ProvenanceAudit

    note_parts = []
    if payload.bibliography:
        note_parts.append(f"Bib: {payload.bibliography}")
    if payload.notes:
        note_parts.append(payload.notes)

    audit = ProvenanceAudit(
        inscription_id=insc.id,
        old_status=old_status,
        new_status=payload.new_status,
        notes=" | ".join(note_parts) if note_parts else None,
        created_by=payload.reviewed_by,
    )
    session.add(audit)
    await session.commit()

    return {
        "status": "promoted",
        "inscription_id": inscription_id,
        "old_status": old_status,
        "new_status": payload.new_status,
        "audit_id": audit.id,
    }


@app.get(
    "/inscription/{inscription_id}/provenance-history",
    tags=["Corpus"],
    response_model=ProvenanceHistoryResponse,
)
@limiter.limit("60/minute")
async def provenance_history(
    request: Request,
    inscription_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Return the full provenance audit trail for an inscription."""
    from openetruscan.db.models import ProvenanceAudit
    from sqlalchemy import select

    stmt = (
        select(ProvenanceAudit)
        .where(ProvenanceAudit.inscription_id == inscription_id)
        .order_by(ProvenanceAudit.created_at.desc())
    )
    result = await session.execute(stmt)
    audits = result.scalars().all()

    return ProvenanceHistoryResponse(
        inscription_id=inscription_id,
        audits=[
            ProvenanceAuditEntry(
                id=a.id,
                old_status=a.old_status,
                new_status=a.new_status,
                notes=a.notes,
                created_by=a.created_by,
                created_at=a.created_at.isoformat() if a.created_at else None,
            )
            for a in audits
        ],
    )

@app.get("/sources", tags=["Sources"])
@limiter.limit("60/minute")
async def list_data_sources(request: Request, session: AsyncSession = Depends(get_session)):
    """List the data sources backing the corpus, with provenance baselines.

    Each entry includes the canonical citation, license, and the *typical*
    archaeological provenance tier of rows from that source. Per-row provenance
    is still in `inscriptions.provenance_status`; the source baseline is just
    a hint for the UI ("most rows from Larth are unprovenanced").
    """
    from sqlalchemy import select, func as sa_func

    from openetruscan.db.models import DataSource, Inscription

    counts_subq = (
        select(
            Inscription.source_id.label("source_id"),
            sa_func.count().label("count"),
        )
        .where(Inscription.source_id.is_not(None))
        .group_by(Inscription.source_id)
        .subquery()
    )
    stmt = select(DataSource, counts_subq.c.count).join(
        counts_subq, counts_subq.c.source_id == DataSource.id, isouter=True
    )
    rows = (await session.execute(stmt)).all()

    return {
        "sources": [
            {
                "id": s.id,
                "display_name": s.display_name,
                "citation": s.citation,
                "license": s.license,
                "url": s.url,
                "provenance_baseline": s.provenance_baseline,
                "retrieved_at": s.retrieved_at.isoformat() if s.retrieved_at else None,
                "inscription_count": int(c or 0),
            }
            for s, c in rows
        ]
    }


# ── Hybrid search (BM25 ∪ pgvector → cross-encoder rerank) ──────────────────


# Lazy global so the cross-encoder model is loaded once per worker. The model
# is small (~280 MB) and CPU-only; first call pays the load cost (~3 s on the
# e2-small host), subsequent calls reuse the loaded weights.
_RERANKER = None
_RERANKER_LOAD_LOCK = None


async def _get_reranker():
    global _RERANKER, _RERANKER_LOAD_LOCK
    if _RERANKER is not None:
        return _RERANKER
    import asyncio

    if _RERANKER_LOAD_LOCK is None:
        _RERANKER_LOAD_LOCK = asyncio.Lock()

    async with _RERANKER_LOAD_LOCK:
        if _RERANKER is not None:
            return _RERANKER
        try:
            from sentence_transformers import CrossEncoder

            # Run the synchronous model load in a thread so we do not block the
            # event loop. The model is light enough that this is OK on the e2-small.
            _RERANKER = await asyncio.to_thread(
                CrossEncoder, "cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=256
            )
        except ImportError:
            # The hybrid endpoint is opt-in; if sentence-transformers is not
            # installed we still return the union (no rerank).
            _RERANKER = False
        return _RERANKER


@app.get("/search/hybrid", response_model=SearchResponse, tags=["Search"])
@limiter.limit("30/minute")
async def search_hybrid(
    request: Request,
    q: Annotated[
        str,
        Query(description="Free-text query", min_length=1, max_length=MAX_TEXT_LEN),
    ],
    field: Annotated[
        str,
        Query(
            description="Vector field to compare against",
            pattern="^(emb_text|emb_context|emb_combined)$",
        ),
    ] = "emb_combined",
    rerank: Annotated[
        bool,
        Query(description="Apply CPU cross-encoder rerank to the union of FTS + vector hits"),
    ] = True,
    has_provenance: Annotated[
        bool | None,
        Query(description="Restrict to inscriptions with (true) or without (false) a known findspot"),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=50),
    ] = 20,
    session: AsyncSession = Depends(get_session),
):
    """Hybrid retrieval: BM25 (FTS) ∪ pgvector top-k → optional cross-encoder rerank.

    The endpoint:
      1. runs the FTS path (`fts_canonical @@ plainto_tsquery`) for sparse hits,
      2. embeds the query via Gemini text-embedding-004 and runs the dense path
         against the chosen vector field with HNSW,
      3. unions the candidates (max-of-ranks) and, if `rerank=true`, re-scores
         each candidate with a CPU MiniLM cross-encoder.
    Returns the top `limit` results.
    """
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GEMINI_API_KEY not configured on server",
        )

    repo = InscriptionRepository(session)
    text_q = _clamp_text(q) or ""

    # 1. FTS path. Pull a generous candidate pool (4× target) so the union has
    #    room to mix sparse + dense.
    fts_results = await repo.search(
        text_query=text_q,
        has_provenance=has_provenance,
        limit=min(limit * 4, 80),
        offset=0,
        sort_by="id",
    )

    # 2. Dense path. Embed the query, then run pgvector cosine search.
    try:
        cache = getattr(request.app.state, "query_embedding_cache", None)
        if cache is not None and text_q in cache:
            embedding = cache[text_q]
            cache.move_to_end(text_q)
        else:
            client = request.app.state.http
            resp = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent",
                json={"content": {"parts": [{"text": text_q[:2048]}]}},
                headers={"x-goog-api-key": settings.gemini_api_key},
            )
            resp.raise_for_status()
            embedding = resp.json()["embedding"]["values"]
            if cache is not None:
                cache[text_q] = embedding
                if len(cache) > 1000:
                    cache.popitem(last=False)
    except Exception as e:
        logger.warning(f"Hybrid: embedding fetch failed, falling back to FTS only: {e}")
        embedding = None

    dense_results = []
    if embedding is not None:
        try:
            dense = await repo.semantic_search(
                query_embedding=embedding,
                field=field,
                limit=min(limit * 4, 80),
            )
            dense_results = dense.inscriptions
        except Exception as e:
            logger.warning(f"Hybrid: vector search failed, falling back to FTS only: {e}")

    # 3. Union via Reciprocal Rank Fusion (k=60 is the standard tuning).
    rrf_k = 60
    scored: dict[str, tuple[float, Any]] = {}
    for rank, insc in enumerate(fts_results.inscriptions):
        scored[insc.id] = (1.0 / (rrf_k + rank), insc)
    for rank, insc in enumerate(dense_results):
        prev = scored.get(insc.id)
        contrib = 1.0 / (rrf_k + rank)
        if prev:
            scored[insc.id] = (prev[0] + contrib, insc)
        else:
            scored[insc.id] = (contrib, insc)

    candidates = sorted(scored.values(), key=lambda t: -t[0])[: max(limit * 2, 20)]

    # 4. Optional cross-encoder rerank. We send (query, canonical) pairs and
    #    let the model produce a relevance score. Skip if the library isn't
    #    installed or if the candidate pool is empty.
    if rerank and candidates:
        reranker = await _get_reranker()
        if reranker:
            import asyncio

            pairs = [(text_q, c[1].canonical) for c in candidates]
            try:
                scores = await asyncio.to_thread(reranker.predict, pairs)
                candidates = sorted(
                    zip(scores, [c[1] for c in candidates], strict=True),
                    key=lambda t: -float(t[0]),
                )
                final = [c[1] for c in candidates[:limit]]
            except Exception as e:
                logger.warning(f"Hybrid rerank failed; returning RRF order: {e}")
                final = [c[1] for c in candidates[:limit]]
        else:
            final = [c[1] for c in candidates[:limit]]
    else:
        final = [c[1] for c in candidates[:limit]]

    data = [_build_model(i) for i in final]
    return {"total": len(final), "count": len(data), "results": data}
