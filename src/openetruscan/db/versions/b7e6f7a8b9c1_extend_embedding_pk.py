"""extend_embedding_pk

Extend ``language_word_embeddings`` primary key from ``(language, word)`` to
``(language, word, embedder, embedder_revision)`` so the same surface form
can carry vectors from multiple embedders side-by-side (LaBSE alongside
xlmr-lora-v4, etc.) without one's ingest clobbering the other's rows.

Revision ID: b7e6f7a8b9c1
Revises: a6d56926ff21
Create Date: 2026-05-11 00:30:00.000000

Why this id, not j5e6f7a8b9c0
-----------------------------
A planning-agent draft suggested ``j5e6f7a8b9c0`` as the next revision id.
That's the exact phantom revision that broke prod deploys for hours on
2026-05-10 and required a direct-SQL ``UPDATE alembic_version SET
version_num = 'a6d56926ff21'`` to unblock. Re-using the id would
collide with the SQL-stamp's history and reintroduce the same class of
bookkeeping bug. The fresh id ``b7e6f7a8b9c1`` was verified not to
appear anywhere in this repo's git history via
``git log -S '...' --pickaxe-regex`` before being assigned.

Phase 1 reconnaissance, 2026-05-11
----------------------------------
Verified against prod before writing this migration:

* alembic head == ``a6d56926ff21`` (confirmed)
* 210,268 total rows across (ett, grc, lat); zero (language, word) duplicates
* No rows have ``embedder IS NULL`` or ``embedder_revision IS NULL``
* Distribution of (embedder, embedder_revision):
    - ``sentence-transformers/LaBSE`` / ``v1``       — 208,680
    - ``xlm-roberta-base`` / ``v3-base``             —   1,176
    - ``xlm-roberta-base+etr-lora-v3`` / ``v3``      —     412
* HNSW index ``ix_language_word_embeddings_vector_hnsw`` is on ``(vector)``
  only and is NOT affected by the PK change. Do not touch it.

This means **no backfill is needed**. All existing rows already carry
non-null values in both columns. The migration only:

1. Flips ``embedder_revision`` from nullable to NOT NULL (defensive — no
   data change since there are zero nulls).
2. Drops the existing 2-column PK.
3. Adds the new 4-column PK.
4. Creates a compound supporting index on
   ``(language, embedder, embedder_revision)`` so the new WHERE shape in
   ``find_cross_language_neighbours`` gets index access.

Lock note
---------
``DROP CONSTRAINT`` briefly holds ``ACCESS EXCLUSIVE``. With 210k rows the
PK rebuild completes in single-digit seconds, but in-flight
``/neural/rosetta`` queries block for the duration. The transaction is
atomic; if anything fails, no partial PK is left behind.

Downgrade is destructive
------------------------
``downgrade()`` cannot reduce a 4-column PK back to 2 columns while keeping
all rows, because once two distinct embedders' rows coexist for the same
``(language, word)`` (the whole point of this migration), a 2-column PK
would have duplicates. The downgrade DELETEs anything that isn't
``sentence-transformers/LaBSE`` / ``v1`` first to recover the old shape.
Run downgrade only on a fresh DB or one you're willing to lose v4-ingest
work from.
"""
from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b7e6f7a8b9c1"
down_revision: str | Sequence[str] | None = "a6d56926ff21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Defensive: keep the statement_timeout short so a stuck migration
    # aborts rather than wedging the API behind the ACCESS EXCLUSIVE lock.
    op.execute("SET LOCAL statement_timeout = '60s'")

    # 1. embedder_revision: NULLABLE → NOT NULL. Phase-1 audit confirmed
    #    zero existing nulls, so this is a definitional change with no
    #    data motion.
    op.execute(
        "ALTER TABLE language_word_embeddings "
        "ALTER COLUMN embedder_revision SET NOT NULL"
    )

    # 2. Drop the existing 2-column PK.
    op.execute(
        "ALTER TABLE language_word_embeddings "
        "DROP CONSTRAINT language_word_embeddings_pkey"
    )

    # 3. Add the 4-column PK. PostgreSQL builds the supporting UNIQUE
    #    index in-line; no separate CREATE INDEX needed for the PK itself.
    op.execute(
        "ALTER TABLE language_word_embeddings "
        "ADD CONSTRAINT language_word_embeddings_pkey "
        "PRIMARY KEY (language, word, embedder, embedder_revision)"
    )

    # 4. Compound supporting index for the new WHERE shape in
    #    find_cross_language_neighbours:
    #    WHERE language = :l AND embedder = :e AND embedder_revision = :r
    #    The PK's unique index leads with (language, word) so it doesn't
    #    help that query; this one does.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lwe_lang_embedder_revision "
        "ON language_word_embeddings (language, embedder, embedder_revision)"
    )


def downgrade() -> None:
    """Downgrade schema (destructive — see module docstring)."""
    op.execute("SET LOCAL statement_timeout = '60s'")

    op.execute("DROP INDEX IF EXISTS ix_lwe_lang_embedder_revision")

    # Drop new PK first so the next ADD PRIMARY KEY can claim the name.
    op.execute(
        "ALTER TABLE language_word_embeddings "
        "DROP CONSTRAINT language_word_embeddings_pkey"
    )

    # Without this DELETE, ADD PRIMARY KEY (language, word) fails on
    # duplicate keys whenever multiple embedders have a row for the same
    # surface form. We retain only the LaBSE/v1 partition to match the
    # pre-T2.3 state. Any other embedder rows are dropped.
    op.execute(
        "DELETE FROM language_word_embeddings "
        "WHERE NOT (embedder = 'sentence-transformers/LaBSE' "
        "          AND embedder_revision = 'v1')"
    )

    op.execute(
        "ALTER TABLE language_word_embeddings "
        "ADD CONSTRAINT language_word_embeddings_pkey "
        "PRIMARY KEY (language, word)"
    )

    op.execute(
        "ALTER TABLE language_word_embeddings "
        "ALTER COLUMN embedder_revision DROP NOT NULL"
    )
