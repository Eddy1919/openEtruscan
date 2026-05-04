"""add_archaeogenetics_hardening_fields

Revision ID: a6d56926ff21
Revises: i4d5e6f7a8b9
Create Date: 2026-05-04 11:30:31.477497

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6d56926ff21'
down_revision: str | Sequence[str] | None = 'i4d5e6f7a8b9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('genetic_samples', sa.Column('tomb_id', sa.Text(), nullable=True))
    op.add_column('genetic_samples', sa.Column('context_detail', sa.Text(), nullable=True))
    op.add_column('genetic_samples', sa.Column('ancestry_components', sa.Text(), nullable=True))
    op.create_index(op.f('ix_genetic_samples_tomb_id'), 'genetic_samples', ['tomb_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_genetic_samples_tomb_id'), table_name='genetic_samples')
    op.drop_column('genetic_samples', 'ancestry_components')
    op.drop_column('genetic_samples', 'context_detail')
    op.drop_column('genetic_samples', 'tomb_id')
