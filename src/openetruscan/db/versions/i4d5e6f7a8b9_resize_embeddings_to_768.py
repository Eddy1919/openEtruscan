"""Resize language_word_embeddings vector column from 300 to 768.

Revision ID: i4d5e6f7a8b9
Revises: h3c4d5e6f7a8
Create Date: 2026-05-04

Background
----------
The original `language_word_embeddings` table (migration h3c4d5e6f7a8)
sized the vector column at 300 dims because the initial Rosetta plan
called for fasttext.cc word vectors (which are 300d). After a clean-room
review, the architecture changed: we now use a multilingual transformer
(XLM-RoBERTa-base) with LoRA-adapter fine-tuning on Etruscan, then take
contextual embeddings out of the encoder. XLM-R-base produces 768-dim
hidden states, so the column has to match.

The table is empty in production — vectors were never populated under
the old architecture — so a destructive recreate is the cleanest path.
The HNSW index is dropped and recreated against the new column type;
pgvector cannot ALTER COLUMN dimension in place.

If anyone has populated vectors locally, this migration drops them.
That is intentional. Local re-populate from the new pipeline is a
single command (`scripts/ops/populate_language.py`) once the encoder
is available.
"""

from collections.abc import Sequence

from alembic import op


revision: str = "i4d5e6f7a8b9"
down_revision: str | Sequence[str] | None = "h3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop + recreate the table at vector(768)."""
    op.execute("DROP INDEX IF EXISTS ix_language_word_embeddings_vector_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_language_word_embeddings_language")
    op.execute("DROP TABLE IF EXISTS language_word_embeddings")

    op.execute(
        """
        CREATE TABLE language_word_embeddings (
            language          TEXT       NOT NULL,
            word              TEXT       NOT NULL,
            vector            vector(768) NOT NULL,
            frequency         INTEGER,
            source            TEXT,
            embedder          TEXT       NOT NULL DEFAULT 'xlm-roberta-base',
            embedder_revision TEXT,
            created_at        TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY (language, word)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_language_word_embeddings_language "
        "ON language_word_embeddings (language)"
    )
    op.execute(
        "CREATE INDEX ix_language_word_embeddings_vector_hnsw "
        "ON language_word_embeddings USING hnsw (vector vector_cosine_ops)"
    )


def downgrade() -> None:
    """Restore the previous 300-dim shape (without alignment_source)."""
    op.execute("DROP INDEX IF EXISTS ix_language_word_embeddings_vector_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_language_word_embeddings_language")
    op.execute("DROP TABLE IF EXISTS language_word_embeddings")

    op.execute(
        """
        CREATE TABLE language_word_embeddings (
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
    op.execute(
        "CREATE INDEX ix_language_word_embeddings_language "
        "ON language_word_embeddings (language)"
    )
    op.execute(
        "CREATE INDEX ix_language_word_embeddings_vector_hnsw "
        "ON language_word_embeddings USING hnsw (vector vector_cosine_ops)"
    )
