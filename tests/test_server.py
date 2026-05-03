"""
Integration tests for the OpenEtruscan FastAPI server (Async Version).

The DB and session fixtures live in `tests/conftest.py` and now point at a
real Postgres backend (CI: the `services:` Postgres; local dev: a
testcontainers-managed pgvector container; SQLite is only the last-resort
fallback). Tests that depend on PostGIS or pgvector are tagged with
`requires_postgis` / `requires_pgvector` markers.

Tests cover:
- Health endpoints (/health)
- Search endpoints (/search, /radius)
- Stats endpoints (/stats, /stats/frequency)
- CORS and security headers
- Rate limiting
- Error handling
"""

import os

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

os.environ["ENVIRONMENT"] = "testing"
os.environ["ENABLE_DOCS"] = "1"

from openetruscan.api.server import app
from openetruscan.db.session import get_session
from openetruscan.db.repository import InscriptionRepository, InscriptionData


# All tests in this module mount the FastAPI app + a real Postgres session
# from conftest.py. Per-test fixture turnaround is ~250 ms, which is
# acceptable now that the slow cluster tests have been rewritten as pure-
# compute (no DB). These run in the main CI path.


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def sample_data(db_session: AsyncSession):
    repo = InscriptionRepository(db_session)
    test_data = [
        InscriptionData(
            id="ETR_001",
            raw_text="LARTHAL",
            canonical="larθal",
            findspot="Cerveteri",
            findspot_lat=42.0,
            findspot_lon=12.0,
            language="etruscan",
            classification="funerary",
        ),
        InscriptionData(
            id="ETR_002",
            raw_text="ARNTH",
            canonical="arnθ",
            findspot="Tarquinia",
            findspot_lat=42.5,
            findspot_lon=11.5,
            language="etruscan",
            classification="funerary",
        ),
        InscriptionData(
            id="ETR_003",
            raw_text="TEST",
            canonical="test",
            findspot="Rome",
            findspot_lat=41.9,
            findspot_lon=12.5,
            language="latin",
            classification="legal",
        ),
    ]
    for item in test_data:
        await repo.add(item)
    await db_session.commit()
    return test_data


# ============================================================================
# Health Endpoints
# ============================================================================


async def test_health_status_code(client: AsyncClient, sample_data):
    """Test /health returns 200."""
    response = await client.get("/health")
    assert response.status_code == 200


async def test_health_response_structure(client: AsyncClient, sample_data):
    """Test /health returns correct structure."""
    response = await client.get("/health")
    data = response.json()
    required = ["status", "version", "uptime_seconds", "checks", "timestamp"]
    assert all(k in data for k in required), f"missing keys; got {list(data)}"
    assert "db" in data["checks"]


async def test_health_status_healthy(client: AsyncClient, sample_data):
    """Test /health returns healthy with loaded corpus."""
    response = await client.get("/health")
    data = response.json()
    assert data["status"] == "healthy"
    assert data["checks"]["db"]["ok"] is True
    assert data["checks"]["db"]["count"] >= 3


# ============================================================================
# Search Endpoints
# ============================================================================


async def test_search_basic(client: AsyncClient, sample_data):
    """Test basic search without parameters."""
    response = await client.get("/search")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 3
    assert data["count"] >= 3


async def test_search_with_findspot_filter(client: AsyncClient, sample_data):
    """Test search with findspot filter."""
    response = await client.get("/search?findspot=Cerveteri")
    assert response.status_code == 200
    assert response.json()["count"] >= 1


async def test_search_with_language_filter(client: AsyncClient, sample_data):
    """Test search with language filter."""
    response = await client.get("/search?language=latin")
    assert response.status_code == 200
    assert response.json()["count"] >= 1


async def test_search_with_classification_filter(client: AsyncClient, sample_data):
    """Test search with classification filter."""
    response = await client.get("/search?classification=funerary")
    assert response.status_code == 200
    assert response.json()["count"] >= 2


async def test_search_pagination_limit(client: AsyncClient, sample_data):
    """Test search with limit parameter."""
    response = await client.get("/search?limit=2")
    assert response.status_code == 200
    assert response.json()["count"] == 2


async def test_search_validation_error(client: AsyncClient, sample_data):
    """Test search with invalid limit returns 422."""
    response = await client.get("/search?limit=invalid")
    assert response.status_code == 422


