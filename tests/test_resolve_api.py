"""Standard references resolve to records: /resolve, /inscription/{ref}, /references."""

from __future__ import annotations

import os

import pytest
from httpx import AsyncClient

os.environ["ENVIRONMENT"] = "testing"


@pytest.fixture()
async def aliases(db_session, sample_data):  # type: ignore[no-untyped-def]
    from openetruscan.db.models import InscriptionAlias, InscriptionEdition

    rows = [
        # ETR_001 carries CIE 4538 directly; ETR_002 reaches it through CIEP numbering.
        ("ETR_001", "cie", "cie:4538", "CIE 4538", "own_id", "certain"),
        ("ETR_002", "cie", "cie:4538", "CIE 4538", "ciep_cie_numbering", "probable"),
        ("ETR_001", "et", "et:pe 8.4", "ET Pe 8.4", "concordance", "high"),
        ("ETR_002", "et", "et:pe 8.4", "ET Pe 8.4", "ciep_cie_numbering", "probable"),
        ("ETR_003", "tle", "tle:570", "TLE 570", "concordance", "high"),
        ("ETR_003", "tm", "tm:153357", "TM 153357", "concordance", "high"),
        ("ETR_003", "et", "et:ta 3.6", "ET Ta 3.6", "concordance", "high"),
    ]
    for rid, scheme, key, value, basis, conf in rows:
        db_session.add(
            InscriptionAlias(
                inscription_id=rid,
                scheme=scheme,
                lookup_key=key,
                value=value,
                basis=basis,
                confidence=conf,
                source="test",
            )
        )
    db_session.add(
        InscriptionEdition(
            inscription_id="ETR_003",
            rix_siglum="Ta 3.6",
            rix_text_class="3",
            rix_class_basis="concordance",
        )
    )
    await db_session.commit()
    return rows


async def test_unique_reference_redirects(client: AsyncClient, aliases) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/inscription/TLE 570", params={"format": "json"})
    assert r.status_code == 308
    assert r.headers["location"] == "/inscription/ETR_003?format=json"


async def test_tm_reference_redirects(client: AsyncClient, aliases) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/inscription/Trismegistos 153357")
    assert r.status_code == 308
    assert r.headers["location"] == "/inscription/ETR_003"


async def test_bare_et_siglum_redirects(client: AsyncClient, aliases) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/inscription/Ta 3.6")
    assert r.status_code == 308
    assert r.headers["location"] == "/inscription/ETR_003"


async def test_ambiguous_reference_lists_candidates(client: AsyncClient, aliases) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/inscription/ET Pe 8.4")
    assert r.status_code == 300
    body = r.json()
    assert body["reference"] == "ET Pe 8.4"
    assert [m["inscription_id"] for m in body["matches"]] == ["ETR_001", "ETR_002"]
    assert body["matches"][0]["basis"] == "concordance"


async def test_record_id_wins_over_alias(client: AsyncClient, aliases, db_session) -> None:  # type: ignore[no-untyped-def]
    """A record whose own ID is a reference another record holds as an alias."""
    from openetruscan.db.repository import InscriptionData, InscriptionRepository

    await InscriptionRepository(db_session).add(
        InscriptionData(id="TLE 570", raw_text="X", canonical="x", language="etruscan")
    )
    await db_session.commit()
    r = await client.get("/inscription/TLE 570", params={"format": "json"})
    assert r.status_code == 200
    assert r.json()["id"] == "TLE 570"


async def test_unknown_reference_404(client: AsyncClient, aliases) -> None:  # type: ignore[no-untyped-def]
    assert (await client.get("/inscription/CIE 99999")).status_code == 404
    assert (await client.get("/inscription/not-a-ref")).status_code == 404


async def test_resolve_endpoint(client: AsyncClient, aliases) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/resolve", params={"ref": "cie 04538"})
    assert r.status_code == 200
    body = r.json()
    assert body["parsed"] == {"scheme": "cie", "key": "cie:4538", "display": "CIE 4538"}
    assert [(m["inscription_id"], m["confidence"]) for m in body["matches"]] == [
        ("ETR_001", "certain"),
        ("ETR_002", "probable"),
    ]


async def test_resolve_endpoint_record_id(client: AsyncClient, aliases) -> None:  # type: ignore[no-untyped-def]
    body = (await client.get("/resolve", params={"ref": "ETR_002"})).json()
    assert body["parsed"] is None
    assert body["matches"] == [
        {
            "inscription_id": "ETR_002",
            "value": "ETR_002",
            "basis": "record_id",
            "confidence": "certain",
        }
    ]


async def test_references_endpoint(client: AsyncClient, aliases) -> None:  # type: ignore[no-untyped-def]
    body = (await client.get("/inscription/ETR_003/references")).json()
    keys = {a["lookup_key"] for a in body["aliases"]}
    assert {"tle:570", "tm:153357", "et:ta 3.6"} <= keys
    assert body["edition"]["rix_siglum"] == "Ta 3.6"
    # A findspot moved out as a custody note stays reachable through the API.
    assert "findspot_source_text" in body["edition"]
    assert (await client.get("/inscription/NOPE/references")).status_code == 404
