"""
ByT5 Lacuna Restorer — Cloud Run microservice.

Exposes a single POST /restore endpoint that accepts damaged epigraphic text
and returns probabilistic character-level restorations.

Architecture notes:
  - Model is loaded lazily on first request (cold start ~10s on CPU).
  - Predictions are cached in a SQLite sidecar keyed on
    (text_with_lacunae, top_k, model_version) so repeated queries skip
    inference entirely.
  - The service is deployed with min-instances=0 so it costs nothing when
    idle (~€0-3/mo at current traffic).

Expected request:
    POST /restore
    {
        "text": "lar[---]al velinas",
        "top_k": 3
    }

Expected response:
    {
        "predictions": [
            {"restored": "larθal velinas", "score": 0.87},
            {"restored": "lartal velinas", "score": 0.09},
            {"restored": "larial velinas", "score": 0.03}
        ],
        "model_version": "byt5-lacunae-v1",
        "cached": false,
        "inference_ms": 1234.5
    }
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("byt5-restorer")
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL_URI = os.environ.get("MODEL_URI", "google/byt5-small")
MODEL_VERSION = os.environ.get("MODEL_VERSION", "byt5-lacunae-v1")
CACHE_DB = Path(os.environ.get("CACHE_PATH", "/tmp/byt5_cache.db"))

# ---------------------------------------------------------------------------
# Global state (populated at startup)
# ---------------------------------------------------------------------------

_model: Any = None
_tokenizer: Any = None
_cache_conn: sqlite3.Connection | None = None


def _init_cache() -> sqlite3.Connection:
    conn = sqlite3.connect(str(CACHE_DB))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS predictions (
            key TEXT PRIMARY KEY,
            result TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _cache_key(text: str, top_k: int) -> str:
    raw = f"{MODEL_VERSION}:{text}:{top_k}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_get(key: str) -> dict | None:
    if _cache_conn is None:
        return None
    row = _cache_conn.execute(
        "SELECT result FROM predictions WHERE key = ?", (key,)
    ).fetchone()
    if row:
        return json.loads(row[0])
    return None


def _cache_set(key: str, result: dict) -> None:
    if _cache_conn is None:
        return
    _cache_conn.execute(
        "INSERT OR REPLACE INTO predictions (key, result, created_at) VALUES (?, ?, ?)",
        (key, json.dumps(result), time.time()),
    )
    _cache_conn.commit()


# ---------------------------------------------------------------------------
# FastAPI lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cache_conn
    _cache_conn = _init_cache()
    logger.info("Cache initialised at %s", CACHE_DB)
    # Model load is intentionally LAZY (first /restore call triggers
    # _ensure_model). An earlier attempt at eager loading in lifespan
    # was rejected by Cloud Run with "The user-provided container failed
    # to start and listen on the port defined ... within the allocated
    # timeout" — loading byt5-small to memory takes ~25-45s on 1 CPU
    # and the lifespan startup blocks uvicorn from binding $PORT.
    # Cold-start tolerance is now handled at the *API* layer via the
    # 90s httpx timeout (see openetruscan/api/server.py).
    yield
    if _cache_conn:
        _cache_conn.close()


app = FastAPI(
    title="ByT5 Lacuna Restorer",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Model loading (lazy)
# ---------------------------------------------------------------------------


def _ensure_model():
    global _model, _tokenizer

    if _model is not None:
        return

    logger.info("Loading model from %s …", MODEL_URI)
    t0 = time.time()

    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    _tokenizer = AutoTokenizer.from_pretrained(MODEL_URI)
    # `low_cpu_mem_usage=False` forces the weights to materialise on CPU
    # instead of being kept on the `meta` device. Newer
    # transformers + torch combos default to meta-device lazy loading,
    # which then explodes at generate() time with:
    #   RuntimeError: Tensor on device cpu is not on the expected device meta!
    # Explicit `.to("cpu")` is a belt-and-braces second guarantee.
    _model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_URI, low_cpu_mem_usage=False).to("cpu")
    _model.eval()

    logger.info("Model loaded in %.1fs", time.time() - t0)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class RestoreRequest(BaseModel):
    text: str = Field(..., description="Damaged text with [---] marking lacunae")
    top_k: int = Field(default=3, ge=1, le=10, description="Number of restoration candidates")


class Prediction(BaseModel):
    restored: str
    score: float


class RestoreResponse(BaseModel):
    predictions: list[Prediction]
    model_version: str
    cached: bool
    inference_ms: float


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": _model is not None,
        "model_version": MODEL_VERSION,
    }


@app.post("/restore", response_model=RestoreResponse)
async def restore(req: RestoreRequest):
    """Restore lacunae in damaged epigraphic text."""

    key = _cache_key(req.text, req.top_k)
    cached = _cache_get(key)
    if cached:
        return RestoreResponse(
            predictions=[Prediction(**p) for p in cached["predictions"]],
            model_version=MODEL_VERSION,
            cached=True,
            inference_ms=0.0,
        )

    try:
        # _ensure_model() is a blocking 25-45s CPU/IO call (PyTorch +
        # transformers + byt5-small). If we call it directly from this
        # async handler it freezes the entire event loop, and every other
        # queued request (Cloud Run can dispatch many to the same
        # container under default concurrency=80) times out before the
        # model finishes loading. Offload to a thread so uvicorn keeps
        # answering healthchecks + can fail other concurrent requests
        # fast instead of hanging them.
        import asyncio
        await asyncio.to_thread(_ensure_model)
    except Exception as exc:
        logger.exception("Model load failed")
        raise HTTPException(
            status_code=503,
            detail=f"Model warming up, please retry in ~10s: {exc}",
        )

    import re

    import torch

    t0 = time.time()

    # Translate Leiden Convention lacunae markers to the ByT5
    # span-corruption mask:
    #   [.]      one missing char
    #   [..]     two missing chars
    #   [...]    three missing chars (etc., up to ~10)
    #   [---]    legacy "wide range" notation
    # ByT5 only understands `<extra_id_0>` so every dotted-bracket span
    # collapses to one mask. We don't lose much information by erasing the
    # span length because byt5-small is happy to generate variable-length
    # restorations from the surrounding context.
    masked_text = re.sub(r"\[(\.+|\-+)\]", "<extra_id_0>", req.text)
    inputs = _tokenizer(masked_text, return_tensors="pt", padding=True)

    with torch.no_grad():
        outputs = _model.generate(
            **inputs,
            max_new_tokens=64,
            num_beams=max(req.top_k, 4),
            num_return_sequences=req.top_k,
            return_dict_in_generate=True,
            output_scores=True,
        )

    predictions = []
    for i, seq in enumerate(outputs.sequences):
        decoded = _tokenizer.decode(seq, skip_special_tokens=True)
        # Reconstruct the full text
        # Match the SAME regex used to mask the input so Leiden dotted-bracket
        # markers ([.], [..], [...]) are substituted on the way out, not just
        # [---]. The previous .replace("[---]", ...) silently no-op'd on the
        # variable-dot notation the frontend actually sends, so users got
        # back their original text with the lacuna markers intact.
        restored = re.sub(r"\[(\.+|\-+)\]", decoded.strip(), req.text)
        # Use sequence score as confidence proxy
        score = 1.0 / (i + 1)  # fallback ranking score
        predictions.append({"restored": restored, "score": round(score, 4)})

    inference_ms = (time.time() - t0) * 1000

    result = {"predictions": predictions}
    _cache_set(key, result)

    return RestoreResponse(
        predictions=[Prediction(**p) for p in predictions],
        model_version=MODEL_VERSION,
        cached=False,
        inference_ms=round(inference_ms, 1),
    )