@pytest.mark.skip(reason="Requires PostgreSQL and PostGIS")
async def test_radius_search_basic(client: AsyncClient, sample_data):
    """Test radius search (falls back to 501 on SQLite without PostGIS)."""
    response = await client.get("/radius?lat=42.0&lon=12.0&radius_km=100")
    if response.status_code == 200:
        assert "results" in response.json()
    else:
        assert response.status_code == 501


# ============================================================================
# Stats Endpoints
# ============================================================================


async def test_stats_basic(client: AsyncClient, sample_data):
    """Test /stats returns count."""
    response = await client.get("/stats")
    assert response.status_code == 200
    assert response.json()["total_inscriptions"] >= 3


async def test_stats_frequency_basic(client: AsyncClient, sample_data):
    """Test /stats/frequency (placeholder in current repo)."""
    response = await client.get("/stats/frequency")
    assert response.status_code == 200


async def test_stats_clusters_validation(client: AsyncClient, sample_data):
    """Test /stats/clusters validation."""
    response = await client.get("/stats/clusters?min_inscriptions=1")
    assert response.status_code == 422


async def test_stats_date_estimate_basic(client: AsyncClient, sample_data):
    """Test /stats/date-estimate."""
    response = await client.get("/stats/date-estimate?text=larθal")
    # Returns 404 or 200 depending on model availability
    assert response.status_code in (200, 404)


# ============================================================================
# CORS and Security Headers
# ============================================================================


async def test_security_headers_present(client: AsyncClient, sample_data):
    """Test security headers present."""
    response = await client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"


async def test_cors_headers(client: AsyncClient, sample_data):
    """Test CORS headers present."""
    response = await client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert "access-control-allow-origin" in response.headers


