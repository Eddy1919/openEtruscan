"""Corpus statistics, frequency analysis, clustering and date estimation."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from openetruscan.api.deps import MAX_TEXT_LEN, limiter
from openetruscan.api.schemas import StatsResponse
from openetruscan.db.repository import InscriptionRepository
from openetruscan.db.session import get_session

router = APIRouter()


@router.get("/stats/summary", tags=["Statistics"])
@limiter.limit("30/minute")
async def stats_summary(request: Request, session: AsyncSession = Depends(get_session)):
    """Full corpus statistics for dashboard display, including the provenance breakdown."""
    repo = InscriptionRepository(session)
    return await repo.get_stats_summary()


@router.get("/stats/provenance", tags=["Statistics"])
@limiter.limit("60/minute")
async def stats_provenance(request: Request, session: AsyncSession = Depends(get_session)):
    """
    Honest provenance breakdown of the corpus.

    Returns the per-tier counts plus the share of the corpus that has a
    documented findspot vs. is unprovenanced. Citation tooling (and the
    homepage) should consume this rather than the headline `total` so users
    can distinguish "philologically attested" from "archaeologically located".
    """
    repo = InscriptionRepository(session)
    summary = await repo.get_stats_summary()
    return summary["provenance"]


@router.get("/stats/timeline", tags=["Statistics"])
@limiter.limit("30/minute")
async def stats_timeline(request: Request, session: AsyncSession = Depends(get_session)):
    """Dated + geolocated inscriptions with minimal fields for timeline map."""
    repo = InscriptionRepository(session)
    return await repo.get_timeline_stats()


@router.get("/stats", response_model=StatsResponse, tags=["Statistics"])
async def corpus_stats(session: AsyncSession = Depends(get_session)) -> Any:
    """Get corpus counts."""
    repo = InscriptionRepository(session)
    count = await repo.count()
    return StatsResponse(total_inscriptions=count)


# ── Statistical Analysis Endpoints ──────────────────────────────────────────


@router.get("/stats/frequency", tags=["Statistics"])
@limiter.limit("30/minute")
async def frequency_analysis(
    request: Request,
    findspot: Annotated[
        str | None,
        Query(description="Filter by findspot", max_length=MAX_TEXT_LEN),
    ] = None,
    findspot_b: Annotated[
        str | None,
        Query(description="Second findspot for comparison", max_length=MAX_TEXT_LEN),
    ] = None,
    date_from: Annotated[
        int | None,
        Query(description="Date range start (BCE, positive int)"),
    ] = None,
    date_to: Annotated[
        int | None,
        Query(description="Date range end (BCE, positive int)"),
    ] = None,
    language: Annotated[
        str,
        Query(description="Language adapter to use", max_length=50),
    ] = "etruscan",
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Letter frequency analysis, optionally comparing two sites (chi² test)."""
    from openetruscan.core.statistics import (
        compare_frequencies,
        letter_frequencies,
    )

    repo = InscriptionRepository(session)
    rows_a = await repo.get_all_canonical_texts(findspot=findspot)
    texts_a = [r["canonical"] for r in rows_a if r["canonical"]]
    freq_a = letter_frequencies(texts_a, language=language)

    response: dict[str, Any] = {"primary": freq_a.to_dict(), "label_a": findspot or "All sites"}

    if findspot_b:
        rows_b = await repo.get_all_canonical_texts(findspot=findspot_b)
        texts_b = [r["canonical"] for r in rows_b if r["canonical"]]
        freq_b = letter_frequencies(texts_b, language=language)
        comparison = compare_frequencies(freq_a, freq_b)
        response["secondary"] = freq_b.to_dict()
        response["label_b"] = findspot_b
        response["comparison"] = comparison.to_dict()

    return response


@router.get("/stats/clusters", tags=["Statistics"])
@limiter.limit("15/minute")
async def dialect_clusters(
    request: Request,
    min_inscriptions: Annotated[
        int,
        Query(description="Minimum inscriptions per site", ge=2, le=100),
    ] = 5,
    language: Annotated[
        str,
        Query(description="Language adapter", max_length=50),
    ] = "etruscan",
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Dialect clustering via Ward's hierarchical method with cosine distance."""
    from openetruscan.core.statistics import cluster_sites_from_texts

    repo = InscriptionRepository(session)
    rows = await repo.get_all_canonical_texts()
    result = cluster_sites_from_texts(rows, language=language, min_inscriptions=min_inscriptions)
    return result.to_dict()


@router.get("/stats/date-estimate", tags=["Statistics"])
@limiter.limit("60/minute")
async def date_estimate(
    request: Request,
    text: Annotated[
        str,
        Query(description="Inscription text to analyze", max_length=MAX_TEXT_LEN),
    ],
    language: Annotated[
        str,
        Query(description="Language adapter", max_length=50),
    ] = "etruscan",
) -> Any:
    """Estimate chronological period from orthographic features."""
    from openetruscan.core.statistics import estimate_date

    result = estimate_date(text, language=language)
    return result.to_dict()


@router.get("/stats/bayesian-date", tags=["Statistics"])
@limiter.limit("30/minute")
async def bayesian_date_estimate(
    request: Request,
    text: Annotated[
        str,
        Query(description="Inscription text to date probabilistically", max_length=MAX_TEXT_LEN),
    ],
    language: Annotated[
        str,
        Query(description="Language adapter", max_length=50),
    ] = "etruscan",
):
    """Estimate inscription date using Bayesian inference over time bins."""
    from openetruscan.core.statistics import bayesian_date

    result = bayesian_date(text, language=language)
    return result.to_dict()
