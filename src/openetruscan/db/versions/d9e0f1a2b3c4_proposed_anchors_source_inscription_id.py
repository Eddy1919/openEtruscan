"""proposed_anchors: source_inscription_id

Add an optional `source_inscription_id` column to ``proposed_anchors``
so a community submission can carry the corpus identifier of the
inscription the submitter was reading when they proposed the gloss.

Motivation (see research/notes/community-curation-design.md):
    The ``ProposeCard`` chip-row on the frontend's inscription detail
    page deep-links into ``/propose/<word>?from=<id>``. Previously the
    ``?from=`` was only echoed in the source-citation textarea — useful
    UX, but not a structured field reviewers could query against. With
    this column the editorial dashboard can show "5 proposals derived
    from ETR_001" and corpus-level analytics can attribute submissions
    to specific inscriptions.

Design choices, briefly:

  * **Nullable.** A submitter typing /propose/aesar by hand has no
    inscription context. The column must be optional.

  * **No FK to ``inscriptions.id``.** Corpus IDs are namespaced (ET,
    TLE, ETR_*) and some external references won't have a row in the
    inscriptions table at the moment the proposal is filed. We accept
    the loose coupling for now; if it becomes a problem we can ALTER
    in a follow-up.

  * **CHECK length 1–64.** Real IDs land between 3 and ~30 characters;
    64 is a comfortable ceiling that still rules out paste-bombs.
    Empty string is rejected so the column stays meaningful — a blank
    `?from=` must become NULL, not "".

  * **No index.** Query pattern is the editorial dashboard's "filter
    by inscription"; cardinality is bounded by total submissions
    (small), so a sequential scan is fine. Add the index when N grows.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-05-11 14:55:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: str | Sequence[str] | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "proposed_anchors",
        sa.Column("source_inscription_id", sa.Text(), nullable=True),
    )
    # See models.py for the rationale on `length()` over `char_length()`.
    op.create_check_constraint(
        "ck_proposed_anchors_source_inscription_id_shape",
        "proposed_anchors",
        "source_inscription_id IS NULL OR (length(source_inscription_id) BETWEEN 1 AND 64)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_proposed_anchors_source_inscription_id_shape",
        "proposed_anchors",
        type_="check",
    )
    op.drop_column("proposed_anchors", "source_inscription_id")
