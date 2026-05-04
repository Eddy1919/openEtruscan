"""Multilingual word-embedding table for the Rosetta Vector Space.

Revision ID: h3c4d5e6f7a8
Revises: g2b3c4d5e6f7
Create Date: 2026-05-03

Background
----------
Phase 2a (commit f7b8ff6) shipped supervised Procrustes alignment between
Etruscan and Latin in-memory only — every call has to retrain or reload
both models. To support cross-language nearest-neighbour queries from the
public API and to allow offline batch population from heterogeneous
sources (pretrained fasttext.cc, custom-trained from epigraphic dumps,
…), we need persistent storage for the *aligned* word vectors.

Design choices
--------------
* **One table for every language**, partitioned by a `language` column,
  not a table-per-language. Cross-language queries are then a single
  WHERE clause + pgvector cosine, instead of N round-trips. Storage is
  small (≤ 1M words × 300 dims × 4 bytes ≈ 1.2 GB total even at full
  scale).
* **Vectors are stored already-aligned** — every row is in the *shared*
  Rosetta space. The ``alignment_source`` column records which rotation
  produced it ("native" for the anchor language, "procrustes_v1" etc.
  for the rest), so we can re-align without losing the raw vectors
  (those live in their original .bin model files in Cloud Storage).
* **vector(300)** because that's what fasttext.cc uses; it's also the
  most common dim for academic NLP work, so we don't have to PCA-project
  every imported model.
* **HNSW index** on (language, vector) so cross-language queries hit
  pgvector's approximate-NN code path instead of full scans.

The table schema is deliberately minimal — no foreign keys to
inscriptions, no per-word inscriptions list. That belongs in the
existing ``inscriptions.emb_*`` columns. This table is for *word-level*
multilingual semantics; it doesn't replace per-inscription embeddings.
"""

from collections.abc import Sequence

from alembic import op


revision: str = "h3c4d5e6f7a8"
down_revision: str | Sequence[str] | None = "g2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create language_word_embeddings + an HNSW index."""
    # Make sure pgvector is available. The deploy already creates this
    # extension elsewhere but the migration is idempotent.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS language_word_embeddings (
            language          TEXT       NOT NULL,
            word              TEXT       NOT NULL,
            vector            vector(300) NOT NULL,
            frequency         INTEGER,
            source            TEXT,
            alignment_source  TEXT       NOT NULL DEFAULT 'native',
            created_at        TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY (language, word)
        )
        """
    )

    # Plain B-tree on language for the WHERE filter; pgvector's HNSW for
    # the actual cosine search. Combined index (language, vector) isn't
    # supported by pgvector — the planner uses the language WHERE +
    # vector index serially, which is the right plan for our cardinality.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_language_word_embeddings_language "
        "ON language_word_embeddings (language)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_language_word_embeddings_vector_hnsw "
        "ON language_word_embeddings USING hnsw (vector vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_language_word_embeddings_vector_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_language_word_embeddings_language")
    op.execute("DROP TABLE IF EXISTS language_word_embeddings")
