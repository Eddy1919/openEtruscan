"""Add source_code / source_detail / original_script_entry columns.

Revision ID: b2e3d4f5a6b7
Revises: a1f2c3d4e5f6
Create Date: 2026-05-01

Background
----------
The Inscription SQLAlchemy model in `db/models.py` has declared three columns
since 2026-04 — `source_code`, `source_detail`, `original_script_entry` —
that were never present in the production database. While the broken
auto-deploy (#8) was masking new code from reaching prod, the model/database
mismatch was invisible. As soon as the new code finally deployed (after
fixing the deploy in #8 and merging #9 with the SELECT-* projection cleanup),
every async `select(Inscription)` blew up with

    asyncpg.exceptions.UndefinedColumnError:
    column inscriptions.source_code does not exist

This migration adds the three columns so the model and the database agree.
The columns are added on a populated table; existing rows get sensible
defaults (`source_code = 'unknown'`, the others NULL).

The columns were added via direct ALTER TABLE on prod the moment the deploy
broke — this migration captures that change in source so any environment
rebuilt from `alembic upgrade head` ends up in the same state.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2e3d4f5a6b7"
down_revision: str | Sequence[str] | None = "a1f2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the three source-metadata columns (idempotent for prod re-application)."""
    op.execute(
        sa.text(
            "ALTER TABLE inscriptions "
            "ADD COLUMN IF NOT EXISTS source_code TEXT NOT NULL DEFAULT 'unknown'"
        )
    )
    op.execute(
        sa.text("ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS source_detail TEXT")
    )
    op.execute(
        sa.text(
            "ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS original_script_entry TEXT"
        )
    )


def downgrade() -> None:
    """Drop the three columns. Destructive — review before running in prod."""
    op.drop_column("inscriptions", "original_script_entry")
    op.drop_column("inscriptions", "source_detail")
    op.drop_column("inscriptions", "source_code")
