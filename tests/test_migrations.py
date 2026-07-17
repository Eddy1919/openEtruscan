"""Exercise the Alembic migration chain against a real Postgres.

conftest.py builds the test schema with ``Base.metadata.create_all`` for
speed, which means the 17 hand-written migration scripts under
``db/versions/`` were never executed by any test — ORM-vs-migration drift
could ship silently. This module runs the full ``upgrade head`` chain on a
scratch database and cross-checks the resulting tables against the ORM
metadata.

The chain tests are Postgres-only: several migrations use pgvector/PostGIS
column types that SQLite cannot represent. The scratch database is created
and dropped per test run so the chain always starts from an empty schema,
independent of whatever state the shared test database is in. The
misconfiguration test needs no database at all — env.py fails before
connecting.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

DATABASE_URL = os.environ.get("DATABASE_URL", "")

requires_postgres = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"),
    reason="migration chain requires Postgres (pgvector column types)",
)


@pytest.fixture()
def scratch_db_url():
    """A freshly created, empty database on the same server; dropped after."""
    admin = create_engine(
        DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://"),
        isolation_level="AUTOCOMMIT",
    )
    name = f"migrations_{uuid.uuid4().hex[:12]}"
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    base, _, _ = DATABASE_URL.rpartition("/")
    url = f"{base}/{name}".replace("postgresql+asyncpg://", "postgresql://")
    try:
        yield url
    finally:
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :n AND pid <> pg_backend_pid()"
                ),
                {"n": name},
            )
            conn.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()


def _upgrade_head(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    # env.py prefers DATABASE_URL from the environment; point it at the
    # scratch database for the duration of the upgrade.
    old = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(cfg, "head")
    finally:
        if old is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old


@requires_postgres
def test_upgrade_head_from_empty(scratch_db_url):
    """The full chain applies cleanly to an empty database."""
    _upgrade_head(scratch_db_url)
    eng = create_engine(scratch_db_url)
    try:
        tables = set(inspect(eng).get_table_names())
    finally:
        eng.dispose()
    assert "alembic_version" in tables
    assert "inscriptions" in tables


@requires_postgres
def test_migrations_cover_orm_tables(scratch_db_url):
    """Every ORM-mapped table must exist after `upgrade head`.

    A table present in models.py but absent from the migration chain means a
    fresh production deploy (which runs alembic, not create_all) would be
    missing it — the classic drift this test exists to catch.
    """
    from openetruscan.db.models import Base

    _upgrade_head(scratch_db_url)
    eng = create_engine(scratch_db_url)
    try:
        migrated = set(inspect(eng).get_table_names())
    finally:
        eng.dispose()
    orm_tables = set(Base.metadata.tables)
    missing = orm_tables - migrated
    assert not missing, (
        f"ORM tables missing from the migration chain: {sorted(missing)} — "
        f"add a migration or the next alembic-based deploy diverges from the ORM"
    )


def test_online_migration_without_database_url_fails_clearly(monkeypatch):
    """With neither DATABASE_URL nor sqlalchemy.url set, env.py must raise a
    clear RuntimeError instead of handing None to create_async_engine (which
    used to surface as an opaque SQLAlchemy error). No database is needed:
    the check fires before any connection attempt."""
    from alembic import command
    from alembic.config import Config

    monkeypatch.delenv("DATABASE_URL", raising=False)
    cfg = Config()  # no ini file, so there is no sqlalchemy.url fallback
    cfg.set_main_option(
        "script_location", str(Path(__file__).resolve().parent.parent / "src/openetruscan/db")
    )
    with pytest.raises(RuntimeError, match="No database URL configured"):
        command.upgrade(cfg, "head")
