"""Pelagios and Pleiades linked-data feeds, and bulk EpiDoc export."""

from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from openetruscan.api.deps import limiter
from openetruscan.db.repository import InscriptionRepository
from openetruscan.db.session import get_session

router = APIRouter()


@router.get("/pelagios.jsonld", tags=["Linked Data"])
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


@router.get("/pleiades-stats", tags=["Linked Data"])
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


@router.get("/export/epidoc", tags=["Export"])
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


@router.get("/admin/validate-pleiades", tags=["Admin"])
@limiter.limit("10/minute")
async def admin_validate_pleiades(request: Request, session: AsyncSession = Depends(get_session)):
    """Administrative audit endpoint for Pleiades identifier alignments."""
    repo = InscriptionRepository(session)
    return await repo.validate_pleiades_ids()
