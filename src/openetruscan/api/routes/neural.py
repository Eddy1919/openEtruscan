"""Lacuna restoration and the cross-language Rosetta lookup."""

import logging
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from openetruscan.api.deps import MAX_TEXT_LEN, limiter
from openetruscan.core.config import settings
from openetruscan.db.session import get_session

logger = logging.getLogger("openetruscan")

router = APIRouter()


class RestoreRequest(BaseModel):
    """Pydantic model for neural lacunae restoration requests."""

    text: str
    top_k: int = 5
    model_uri: str = "local://default"


@router.post("/neural/restore", tags=["Neural"])
@limiter.limit("60/minute")
async def restore_lacunae(
    request: Request,
    body: RestoreRequest,
):
    """Predict missing characters in text with Leiden conventions (e.g. lar[..]i).

    **Public** endpoint. This is the inference path the frontend `/lacunae`
    page calls directly from the browser, so the previous `verify_admin`
    gate was an outright UX bug (the page silently fell back to "demo
    predictions" because every real call returned 401). Rate-limiting at
    60 req/min/IP (via the slowapi decorator above) is what stops abuse.
    The model is read-only and the input is rejected if it's longer than
    the model's max sequence, so there's no privileged data path to guard.

    Two modes:
      * **Remote**: if ``settings.byt5_service_url`` is set we proxy the request
        to a dedicated Cloud Run service (`services/byt5-restorer/`). This is
        the production mode: the API container stays small and inference
        autoscales to zero between calls.
      * **In-process**: fallback when no service URL is configured. Loads the
        torch model lazily and offloads inference to a worker thread.
    """
    if settings.byt5_service_url:
        client = request.app.state.http
        try:
            # 90s, not 30s, because the byt5 service is on Cloud Run with
            # min-instances=0 and a cold start that includes loading the
            # transformer weights into memory (~25-45s on a 1 CPU /
            # 2Gi instance). With a 30s timeout the first request after
            # scale-to-zero was always failing with 502; 90s gives the
            # service enough headroom to warm up and respond on the same
            # connection. Once warm, inference is sub-second so the bigger
            # timeout has no downside.
            resp = await client.post(
                f"{settings.byt5_service_url.rstrip('/')}/restore",
                json={"text": body.text, "top_k": body.top_k},
                timeout=90.0,
            )
            resp.raise_for_status()
            return {"text": body.text, "predictions": resp.json().get("predictions", [])}
        except httpx.HTTPStatusError as e:
            # The remote service is up but rejected the call; surface its status.
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.HTTPError as e:
            # Connection / timeout. 502 is the right shape for "we couldn't reach
            # an upstream we depend on".
            raise HTTPException(status_code=502, detail=f"ByT5 service unreachable: {e}")

    try:
        from openetruscan.ml.neural import _TORCH_AVAILABLE, LacunaeRestorer

        if not _TORCH_AVAILABLE:
            raise HTTPException(
                status_code=501,
                detail="Lacunae restoration requires PyTorch, which is not installed in the lightweight API container.",
            )

        import asyncio

        registry = getattr(request.app.state, "lacunae_registry", {})
        restorer: LacunaeRestorer | None = registry.get(body.model_uri)
        if restorer is None:
            # First-time model load is also CPU-bound and >5 s; offload it.
            restorer = await asyncio.to_thread(LacunaeRestorer, model_uri=body.model_uri)
            registry[body.model_uri] = restorer
            request.app.state.lacunae_registry = registry

        # Inference is CPU-bound torch; running it directly blocks the event
        # loop and starves every other request. Offload to the default thread
        # pool, matching the pattern used by /search/hybrid's reranker.
        results = await asyncio.to_thread(restorer.predict, body.text, top_k=body.top_k)
        return {"text": body.text, "predictions": results}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during restoration")


# ── Rosetta multilingual lookup ─────────────────────────────────────────────


@router.get("/neural/rosetta/languages", tags=["Neural"])
@limiter.limit("60/minute")
async def rosetta_languages(request: Request) -> dict[str, Any]:
    """List every language registered in the Rosetta vector space.

    Each entry surfaces the language's tier, decipherment status, and
    whether it can participate in cross-language semantic queries. Tier-3
    languages (Linear A, Nuragic, Illyrian, Faliscan) are listed for
    transparency but the lookup endpoint refuses to use them as either
    source or target.
    """
    from openetruscan.ml.multilingual import LANGUAGE_TIERS

    return {
        "languages": [
            {
                "code": r.code,
                "name": r.name,
                "tier": r.tier,
                "deciphered": r.deciphered,
                "alignable": r.alignable,
                "corpus_status": r.corpus_status,
                "notes": r.notes,
                "typical_source": r.typical_source,
            }
            for r in LANGUAGE_TIERS.values()
        ]
    }


