"""Single source of truth for `inscriptions.provenance_status` in pipeline scripts.

The four-tier vocabulary and the findspot-based assignment rule mirror the
definitive `a1f2c3d4e5f6_provenance_integrity` migration
(src/openetruscan/db/versions/a1f2c3d4e5f6_provenance_integrity.py), whose
CHECK constraint rejects every other value. The ingestion scripts used to
hardcode the pre-migration value 'verified', which that constraint prohibits.

Two tiers are deliberately never returned by the mapping below, for the same
reasons the migration's backfill never assigns them: `excavated` is a stronger
scholarly claim reserved for curatorial review of each record's bibliography,
and `unknown` marks records whose provenance has not been assessed — a script
that has the findspot field in hand has already assessed it.
"""

PROVENANCE_STATUSES = (
    "excavated",
    "acquired_documented",
    "acquired_undocumented",
    "unknown",
)


def provenance_status_for_findspot(findspot: str | None) -> str:
    """Map findspot evidence to a provenance tier, exactly as the migration backfill does.

    Mirrors the backfill CASE expression: a non-empty findspot means the spot
    is named in the source bibliography but the archaeological context is not
    recorded ('acquired_documented'); a missing or empty findspot means the
    context is unknown ('acquired_undocumented'). Like the SQL predicate
    (`findspot <> ''`), a whitespace-only string counts as a named findspot —
    trimming is the caller's job.
    """
    if findspot:  # mirrors: findspot IS NOT NULL AND findspot <> ''
        return "acquired_documented"
    return "acquired_undocumented"
