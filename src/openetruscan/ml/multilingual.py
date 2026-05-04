"""Multilingual word-vector storage + cross-language nearest-neighbour lookup.

This module turns the in-memory Procrustes alignment from `alignment.py`
into a persistent, queryable cross-language vector space. It writes
*aligned* word vectors into the ``language_word_embeddings`` pgvector
table (migration ``h3c4d5e6f7a8``) so the API can answer "which Latin
words are nearest to Etruscan ``zich``?" with a single SQL round-trip
instead of reloading two FastText models.

Public surface
--------------

  LANGUAGE_TIERS              — registry of every language we know about,
                                with viability classification + data status.
  LanguageRecord              — schema for one language's metadata.
  populate_aligned_language(...) — store an aligned model's word vectors.
  find_cross_language_neighbours(word, source_lang, target_lang) — query.

Honest scoping
--------------

`LANGUAGE_TIERS` codifies which languages this module *can* honestly
support today. Three tiers:

  * tier 1 (deciphered, large corpus, alignable): Latin, Ancient Greek.
  * tier 2 (deciphered, small corpus, alignable but noisy): Etruscan,
    Phoenician, Oscan, Coptic Egyptian, modern-Basque-as-proxy.
  * tier 3 (undeciphered or insufficient corpus, structural-only):
    Linear A / Minoan, Nuragic, Illyrian, Faliscan.

Tier 3 entries can have their structural embeddings stored in the
table (so the schema is uniform), but `find_cross_language_neighbours`
explicitly refuses to produce semantic alignments TO/FROM them. We're
not going to publish "Linear A word X means Latin Y" claims that the
data cannot actually support.
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("openetruscan.multilingual")

EMBEDDING_DIM = 300


# ---------------------------------------------------------------------------
# Language registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LanguageRecord:
    """Metadata for one language we might store vectors for.

    Two independent capability flags:

    * ``alignable`` — can be honestly aligned to other deciphered languages
      via supervised Procrustes. Tier 1+2 only. The cross-language API
      refuses queries where either side has ``alignable=False``.
    * ``structural_embedding_viable`` — has enough corpus / co-occurrence
      data for FastText to learn meaningful within-language sign
      relationships, even if cross-language alignment is impossible.
      Linear A (undeciphered, ~1500 fragments) qualifies; Illyrian
      (onomastic-only, no productive corpus) does not.

    A tier-3 language can have ``structural_embedding_viable=True`` —
    that means we can store its native vectors in the table for
    within-language exploration ("which Linear A sign clusters appear in
    similar contexts?") without claiming any cross-language meaning.
    """

    code: str               # ISO 639-3 where possible; otherwise project-local
    name: str               # human-readable
    tier: int               # 1 = best, 3 = structural only
    deciphered: bool
    alignable: bool         # gate for cross-language semantic queries
    corpus_status: str      # one of: pretrained, ingest_pending, undeciphered, missing
    notes: str = ""
    expected_dim: int = EMBEDDING_DIM
    typical_source: str = ""
    structural_embedding_viable: bool = True  # default True for the alignable languages;
                                              # tier-3 entries set this explicitly


LANGUAGE_TIERS: dict[str, LanguageRecord] = {
    # ── Tier 1: large, deciphered, pretrained models exist ─────────────
    "lat": LanguageRecord(
        code="lat", name="Latin", tier=1, deciphered=True, alignable=True,
        corpus_status="pretrained",
        typical_source="fasttext.cc cc.la.300.bin",
        notes="The primary alignment target for Etruscan. ~10⁸ tokens.",
    ),
    "grc": LanguageRecord(
        code="grc", name="Ancient Greek", tier=1, deciphered=True, alignable=True,
        corpus_status="pretrained",
        typical_source="CLTK Greek embeddings or PHI Greek",
        notes="Etruscan-Greek alignment is best done transitively via Latin "
              "(few documented direct equivalences besides theonyms).",
    ),
    # ── Tier 2: small but viable, alignable with caveats ───────────────
    "ett": LanguageRecord(
        code="ett", name="Etruscan", tier=2, deciphered=True, alignable=True,
        corpus_status="ingest_pending",  # we have it; the model is in Cloud Storage
        typical_source="trained from this repo's corpus DB",
        notes="The anchor language for the Rosetta initiative.",
    ),
    "phn": LanguageRecord(
        code="phn", name="Phoenician", tier=2, deciphered=True, alignable=True,
        corpus_status="ingest_pending",
        typical_source="KAI corpus (Donner-Röllig digitisation)",
        notes="Trains at ~50k tokens — same scale as Etruscan, similar ceiling.",
    ),
    "osc": LanguageRecord(
        code="osc", name="Oscan", tier=2, deciphered=True, alignable=True,
        corpus_status="ingest_pending",
        typical_source="ImagInes Italicae digitisation",
        notes="~5k tokens. Tight Italic ties to Latin make supervised "
              "alignment promising once ingested.",
    ),
    "cop": LanguageRecord(
        code="cop", name="Coptic", tier=2, deciphered=True, alignable=True,
        corpus_status="pretrained",
        typical_source="CLTK Coptic embeddings",
        notes="The latest stage of Egyptian. Older stages (Old, Middle "
              "Egyptian, Demotic) require hieroglyphic transliteration "
              "pipelines we don't ship; flagged separately as `egy`.",
    ),
    "egy": LanguageRecord(
        code="egy", name="Egyptian (Old/Middle/Late)", tier=2, deciphered=True,
        alignable=True, corpus_status="missing",
        notes="Hieroglyphic. Substantial specialist work (Manuel de Codage "
              "transliteration, register split). Not on the immediate path.",
    ),
    "eus": LanguageRecord(
        code="eus", name="Basque (modern, proxy for Aquitanian)", tier=2,
        deciphered=True, alignable=True, corpus_status="pretrained",
        typical_source="fasttext.cc cc.eu.300.bin",
        notes="Modern Basque is the closest living relative of pre-Roman "
              "Aquitanian. Cross-language alignment must label results "
              "MODERN-BASQUE-VIA-PROXY, never claim direct Aquitanian "
              "equivalence.",
    ),
    # ── Tier 3: structural-only, NOT semantically alignable ────────────
    # `structural_embedding_viable` differentiates "we can train within-
    # language structural FastText" from "the corpus is too thin even
    # for that". Cross-language semantic alignment is refused for ALL
    # tier-3 entries regardless.
    "lin_a": LanguageRecord(
        code="lin_a", name="Linear A / Minoan", tier=3,
        deciphered=False, alignable=False,
        structural_embedding_viable=True,
        corpus_status="ingest_pending",
        typical_source="Younger's Linear A inscription database",
        notes="~1500 fragments / ~3000 sign tokens. Enough sign-sequence "
              "co-occurrence to train a FastText that captures structural "
              "neighbourhoods (which sign clusters appear in similar "
              "contexts). Cross-language alignment to deciphered languages "
              "is NOT supported — there's no semantic ground truth.",
    ),
    "xnu": LanguageRecord(
        code="xnu", name="Nuragic / pre-Roman Sardic", tier=3,
        deciphered=False, alignable=False,
        structural_embedding_viable=False,
        corpus_status="undeciphered",
        notes="~30-50 short inscriptions. Below FastText viability "
              "threshold even for structural embeddings. Move to "
              "structural_embedding_viable=True if a larger digitisation "
              "(e.g. all known Nuragic bronzetto inscriptions) lands.",
    ),
    "xil": LanguageRecord(
        code="xil", name="Illyrian", tier=3,
        deciphered=False, alignable=False,
        structural_embedding_viable=False,
        corpus_status="missing",
        notes="Predominantly onomastic data — personal names attested in "
              "Greek/Latin sources, no running text. FastText needs "
              "co-occurrence context that this corpus doesn't provide.",
    ),
    "xfa": LanguageRecord(
        code="xfa", name="Faliscan", tier=3,
        deciphered=True, alignable=False,
        structural_embedding_viable=False,
        corpus_status="missing",
        notes="Deciphered (Italic, sister of Latin) but corpus is ~300 "
              "inscriptions / sub-1k tokens — below FastText viability "
              "threshold. Move to tier 2 + alignable=True if a larger "
              "digitisation lands; the language itself supports semantic "
              "alignment, only the data is missing.",
    ),
}


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


@dataclass
class PopulateResult:
    """Outcome of a populate_aligned_language run."""

    language: str
    n_inserted: int
    n_skipped_oov: int
    skipped_examples: list[str] = field(default_factory=list)


async def populate_aligned_language(
    *,
    language: str,
    model: Any,
    alignment_W: Any | None,
    session: AsyncSession,
    source: str,
    alignment_source: str = "procrustes_v1",
    max_words: int | None = None,
    min_frequency: int | None = None,
) -> PopulateResult:
    """Insert one language's word vectors into ``language_word_embeddings``.

    ``alignment_W``: pass the Procrustes rotation matrix (vector_size² of
    floats) to project every model word into the shared Rosetta space.
    For the *anchor* language (Etruscan) pass ``None`` — the native
    vectors go in unchanged with ``alignment_source='native'``.

    ``model``: any object with a gensim-compatible ``.wv`` interface.
    Iterates ``model.wv.key_to_index`` to enumerate the vocab.

    Vectors are unit-normalised at write time so cosine queries reduce to
    inner products on the pgvector side.
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
            f"Language {language!r} is registered as structurally non-viable "
            f"(insufficient corpus). Refusing to populate vectors that would "
            f"be misleading. Note: {record.notes}"
        )

    rows: list[dict[str, Any]] = []
    n_skipped_oov = 0
    skipped_examples: list[str] = []

    keys = list(model.wv.key_to_index)
    if max_words is not None:
        # Most-frequent-first ordering; gensim already orders index by freq.
        keys = keys[:max_words]

    for word in keys:
        # Frequency filter (gensim stores it on the vocab object).
        freq = getattr(model.wv.get_vecattr(word, "count"), "__int__", None)
        if min_frequency is not None and freq is not None and freq < min_frequency:
            continue

        try:
            vec = model.wv[word]
        except KeyError:
            n_skipped_oov += 1
            if len(skipped_examples) < 5:
                skipped_examples.append(word)
            continue

        if alignment_W is not None:
            vec = vec @ alignment_W

        if vec.shape[0] != record.expected_dim:
            # Procrustes preserves dimension; if we hit this it's a config
            # bug, not a runtime failure. Fail loudly.
            raise ValueError(
                f"Vector dim {vec.shape[0]} != expected {record.expected_dim} "
                f"for language {language!r}. Re-train at the right size or "
                f"PCA-project before populating."
            )

        # L2-normalise for cosine == dot product on pgvector's side.
        norm = float(np.linalg.norm(vec))
        if norm == 0:
            n_skipped_oov += 1
            continue
        vec = (vec / norm).astype(np.float32)

        rows.append(
            {
                "language": language,
                "word": unicodedata.normalize("NFC", word).lower(),
                "vector": vec.tolist(),
                "frequency": int(freq) if freq is not None else None,
                "source": source,
                "alignment_source": alignment_source if alignment_W is not None else "native",
            }
        )

    if not rows:
        return PopulateResult(
            language=language,
            n_inserted=0,
            n_skipped_oov=n_skipped_oov,
            skipped_examples=skipped_examples,
        )

    # Upsert: replace any existing (language, word) row so re-running
    # populate_aligned_language with a fresher model is idempotent.
    stmt = text(
        """
        INSERT INTO language_word_embeddings
            (language, word, vector, frequency, source, alignment_source)
        VALUES (:language, :word, :vector, :frequency, :source, :alignment_source)
        ON CONFLICT (language, word) DO UPDATE SET
            vector = EXCLUDED.vector,
            frequency = EXCLUDED.frequency,
            source = EXCLUDED.source,
            alignment_source = EXCLUDED.alignment_source
        """
    )

    # Batch executemany for throughput; pgvector via asyncpg+sqlalchemy
    # accepts list-of-floats directly when registered, but the safe path
    # for a generic Postgres deployment is the array-cast string form.
    BATCH = 1000
    for i in range(0, len(rows), BATCH):
        batch = rows[i : i + BATCH]
        # asyncpg + sqlalchemy.text doesn't take vector(300) literals
        # transparently; encode each vector as a Postgres array literal.
        for row in batch:
            row["vector"] = "[" + ",".join(f"{x:.6f}" for x in row["vector"]) + "]"
        await session.execute(stmt, batch)
    await session.commit()

    logger.info(
        "Inserted %d vectors for language %r (skipped %d OOV)",
        len(rows), language, n_skipped_oov,
    )
    return PopulateResult(
        language=language,
        n_inserted=len(rows),
        n_skipped_oov=n_skipped_oov,
        skipped_examples=skipped_examples,
    )


