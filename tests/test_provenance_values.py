"""Unit tests for scripts/data_pipeline/provenance_values.py.

The helper is the pipeline-side mirror of the a1f2c3d4e5f6_provenance_integrity
migration: same four-tier vocabulary, same findspot-based backfill rule. These
tests pin the mapping semantics and load the migration module itself so the two
files cannot drift apart silently. Pure Python — no database, no docker.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


provenance_values = _load_module(
    REPO_ROOT / "scripts" / "data_pipeline" / "provenance_values.py",
    "provenance_values",
)
migration = _load_module(
    REPO_ROOT / "src" / "openetruscan" / "db" / "versions" / "a1f2c3d4e5f6_provenance_integrity.py",
    "provenance_integrity_migration",
)


def test_vocabulary_matches_migration():
    assert provenance_values.PROVENANCE_STATUSES == migration.PROVENANCE_KINDS


def test_named_findspot_is_acquired_documented():
    assert provenance_values.provenance_status_for_findspot("Tarquinia") == "acquired_documented"
    assert provenance_values.provenance_status_for_findspot("Clusii") == "acquired_documented"


def test_missing_findspot_is_acquired_undocumented():
    assert provenance_values.provenance_status_for_findspot(None) == "acquired_undocumented"
    assert provenance_values.provenance_status_for_findspot("") == "acquired_undocumented"


def test_whitespace_findspot_mirrors_sql_predicate():
    # The migration's CASE uses `findspot <> ''`, for which ' ' is non-empty.
    # The helper deliberately reproduces that; trimming is the caller's job.
    assert provenance_values.provenance_status_for_findspot(" ") == "acquired_documented"


def test_mapping_never_leaves_vocabulary_or_claims_reserved_tiers():
    for findspot in (None, "", " ", "Perusia", "unknown"):
        status = provenance_values.provenance_status_for_findspot(findspot)
        assert status in provenance_values.PROVENANCE_STATUSES
        # 'excavated' requires curatorial review; 'unknown' means untriaged.
        # The backfill rule assigns neither, and neither should the mirror.
        assert status not in ("excavated", "unknown")
