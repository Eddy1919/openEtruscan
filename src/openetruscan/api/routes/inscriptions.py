"""Single-inscription reads (JSON, JSON-LD, Turtle), imports and validation."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from openetruscan.api.deps import limiter, verify_admin
from openetruscan.api.schemas import _build_model
from openetruscan.db.repository import InscriptionRepository
from openetruscan.db.session import get_session

logger = logging.getLogger("openetruscan")

router = APIRouter()


def _inscription_jsonld(inscription) -> dict:
    """Render an inscription as Schema.org / Pelagios-flavoured JSON-LD."""
    base = "https://api.openetruscan.com"
    iri = f"{base}/inscription/{inscription.id}"
    place = (
        {
            "@type": "Place",
            "name": inscription.findspot,
            **(
                {
                    "geo": {
                        "@type": "GeoCoordinates",
                        "latitude": inscription.findspot_lat,
                        "longitude": inscription.findspot_lon,
                    }
                }
                if inscription.findspot_lat is not None and inscription.findspot_lon is not None
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
        same_as.append(
            f"https://www.edr-edr.it/edr_programmi/res_complex_comune.php?do=show&id_nr={inscription.eagle_id}"
        )

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
        "schema:license": "https://creativecommons.org/licenses/by/4.0/",
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


@router.get("/inscription/{inscription_id}", tags=["Corpus"])
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

    # JSON is the default. Emit Pydantic via JSONResponse so the Link header lands.
    data = _build_model(inscription).model_dump()

    if inscription.zotero_id:
        zotero_data = await request.app.state.zotero.get_item_csl(inscription.zotero_id)
        if zotero_data:
            data["zotero_bibliography"] = zotero_data

    return JSONResponse(
        data,
        headers=headers,
    )


@router.get("/inscription/{inscription_id}/concordance", tags=["Research"])
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


# In-memory idempotency store for /inscriptions POST. The endpoint runs at
# 30/minute on a single VM instance and the import flow is admin-only, so a
# process-local TTL cache is the right level of complexity. Once the API moves
# to Cloud Run (multi-instance), this will need to migrate to Redis or a
# `idempotency_keys` table (see ROADMAP.md).
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


@router.post("/inscriptions", tags=["Corpus"])
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


@router.get("/ids", tags=["Corpus"])
@limiter.limit("10/minute")
async def get_all_ids(request: Request, session: AsyncSession = Depends(get_session)):
    """Return the list of all inscription IDs (lightweight, ~50KB)."""
    repo = InscriptionRepository(session)
    return await repo.get_all_ids()


@router.get("/inscriptions/{inscription_id}/validate", tags=["Corpus"])
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
