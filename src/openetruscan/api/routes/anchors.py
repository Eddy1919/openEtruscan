"""Proposed and attested bilingual anchors."""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from openetruscan.api.deps import limiter, verify_admin
from openetruscan.db.session import get_session

router = APIRouter()


# ────────────────────────────────────────────────────────────────────
# Community-curation surfaces (WBS P4 Option C).
#
# Three endpoints + one admin promote-action implement the moderation
# pipeline specified in the maintainer-held community-curation design note.
# Submissions land in the `proposed_anchors` table (alembic
# c8d9e0f1a2b3); admins approve via Bearer-token-gated /anchors/{id}/promote;
# approved rows are surfaced read-only via /anchors/attested AND
# appended to research/anchors/attested.jsonl on the next data-refresh PR
# (out-of-band, via a separate Cloud Build job).
# ────────────────────────────────────────────────────────────────────


class ProposeAnchorRequest(BaseModel):
    """Body for `POST /anchors/propose`. Server-side validation rules
    match the `proposed_anchors` table CHECK constraints; the Pydantic
    layer fails-fast with a clear error before the DB does."""

    etruscan_word: str = Field(min_length=1, max_length=200)
    equivalent: str = Field(min_length=1, max_length=500)
    equivalent_language: str = Field(pattern="^(lat|grc)$")
    evidence_quote: str = Field(min_length=10, max_length=2000)
    source: str = Field(min_length=3, max_length=500)
    # Simple regex-validated email; sidesteps the email-validator
    # dependency. Format-validation is intentionally permissive
    # (the gating logic on submissions is the 100/day-per-email rate
    # limit + the admin review pass, not RFC 5322 compliance).
    submitter_email: str = Field(
        pattern=r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$",
        max_length=320,
    )
    submitter_orcid: str | None = Field(default=None, max_length=64)
    # Optional corpus ID of the inscription the submitter was reading
    # when they filed the proposal. The frontend's ProposeCard chip row
    # threads it in via `?from=<id>` on /propose/<word>. Stored
    # verbatim; we do not validate that the ID exists in the
    # inscriptions table; see the migration's "no FK" rationale.
    source_inscription_id: str | None = Field(default=None, max_length=64)


class PromoteAnchorRequest(BaseModel):
    """Body for `POST /anchors/{id}/promote`."""

    action: str = Field(pattern="^(approve|reject|duplicate)$")
    review_note: str | None = Field(default=None, max_length=2000)


def _load_attested_jsonl() -> list[dict[str, Any]]:
    """Read research/anchors/attested.jsonl from the repo (mounted in the
    image at /app/research/anchors/attested.jsonl).

    Read on every call. The file is small (17 rows of about 500 chars,
    9 KB), so no cache is needed.
    """
    from pathlib import Path

    candidates = [
        # routes/ -> api/ -> openetruscan/ -> src/ -> repo root
        Path(__file__).resolve().parents[4] / "research" / "anchors" / "attested.jsonl",
        Path("/app/research/anchors/attested.jsonl"),
    ]
    for p in candidates:
        if p.is_file():
            rows: list[dict[str, Any]] = []
            with p.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            return rows
    return []


