"""Cross-encoder rerank for the Rosetta cross-language retrieval pipeline.

The bi-encoder /neural/rosetta endpoint returns top-k Latin candidates
ordered by cosine similarity in the shared multilingual space. A
cross-encoder rerank pass — score each (query, candidate) pair jointly
with a transformer that takes both as input — can in principle reorder
those candidates by something closer to true relevance.

This module is built to be **callable from the eval harness without
deploying a service**. The cross-encoder runs in-process via the
``sentence-transformers`` library, lazily loaded so the rest of the
eval doesn't depend on it.

Default model: ``BAAI/bge-reranker-v2-m3``. Multilingual, ~568M params,
trained on parallel and translation-retrieval data across 100+
languages. Latin and Etruscan are not in the training set, but the
model's sub-word fallback to related scripts (Latin script overlap;
Greek-via-XLM-R-base genealogy) gives it a fighting chance to recover
signal that pure bi-encoder cosine can't.

If the rerank pass moves the field@k metric meaningfully on
``rosetta-eval-v1``, the next step is to deploy a small Cloud Run
service so the API path can use it too. The service skeleton already
lives at ``services/minilm-reranker/`` — it just needs a model swap
and a deploy.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("openetruscan.rerank")

# Default multilingual cross-encoder.
DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"

_RERANK_MODEL_CACHE: dict[str, Any] = {}


def get_reranker(model_name: str | None = None) -> Any:
    """Lazy-load a sentence-transformers CrossEncoder. Caches by name.

    The first call after process start downloads the model (~600 MB
    for bge-reranker-v2-m3) into the HF cache. Subsequent calls reuse
    the in-memory instance.
    """
    name = model_name or DEFAULT_RERANK_MODEL
    if name in _RERANK_MODEL_CACHE:
        return _RERANK_MODEL_CACHE[name]
    # Import lazily so harness consumers that don't use rerank don't
    # pay the sentence-transformers dependency.
    from sentence_transformers import CrossEncoder  # type: ignore[import-untyped]
    logger.info("loading cross-encoder %s", name)
    model = CrossEncoder(name)
    _RERANK_MODEL_CACHE[name] = model
    return model


def rerank_candidates(
    query: str,
    candidates: list[tuple[str, float]],
    *,
    model_name: str | None = None,
    top_k: int | None = None,
) -> list[tuple[str, float]]:
    """Re-rank ``candidates`` (a list of (word, bi-encoder-cosine) pairs)
    by joint cross-encoder relevance to ``query``.

    Returns a new list of (word, new_score) pairs sorted descending by
    cross-encoder score. The original cosines are discarded — the
    returned scores are the cross-encoder's relevance logits, not a
    cosine. Downstream metric code that depends on cosines specifically
    should use the bi-encoder pre-rerank.

    ``top_k`` (if set) truncates the output. Useful when the bi-encoder
    returns top-50 and the eval scores top-10 after rerank.
    """
    if not candidates:
        return []
    model = get_reranker(model_name)
    pairs = [[query, word] for word, _ in candidates]
    scores = model.predict(pairs)
    ranked = sorted(
        zip([w for w, _ in candidates], scores, strict=True),
        key=lambda x: x[1],
        reverse=True,
    )
    if top_k is not None:
        ranked = ranked[:top_k]
    return [(w, float(s)) for w, s in ranked]
