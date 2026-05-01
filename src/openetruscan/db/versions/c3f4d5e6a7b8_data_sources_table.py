"""Per-source provenance metadata: data_sources table.

Revision ID: c3f4d5e6a7b8
Revises: b2e3d4f5a6b7
Create Date: 2026-05-01

Background
----------
The ``inscriptions.source`` column is a denormalised display string. Rows that
share a source string ("Larth (Vico & Spanakis, 2023)" — 4,712 rows; the
CIE Vol I extractions — 1,905 rows) all carry it independently, with no
canonical record of:

  - the **citation** in a stable scholarly form,
  - the **license** under which the records may be redistributed,
  - the **provenance baseline** of the upstream collection (does the source
    typically inherit unprovenanced material? does it require curatorial
    review?),
  - **when** the corpus was retrieved.

This migration introduces a small ``data_sources`` reference table so each
inscription can point at one row and the API can disclose the source's
provenance baseline alongside the per-row provenance status from
``a1f2c3d4e5f6_provenance_integrity``.

Design choices
~~~~~~~~~~~~~~
1. ``data_sources.id`` is a short SLUG (e.g. ``larth-2023``,
   ``cie-vol-i``) so URLs and JSON-LD are stable.
2. ``inscriptions.source_id`` is added as a nullable FK so existing rows
   are not broken; the denormalised string column ``source`` is kept for
   backward compatibility (for now).
3. ``provenance_baseline`` mirrors the per-row vocabulary
   (``excavated``/``acquired_documented``/``acquired_undocumented``/``unknown``).
   This is the *typical* tier for the source — a hint, not a hard claim.
4. The table is seeded with the two known live sources so the API can
   resolve them immediately. Backfilling ``inscriptions.source_id`` from
   the textual ``source`` field is done in the same migration via a
   small CASE expression.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3f4d5e6a7b8"
down_revision: str | Sequence[str] | None = "b2e3d4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create data_sources, seed the two live sources, and link inscriptions.source_id."""

    op.create_table(
        "data_sources",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("citation", sa.Text(), nullable=False),
        sa.Column("license", sa.Text(), nullable=False, server_default="unknown"),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column(
            "provenance_baseline",
            sa.Text(),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("retrieved_at", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provenance_baseline IN ('excavated','acquired_documented',"
            "'acquired_undocumented','unknown')",
            name="ck_data_sources_provenance_baseline",
        ),
    )

    # Seed the two sources we have rows for. Provenance baselines reflect what is
    # known about the upstream corpus, not a per-row claim — see README and
    # ROADMAP "per-source provenance metadata".
    op.execute(
        sa.text(
            """
            INSERT INTO data_sources
              (id, display_name, citation, license, url, provenance_baseline, retrieved_at)
            VALUES
              ('larth-2023',
               'Larth Dataset',
               'Vico, F. & Spanakis, G. (2023). Larth: an Etruscan Inscriptions Dataset. arXiv:2310.06065.',
               'CC-BY-4.0',
               'https://huggingface.co/datasets/Eddy1919/larth',
               'acquired_undocumented',
               '2024-04-01'),
              ('cie-vol-i',
               'Corpus Inscriptionum Etruscarum, Volume I',
               'Pauli, C. (ed.) (1893–). Corpus Inscriptionum Etruscarum, Vol. I (Clusium fascicles). Leipzig.',
               'public-domain',
               'https://archive.org/details/corpusinscriptio01paulgoog',
               'acquired_documented',
               '2024-04-01')
            ON CONFLICT (id) DO NOTHING
            """
        )
    )

    # Add the FK column. Idempotent guard for re-runs.
    op.execute(
        sa.text(
            """
            ALTER TABLE inscriptions
              ADD COLUMN IF NOT EXISTS source_id TEXT
              REFERENCES data_sources(id) ON DELETE SET NULL
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_inscriptions_source_id "
            "ON inscriptions(source_id)"
        )
    )

    # Backfill source_id from the textual `source` field.
    op.execute(
        sa.text(
            """
            UPDATE inscriptions
            SET source_id = CASE
                WHEN source ILIKE '%Larth%Vico%Spanakis%' OR source = 'Larth (Vico & Spanakis, 2023)'
                  THEN 'larth-2023'
                WHEN source ILIKE 'CIE %Vol%I%' OR source ILIKE '%CIE Vol I%'
                  OR source ILIKE 'CIE Volume I%'
                  THEN 'cie-vol-i'
                ELSE NULL
            END
            WHERE source_id IS NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_inscriptions_source_id"))
    op.execute(sa.text("ALTER TABLE inscriptions DROP COLUMN IF EXISTS source_id"))
    op.drop_table("data_sources")
