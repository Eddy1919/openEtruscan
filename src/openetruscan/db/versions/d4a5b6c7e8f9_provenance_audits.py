"""Provenance audit log for curatorial promotions.

Revision ID: d4a5b6c7e8f9
Revises: c3f4d5e6a7b8
Create Date: 2026-05-02

A small table that records every change to ``inscriptions.provenance_status``
made by a curator. The interesting transition is
``acquired_documented → excavated``: that is the only tier the system never
assigns by heuristic, so the audit row is the chain-of-evidence behind the
upgrade — who reviewed it, when, against which bibliography.

The table is intentionally append-only at the model layer; deletes happen via
the FK ``ON DELETE CASCADE`` if the parent inscription itself is removed.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d4a5b6c7e8f9"
down_revision: str | Sequence[str] | None = "c3f4d5e6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS provenance_audits (
                id SERIAL PRIMARY KEY,
                inscription_id TEXT NOT NULL
                    REFERENCES inscriptions(id) ON DELETE CASCADE,
                old_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                notes TEXT,
                created_by TEXT NOT NULL DEFAULT 'system',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_provenance_audits_inscription_id "
            "ON provenance_audits(inscription_id)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_provenance_audits_inscription_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS provenance_audits"))