# ── Embedder partition aliases ────────────────────────────────────────────
# Public-facing `?embedder=` values map to the (embedder, embedder_revision)
# tuple stored in language_word_embeddings, and the mapping is *language-
# aware* because a single column (e.g. "xlmr-lora-v4") may legitimately
# correspond to different DB labels per language. Specifically: Etruscan
# under v4 went through XLM-R-base + an Etruscan LoRA adapter (labelled
# `xlmr-lora`); Latin under v4 went through XLM-R-base only, no LoRA
# (labelled `xlm-roberta-base`). The DB labels reflect what was actually
# done; the alias gives clients a single name for the head-to-head column.
#
# Adding a partition: append one entry. Unknown aliases → 400 with the
# valid-list so clients self-discover.
#
# The default (None) MUST match the canonical labels already in prod
# (`sentence-transformers/LaBSE` / `v1`); see DEFAULT_EMBEDDER in
# multilingual.py for the same constants. Drift between this map and
# those constants would silently return empty result sets.
#
# Schema: alias → {language → (embedder, embedder_revision)}. A "*" key
# in the inner dict serves as the fallback for any language without an
# explicit entry.
_EMBEDDER_ALIASES: dict[str | None, dict[str, tuple[str, str]]] = {
    None: {"*": ("sentence-transformers/LaBSE", "v1")},
    "LaBSE": {"*": ("sentence-transformers/LaBSE", "v1")},
    "xlmr-lora-v4": {
        "ett": ("xlmr-lora", "v4"),  # etr-lora-v4 adapter applied
        "*": ("xlm-roberta-base", "v4"),  # vanilla XLM-R-base for everyone else
    },
}


def _resolve_embedder(alias: str | None, language: str) -> tuple[str, str]:
    """Translate a public `?embedder=` value + language to the
    (embedder, embedder_revision) partition stored on disk.

    Raises ValueError for unknown aliases. Within a known alias, a
    language without an explicit entry falls through to the alias's "*"
    default; if neither matches, raises (defensive: every alias should
    have a "*" fallback in the map above).
    """
    if alias not in _EMBEDDER_ALIASES:
        valid = sorted(k for k in _EMBEDDER_ALIASES if k is not None)
        raise ValueError(f"Unknown embedder alias {alias!r}; valid: {valid}")
    per_lang = _EMBEDDER_ALIASES[alias]
    if language in per_lang:
        return per_lang[language]
    if "*" in per_lang:
        return per_lang["*"]
    raise ValueError(
        f"Embedder alias {alias!r} has no partition for language {language!r} and no '*' default"
    )


# Valid track values for the T5.4 dual-track API:
#   "all":       no filtering (legacy default; what /neural/rosetta has
#                 always returned).
#   "semantic":  drop top-1 if it equals the source word case-
#                 insensitively (the loanword / surface-form match) so
#                 the response leads with the next-best candidate.
#                 Useful for "give me the meaning-translation, not the
#                 loanword" call sites.
#   "loanword":  return only the top-1 if it equals the source word,
#                 empty otherwise. The dual of "semantic"; useful for
#                 "is this word also in the target vocab as a direct
#                 surface match?" queries.
_VALID_TRACKS = ("all", "semantic", "loanword")


