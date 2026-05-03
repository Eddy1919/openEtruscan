"""Add zotero_id to inscriptions
 
 Revision ID: f1a2b3c4d5e6
 Revises: d4a5b6c7e8f9
 Create Date: 2026-05-03
 
 """
 
 from collections.abc import Sequence
 
 from alembic import op
 import sqlalchemy as sa
 
 revision: str = "f1a2b3c4d5e6"
 down_revision: str | Sequence[str] | None = "d4a5b6c7e8f9"
 branch_labels: str | Sequence[str] | None = None
 depends_on: str | Sequence[str] | None = None
 
 
 def upgrade() -> None:
     op.add_column("inscriptions", sa.Column("zotero_id", sa.Text(), nullable=True))
 
 
 def downgrade() -> None:
     op.drop_column("inscriptions", "zotero_id")