# ---------------------------------------------------------------------------
# Cross-language lookup
# ---------------------------------------------------------------------------


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
) -> list[CrossLanguageHit]:
    """For ``word`` in ``source_lang``, return the top-k nearest words in
    ``target_lang`` (cosine similarity in the shared Rosetta space).

    Refuses when either language is tier-3 (undeciphered or sub-viable):
    stored structural embeddings carry no semantic anchor that would make
    the result meaningful.
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

    # 1. Look up the source word's stored vector. Sub-word fallback at the
    #    SQL layer doesn't exist; the caller can fall back to running
    #    `model.wv[word]` themselves and passing the vector explicitly.
    src_row = await session.execute(
        text(
            "SELECT vector FROM language_word_embeddings "
            "WHERE language = :lang AND word = :word"
        ),
        {"lang": source_lang, "word": word},
    )
    row = src_row.first()
    if row is None:
        return []
    src_vector = row[0]

    # 2. Cosine-search target language. Vectors are L2-normalised on
    #    insert so cosine ≡ inner product, but pgvector's native operator
    #    is `<=>` (cosine *distance*). Convert back at the end.
    target = await session.execute(
        text(
            """
            SELECT word, 1 - (vector <=> CAST(:src AS vector)) AS cosine
            FROM language_word_embeddings
            WHERE language = :target
            ORDER BY vector <=> CAST(:src AS vector)
            LIMIT :k
            """
        ),
        {
            "src": src_vector,
            "target": target_lang,
            "k": k,
        },
    )
    return [
        CrossLanguageHit(word=w, cosine=float(c), language=target_lang)
        for w, c in target.all()
    ]