async def test_cors_preflight(client: AsyncClient, sample_data):
    """Test CORS preflight request."""
    response = await client.options(
        "/search",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200


# ============================================================================
# Error Handling
# ============================================================================


async def test_404_not_found(client: AsyncClient, sample_data):
    """Test 404 for non-existent endpoints."""
    response = await client.get("/nonexistent")
    assert response.status_code == 404


# ============================================================================
# Curatorial workflow (promote-provenance)
# ============================================================================


async def test_promote_provenance_happy_path(client: AsyncClient, sample_data, monkeypatch):
    """End-to-end: promote a row, confirm audit row, then read it back via history.

    This used to silently 500 in prod because the endpoint called
    `repo.get_inscription`, which doesn't exist. Pin a regression here.
    """
    from openetruscan.core.config import settings

    monkeypatch.setattr(settings, "admin_token", "test-admin-token")
    headers = {"Authorization": "Bearer test-admin-token"}

    response = await client.post(
        "/inscription/ETR_001/promote-provenance",
        json={
            "new_status": "excavated",
            "bibliography": "CIE I 1234",
            "notes": "Confirmed via 1923 excavation report",
            "reviewed_by": "test_curator",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "promoted"
    # New rows get the schema default "unknown"; the migration backfill rule
    # only applies to rows that pre-existed when a1f2c3d4e5f6 ran.
    assert body["old_status"] == "unknown"
    assert body["new_status"] == "excavated"
    assert isinstance(body["audit_id"], int)

    history = await client.get("/inscription/ETR_001/provenance-history")
    assert history.status_code == 200
    audits = history.json()["audits"]
    assert len(audits) >= 1
    latest = audits[0]
    assert latest["new_status"] == "excavated"
    assert latest["created_by"] == "test_curator"
    assert "CIE I 1234" in (latest["notes"] or "")


async def test_promote_provenance_rejects_invalid_status(client: AsyncClient, sample_data, monkeypatch):
    """Invalid status must 400, not 500 — guards the DB CHECK constraint."""
    from openetruscan.core.config import settings

    monkeypatch.setattr(settings, "admin_token", "test-admin-token")
    response = await client.post(
        "/inscription/ETR_001/promote-provenance",
        json={"new_status": "definitely_not_a_real_tier"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 400


async def test_promote_provenance_requires_admin(client: AsyncClient, sample_data):
    """Missing or wrong bearer token must 401/403, never 200."""
    response = await client.post(
        "/inscription/ETR_001/promote-provenance",
        json={"new_status": "excavated"},
    )
    assert response.status_code in (401, 403)


# ============================================================================
# Content negotiation
# ============================================================================


async def test_inscription_default_returns_json(client: AsyncClient, sample_data):
    """No Accept header / no ?format → application/json."""
    response = await client.get("/inscription/ETR_001")
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    assert response.json()["id"] == "ETR_001"


async def test_inscription_format_jsonld(client: AsyncClient, sample_data):
    """?format=jsonld returns application/ld+json with Schema.org + LAWD shape."""
    response = await client.get("/inscription/ETR_001?format=jsonld")
    assert response.status_code == 200
    assert "application/ld+json" in response.headers["content-type"]
    body = response.json()
    assert body.get("@context"), "JSON-LD must declare @context"
    assert body.get("@id", "").endswith("ETR_001"), "JSON-LD must declare a canonical @id"


async def test_inscription_accept_turtle(client: AsyncClient, sample_data):
    """Accept: text/turtle returns RDF Turtle with proper prefixes."""
    response = await client.get(
        "/inscription/ETR_001",
        headers={"Accept": "text/turtle"},
    )
    assert response.status_code == 200
    assert "text/turtle" in response.headers["content-type"]
    assert "@prefix" in response.text, "Turtle must declare prefixes"


async def test_inscription_alternate_links_header(client: AsyncClient, sample_data):
    """Every representation must link to the others via Link: rel=alternate."""
    response = await client.get("/inscription/ETR_001")
    assert response.status_code == 200
    link = response.headers.get("Link", "")
    assert 'rel="alternate"' in link
    assert "application/ld+json" in link
    assert "text/turtle" in link
    assert "application/tei+xml" in link
    assert response.headers.get("Vary") == "Accept"


async def test_inscription_unknown_id_404(client: AsyncClient, sample_data):
    """404 should propagate through content negotiation, not silently 200."""
    response = await client.get("/inscription/DEFINITELY_NOT_REAL?format=jsonld")
    assert response.status_code == 404


# ============================================================================
# Neural restore (proxy mode)
# ============================================================================


async def test_neural_restore_proxies_when_byt5_url_set(
    client: AsyncClient, sample_data, monkeypatch
):
    """When BYT5_SERVICE_URL is set, /neural/restore must call the remote
    service instead of loading torch in-process.

    Pinned because the cutover is one env var: any regression that brings
    in-process torch back to prod silently undoes the ~700 MB RAM win.
    """
    from openetruscan.api import server as server_mod
    from openetruscan.core.config import settings

    monkeypatch.setattr(settings, "admin_token", "test-admin-token")
    monkeypatch.setattr(settings, "byt5_service_url", "https://byt5.example/")

    calls: list[str] = []

    class _FakeResp:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"predictions": [{"restored": "larθal", "score": 0.9}]}

    class _FakeClient:
        async def post(self, url, json, timeout):  # noqa: A002
            calls.append(url)
            return _FakeResp()

    # The lifespan-singleton httpx client lives at app.state.http; swap it.
    server_mod.app.state.http = _FakeClient()

    response = await client.post(
        "/neural/restore",
        json={"text": "lar[---]al", "top_k": 3},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["predictions"][0]["restored"] == "larθal"
    assert calls == ["https://byt5.example/restore"], (
        "expected exactly one upstream call to the proxied service"
    )


async def test_admin_endpoint_returns_503_when_token_unconfigured(
    client: AsyncClient, sample_data, monkeypatch
):
    """If ADMIN_TOKEN is not set on the deployment, admin endpoints must 503,
    not 500 — the write surface is intentionally disabled, not crashing."""
    from openetruscan.core.config import settings

    monkeypatch.setattr(settings, "admin_token", None)
    response = await client.post(
        "/inscription/ETR_001/promote-provenance",
        json={"new_status": "excavated"},
        headers={"Authorization": "Bearer anything"},
    )
    assert response.status_code == 503
    assert "ADMIN_TOKEN" in response.json()["detail"]


async def test_health_surfaces_admin_token_configured_flag(client: AsyncClient, sample_data):
    """/health must report whether the admin write surface is reachable.
    Catches the operational gap of forgetting ADMIN_TOKEN in prod env."""
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert "admin_token_configured" in body["checks"]
    assert isinstance(body["checks"]["admin_token_configured"], bool)


async def test_method_not_allowed(client: AsyncClient, sample_data):
    """Test POST to GET-only endpoint."""
    response = await client.post("/search")
    assert response.status_code == 405
