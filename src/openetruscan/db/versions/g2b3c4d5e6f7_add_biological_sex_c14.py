"""add biological_sex and c14_date_range to genetic_samples

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-05-03

"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "g2b3c4d5e6f7"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("genetic_samples", sa.Column("biological_sex", sa.Text(), nullable=True))
    op.add_column("genetic_samples", sa.Column("c14_date_range", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("genetic_samples", "c14_date_range")
    op.drop_column("genetic_samples", "biological_sex")