@router.post("/anchors/propose", tags=["Anchors"], status_code=201)
@limiter.limit("10/hour")
async def propose_anchor(
    request: Request,
    payload: ProposeAnchorRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Submit a candidate Etruscan↔Latin/Greek gloss equivalence to the
    moderation queue.

    Three dedup gates before the row is queued:

      1. Already in `attested.jsonl` → returns ``status: "already_attested"``
         with the existing source.
      2. Already pending under the same `(etruscan_word, equivalent,
         equivalent_language)` triple → returns ``status: "duplicate"``
         with the existing id.
      3. New submission → inserted with ``status: "pending"``.

    Rate-limited at 10 submissions per hour per IP via the existing
    slowapi limiter. The 100-per-day-per-email rule from the design
    doc is enforced server-side via a query against this table.
    """
    from sqlalchemy import func, select

    from openetruscan.db.models import ProposedAnchor

    # Gate 1: collision with the canonical attested set.
    attested = _load_attested_jsonl()
    for row in attested:
        if (
            row.get("etruscan_word", "").strip().lower() == payload.etruscan_word.strip().lower()
            and row.get("equivalent", "").strip().lower() == payload.equivalent.strip().lower()
            and row.get("equivalent_language") == payload.equivalent_language
        ):
            return {
                "status": "already_attested",
                "message": "This equivalence is already in the canonical attested set.",
                "existing_source": row.get("source"),
            }

    # Gate 2: already-pending duplicate.
    stmt = select(ProposedAnchor).where(
        func.lower(ProposedAnchor.etruscan_word) == payload.etruscan_word.strip().lower(),
        func.lower(ProposedAnchor.equivalent) == payload.equivalent.strip().lower(),
        ProposedAnchor.equivalent_language == payload.equivalent_language,
        ProposedAnchor.status == "pending",
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return {
            "id": existing.id,
            "status": "duplicate",
            "message": f"An identical proposal already exists at id={existing.id}, pending review.",
        }

    # Gate 3 (rate-limit per email): 100/day cap.
    from datetime import datetime, timedelta, timezone

    since = datetime.now(tz=timezone.utc) - timedelta(days=1)
    daily_count_stmt = (
        select(func.count())
        .select_from(ProposedAnchor)
        .where(
            ProposedAnchor.submitter_email == payload.submitter_email,
            ProposedAnchor.created_at >= since,
        )
    )
    daily_count = (await session.execute(daily_count_stmt)).scalar_one()
    if daily_count >= 100:
        raise HTTPException(
            status_code=429,
            detail=f"Daily submission cap reached ({daily_count}/100) for {payload.submitter_email}. Try tomorrow.",
        )

    # Insert. Empty `source_inscription_id` stripped to None to satisfy the
    # CHECK constraint that rejects empty-but-not-NULL inscription IDs.
    src_ins = (payload.source_inscription_id or "").strip() or None
    new_row = ProposedAnchor(
        etruscan_word=payload.etruscan_word.strip(),
        equivalent=payload.equivalent.strip(),
        equivalent_language=payload.equivalent_language,
        evidence_quote=payload.evidence_quote.strip(),
        source=payload.source.strip(),
        submitter_email=payload.submitter_email,
        submitter_orcid=payload.submitter_orcid,
        source_inscription_id=src_ins,
        status="pending",
    )
    session.add(new_row)
    await session.commit()
    await session.refresh(new_row)

    # Approximate the queue position: count pending rows older than this one.
    queue_pos_stmt = (
        select(func.count())
        .select_from(ProposedAnchor)
        .where(
            ProposedAnchor.status == "pending",
            ProposedAnchor.created_at <= new_row.created_at,
        )
    )
    queue_pos = (await session.execute(queue_pos_stmt)).scalar_one()

    return {
        "id": new_row.id,
        "status": "pending",
        "queue_position": int(queue_pos),
    }


@router.get("/anchors/queue", tags=["Anchors"])
@limiter.limit("60/minute")
async def anchors_queue(
    request: Request,
    limit: int = 50,
    _auth: HTTPAuthorizationCredentials = Depends(verify_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List pending anchor submissions in oldest-first order.

    Auth: Bearer ``settings.admin_token`` (same gate as
    ``promote_provenance``). The endpoint is intentionally small.
    Pagination is via ``limit`` (max 200); the queue is short by design.
    """
    from sqlalchemy import asc, func, select

    from openetruscan.db.models import ProposedAnchor

    limit = max(1, min(200, limit))
    stmt = (
        select(ProposedAnchor)
        .where(ProposedAnchor.status == "pending")
        .order_by(asc(ProposedAnchor.created_at))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()

    total_stmt = (
        select(func.count()).select_from(ProposedAnchor).where(ProposedAnchor.status == "pending")
    )
    total_pending = (await session.execute(total_stmt)).scalar_one()

    items = [
        {
            "id": r.id,
            "etruscan_word": r.etruscan_word,
            "equivalent": r.equivalent,
            "equivalent_language": r.equivalent_language,
            "evidence_quote": r.evidence_quote,
            "source": r.source,
            "submitter_email": r.submitter_email,
            "submitter_orcid": r.submitter_orcid,
            # Surface the inscription provenance to the reviewer UI. Frontend
            # /review page can render this as a "from inscription <id>" chip
            # that deep-links back to the inscription detail page.
            "source_inscription_id": r.source_inscription_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return {"items": items, "total_pending": int(total_pending)}


@router.post("/anchors/{anchor_id}/promote", tags=["Anchors"])
@limiter.limit("60/minute")
async def promote_anchor(
    request: Request,
    anchor_id: int,
    payload: PromoteAnchorRequest,
    _auth: HTTPAuthorizationCredentials = Depends(verify_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Admin: approve / reject / mark-duplicate a pending submission.

    On ``approve``: status moves to ``approved``. The row does NOT get
    auto-appended to ``research/anchors/attested.jsonl`` from this
    handler. That's done out-of-band by a Cloud Build job that polls
    the table, rebuilds the JSONL, and opens a data-refresh PR. This
    avoids granting the API server git-push permissions, which would
    be a serious security boundary violation.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from openetruscan.db.models import ProposedAnchor

    stmt = select(ProposedAnchor).where(ProposedAnchor.id == anchor_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"anchor {anchor_id} not found")
    if row.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"anchor {anchor_id} already in terminal state {row.status!r}; cannot re-promote",
        )

    action_to_status = {
        "approve": "approved",
        "reject": "rejected",
        "duplicate": "duplicate",
    }
    row.status = action_to_status[payload.action]
    row.reviewer = "admin"  # In a future extension, derive from the bearer token's subject claim.
    row.review_note = payload.review_note
    row.reviewed_at = datetime.now(tz=timezone.utc)
    await session.commit()

    return {
        "id": row.id,
        "status": row.status,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
    }


@router.get("/anchors/attested", tags=["Anchors"])
@limiter.limit("60/minute")
async def anchors_attested(request: Request, word: str | None = None) -> dict[str, Any]:
    """Public-read attested equivalences for an Etruscan word.

    Sources the canonical `research/anchors/attested.jsonl` shipped in
    the repo image. When `word` is omitted, returns all 17 attested
    anchors (small fixed set; no pagination needed). With `word`,
    returns the subset whose `etruscan_word` matches case-insensitively.
    """
    rows = _load_attested_jsonl()
    if word:
        target = word.strip().lower()
        rows = [r for r in rows if r.get("etruscan_word", "").strip().lower() == target]
    return {"items": rows, "count": len(rows)}
