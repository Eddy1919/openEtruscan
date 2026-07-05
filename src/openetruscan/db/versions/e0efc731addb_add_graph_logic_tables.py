"""Add graph logic tables

Revision ID: e0efc731addb
Revises: 12beabe2bd09
Create Date: 2026-04-04 16:20:59.057716

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e0efc731addb"
down_revision: str | Sequence[str] | None = "12beabe2bd09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "clans",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), server_default="", nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "entities",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("inscription_id", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), server_default="", nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True
        ),
        sa.ForeignKeyConstraint(["inscription_id"], ["inscriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entities_inscription_id", "entities", ["inscription_id"], unique=False)

    op.create_table(
        "relationships",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("person_id", sa.Text(), nullable=True),
        sa.Column("related_person_id", sa.Text(), nullable=True),
        sa.Column("clan_id", sa.Text(), nullable=True),
        sa.Column("relationship_type", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True
        ),
        sa.CheckConstraint(
            "(related_person_id IS NOT NULL AND clan_id IS NULL) OR (clan_id IS NOT NULL AND related_person_id IS NULL)",
            name="check_relationship_target",
        ),
        sa.ForeignKeyConstraint(["clan_id"], ["clans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["related_person_id"], ["entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_relationships_clan_id", "relationships", ["clan_id"], unique=False)
    op.create_index("ix_relationships_person_id", "relationships", ["person_id"], unique=False)
    op.create_index(
        "ix_relationships_related_person_id", "relationships", ["related_person_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_relationships_related_person_id", table_name="relationships")
    op.drop_index("ix_relationships_person_id", table_name="relationships")
    op.drop_index("ix_relationships_clan_id", table_name="relationships")
    op.drop_table("relationships")

    op.drop_index("ix_entities_inscription_id", table_name="entities")
    op.drop_table("entities")

    op.drop_table("clans")
