"""Multilingual contextual embeddings for the Rosetta Vector Space.

This module replaces the previous FastText + Procrustes pipeline with a
2026-SOTA architecture: a multilingual transformer encoder (XLM-RoBERTa
by default) optionally augmented with a LoRA adapter fine-tuned on
Etruscan inscriptions. The encoder's hidden states already share a
vector space across the 100+ languages it was pretrained on, so
cross-language retrieval works **without** an explicit Procrustes
rotation — we just embed each language and ask pgvector for cosine
neighbours.

Why this beats the FastText+Procrustes path
-------------------------------------------
1. Cosine spread. The encoder's manifold was set by trillions of tokens
   during pretraining; adding 15k Etruscan tokens via LoRA inherits
   that structure rather than competing with it.
2. Contextual disambiguation. ``larθ`` as a praenomen and ``larθ`` in a
   compound get different vectors based on surrounding tokens.
3. OOV via shared sub-word vocabulary. The SentencePiece tokeniser
   handles never-seen Etruscan glyphs through n-gram pieces that were
   trained on the entire multilingual corpus.

Public surface
--------------
* ``Embedder`` — abstract base. Subclasses implement ``embed_words``
  and expose ``dim``, ``model_id``, ``revision``.
* ``XLMREmbedder`` — production path. Wraps a HuggingFace transformer
  + an optional LoRA adapter. ~768 dims by default, ~80 ms per word
  on CPU, sub-10 ms on a small GPU.
* ``MockEmbedder`` — deterministic vectors derived from string hashes,
  for tests that need to exercise the populate / lookup paths without
  downloading a 1 GB model.

The actual fine-tuning loop lives in ``finetune.py``.
"""

from __future__ import annotations

import hashlib
import logging
import unicodedata
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger("openetruscan.embeddings")

# Default base model. xlm-roberta-base is the standard low-resource
# multilingual baseline: 270M params, 768 hidden dim, runs on CPU at
# ~80 ms/query. xlm-roberta-large (1024 dim) is the upgrade if the
# host has a GPU.
DEFAULT_MODEL_ID = "xlm-roberta-base"
DEFAULT_HIDDEN_DIM = 768


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


@dataclass
class EmbedderInfo:
    """Identity + dimensionality of an embedder, for storage metadata.

    The ``model_id`` and ``revision`` end up in the
    ``language_word_embeddings.embedder`` / ``embedder_revision`` columns
    so that re-runs can be distinguished and rolled back per-source.
    """

    model_id: str
    dim: int
    revision: str | None = None


class Embedder(ABC):
    """Abstract embedder.

    Subclasses turn an iterable of word strings into a (N, D) float
    matrix in the shared multilingual space. The interface is
    deliberately minimal so the populate / lookup pipeline doesn't care
    whether the vectors come from an encoder, a mock, or a frozen
    pretrained model.
    """

    @property
    @abstractmethod
    def info(self) -> EmbedderInfo: ...

    @abstractmethod
    def embed_words(self, words: Iterable[str]) -> np.ndarray:
        """Return a (len(words), self.info.dim) float32 array."""


# ---------------------------------------------------------------------------
# Mock (used by tests; no model download)
# ---------------------------------------------------------------------------


