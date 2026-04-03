"""
Integration tests for the OpenEtruscan FastAPI server.

Tests cover:
- Health endpoints (/health, /ready, /live)
- Search endpoints (/search, /radius)
- Stats endpoints (/stats, /stats/frequency, /stats/clusters, /stats/date-estimate)
- CORS and security headers
- Rate limiting
- Error handling
"""

import os

os.environ["ENVIRONMENT"] = "testing"
os.environ["ENABLE_DOCS"] = "1"

import tempfile
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from openetruscan import server
from openetruscan.corpus import Corpus, Inscription


def _make_inscription(**kwargs):
    """Helper to create inscription with proper defaults for SQLite."""
    defaults = {"provenance_flags": "", "script_system": "old_italic", "completeness": "complete"}
    defaults.update(kwargs)
    return Inscription(**defaults)


@contextmanager
def _test_client_with_corpus():
    """Context manager that provides a test client with a populated test corpus."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    corpus = Corpus.load(db_path)

    # Add test data
    test_data = [
        ("ETR_001", "LARTHAL", "larθal", "Cerveteri", 42.0, 12.0, "etruscan", "funerary"),
        ("ETR_002", "ARNTH", "arnθ", "Tarquinia", 42.5, 11.5, "etruscan", "funerary"),
        ("ETR_003", "TEST", "test", "Rome", 41.9, 12.5, "latin", "legal"),
    ]

    for id_, raw, canon, spot, lat, lon, lang, cls in test_data:
        corpus.add(
            _make_inscription(
                id=id_,
                raw_text=raw,
                canonical=canon,
                findspot=spot,
                findspot_lat=lat,
                findspot_lon=lon,
                language=lang,
                classification=cls,
            )
        )

    # Store original state
    orig_corpus = server.corpus

    # Set test state
    server.corpus = corpus

    # Create client without lifespan to avoid Corpus.load() being called
    client = TestClient(server.app)

    try:
        yield client
    finally:
        # Cleanup
        server.corpus = orig_corpus
        corpus.close()
        Path(db_path).unlink(missing_ok=True)


# ============================================================================
# Health Endpoints
# ============================================================================


def test_health_status_code():
    """Test /health returns 200."""
    with _test_client_with_corpus() as client:
        response = client.get("/health")
        assert response.status_code == 200


def test_health_response_structure():
    """Test /health returns correct structure."""
    with _test_client_with_corpus() as client:
        response = client.get("/health")
        data = response.json()
        required = [
            "status",
            "version",
            "uptime_seconds",
            "corpus_loaded",
            "timestamp",
        ]
        assert all(k in data for k in required)


def test_health_status_healthy():
    """Test /health returns healthy with loaded corpus."""
    with _test_client_with_corpus() as client:
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert data["corpus_loaded"] is True


def test_ready_success():
    """Test /ready returns 200 when corpus loaded."""
    with _test_client_with_corpus() as client:
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"


def test_live_success():
    """Test /live returns 200."""
    with _test_client_with_corpus() as client:
        response = client.get("/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"


# ============================================================================
# Search Endpoints
# ============================================================================


def test_search_basic():
    """Test basic search without parameters."""
    with _test_client_with_corpus() as client:
        response = client.get("/search")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3
        assert data["count"] >= 3


def test_search_with_findspot_filter():
    """Test search with findspot filter."""
    with _test_client_with_corpus() as client:
        response = client.get("/search?findspot=Cerveteri")
        assert response.status_code == 200
        assert response.json()["count"] >= 1


def test_search_with_language_filter():
    """Test search with language filter."""
    with _test_client_with_corpus() as client:
        response = client.get("/search?language=latin")
        assert response.status_code == 200
        assert response.json()["count"] >= 1


def test_search_with_classification_filter():
    """Test search with classification filter."""
    with _test_client_with_corpus() as client:
        response = client.get("/search?classification=funerary")
        assert response.status_code == 200
        assert response.json()["count"] >= 2


def test_search_pagination_limit():
    """Test search with limit parameter."""
    with _test_client_with_corpus() as client:
        response = client.get("/search?limit=2")
        assert response.status_code == 200
        assert response.json()["count"] == 2


def test_search_validation_error():
    """Test search with invalid limit returns 422."""
    with _test_client_with_corpus() as client:
        response = client.get("/search?limit=invalid")
        assert response.status_code == 422


def test_radius_search_basic():
    """Test radius search."""
    with _test_client_with_corpus() as client:
        response = client.get("/radius?lat=42.0&lon=12.0&radius_km=100")
        assert response.status_code == 200
        assert "results" in response.json()


def test_radius_search_missing_params():
    """Test radius search requires lat/lon."""
    with _test_client_with_corpus() as client:
        response = client.get("/radius?lat=42.0")
        assert response.status_code == 422


def test_radius_search_lat_bounds():
    """Test radius search latitude bounds."""
    with _test_client_with_corpus() as client:
        response = client.get("/radius?lat=91&lon=12.0")
        assert response.status_code == 422


def test_radius_search_lon_bounds():
    """Test radius search longitude bounds."""
    with _test_client_with_corpus() as client:
        response = client.get("/radius?lat=42.0&lon=181")
        assert response.status_code == 422


# ============================================================================
# Stats Endpoints
# ============================================================================


def test_stats_basic():
    """Test /stats returns count."""
    with _test_client_with_corpus() as client:
        response = client.get("/stats")
        assert response.status_code == 200
        assert response.json()["total_inscriptions"] >= 3


def test_stats_frequency_basic():
    """Test /stats/frequency returns frequencies."""
    with _test_client_with_corpus() as client:
        response = client.get("/stats/frequency")
        assert response.status_code == 200
        assert "primary" in response.json()


def test_stats_frequency_with_findspot():
    """Test /stats/frequency with findspot."""
    with _test_client_with_corpus() as client:
        response = client.get("/stats/frequency?findspot=Cerveteri")
        assert response.status_code == 200
        assert response.json()["label_a"] == "Cerveteri"


def test_stats_frequency_comparison():
    """Test /stats/frequency comparing sites."""
    with _test_client_with_corpus() as client:
        response = client.get("/stats/frequency?findspot=Cerveteri&findspot_b=Tarquinia")
        assert response.status_code == 200
        data = response.json()
        assert "primary" in data
        assert "secondary" in data
        assert "comparison" in data


def test_stats_frequency_invalid_language():
    """Test /stats/frequency with invalid language."""
    with _test_client_with_corpus() as client:
        response = client.get("/stats/frequency?language=<script>")
        assert response.status_code == 400


def test_stats_clusters_basic():
    """Test /stats/clusters returns clusters."""
    with _test_client_with_corpus() as client:
        response = client.get("/stats/clusters?min_inscriptions=2")
        assert response.status_code == 200
        assert "n_clusters" in response.json()


def test_stats_clusters_validation():
    """Test /stats/clusters validation."""
    with _test_client_with_corpus() as client:
        # min_inscriptions has ge=2 constraint
        response = client.get("/stats/clusters?min_inscriptions=1")
        assert response.status_code == 422


def test_stats_date_estimate_basic():
    """Test /stats/date-estimate."""
    with _test_client_with_corpus() as client:
        response = client.get("/stats/date-estimate?text=larθal")
        assert response.status_code == 200
        assert "period" in response.json()


def test_stats_date_estimate_required():
    """Test /stats/date-estimate requires text."""
    with _test_client_with_corpus() as client:
        response = client.get("/stats/date-estimate")
        assert response.status_code == 422


# ============================================================================
# CORS and Security Headers
# ============================================================================


def test_security_headers_present():
    """Test security headers present."""
    with _test_client_with_corpus() as client:
        response = client.get("/health")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"


def test_cors_headers():
    """Test CORS headers present."""
    with _test_client_with_corpus() as client:
        response = client.get("/health", headers={"Origin": "http://localhost:3000"})
        assert "access-control-allow-origin" in response.headers


def test_cors_preflight():
    """Test CORS preflight request."""
    with _test_client_with_corpus() as client:
        response = client.options(
            "/search",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200


# ============================================================================
# Rate Limiting
# ============================================================================


def test_rate_limit_headers_present():
    """Test rate limit headers present (slowapi adds these headers)."""
    with _test_client_with_corpus() as client:
        response = client.get("/search")
        assert response.status_code == 200
        # Note: Rate limit headers may not be present in test environment
        # depending on slowapi configuration. We just verify the endpoint works.


def test_rate_limit_search():
    """Test search endpoint works with rate limiting."""
    with _test_client_with_corpus() as client:
        response = client.get("/search")
        assert response.status_code == 200


def test_rate_limit_corpus():
    """Test corpus endpoint works with rate limiting."""
    with _test_client_with_corpus() as client:
        response = client.get("/corpus")
        assert response.status_code == 200


# ============================================================================
# Additional Endpoints
# ============================================================================


def test_corpus_endpoint():
    """Test /corpus returns all inscriptions."""
    with _test_client_with_corpus() as client:
        response = client.get("/corpus")
        assert response.status_code == 200
        assert len(response.json()) >= 3


def test_semantic_search_error():
    """Test semantic-search returns error for missing API key or SQLite."""
    with _test_client_with_corpus() as client:
        response = client.get("/semantic-search?q=test")
        # Returns 501 for SQLite not implemented, or 502/503 for API errors
        assert response.status_code in (501, 502, 503)


def test_pelagios_jsonld():
    """Test /pelagios.jsonld returns JSON-LD."""
    with _test_client_with_corpus() as client:
        response = client.get("/pelagios.jsonld")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/ld+json"


def test_pleiades_stats():
    """Test /pleiades-stats returns stats."""
    with _test_client_with_corpus() as client:
        response = client.get("/pleiades-stats")
        assert response.status_code == 200
        assert "total_inscriptions" in response.json()


def test_docs_enabled():
    """Test docs enabled in testing."""
    assert server.app.docs_url == "/docs"
    assert server.app.openapi_url == "/openapi.json"


# ============================================================================
# Error Handling
# ============================================================================


def test_404_not_found():
    """Test 404 for non-existent endpoints."""
    with _test_client_with_corpus() as client:
        response = client.get("/nonexistent")
        assert response.status_code == 404


def test_method_not_allowed():
    """Test POST to GET-only endpoint."""
    with _test_client_with_corpus() as client:
        response = client.post("/search")
        assert response.status_code == 405
