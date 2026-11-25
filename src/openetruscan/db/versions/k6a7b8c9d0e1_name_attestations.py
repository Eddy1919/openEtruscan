"""name index: one row per personal name in an inscription

The Name Index read ``entities``, which held whatever a formula parser
returned for a whole text, so a "name" could be an entire inscription.
``name_attestations`` holds single words: praenomina, read from
``reference/praenomina.csv``, and the family name that follows each one,
with the basis and confidence of each reading. The site reads it through
the frontend's ``/api/names/network`` route (openEtruscan-frontend); this
API's ``/names/network`` endpoint is unchanged. ``entities`` is left alone:
the lineage tables join on it.

Data comes from ``scripts/data_pipeline/build_name_index.py``.

Revision ID: k6a7b8c9d0e1
Revises: j5f6a7b8c9d0
Create Date: 2026-11-25 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "j5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "name_attestations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "inscription_id",
            sa.Text(),
            sa.ForeignKey("inscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("form", sa.Text(), nullable=False),
        sa.Column("lemma", sa.Text(), nullable=False),
        sa.Column("name_type", sa.Text(), nullable=False),
        sa.Column("gender", sa.Text(), nullable=True),
        sa.Column("basis", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "name_type IN ('praenomen', 'gentilicium')",
            name=op.f("ck_name_attestations_name_type"),
        ),
        sa.CheckConstraint(
            "gender IS NULL OR gender IN ('m', 'f')",
            name=op.f("ck_name_attestations_gender"),
        ),
        sa.CheckConstraint(
            "basis IN ('praenomen_list', 'praenomen_abbreviation', 'follows_praenomen')",
            name=op.f("ck_name_attestations_basis"),
        ),
        sa.CheckConstraint(
            "confidence IN ('high', 'probable')",
            name=op.f("ck_name_attestations_confidence"),
        ),
    )
    op.create_index("ix_name_attestations_inscription_id", "name_attestations", ["inscription_id"])
    op.create_index("ix_name_attestations_lemma", "name_attestations", ["lemma"])
    op.create_index(
        "uq_name_attestations_record_position",
        "name_attestations",
        ["inscription_id", "position"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("name_attestations")
