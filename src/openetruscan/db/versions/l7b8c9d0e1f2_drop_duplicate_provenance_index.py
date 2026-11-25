"""drop the duplicate provenance_status index

Two identical btree indexes on ``inscriptions(provenance_status)`` existed
on production: ``ix_inscriptions_provenance_status`` from migration
a1f2c3d4e5f6, and ``idx_provenance`` from the library's own schema setup
(``core/corpus_sql.py``). The library now uses the alembic name, so this
drops the other one. Both statements are no-ops where the index is absent.

Revision ID: l7b8c9d0e1f2
Revises: k6a7b8c9d0e1
Create Date: 2026-11-25 02:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "l7b8c9d0e1f2"
down_revision: str | Sequence[str] | None = "k6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("idx_provenance", table_name="inscriptions", if_exists=True)


def downgrade() -> None:
    op.create_index("idx_provenance", "inscriptions", ["provenance_status"], if_not_exists=True)
