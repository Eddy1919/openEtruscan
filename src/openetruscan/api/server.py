"""
FastAPI application for the OpenEtruscan corpus: the composition root.

Builds the app (lifespan, rate limiting, CORS, security headers, error
handlers) and mounts the per-domain routers from ``openetruscan.api.routes``.
Run locally:
    uvicorn openetruscan.api.server:app --reload
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from openetruscan import __version__
from openetruscan.api import state
from openetruscan.api.deps import limiter
from openetruscan.api.routes import (
    anchors,
    health,
    inscriptions,
    linked_data,
    neural,
    prosopography,
    provenance,
    search,
    stats,
)
from openetruscan.core.config import settings

logger = logging.getLogger("openetruscan")


def _configure_logging():
    """Setup structured JSON logging for production."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    if settings.is_production:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            # In a production implementation, we'd use structlog or python-json-logger
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
    in-memory only, which is useful for local debugging via ``otel-cli``.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        # Optional. Production prefers explicit dep install; dev runs without.
        return

    resource = Resource.create(
        {
            "service.name": "openetruscan-api",
            "service.version": __version__,
        }
    )
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
    state.START_TIME = datetime.now(timezone.utc)
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

    from openetruscan.api.zotero import ZoteroClient

    app.state.zotero = ZoteroClient(
        group_id=settings.zotero_group_id, api_key=settings.zotero_api_key, client=app.state.http
    )

    try:
        yield
    finally:
        await app.state.http.aclose()


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


# Explicitly handle rate limit breaches with the custom handler (429 Too Many Requests).
# Starlette types every exception handler as taking a bare Exception, so slowapi's
# handler (typed for RateLimitExceeded) needs this narrowing adapter.
def _handle_rate_limit(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, RateLimitExceeded)  # the only type Starlette routes here
    return _rate_limit_exceeded_handler(request, exc)


app.add_exception_handler(RateLimitExceeded, _handle_rate_limit)

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
            "instance": request.url.path,
        },
        media_type="application/problem+json",
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
            "instance": request.url.path,
        },
        media_type="application/problem+json",
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
            "instance": request.url.path,
        },
        media_type="application/problem+json",
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
            "instance": request.url.path,
        },
        media_type="application/problem+json",
    )


# Mount order is dispatch order: where two routers could match a URL, the
# first one mounted answers. No two overlap today.
for _module in (
    health,
    search,
    inscriptions,
    provenance,
    neural,
    stats,
    prosopography,
    anchors,
    linked_data,
):
    app.include_router(_module.router)
