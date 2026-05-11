"""Multilingual word-vector storage + cross-language nearest-neighbour lookup.

The Rosetta Vector Space's persistence + query layer.

Architecture (see ROADMAP):
  * A multilingual transformer encoder (XLM-RoBERTa by default) produces
    contextual word vectors. The encoder's pretraining covers 100+
    languages so cross-language retrieval is implicit — no Procrustes
    alignment step required.
  * For Etruscan specifically, a LoRA adapter is fine-tuned on the
    inscriptions corpus (see ``finetune.py``). The adapter teaches the
    encoder Etruscan-specific morphology without overwriting the
    pretrained multilingual structure.
  * Word vectors are persisted in the ``language_word_embeddings``
    pgvector table (migration ``i4d5e6f7a8b9``, vector(768)). Each row
    records which encoder + revision produced it so re-runs are
    distinguishable and rollback-able.

Public surface
--------------
  LANGUAGE_TIERS              — registry of every language we recognise,
                                with viability classification + data status.
  LanguageRecord              — schema for one language's metadata.
  populate_language(...)      — embed a vocabulary list with an Embedder
                                and upsert into the pgvector table.
  find_cross_language_neighbours(word, source_lang, target_lang) — query.

Honest scoping
--------------
``LANGUAGE_TIERS`` codifies which languages this module *can* honestly
support today. Three tiers:

  * tier 1 (deciphered, well-represented in the encoder's pretraining):
    Latin, Ancient Greek.
  * tier 2 (deciphered, supported via fine-tuning or proxy):
    Etruscan, Phoenician, Oscan, Coptic, Egyptian, Modern Basque.
  * tier 3 (undeciphered or insufficient corpus): Linear A / Minoan,
    Nuragic, Illyrian, Faliscan. Only Linear A has enough sign-sequence
    data to support within-language structural embeddings; the rest
    are listed for transparency but populate refuses to write them.

Tier-3 entries can have their structural embeddings stored, but
``find_cross_language_neighbours`` refuses to produce semantic
alignments TO/FROM them. We're not going to publish "Linear A word X
means Latin Y" claims that the data cannot actually support.
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from openetruscan.ml.embeddings import Embedder

logger = logging.getLogger("openetruscan.multilingual")

# Native hidden dim for XLM-R-base. xlm-roberta-large is 1024; mBERT
# is 768. The pgvector schema fixes this at the column type so changes
# require a new migration.
EMBEDDING_DIM = 768


# ---------------------------------------------------------------------------
# Language registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LanguageRecord:
    """Metadata for one language we might store vectors for.

    Two independent capability flags:

    * ``alignable`` — the encoder can place this language in the shared
      multilingual space honestly. Tier 1 + 2 only. Cross-language
      neighbour queries refuse pairs where either side is not alignable.
    * ``structural_embedding_viable`` — has enough corpus / co-occurrence
      data for the encoder to learn meaningful within-language sign
      relationships. Linear A qualifies; Illyrian (onomastic-only) does
      not. populate_language() refuses to write languages where this is
      False.
    """

    code: str
    name: str
    tier: int               # 1 = best, 3 = undeciphered or sub-viable
    deciphered: bool
    alignable: bool
    corpus_status: str      # one of: pretrained_in_encoder, ingest_pending, undeciphered, missing
    notes: str = ""
    expected_dim: int = EMBEDDING_DIM
    typical_source: str = ""
    structural_embedding_viable: bool = True


LANGUAGE_TIERS: dict[str, LanguageRecord] = {
    # ── Tier 1: deciphered, well-covered by the encoder's pretraining ──
    "lat": LanguageRecord(
        code="lat", name="Latin", tier=1, deciphered=True, alignable=True,
        corpus_status="pretrained_in_encoder",
        typical_source="XLM-RoBERTa multilingual pretraining (CC + Wikipedia Latin)",
        notes="Latin is one of XLM-R's 100 pretraining languages, with "
              "substantial Common Crawl + Wikipedia coverage. Vectors come "
              "directly from the encoder, no separate model needed.",
    ),
    "grc": LanguageRecord(
        code="grc", name="Ancient Greek", tier=1, deciphered=True, alignable=True,
        corpus_status="pretrained_in_encoder",
        typical_source="XLM-R multilingual pretraining (with Greek-BERT fallback for hard inputs)",
        notes="Ancient Greek shares vocabulary + syntax with modern Greek "
              "well enough that XLM-R's `el` weights transfer. For domain-"
              "specific work consider Greek-BERT (Koutsikakis et al 2020) "
              "as an alternative encoder.",
    ),
    # ── Tier 2: deciphered, supported via LoRA fine-tuning or proxy ────
    "ett": LanguageRecord(
        code="ett", name="Etruscan", tier=2, deciphered=True, alignable=True,
        corpus_status="ingest_pending",
        typical_source="XLM-R + LoRA adapter fine-tuned on this corpus",
        notes="The anchor language for the Rosetta initiative. The LoRA "
              "adapter is fine-tuned on the 6,633-inscription corpus so "
              "Etruscan vectors live in the same multilingual space as "
              "the languages already covered by XLM-R pretraining.",
    ),
    "phn": LanguageRecord(
        code="phn", name="Phoenician", tier=2, deciphered=True, alignable=True,
        corpus_status="ingest_pending",
        typical_source="XLM-R + LoRA fine-tune on KAI corpus",
        notes="~50k tokens (KAI digitisation). LoRA fine-tune the same way "
              "we do Etruscan; Latin-via-Greek-via-Phoenician transfer "
              "should be measurable.",
    ),
    "osc": LanguageRecord(
        code="osc", name="Oscan", tier=2, deciphered=True, alignable=True,
        corpus_status="ingest_pending",
        typical_source="XLM-R + LoRA fine-tune on ImagInes Italicae",
        notes="~5k tokens. Tight Italic ties to Latin make this an easy "
              "transfer once the corpus is ingested.",
    ),
    "cop": LanguageRecord(
        code="cop", name="Coptic", tier=2, deciphered=True, alignable=True,
        corpus_status="ingest_pending",
        typical_source="XLM-R + LoRA fine-tune (or use Coptic-SCRIPTORIUM's encoder directly)",
        notes="Latest stage of Egyptian. Older stages flagged separately as `egy`.",
    ),
    "egy": LanguageRecord(
        code="egy", name="Egyptian (Old/Middle/Late)", tier=2, deciphered=True,
        alignable=True, corpus_status="missing",
        notes="Hieroglyphic. Substantial specialist work (Manuel de Codage "
              "transliteration, register split). Not on the immediate path.",
    ),
    "eus": LanguageRecord(
        code="eus", name="Basque (modern, proxy for Aquitanian)", tier=2,
        deciphered=True, alignable=True,
        corpus_status="pretrained_in_encoder",
        typical_source="XLM-R multilingual pretraining (modern Basque)",
        notes="Modern Basque is the closest living relative of pre-Roman "
              "Aquitanian. Cross-language results MUST be labelled "
              "MODERN-BASQUE-VIA-PROXY, never claim direct Aquitanian "
              "equivalence.",
    ),
    # ── Tier 3: structural-only or non-viable ──────────────────────────
    "lin_a": LanguageRecord(
        code="lin_a", name="Linear A / Minoan", tier=3,
        deciphered=False, alignable=False,
        structural_embedding_viable=True,
        corpus_status="ingest_pending",
        typical_source="custom encoder fine-tuned from random init on Younger's database",
        notes="~1500 fragments. Enough sign-sequence data to learn "
              "structural neighbourhoods (which sign clusters appear in "
              "similar contexts). Cross-language alignment to deciphered "
              "languages is NOT supported — no semantic ground truth.",
    ),
    "xnu": LanguageRecord(
        code="xnu", name="Nuragic / pre-Roman Sardic", tier=3,
        deciphered=False, alignable=False,
        structural_embedding_viable=False,
        corpus_status="undeciphered",
        notes="~30-50 short inscriptions. Below viability threshold even "
              "for structural embeddings.",
    ),
    "xil": LanguageRecord(
        code="xil", name="Illyrian", tier=3,
        deciphered=False, alignable=False,
        structural_embedding_viable=False,
        corpus_status="missing",
        notes="Onomastic-only — personal names attested in Greek/Latin "
              "sources, no running text for the encoder to learn from.",
    ),
    "xfa": LanguageRecord(
        code="xfa", name="Faliscan", tier=3,
        deciphered=True, alignable=False,
        structural_embedding_viable=False,
        corpus_status="missing",
        notes="Deciphered (Italic, sister of Latin) but corpus is ~300 "
              "inscriptions / sub-1k tokens. Move to tier 2 + alignable "
              "if a larger digitisation lands.",
    ),
}


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


@dataclass
class PopulateResult:
    """Outcome of a populate_language run."""

    language: str
    embedder_model_id: str
    embedder_revision: str | None
    n_inserted: int
    n_skipped_empty: int
    skipped_examples: list[str] = field(default_factory=list)


async def populate_language(
    *,
    language: str,
    words: list[str],
    embedder: Embedder,
    session: AsyncSession,
    source: str,
    frequencies: dict[str, int] | None = None,
) -> PopulateResult:
    """Embed a vocabulary list and upsert it into ``language_word_embeddings``.

    The caller is responsible for assembling the vocab — typically by
    iterating a corpus and counting tokens, or by reading the
    ``language_word_embeddings.word`` column from a previous run for
    re-population.

    The embedder identifies itself via ``embedder.info`` so future
    queries can know which model + revision produced each row.
    """
    import numpy as np
    from sqlalchemy import text

    record = LANGUAGE_TIERS.get(language)
    if record is None:
        raise ValueError(
            f"Unknown language code {language!r}. Add it to LANGUAGE_TIERS first."
        )
    if not record.structural_embedding_viable:
        raise ValueError(
            f"Language {language!r} is registered as structurally non-viable. "
            f"Refusing to populate vectors that would be misleading. "
            f"Note: {record.notes}"
        )

    info = embedder.info
    if info.dim != record.expected_dim:
        raise ValueError(
            f"Embedder dim {info.dim} != expected {record.expected_dim} for "
            f"language {language!r}. Either change the embedder or write a "
            f"new migration that resizes the vector column."
        )

    if not words:
        logger.warning("populate_language(%r): empty word list, nothing to do", language)
        return PopulateResult(
            language=language,
            embedder_model_id=info.model_id,
            embedder_revision=info.revision,
            n_inserted=0,
            n_skipped_empty=0,
        )

    # Compute embeddings in one batch (Embedder handles internal batching).
    logger.info(
        "populate_language(%r): embedding %d words via %s",
        language, len(words), info.model_id,
    )
    vectors = embedder.embed_words(words)

    rows: list[dict[str, Any]] = []
    n_skipped_empty = 0
    skipped_examples: list[str] = []

    for word, vec in zip(words, vectors, strict=True):
        norm = float(np.linalg.norm(vec))
        if norm == 0:
            n_skipped_empty += 1
            if len(skipped_examples) < 5:
                skipped_examples.append(word)
            continue
        rows.append(
            {
                "language": language,
                "word": unicodedata.normalize("NFC", word).lower(),
                "vector": "[" + ",".join(f"{x:.6f}" for x in vec.tolist()) + "]",
                "frequency": frequencies.get(word) if frequencies else None,
                "source": source,
                "embedder": info.model_id,
                "embedder_revision": info.revision,
            }
        )

    if not rows:
        return PopulateResult(
            language=language,
            embedder_model_id=info.model_id,
            embedder_revision=info.revision,
            n_inserted=0,
            n_skipped_empty=n_skipped_empty,
            skipped_examples=skipped_examples,
        )

    # Upsert: rerunning is idempotent + replaces vectors with the latest
    # encoder output. Conflict key matches the post-T2.3 4-column PK so
    # different (embedder, embedder_revision) partitions for the same
    # (language, word) coexist; re-running this populate replaces only
    # the matching partition.
    stmt = text(
        """
        INSERT INTO language_word_embeddings
            (language, word, vector, frequency, source, embedder, embedder_revision)
        VALUES
            (:language, :word, :vector, :frequency, :source, :embedder, :embedder_revision)
        ON CONFLICT (language, word, embedder, embedder_revision) DO UPDATE SET
            vector = EXCLUDED.vector,
            frequency = EXCLUDED.frequency,
            source = EXCLUDED.source
        """
    )

    BATCH = 500
    for i in range(0, len(rows), BATCH):
        await session.execute(stmt, rows[i : i + BATCH])
    await session.commit()

    logger.info(
        "populate_language(%r): inserted %d rows (skipped %d zero-norm)",
        language, len(rows), n_skipped_empty,
    )
    return PopulateResult(
        language=language,
        embedder_model_id=info.model_id,
        embedder_revision=info.revision,
        n_inserted=len(rows),
        n_skipped_empty=n_skipped_empty,
        skipped_examples=skipped_examples,
    )


# ---------------------------------------------------------------------------
# Cross-language lookup
# ---------------------------------------------------------------------------

# Default partition served when no `embedder` is requested. This MUST match
# the canonical labels already in prod (verified 2026-05-11: rows are
# labelled `sentence-transformers/LaBSE` / `v1`, NOT `LaBSE` / `v1`).
# Changing either string here without also re-labelling the existing rows
# would silently return an empty result set for the default call.
DEFAULT_EMBEDDER = "sentence-transformers/LaBSE"
DEFAULT_EMBEDDER_REVISION = "v1"


@dataclass
class CrossLanguageHit:
    word: str
    cosine: float
    language: str


async def find_cross_language_neighbours(
    *,
    word: str,
    source_lang: str,
    target_lang: str,
    session: AsyncSession,
    k: int = 10,
    embedder: str | None = None,
    embedder_revision: str | None = None,
) -> list[CrossLanguageHit]:
    """For ``word`` in ``source_lang``, return the top-k nearest words in
    ``target_lang`` (cosine similarity in the shared multilingual space).

    Refuses tier-3 languages on either side. Refuses unknown codes.
    Returns an empty list if the source word has no stored vector — the
    caller can decide whether to embed-on-demand and retry.

    Parameters
    ----------
    embedder, embedder_revision : str | None
        Filter on the ``(embedder, embedder_revision)`` partition of
        ``language_word_embeddings``. Both default to the canonical
        LaBSE/v1 partition that the API has served since launch; pass
        explicit values (e.g. ``embedder='xlmr-lora', embedder_revision='v4'``)
        to query a different partition. Source word and target neighbours
        are filtered consistently to the same partition.
    """
    from sqlalchemy import text

    src = LANGUAGE_TIERS.get(source_lang)
    tgt = LANGUAGE_TIERS.get(target_lang)
    if src is None or tgt is None:
        raise ValueError(
            f"Unknown language code(s): "
            f"source={source_lang!r}, target={target_lang!r}"
        )
    if not src.alignable or not tgt.alignable:
        unaligned = [
            f"{lr.code} ({lr.notes})"
            for lr in (src, tgt)
            if not lr.alignable
        ]
        raise ValueError(
            "Cross-language semantic neighbours refused: "
            + "; ".join(unaligned)
        )

    word = unicodedata.normalize("NFC", word).lower()
    embedder = embedder if embedder is not None else DEFAULT_EMBEDDER
    embedder_revision = (
        embedder_revision if embedder_revision is not None else DEFAULT_EMBEDDER_REVISION
    )

    src_row = await session.execute(
        text(
            "SELECT vector FROM language_word_embeddings "
            "WHERE language = :lang AND word = :word "
            "  AND embedder = :embedder AND embedder_revision = :embedder_revision"
        ),
        {
            "lang": source_lang,
            "word": word,
            "embedder": embedder,
            "embedder_revision": embedder_revision,
        },
    )
    row = src_row.first()
    if row is None:
        return []
    src_vector = row[0]

    target = await session.execute(
        text(
            """
            SELECT word, 1 - (vector <=> CAST(:src AS vector)) AS cosine
            FROM language_word_embeddings
            WHERE language = :target
              AND embedder = :embedder AND embedder_revision = :embedder_revision
            ORDER BY vector <=> CAST(:src AS vector)
            LIMIT :k
            """
        ),
        {
            "src": src_vector,
            "target": target_lang,
            "embedder": embedder,
            "embedder_revision": embedder_revision,
            "k": k,
        },
    )
    return [
        CrossLanguageHit(word=w, cosine=float(c), language=target_lang)
        for w, c in target.all()
    ]
