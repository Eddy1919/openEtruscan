"""Provenance integrity: tiered provenance_status with honest backfill.

Revision ID: a1f2c3d4e5f6
Revises: e0efc731addb
Create Date: 2026-05-01

Background
----------
Before this migration the corpus had a single `provenance_status` value
('verified') applied uniformly to all 6,633 rows, regardless of whether
the inscription's archaeological context was actually known. 65% of the
corpus had no findspot at all, yet was still labelled 'verified', which
conflated *editorial verification of the text* with *documented
archaeological provenance* — two very different scholarly claims.

This migration introduces a tiered vocabulary that follows current best
practice in the digital epigraphy and museum-studies literature
(notably Brodie 2006, Gerstenblith 2007, Fincham 2019, and the AIA
Code of Ethics on archaeological context). The four tiers are:

  - **excavated**            : recovered through documented stratigraphic
                               excavation, with at least a published find
                               context.
  - **acquired_documented**  : findspot is named in the source bibliography
                               but the archaeological context (stratum,
                               associated finds, excavator, date of
                               recovery) is not recorded. Includes most
                               19th-c. CIE entries and museum acquisitions
                               with collection records.
  - **acquired_undocumented**: no findspot is recorded. The text is
                               attested in the philological literature
                               but the archaeological context is unknown.
                               This is the "Discovery Vector / Unprovenanced"
                               case. ~65% of the current corpus.
  - **unknown**              : provenance has not been assessed. Reserved
                               for newly imported records that have not
                               been triaged yet.

The backfill rule for this migration is conservative:
  - rows with a non-empty `findspot` → **acquired_documented**
  - rows without `findspot`          → **acquired_undocumented**

`excavated` is intentionally NOT assigned by automatic heuristic. It is
a stronger scholarly claim that requires curatorial review of each
record's bibliography (e.g. tomb numbers, stratum references, excavator
publications). The frontend exposes a curatorial workflow for promoting
records into this tier.

A new `provenance_baseline` column on a future `data_sources` table is
left as follow-up — see ROADMAP.md ("per-source provenance metadata").

This migration also adds an index on `provenance_status` so the new
faceted `/search?provenance=…` filter and `/stats/provenance` aggregate
do not full-scan.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1f2c3d4e5f6"
down_revision: str | Sequence[str] | None = "e0efc731addb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PROVENANCE_KINDS = (
    "excavated",
    "acquired_documented",
    "acquired_undocumented",
    "unknown",
)


def upgrade() -> None:
    """Reify the provenance_status field and backfill from findspot evidence."""

    # 1. Drop any prior CHECK constraint on the column (best-effort; some envs
    #    have a generic constraint name, others have a model-derived one).
    if op.get_context().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                DO $$
                DECLARE c text;
                BEGIN
                  FOR c IN
                    SELECT conname FROM pg_constraint
                    WHERE conrelid = 'public.inscriptions'::regclass
                      AND conname ILIKE '%provenance_status%'
                  LOOP
                    EXECUTE format('ALTER TABLE inscriptions DROP CONSTRAINT %I', c);
                  END LOOP;
                END $$;
                """
            )
        )

    # 2. Backfill. We do this in a single UPDATE: rows with a non-empty findspot
    #    move to 'acquired_documented'; rows without move to
    #    'acquired_undocumented'. Anything that does not match either branch
    #    (none should, but defensive) becomes 'unknown'.
    op.execute(
        sa.text(
            """
            UPDATE inscriptions
            SET provenance_status = CASE
                WHEN findspot IS NOT NULL AND findspot <> '' THEN 'acquired_documented'
                WHEN findspot IS NULL OR findspot = ''        THEN 'acquired_undocumented'
                ELSE 'unknown'
            END
            """
        )
    )

    # 3. Reaffirm the column NOT NULL (it already is per models.py, but the
    #    backfill should have left no nulls — assert that explicitly so the
    #    migration fails loudly if a row sneaked through).
    if op.get_context().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                DO $$
                BEGIN
                  IF EXISTS (SELECT 1 FROM inscriptions WHERE provenance_status IS NULL) THEN
                    RAISE EXCEPTION 'provenance_status is null on at least one row after backfill';
                  END IF;
                END $$;
                """
            )
        )


    # 4. Add a CHECK constraint with the new vocabulary. Use a dedicated name
    #    so future migrations can find and modify it.
    op.create_check_constraint(
        "ck_inscriptions_provenance_status_tiered",
        "inscriptions",
        "provenance_status IN ('excavated', 'acquired_documented', "
        "'acquired_undocumented', 'unknown')",
    )

    # 5. Set a sane default for new rows.
    op.alter_column(
        "inscriptions",
        "provenance_status",
        server_default=sa.text("'unknown'"),
    )

    # 6. Index it. The new /search?provenance=… and /stats/provenance endpoints
    #    will scan by this column.
    op.create_index(
        "ix_inscriptions_provenance_status",
        "inscriptions",
        ["provenance_status"],
        if_not_exists=True,
    )


def downgrade() -> None:
    """Revert to the single-value 'verified' column."""
    op.drop_index("ix_inscriptions_provenance_status", table_name="inscriptions", if_exists=True)
    op.drop_constraint(
        "ck_inscriptions_provenance_status_tiered",
        "inscriptions",
        type_="check",
    )
    op.execute(sa.text("UPDATE inscriptions SET provenance_status = 'verified'"))
    op.alter_column(
        "inscriptions",
        "provenance_status",
        server_default=sa.text("'verified'"),
    )
