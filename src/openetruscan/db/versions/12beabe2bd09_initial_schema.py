"""initial_schema

Revision ID: 12beabe2bd09
Revises: 
Create Date: 2026-04-04 12:28:05.199232

"""
from collections.abc import Sequence



# revision identifiers, used by Alembic.
revision: str = '12beabe2bd09'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
