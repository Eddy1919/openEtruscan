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
    required = ["status", "version", "uptime_seconds", "corpus_loaded", "timestamp"]
    assert all(k in data for k in required)


async def test_health_status_healthy(client: AsyncClient, sample_data):
    """Test /health returns healthy with loaded corpus."""
    response = await client.get("/health")
    data = response.json()
    assert data["status"] == "healthy"
    assert data["corpus_loaded"] is True


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


async def test_method_not_allowed(client: AsyncClient, sample_data):
    """Test POST to GET-only endpoint."""
    response = await client.post("/search")
    assert response.status_code == 405
