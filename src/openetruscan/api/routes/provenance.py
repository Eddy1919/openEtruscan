"""Provenance promotion, audit history, and the data-source registry."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from openetruscan.api.deps import limiter, verify_admin
from openetruscan.db.repository import InscriptionRepository
from openetruscan.db.session import get_session

router = APIRouter()


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


@router.post(
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
    from openetruscan.core.inscription import PROVENANCE_STATUSES

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


@router.get(
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
    from sqlalchemy import select

    from openetruscan.db.models import ProvenanceAudit

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


@router.get("/sources", tags=["Sources"])
@limiter.limit("60/minute")
async def list_data_sources(request: Request, session: AsyncSession = Depends(get_session)):
    """List the data sources backing the corpus, with provenance baselines.

    Each entry includes the canonical citation, license, and the *typical*
    archaeological provenance tier of rows from that source. Per-row provenance
    is still in `inscriptions.provenance_status`; the source baseline is just
    a hint for the UI ("most rows from Larth are unprovenanced").
    """
    from sqlalchemy import func as sa_func
    from sqlalchemy import select

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