@router.get("/neural/rosetta", tags=["Neural"])
@limiter.limit("30/minute")
async def rosetta_lookup(
    request: Request,
    word: Annotated[str, Query(min_length=1, max_length=MAX_TEXT_LEN)],
    from_lang: Annotated[
        str,
        Query(
            alias="from",
            description="Source language code (see /neural/rosetta/languages)",
        ),
    ] = "ett",
    to_lang: Annotated[
        str,
        Query(
            alias="to",
            description="Target language code",
        ),
    ] = "lat",
    k: Annotated[int, Query(ge=1, le=50)] = 10,
    embedder: Annotated[
        str | None,
        Query(
            description=(
                "Embedder partition to query. Default (omitted) routes to "
                "the LaBSE/v1 partition the API has served since launch. "
                "Pass 'xlmr-lora-v4' for the T2.3 v4 partition once ingested."
            ),
        ),
    ] = None,
    min_margin: Annotated[
        float,
        Query(
            ge=0.0,
            le=1.0,
            description=(
                "T5.3 calibration knob. Returns an empty neighbour list "
                "if (top1.cosine - top2.cosine) < this threshold — i.e. "
                "the bi-encoder isn't confident the top candidate stands "
                "out from the rest. Default 0.0 = no filtering. The eval "
                "in eval/p5-experiments/t5-2-calibration-curve-*.json "
                "characterises the precision/retention trade-off."
            ),
        ),
    ] = 0.0,
    track: Annotated[
        str,
        Query(
            description=(
                "T5.4 dual-track filter. 'all' (default) returns every "
                "candidate. 'semantic' drops the source word if it appears "
                "in the target vocab as a surface-form match (e.g. ett "
                "'fanu' → lat 'fanu' is a loanword, not a translation). "
                "'loanword' returns only that surface-form match, empty "
                "otherwise."
            ),
        ),
    ] = "all",
    session: AsyncSession = Depends(get_session),
):
    """Cross-language nearest-neighbour query in the shared Rosetta space.

    Refuses tier-3 languages (undeciphered or sub-viable corpora). Returns
    HTTP 422 if either `from` or `to` is unknown, 400 if either is
    tier-3, and an empty result list if the word has no stored vector
    in the source language (call the /neural/restore-style training
    pipelines first).
    """
    from openetruscan.ml.multilingual import find_cross_language_neighbours

    if track not in _VALID_TRACKS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown track {track!r}; valid: {list(_VALID_TRACKS)}",
        )

    # Resolve the alias separately for source and target languages.
    # For aliases like "xlmr-lora-v4" the two halves may live in
    # different DB partitions (ett under (xlmr-lora, v4); lat under
    # (xlm-roberta-base, v4)) because Latin doesn't get a LoRA adapter.
    try:
        src_emb_id, src_emb_rev = _resolve_embedder(embedder, from_lang)
        tgt_emb_id, tgt_emb_rev = _resolve_embedder(embedder, to_lang)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # When filtering by margin or track, fetch a wider pool so we have
    # candidates left after dropping. Cap at 50 (the route's documented
    # upper bound) so memory pressure stays bounded.
    fetch_k = min(50, max(k * 2, 10)) if (min_margin > 0 or track != "all") else k

    try:
        hits = await find_cross_language_neighbours(
            word=word,
            source_lang=from_lang,
            target_lang=to_lang,
            session=session,
            k=fetch_k,
            source_embedder=src_emb_id,
            source_embedder_revision=src_emb_rev,
            target_embedder=tgt_emb_id,
            target_embedder_revision=tgt_emb_rev,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ── T5.3: min_margin filter ─────────────────────────────────────────
    margin: float | None = None
    if len(hits) >= 2:
        margin = float(hits[0].cosine - hits[1].cosine)
    margin_pass = margin is None or margin >= min_margin
    if min_margin > 0 and not margin_pass:
        hits = []  # below threshold ⇒ explicit empty, "not confident enough"

    # ── T5.4: dual-track filter ─────────────────────────────────────────
    if hits and track != "all":
        src_lower = word.lower()
        is_loanword = hits[0].word.lower() == src_lower
        if track == "semantic" and is_loanword:
            hits = hits[1:]
        elif track == "loanword":
            hits = hits[:1] if is_loanword else []

    return {
        "query": word,
        "from": from_lang,
        "to": to_lang,
        # Echo the resolved embedder alias (or "LaBSE" when default) so
        # clients can confirm which partition served them. The eval harness
        # uses this to assert the right column was queried in the
        # head-to-head rosetta-eval-v1 run.
        "embedder": embedder if embedder is not None else "LaBSE",
        "track": track,
        # T5.3 surfaces the bi-encoder margin so clients can post-filter
        # their own way too; null when fewer than 2 candidates existed.
        "margin": margin,
        "neighbours": [
            {"word": h.word, "language": h.language, "cosine": h.cosine}
            for h in hits[:k]  # slice back to the requested k after filtering
        ],
    }


# Cache key is (lang, embedder_alias) so the v4 partition's vocab doesn't
# leak into the LaBSE caller's response. The TTL is per-key; each
# partition warms its cache independently on first hit.
_VOCAB_CACHE: dict[tuple[str, str | None], tuple[float, list[str]]] = {}
_VOCAB_TTL_SECONDS = 3600


@router.get("/neural/rosetta/vocab", tags=["Neural"])
@limiter.limit("60/minute")
async def rosetta_vocab(
    request: Request,
    lang: Annotated[
        str,
        Query(description="Language code (e.g. 'lat', 'ett')"),
    ],
    embedder: Annotated[
        str | None,
        Query(
            description=(
                "Embedder partition to query. Default routes to "
                "LaBSE/v1. Pass 'xlmr-lora-v4' for the v4 partition."
            ),
        ),
    ] = None,
    session: AsyncSession = Depends(get_session),
):
    """Retrieve up to 50k vocabulary words for a given language + embedder
    partition. Cached for 1 hour per (lang, embedder) tuple."""
    import time

    from sqlalchemy import text

    try:
        emb_id, emb_rev = _resolve_embedder(embedder, lang)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    now = time.time()
    cache_key = (lang, embedder)
    if cache_key in _VOCAB_CACHE:
        expires_at, words = _VOCAB_CACHE[cache_key]
        if now < expires_at:
            return {"words": words}
        else:
            _VOCAB_CACHE.pop(cache_key, None)

    stmt = text(
        "SELECT word FROM language_word_embeddings "
        "WHERE language = :lang "
        "  AND embedder = :embedder AND embedder_revision = :embedder_revision "
        "ORDER BY word LIMIT 50000"
    )
    result = await session.execute(
        stmt,
        {"lang": lang, "embedder": emb_id, "embedder_revision": emb_rev},
    )
    words = [row[0] for row in result.fetchall()]

    _VOCAB_CACHE[cache_key] = (now + _VOCAB_TTL_SECONDS, words)
    return {"words": words}
