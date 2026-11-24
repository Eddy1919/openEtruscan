"""Full-text, spatial, semantic and hybrid search over the corpus."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from openetruscan.api.deps import (
    MAX_LIMIT,
    MAX_RADIUS_KM,
    MAX_TEXT_LEN,
    _clamp_limit,
    _clamp_text,
    limiter,
)
from openetruscan.api.schemas import SearchResponse, _build_model
from openetruscan.core.config import settings
from openetruscan.db.repository import InscriptionRepository
from openetruscan.db.session import get_session

logger = logging.getLogger("openetruscan")

router = APIRouter()


# /corpus was deprecated in v0.3 in favour of /search with pagination and later
# removed. /search?limit=500 is the drop-in replacement.


@router.get("/search", response_model=SearchResponse, tags=["Search"])
@limiter.limit("60/minute")
async def search_corpus(
    request: Request,
    text: Annotated[
        str | None,
        Query(
            description="Wildcard text search (e.g. *larth*)",
            max_length=MAX_TEXT_LEN,
        ),
    ] = None,
    findspot: Annotated[
        str | None,
        Query(description="Findspot name", max_length=MAX_TEXT_LEN),
    ] = None,
    language: Annotated[
        str | None,
        Query(description="Language filter", max_length=50),
    ] = None,
    classification: Annotated[
        str | None,
        Query(description="Classification filter", max_length=50),
    ] = None,
    provenance: Annotated[
        str | None,
        Query(
            description=(
                "Filter by provenance tier: excavated, acquired_documented, "
                "acquired_undocumented, unknown"
            ),
            pattern="^(excavated|acquired_documented|acquired_undocumented|unknown)$",
        ),
    ] = None,
    has_provenance: Annotated[
        bool | None,
        Query(
            description=(
                "Restrict to inscriptions with (true) or without (false) a known findspot. "
                "Useful for citation contexts: pass `true` to omit unprovenanced material."
            ),
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=MAX_LIMIT, description="Maximum number of results"),
    ] = 100,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of results to skip for pagination"),
    ] = 0,
    sort_by: Annotated[
        str,
        Query(description="Sort order (id, date, site, relevance)"),
    ] = "id",
    session: AsyncSession = Depends(get_session),
):
    """Search by text, location, or metadata with pagination."""
    repo = InscriptionRepository(session)
    actual_sort = sort_by if sort_by in ["date", "-date", "-id"] else "id"

    results = await repo.search(
        text_query=_clamp_text(text),
        findspot=findspot,
        language=language,
        classification=classification,
        provenance=provenance,
        has_provenance=has_provenance,
        limit=_clamp_limit(limit),
        offset=offset,
        sort_by=actual_sort,
    )

    accept_header = request.headers.get("accept", "")
    if (
        "application/xml" in accept_header
        or "application/tei+xml" in accept_header
        or "text/xml" in accept_header
    ):
        from fastapi.responses import Response

        from openetruscan.core.epidoc import results_to_epidoc

        xml_data = results_to_epidoc(results)
        return Response(content=xml_data, media_type="application/tei+xml")

    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@router.get("/search/geo", response_model=SearchResponse, tags=["Search"])
@limiter.limit("30/minute")
async def search_geo(
    request: Request,
    text: Annotated[
        str | None,
        Query(description="Text search", max_length=MAX_TEXT_LEN),
    ] = None,
    findspot: Annotated[
        str | None,
        Query(description="Findspot name", max_length=MAX_TEXT_LEN),
    ] = None,
    classification: Annotated[
        str | None,
        Query(description="Classification filter", max_length=50),
    ] = None,
    provenance: Annotated[
        str | None,
        Query(
            description="Provenance tier filter",
            pattern="^(excavated|acquired_documented|acquired_undocumented|unknown)$",
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=5000, description="Max results"),
    ] = 50,
    session: AsyncSession = Depends(get_session),
):
    """Return only geotagged inscriptions (with coordinates)."""
    repo = InscriptionRepository(session)
    results = await repo.search(
        text_query=_clamp_text(text),
        findspot=findspot,
        classification=classification,
        provenance=provenance,
        limit=min(limit, 5000),
        offset=0,
        geo_only=True,
    )

    accept_header = request.headers.get("accept", "")
    if (
        "application/xml" in accept_header
        or "application/tei+xml" in accept_header
        or "text/xml" in accept_header
    ):
        from fastapi.responses import Response

        from openetruscan.core.epidoc import results_to_epidoc

        xml_data = results_to_epidoc(results)
        return Response(content=xml_data, media_type="application/tei+xml")

    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@router.get("/concordance", tags=["Search"])
@limiter.limit("30/minute")
async def concordance_search(
    request: Request,
    q: Annotated[
        str,
        Query(description="Search term (min 2 chars)", min_length=2, max_length=MAX_TEXT_LEN),
    ],
    context: Annotated[
        int,
        Query(ge=10, le=100, description="Context characters"),
    ] = 40,
    limit: Annotated[
        int,
        Query(ge=1, le=5000, description="Max occurrences to return"),
    ] = 2000,
    session: AsyncSession = Depends(get_session),
):
    """Server-side KWIC (Key Word In Context) concordance search."""
    repo = InscriptionRepository(session)
    rows = await repo.concordance(query=q, limit=limit, context=context)
    unique = len({r["inscId"] for r in rows})
    return {"total": len(rows), "unique_inscriptions": unique, "rows": rows}


@router.get("/radius", response_model=SearchResponse, tags=["Search"])
@limiter.limit("60/minute")
async def search_by_radius(
    request: Request,
    lat: Annotated[
        float,
        Query(description="Latitude of center point", ge=-90, le=90),
    ],
    lon: Annotated[
        float,
        Query(description="Longitude of center point", ge=-180, le=180),
    ],
    radius_km: Annotated[
        float,
        Query(
            description="Radius in kilometers",
            ge=0.1,
            le=MAX_RADIUS_KM,
        ),
    ] = 50.0,
    limit: Annotated[
        int,
        Query(ge=1, le=MAX_LIMIT),
    ] = 100,
    session: AsyncSession = Depends(get_session),
):
    """Search by spatial radius."""
    repo = InscriptionRepository(session)
    results = await repo.search_radius(
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        limit=_clamp_limit(limit),
    )
    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


@router.get("/tiles/{z}/{x}/{y}.pbf", tags=["Search"])
@limiter.limit("500/minute")
async def get_vector_tiles(
    request: Request, z: int, x: int, y: int, session: AsyncSession = Depends(get_session)
):
    """
    Serve PostGIS dynamic vector tiles (MVT).
    Delegates tile generation to the database repository.
    """
    from fastapi.responses import Response

    repo = InscriptionRepository(session)

    try:
        # Fetch the binary MVT data from the database
        mvt_bytes = await repo.get_mvt_tiles(z, x, y)

        # If no geometries intersect the tile, return 204 No Content
        if not mvt_bytes:
            return Response(status_code=204)

        # Return the binary protobuf data
        return Response(
            content=mvt_bytes,
            media_type="application/x-protobuf",
            headers={"Access-Control-Allow-Origin": "*"},
        )
    except Exception as e:
        logger.error(f"Vector tile error for {z}/{x}/{y}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="MVT tile generation failed"
        ) from e


@router.get("/semantic-search", response_model=SearchResponse, tags=["Search"])
@limiter.limit("30/minute")
async def semantic_search(
    request: Request,
    q: Annotated[
        str,
        Query(description="Query text to search for", max_length=MAX_TEXT_LEN),
    ],
    field: Annotated[
        str,
        Query(
            description="Vector field to compare against",
            pattern="^(emb_text|emb_context|emb_combined)$",
        ),
    ] = "emb_combined",
    limit: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 20,
    session: AsyncSession = Depends(get_session),
):
    """
    Perform semantic vector search using Gemini text-embedding-004.
    Matches embeddings in pgvector against the provided query string.
    """
    # 1. Ensure API key is configured
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GEMINI_API_KEY not configured on server",
        )

    # 2. Build Gemini Embedding request. The API key goes in the x-goog-api-key
    # header rather than the URL query string so it does not leak into nginx
    # access logs, browser referrers, or proxy caches.
    url = "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent"
    payload = {"content": {"parts": [{"text": q[:2048]}]}}
    headers = {"x-goog-api-key": settings.gemini_api_key}

    # 3. Fetch from cache or Gemini API
    cache = getattr(request.app.state, "query_embedding_cache", None)
    if cache is not None and q in cache:
        query_embedding = cache[q]
        cache.move_to_end(q)
    else:
        try:
            client = request.app.state.http
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            query_embedding = resp.json()["embedding"]["values"]
            if cache is not None:
                cache[q] = query_embedding
                if len(cache) > 1000:
                    cache.popitem(last=False)
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to generate embedding for search query",
            ) from e

    # 4. Execute the vector search via repository
    try:
        repo = InscriptionRepository(session)
        results = await repo.semantic_search(
            query_embedding=query_embedding,
            field=field,
            limit=_clamp_limit(limit),
        )
    except Exception as e:
        logger.error(f"Semantic search failed in DB: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error during vector search execution",
        ) from e

    # 5. Format results
    data = [_build_model(i) for i in results.inscriptions]
    return {"total": results.total, "count": len(data), "results": data}


# ── Hybrid search (BM25 ∪ pgvector → cross-encoder rerank) ──────────────────


# Lazy global so the cross-encoder model is loaded once per worker. The model
# is small (~280 MB) and CPU-only; first call pays the load cost (~3 s on the
# e2-small host), subsequent calls reuse the loaded weights.
_RERANKER = None
_RERANKER_LOAD_LOCK = None


async def _get_reranker():
    global _RERANKER, _RERANKER_LOAD_LOCK
    if _RERANKER is not None:
        return _RERANKER
    import asyncio

    if _RERANKER_LOAD_LOCK is None:
        _RERANKER_LOAD_LOCK = asyncio.Lock()

    async with _RERANKER_LOAD_LOCK:
        if _RERANKER is not None:
            return _RERANKER
        try:
            from sentence_transformers import CrossEncoder

            # Run the synchronous model load in a thread so we do not block the
            # event loop. The model is light enough that this is OK on the e2-small.
            _RERANKER = await asyncio.to_thread(
                CrossEncoder, "cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=256
            )
        except ImportError:
            # The hybrid endpoint is opt-in; if sentence-transformers is not
            # installed we still return the union (no rerank).
            _RERANKER = False
        return _RERANKER


# ---------------------------------------------------------------------------
# Structured-token parsing for /search/hybrid
# ---------------------------------------------------------------------------

# Period vocabulary maps to (date_min, date_max) inclusive bounds in the
# corpus's native date_approx encoding (negative = BCE).
#
# Bucket boundaries match `eval/harness/build_eval_set.py` so the eval is the
# ground truth for "what does 'archaic' mean here". If the boundaries
# change, update both files together.
_PERIOD_RANGES: dict[str, tuple[int, int]] = {
    "archaic": (-700, -500),  # noqa: E241 - lined up with siblings
    "classical": (-499, -300),  # noqa: E241
    "late": (-299, -50),  # noqa: E241
    # Orientalising overlaps the early end of archaic; keep it as a separate
    # token because Etruscan typology distinguishes them (Pallottino 1968 §3,
    # de Grummond 2014). Querying "orientalising" should return rows in
    # the orientalising window even if they're not flagged "archaic".
    "orientalising": (-720, -580),
    # Hellenistic is the standard alias for "late" in Etruscan studies.
    # Same bounds, so querying either returns the same gold set.
    "hellenistic": (-299, -50),  # noqa: E241
}

# Cross-corpus markers: when one of these tokens appears in the query, we
# additionally require the matching <corpus>_id column to be non-NULL.
# The token is also stripped from the FTS query so it doesn't try to match
# the literal string in canonical text (where it never appears).
_CORPUS_MARKERS: dict[str, str] = {
    "trismegistos": "has_trismegistos",
    "tm": "has_trismegistos",  # noqa: E241
    "pleiades": "has_pleiades",  # noqa: E241
    "eagle": "has_eagle",  # noqa: E241
}


def _parse_structured_query(q: str) -> tuple[str, dict[str, Any]]:
    """Pull period names and corpus markers out of a free-text query.

    Returns ``(residual_text, structured_filters)`` where ``residual_text``
    is the original query with the recognised tokens stripped (whitespace
    collapsed), and ``structured_filters`` is a dict of kwargs ready to
    forward to ``InscriptionRepository.search``.

    Tokens are matched as whole words (case-insensitive) so a query like
    "archaicus" or "lateral" doesn't trigger a false positive. Multiple
    period tokens collapse to the *widest* range. Multiple corpus markers
    AND together (a query for "trismegistos pleiades" requires both IDs).

    Designed to be cheap and side-effect-free, so it can run on every
    /search/hybrid request without measurable overhead.
    """
    tokens = q.lower().split()
    residual_tokens: list[str] = []
    filters: dict[str, Any] = {}

    period_min: int | None = None
    period_max: int | None = None

    for token in tokens:
        # Strip surrounding punctuation that the user might naturally type,
        # e.g. "archaic," or "(late)".
        clean = token.strip(".,;:!?\"'()[]")
        if clean in _PERIOD_RANGES:
            lo, hi = _PERIOD_RANGES[clean]
            period_min = lo if period_min is None else min(period_min, lo)
            period_max = hi if period_max is None else max(period_max, hi)
            continue
        if clean in _CORPUS_MARKERS:
            filters[_CORPUS_MARKERS[clean]] = True
            continue
        residual_tokens.append(token)

    if period_min is not None and period_max is not None:
        filters["date_min"] = period_min
        filters["date_max"] = period_max

    residual = " ".join(residual_tokens).strip()
    return residual, filters


@router.get("/search/hybrid", response_model=SearchResponse, tags=["Search"])
@limiter.limit("30/minute")
async def search_hybrid(
    request: Request,
    q: Annotated[
        str,
        Query(description="Free-text query", min_length=1, max_length=MAX_TEXT_LEN),
    ],
    field: Annotated[
        str,
        Query(
            description="Vector field to compare against",
            pattern="^(emb_text|emb_context|emb_combined)$",
        ),
    ] = "emb_combined",
    rerank: Annotated[
        bool,
        Query(description="Apply CPU cross-encoder rerank to the union of FTS + vector hits"),
    ] = True,
    has_provenance: Annotated[
        bool | None,
        Query(
            description="Restrict to inscriptions with (true) or without (false) a known findspot"
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=50),
    ] = 20,
    session: AsyncSession = Depends(get_session),
):
    """Hybrid retrieval: BM25 (FTS) ∪ pgvector top-k → optional cross-encoder rerank.

    The endpoint:
      1. runs the FTS path (`fts_canonical @@ plainto_tsquery`) for sparse hits,
      2. embeds the query via Gemini text-embedding-004 and runs the dense path
         against the chosen vector field with HNSW,
      3. unions the candidates (max-of-ranks) and, if `rerank=true`, re-scores
         each candidate with a CPU MiniLM cross-encoder.
    Returns the top `limit` results.
    """
    repo = InscriptionRepository(session)
    raw_q = _clamp_text(q) or ""

    # 0. Pull period names ("archaic", "classical", "late") and corpus
    #    markers ("trismegistos", "pleiades", "eagle") out of the query.
    #    Those tokens never appear in canonical text, so leaving them in
    #    the FTS string costs recall. Map them to structured filters
    #    instead and use the residual for the lexical+dense paths.
    text_q, structured_filters = _parse_structured_query(raw_q)

    # 1. FTS path. Pull a generous candidate pool (4× target) so the union has
    #    room to mix sparse + dense. If the user typed a pure structured
    #    query like just "archaic", text_q is empty and we rely on the
    #    structured filters alone; repo.search returns the matching rows
    #    ordered by id, which is fine because the dense path can't help
    #    when there's no text to embed either.
    fts_results = await repo.search(
        text_query=text_q or None,
        has_provenance=has_provenance,
        **structured_filters,
        limit=min(limit * 4, 80),
        offset=0,
        sort_by="id",
    )

    # 2. Dense path. Embed the query, then run pgvector cosine search.
    # Skip the embedding round-trip entirely when text_q is empty (pure
    # structured query like "archaic") or when the Gemini key isn't
    # configured. The endpoint stays usable in both cases: FTS + structured
    # filters still produce results.
    embedding = None
    if text_q and settings.gemini_api_key:
        try:
            cache = getattr(request.app.state, "query_embedding_cache", None)
            if cache is not None and text_q in cache:
                embedding = cache[text_q]
                cache.move_to_end(text_q)
            else:
                client = request.app.state.http
                resp = await client.post(
                    "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent",
                    json={"content": {"parts": [{"text": text_q[:2048]}]}},
                    headers={"x-goog-api-key": settings.gemini_api_key},
                )
                resp.raise_for_status()
                embedding = resp.json()["embedding"]["values"]
                if cache is not None:
                    cache[text_q] = embedding
                    if len(cache) > 1000:
                        cache.popitem(last=False)
        except Exception as e:
            logger.warning(f"Hybrid: embedding fetch failed, falling back to FTS only: {e}")
            embedding = None

    dense_results = []
    if embedding is not None:
        try:
            dense = await repo.semantic_search(
                query_embedding=embedding,
                field=field,
                limit=min(limit * 4, 80),
            )
            dense_results = dense.inscriptions
        except Exception as e:
            logger.warning(f"Hybrid: vector search failed, falling back to FTS only: {e}")

    # 3. Union via Reciprocal Rank Fusion (k=60 is the standard tuning).
    rrf_k = 60
    scored: dict[str, tuple[float, Any]] = {}
    for rank, insc in enumerate(fts_results.inscriptions):
        scored[insc.id] = (1.0 / (rrf_k + rank), insc)
    for rank, insc in enumerate(dense_results):
        prev = scored.get(insc.id)
        contrib = 1.0 / (rrf_k + rank)
        if prev:
            scored[insc.id] = (prev[0] + contrib, insc)
        else:
            scored[insc.id] = (contrib, insc)

    candidates = sorted(scored.values(), key=lambda t: -t[0])[: max(limit * 2, 20)]

    # 4. Optional cross-encoder rerank. We send (query, canonical) pairs and
    #    let the model produce a relevance score. Skip if the library isn't
    #    installed or if the candidate pool is empty.
    if rerank and candidates:
        reranker = await _get_reranker()
        if reranker:
            import asyncio

            pairs = [(text_q, c[1].canonical) for c in candidates]
            try:
                scores = await asyncio.to_thread(reranker.predict, pairs)
                candidates = sorted(
                    zip(scores, [c[1] for c in candidates], strict=True),
                    key=lambda t: -float(t[0]),
                )
                final = [c[1] for c in candidates[:limit]]
            except Exception as e:
                logger.warning(f"Hybrid rerank failed; returning RRF order: {e}")
                final = [c[1] for c in candidates[:limit]]
        else:
            final = [c[1] for c in candidates[:limit]]
    else:
        final = [c[1] for c in candidates[:limit]]

    data = [_build_model(i) for i in final]
    return {"total": len(final), "count": len(data), "results": data}
