"""proposed_anchors

Add the `proposed_anchors` table for the WBS P4 Option C
community-curation pivot. Each row is a candidate Etruscan↔Latin/Greek
gloss equivalence submitted via `POST /anchors/propose`, sitting in a
moderation queue until an admin approves / rejects / marks-duplicate.

Schema (matches the design doc at research/notes/community-curation-design.md):

  - id                  bigserial PK
  - etruscan_word       text NOT NULL
  - equivalent          text NOT NULL
  - equivalent_language text NOT NULL CHECK lat|grc
  - evidence_quote      text NOT NULL
  - source              text NOT NULL
  - submitter_email     text NOT NULL
  - submitter_orcid     text (optional, trust signal)
  - status              text NOT NULL CHECK pending|approved|rejected|duplicate
  - reviewer            text (admin email after action)
  - review_note         text
  - reviewed_at         timestamptz
  - created_at          timestamptz DEFAULT now()

Two indexes:
  - (status, created_at DESC) for the queue listing path.
  - (etruscan_word) for the inscription-page lookup path.

No data migration; new table only.

Revision ID: c8d9e0f1a2b3
Revises: b7e6f7a8b9c1
Create Date: 2026-05-11 14:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: str | Sequence[str] | None = "b7e6f7a8b9c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "proposed_anchors",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("etruscan_word", sa.Text, nullable=False),
        sa.Column("equivalent", sa.Text, nullable=False),
        sa.Column(
            "equivalent_language",
            sa.Text,
            nullable=False,
        ),
        sa.Column("evidence_quote", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("submitter_email", sa.Text, nullable=False),
        sa.Column("submitter_orcid", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.Text,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("reviewer", sa.Text, nullable=True),
        sa.Column("review_note", sa.Text, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "equivalent_language IN ('lat', 'grc')",
            name="ck_proposed_anchors_equivalent_language",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'duplicate')",
            name="ck_proposed_anchors_status",
        ),
        # `length()` (not `char_length()`) so the constraint emits on both
        # Postgres and SQLite — the test fallback uses SQLite, which has no
        # `char_length`. For text values both functions are equivalent.
        sa.CheckConstraint(
            "length(evidence_quote) >= 10",
            name="ck_proposed_anchors_evidence_quote_min_length",
        ),
        sa.CheckConstraint(
            "length(source) >= 3",
            name="ck_proposed_anchors_source_min_length",
        ),
    )
    # Index for the admin queue listing: pending rows first, oldest first.
    op.create_index(
        "ix_proposed_anchors_status_created",
        "proposed_anchors",
        ["status", "created_at"],
    )
    # Index for the inscription-page lookup path.
    op.create_index(
        "ix_proposed_anchors_etr_word",
        "proposed_anchors",
        ["etruscan_word"],
    )


def downgrade() -> None:
    op.drop_index("ix_proposed_anchors_etr_word", table_name="proposed_anchors")
    op.drop_index("ix_proposed_anchors_status_created", table_name="proposed_anchors")
    op.drop_table("proposed_anchors")