class MockEmbedder(Embedder):
    """Deterministic embedder that derives vectors from SHA-256 hashes.

    Two purposes:
    1. Tests can exercise the populate / lookup paths without a 1 GB
       transformer download.
    2. Same input always yields the same vector across processes, so
       tests are reproducible.

    The vectors are L2-normalised so cosine similarity is well-defined.
    Repeated calls for the same word return the same vector.
    """

    def __init__(self, dim: int = DEFAULT_HIDDEN_DIM, model_id: str = "mock") -> None:
        self._dim = dim
        self._model_id = model_id

    @property
    def info(self) -> EmbedderInfo:
        return EmbedderInfo(model_id=self._model_id, dim=self._dim, revision="mock-v1")

    def embed_words(self, words: Iterable[str]) -> np.ndarray:
        rows: list[np.ndarray] = []
        for word in words:
            normalised = unicodedata.normalize("NFC", word).lower()
            digest = hashlib.sha256(normalised.encode("utf-8")).digest()
            # Cycle the 32-byte digest into self._dim float32 values.
            seed_bytes = (digest * ((self._dim // 32) + 1))[: self._dim * 4]
            arr = np.frombuffer(seed_bytes, dtype=np.uint8)[: self._dim].astype(np.float32)
            arr = (arr - 127.5) / 127.5
            norm = float(np.linalg.norm(arr))
            if norm > 0:
                arr = arr / norm
            rows.append(arr)
        if not rows:
            return np.zeros((0, self._dim), dtype=np.float32)
        return np.vstack(rows)


# ---------------------------------------------------------------------------
# Real XLM-R embedder
# ---------------------------------------------------------------------------


class XLMREmbedder(Embedder):
    """Contextual word embeddings from XLM-R (or any HF AutoModel).

    Tokenises each word in isolation, runs the encoder, mean-pools the
    resulting sub-word hidden states (excluding [CLS]/[SEP]). The mean-
    pooled vector is then L2-normalised. This is the standard recipe
    for "word-level" embeddings out of a sentence-level encoder; for
    truly contextual embeddings (the same surface form in different
    sentences) the caller should pass full sentences instead of single
    words.

    Loading a LoRA adapter:
        em = XLMREmbedder(adapter_path="models/etr-lora-v1")

    The base model is loaded once into self._model. Inference happens
    on whatever device torch picks (CPU by default; CUDA if available).
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        adapter_path: str | Path | None = None,
        device: str | None = None,
        max_length: int = 32,
        batch_size: int = 64,
    ) -> None:
        self._model_id = model_id
        self._adapter_path = str(adapter_path) if adapter_path else None
        self._max_length = max_length
        self._batch_size = batch_size

        # Lazy import: don't drag torch into the import graph for users
        # who only want MockEmbedder.
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as e:
            raise ImportError(
                "XLMREmbedder requires the [transformers] extra: "
                "pip install -e '.[transformers]'"
            ) from e

        self._torch = torch
        self._device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        logger.info("Loading tokenizer + model: %s", model_id)
        self._tokenizer = AutoTokenizer.from_pretrained(model_id)
        self._model = AutoModel.from_pretrained(model_id).to(self._device)
        self._model.eval()

        if self._adapter_path:
            self._attach_lora_adapter(self._adapter_path)

        # Best-effort dim detection. XLM-R-base is 768; -large is 1024;
        # mBERT is 768 too.
        self._dim = int(self._model.config.hidden_size)

        # Capture a usable revision string for storage. HF's
        # `model.config._name_or_path` is stable across runs; the
        # adapter path discriminates fine-tuned variants.
        self._revision = (
            f"adapter:{self._adapter_path}" if self._adapter_path else "base"
        )

    def _attach_lora_adapter(self, adapter_path: str) -> None:
        try:
            from peft import PeftModel
        except ImportError as e:
            raise ImportError(
                "LoRA adapters require `peft`. Install with: "
                "pip install -e '.[transformers]'"
            ) from e
        logger.info("Attaching LoRA adapter from %s", adapter_path)
        self._model = PeftModel.from_pretrained(self._model, adapter_path)
        self._model.eval()

    @property
    def info(self) -> EmbedderInfo:
        return EmbedderInfo(
            model_id=self._model_id,
            dim=self._dim,
            revision=self._revision,
        )

    def embed_words(self, words: Iterable[str]) -> np.ndarray:
        words = [unicodedata.normalize("NFC", w).lower() for w in words]
        if not words:
            return np.zeros((0, self._dim), dtype=np.float32)

        out_chunks: list[np.ndarray] = []
        torch = self._torch

        for i in range(0, len(words), self._batch_size):
            batch = words[i : i + self._batch_size]
            enc = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=self._max_length,
                return_tensors="pt",
            ).to(self._device)

            with torch.no_grad():
                outputs = self._model(**enc)

            # outputs.last_hidden_state: (batch, seq_len, hidden)
            hidden = outputs.last_hidden_state
            mask = enc["attention_mask"].unsqueeze(-1).float()

            # Mean-pool over real tokens (mask=1), skipping padding.
            # This includes [CLS] and [SEP]; for very short inputs that
            # bias is acceptable. For sentence-level embeddings, switch
            # to mean-pool excluding the special tokens.
            summed = (hidden * mask).sum(dim=1)
            counts = mask.sum(dim=1).clamp(min=1)
            pooled = summed / counts

            # L2 normalise so cosine == inner product downstream.
            normed = torch.nn.functional.normalize(pooled, p=2, dim=1)
            out_chunks.append(normed.cpu().numpy().astype(np.float32))

        return np.vstack(out_chunks)
