"""Tests for the `/anchors/*` community-curation surface (WBS P4 Option C)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_anchors_attested_returns_canonical_set(client):
    """GET /anchors/attested with no filter returns the full attested set."""
    response = await client.get("/anchors/attested")
    assert response.status_code == 200
    body = response.json()
    # The committed attested.jsonl has 17 rows.
    assert body["count"] >= 1  # Tolerant lower bound for future growth.
    assert isinstance(body["items"], list)
    if body["items"]:
        first = body["items"][0]
        for key in ("etruscan_word", "equivalent", "equivalent_language", "evidence_quote", "source"):
            assert key in first


@pytest.mark.asyncio
async def test_anchors_attested_filters_by_word(client):
    """GET /anchors/attested?word=aesar returns the Suetonius row."""
    response = await client.get("/anchors/attested", params={"word": "aesar"})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["etruscan_word"] == "aesar"
    assert body["items"][0]["equivalent"] == "deus"


@pytest.mark.asyncio
async def test_anchors_attested_word_not_found_returns_empty(client):
    response = await client.get("/anchors/attested", params={"word": "totally-not-an-etruscan-word"})
    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0}


@pytest.mark.asyncio
async def test_anchors_queue_requires_auth(client):
    """GET /anchors/queue without a Bearer token returns 401/403."""
    response = await client.get("/anchors/queue")
    # FastAPI's HTTPBearer dependency emits 403 when the header is missing.
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_propose_anchor_rejects_empty_body(client):
    response = await client.post("/anchors/propose", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_propose_anchor_rejects_invalid_equivalent_language(client):
    response = await client.post(
        "/anchors/propose",
        json={
            "etruscan_word": "tular",
            "equivalent": "limes",
            "equivalent_language": "english",  # not lat/grc
            "evidence_quote": "tular as boundary stone term in Bonfante",
            "source": "Bonfante 2002",
            "submitter_email": "test@example.edu",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_propose_anchor_rejects_short_evidence_quote(client):
    response = await client.post(
        "/anchors/propose",
        json={
            "etruscan_word": "tular",
            "equivalent": "limes",
            "equivalent_language": "lat",
            "evidence_quote": "too short",  # < 10 chars
            "source": "Bonfante 2002",
            "submitter_email": "test@example.edu",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_propose_anchor_rejects_bad_email(client):
    response = await client.post(
        "/anchors/propose",
        json={
            "etruscan_word": "tular",
            "equivalent": "limes",
            "equivalent_language": "lat",
            "evidence_quote": "valid evidence quote here",
            "source": "Bonfante 2002",
            "submitter_email": "not-an-email",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.requires_postgres
async def test_propose_anchor_happy_path_creates_pending_row(client):
    """Valid submission lands as a `pending` row with a queue position."""
    payload = {
        "etruscan_word": "tular",
        "equivalent": "limes",
        "equivalent_language": "lat",
        "evidence_quote": "tular as boundary-stone term in Bonfante 2002 §3.4",
        "source": "Bonfante 2002 §3.4",
        "submitter_email": "philologist@example.edu",
    }
    response = await client.post("/anchors/propose", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert isinstance(body["id"], int)
    assert body["queue_position"] >= 1


@pytest.mark.asyncio
@pytest.mark.requires_postgres
async def test_propose_anchor_deduplicates_same_triple(client):
    """Submitting the same `(etruscan_word, equivalent, equivalent_language)` triple twice
    returns ``status: "duplicate"`` on the second attempt."""
    payload = {
        "etruscan_word": "lautn",
        "equivalent": "familia",
        "equivalent_language": "lat",
        "evidence_quote": "lautn as the Etruscan word for family, per Pallottino 1968",
        "source": "Pallottino 1968 §4.1",
        "submitter_email": "test-dedup@example.edu",
    }
    r1 = await client.post("/anchors/propose", json=payload)
    assert r1.status_code == 201
    first_id = r1.json()["id"]

    r2 = await client.post("/anchors/propose", json=payload)
    assert r2.status_code == 201
    assert r2.json()["status"] == "duplicate"
    assert r2.json()["id"] == first_id


@pytest.mark.asyncio
async def test_propose_anchor_detects_already_attested(client):
    """If the (etr, equivalent, lang) triple is already in attested.jsonl,
    the endpoint reports ``status: "already_attested"``."""
    payload = {
        "etruscan_word": "aesar",
        "equivalent": "deus",
        "equivalent_language": "lat",
        "evidence_quote": "rediscovered the same gloss in another source",
        "source": "Other Source 2026",
        "submitter_email": "test-already-attested@example.edu",
    }
    response = await client.post("/anchors/propose", json=payload)
    body = response.json()
    assert body.get("status") == "already_attested"
    assert "existing_source" in body
