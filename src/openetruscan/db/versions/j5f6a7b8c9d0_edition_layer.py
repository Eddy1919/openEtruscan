"""edition layer: aliases, edition metadata, readings, images, coverage index, glosses

Adds the tables that let a scholar reach a record by the reference they
cite and read it as an edition rather than an aggregator row:

* ``inscription_aliases`` — CIE / ET / TLE / TM / CII / CIL / CIEP
  references that resolve to a record. Record IDs are not changed (the
  sitemap publishes them); aliases sit beside them.
* ``inscription_edition`` — one row per record: ET siglum and text class,
  the findspot resolved to a Pleiades place with a precision, the current
  location split out of the findspot string, editor and autopsy.
* ``inscription_readings`` — reading history, one row per edition.
* ``inscription_images`` — photographs, drawings, IIIF resources, each with
  a required licence and source.
* ``indexed_documents`` — known inscriptions the corpus does not hold,
  stored by reference only.
* ``lexicon_glosses`` — proposed meanings per form with confidence, source
  and adjudication status.

Nothing in ``inscriptions`` changes shape. Data comes from
``scripts/data_pipeline/build_edition_layer.py``.

Revision ID: j5f6a7b8c9d0
Revises: d9e0f1a2b3c4
Create Date: 2026-11-24 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "j5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d9e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _fk() -> sa.ForeignKey:
    return sa.ForeignKey("inscriptions.id", ondelete="CASCADE")


def upgrade() -> None:
    op.create_table(
        "inscription_aliases",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("inscription_id", sa.Text(), _fk(), nullable=False),
        sa.Column("scheme", sa.Text(), nullable=False),
        sa.Column("lookup_key", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("edition", sa.Text(), nullable=False, server_default=""),
        sa.Column("basis", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "basis IN ('own_id', 'concordance', 'ciep_cie_numbering', 'manual')",
            name=op.f("ck_inscription_aliases_basis"),
        ),
        sa.CheckConstraint(
            "confidence IN ('certain', 'high', 'probable', 'uncertain')",
            name=op.f("ck_inscription_aliases_confidence"),
        ),
    )
    op.create_index(
        "ix_inscription_aliases_inscription_id", "inscription_aliases", ["inscription_id"]
    )
    op.create_index("ix_inscription_aliases_lookup_key", "inscription_aliases", ["lookup_key"])
    op.create_index(
        "uq_inscription_aliases_record_key",
        "inscription_aliases",
        ["inscription_id", "lookup_key"],
        unique=True,
    )

    op.create_table(
        "inscription_edition",
        sa.Column("inscription_id", sa.Text(), _fk(), primary_key=True),
        sa.Column("rix_siglum", sa.Text(), nullable=True),
        sa.Column("rix_text_class", sa.Text(), nullable=True),
        sa.Column("rix_class_basis", sa.Text(), nullable=True),
        sa.Column("findspot_place", sa.Text(), nullable=True),
        sa.Column("findspot_precision", sa.Text(), nullable=True),
        sa.Column("findspot_basis", sa.Text(), nullable=True),
        sa.Column("findspot_source_text", sa.Text(), nullable=True),
        sa.Column("current_location", sa.Text(), nullable=True),
        sa.Column("editor", sa.Text(), nullable=True),
        sa.Column("autopsy", sa.Boolean(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
        ),
        sa.CheckConstraint(
            "findspot_precision IS NULL OR findspot_precision IN "
            "('site', 'city', 'territory', 'region')",
            name=op.f("ck_inscription_edition_findspot_precision"),
        ),
        sa.CheckConstraint(
            "rix_text_class IS NULL OR rix_text_class IN "
            "('0','1','2','3','4','5','6','7','8','9','S','G','N')",
            name=op.f("ck_inscription_edition_rix_text_class"),
        ),
    )
    op.create_index(
        "ix_inscription_edition_rix_text_class", "inscription_edition", ["rix_text_class"]
    )

    op.create_table(
        "inscription_readings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("inscription_id", sa.Text(), _fk(), nullable=False),
        sa.Column("reading", sa.Text(), nullable=False),
        sa.Column("edition", sa.Text(), nullable=False),
        sa.Column("editor", sa.Text(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("autopsy", sa.Boolean(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
        ),
    )
    op.create_index(
        "ix_inscription_readings_inscription_id", "inscription_readings", ["inscription_id"]
    )

    op.create_table(
        "inscription_images",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("inscription_id", sa.Text(), _fk(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("iiif_manifest", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("license", sa.Text(), nullable=False),
        sa.Column("rights_holder", sa.Text(), nullable=True),
        sa.Column("source_citation", sa.Text(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
        ),
        sa.CheckConstraint(
            "kind IN ('photo', 'drawing', 'squeeze', 'facsimile', 'iiif')",
            name=op.f("ck_inscription_images_kind"),
        ),
        sa.CheckConstraint(
            "url IS NOT NULL OR iiif_manifest IS NOT NULL",
            name=op.f("ck_inscription_images_has_target"),
        ),
    )
    op.create_index(
        "ix_inscription_images_inscription_id", "inscription_images", ["inscription_id"]
    )

    op.create_table(
        "indexed_documents",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("primary_ref", sa.Text(), nullable=False),
        sa.Column("refs", sa.Text(), nullable=False, server_default=""),
        sa.Column("trismegistos_id", sa.Text(), nullable=True),
        sa.Column("rix_siglum", sa.Text(), nullable=True),
        sa.Column("rix_text_class", sa.Text(), nullable=True),
        sa.Column("region_code", sa.Text(), nullable=True),
        sa.Column("findspot_place", sa.Text(), nullable=True),
        sa.Column("pleiades_id", sa.Text(), nullable=True),
        sa.Column("date_text", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_row", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
        ),
    )
    op.create_index("ix_indexed_documents_primary_ref", "indexed_documents", ["primary_ref"])
    op.create_index(
        "ix_indexed_documents_trismegistos_id", "indexed_documents", ["trismegistos_id"]
    )
    op.create_index("ix_indexed_documents_region_code", "indexed_documents", ["region_code"])

    op.create_table(
        "lexicon_glosses",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("form", sa.Text(), nullable=False),
        sa.Column("headword", sa.Text(), nullable=False),
        sa.Column("gloss_en", sa.Text(), nullable=False),
        sa.Column("latin", sa.Text(), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Text(), nullable=True),
        sa.Column("citation_primary", sa.Text(), nullable=True),
        sa.Column("citation_modern", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
    )
    op.create_index("ix_lexicon_glosses_form", "lexicon_glosses", ["form"])


def downgrade() -> None:
    op.drop_table("lexicon_glosses")
    op.drop_table("indexed_documents")
    op.drop_table("inscription_images")
    op.drop_table("inscription_readings")
    # build_edition_layer.py --clear-custody-findspots moved custody-only
    # findspot strings into findspot_source_text. Put them back before the
    # table goes, or they are lost. provenance_status is not reverted here;
    # the provenance_audits rows that run wrote hold the old values.
    op.execute(
        "UPDATE inscriptions SET findspot = e.findspot_source_text "
        "FROM inscription_edition e WHERE e.inscription_id = inscriptions.id "
        "AND e.findspot_source_text IS NOT NULL "
        "AND COALESCE(inscriptions.findspot, '') = ''"
    )
    op.drop_table("inscription_edition")
    op.drop_table("inscription_aliases")
