"""Widen fts_canonical to include findspot, source, notes, and cross-corpus IDs.

Revision ID: e7c8d9e0f1a2
Revises: d4a5b6c7e8f9
Create Date: 2026-05-03

Background
----------
The eval harness landed in commit 134c6ea exposed a real product gap: the
``fts_canonical`` column only indexes ``canonical`` text, so a search for a
place name like "Tarquinia" returns 0 rows from ``/search/hybrid`` even
though 47 rows have ``findspot = 'Tarquinia'``. NDCG@10 against the
Pelagios- and Trismegistos-grounded gold sets all scored 0.

This migration rebuilds the generated tsvector to include every field a
user can reasonably expect to find by free-text search, with weighted
ranks so canonical text still dominates retrieval relevance:

  weight A — canonical (the inscription text itself, primary signal)
  weight B — findspot, pleiades_id, geonames_id, trismegistos_id, eagle_id
             (place + cross-corpus identifiers; semantic anchors)
  weight C — source, source_detail, bibliography, notes, raw_text
             (bibliographic and editorial context)

Why STORED + GENERATED rather than a trigger
--------------------------------------------
* No write path needs to remember to update the tsvector — the generated
  column does it on every INSERT/UPDATE automatically.
* PostgreSQL planners use the GIN index on the generated column, same as
  a hand-rolled trigger-maintained one. No query-time cost.

Why drop-and-recreate
---------------------
``GENERATED ALWAYS AS … STORED`` columns cannot be ``ALTER`` ed. We must
drop the column and the GIN index, then add them back with the new
expression. On 6,633 rows this takes <1 s and the deploy workflow runs it
inside the alembic step *before* container rotation, so /search/hybrid is
unaffected during the brief window when the index is absent (the old
container is still serving the old column).

After this migration, the eval categories that depend on structured
metadata (place_pleiades, place_findspot, chronology, cross_corpus) should
go from 0.0 to a measurable signal. Once verified, the default gate in
``evals/run_search_eval.py`` is tightened to enforce them.
"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e7c8d9e0f1a2"
down_revision: str | Sequence[str] | None = "d4a5b6c7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Single source of truth for the widened expression. Used by upgrade(), and
# kept in sync with the schema-bootstrap DDL in ``core/corpus.py``.
WIDENED_FTS_EXPR = """
setweight(to_tsvector('simple', coalesce(canonical, '')), 'A') ||
setweight(to_tsvector('simple',
    coalesce(findspot, '') || ' ' ||
    coalesce(pleiades_id, '') || ' ' ||
    coalesce(geonames_id, '') || ' ' ||
    coalesce(trismegistos_id, '') || ' ' ||
    coalesce(eagle_id, '')
), 'B') ||
setweight(to_tsvector('simple',
    coalesce(source, '') || ' ' ||
    coalesce(source_detail, '') || ' ' ||
    coalesce(bibliography, '') || ' ' ||
    coalesce(notes, '') || ' ' ||
    coalesce(raw_text, '')
), 'C')
""".strip()


def upgrade() -> None:
    """Drop the canonical-only tsvector and rebuild it with the wider document."""
    op.execute("DROP INDEX IF EXISTS idx_fts_canonical")
    op.execute("ALTER TABLE inscriptions DROP COLUMN IF EXISTS fts_canonical")
    op.execute(
        f"""
        ALTER TABLE inscriptions
        ADD COLUMN fts_canonical tsvector
        GENERATED ALWAYS AS ({WIDENED_FTS_EXPR}) STORED
        """
    )
    op.execute(
        "CREATE INDEX idx_fts_canonical ON inscriptions USING GIN (fts_canonical)"
    )


def downgrade() -> None:
    """Restore the canonical-only generated column."""
    op.execute("DROP INDEX IF EXISTS idx_fts_canonical")
    op.execute("ALTER TABLE inscriptions DROP COLUMN IF EXISTS fts_canonical")
    op.execute(
        """
        ALTER TABLE inscriptions
        ADD COLUMN fts_canonical tsvector
        GENERATED ALWAYS AS (to_tsvector('simple', coalesce(canonical, ''))) STORED
        """
    )
    op.execute(
        "CREATE INDEX idx_fts_canonical ON inscriptions USING GIN (fts_canonical)"
    )
