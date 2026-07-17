"""Import must survive a Postgres without PostGIS.

The dev stack (``docker-compose.dev.yml``) runs ``pgvector/pgvector:pg16``,
which has no PostGIS: ``Corpus._ensure_db()``'s spatial block rolls back and
the ``geom`` column is never created (no alembic migration creates it
either). ``add()``/``add_batch()`` used to reference ``geom`` unconditionally
— even the no-coordinates branch wrote NULL into it — so every import died
with ``UndefinedColumn``. These tests pin the degraded path: statements built
without the column, detection cached per connection, and an end-to-end import
against a real PostGIS-less Postgres.

Two halves:

* the unit half needs no database — it checks the SQL builders against the
  exact statements the pre-fix code produced (the geom-present path must stay
  byte-for-byte identical) and drives ``add()`` through a recording fake
  connection with the detection flag forced either way;
* the integration half follows ``test_migrations.py``: a scratch database on
  the ``DATABASE_URL`` server, bootstrapped with ``alembic upgrade head``
  exactly like the dev stack, then ``Corpus.connect(..., init_schema=True)``
  and a real import. CI's ``pgvector/pgvector:pg16`` service has no PostGIS,
  so the degraded path is what runs there; on a PostGIS-enabled server the
  test skips rather than asserting the wrong branch.
"""

from __future__ import annotations

import os
import uuid

import pytest

from openetruscan.core.corpus import (
    _COLUMNS,
    _batch_insert_sql,
    _single_insert_sql,
    Corpus,
    Inscription,
)

# ---------------------------------------------------------------------------
# Unit half — no database required
# ---------------------------------------------------------------------------


def _legacy_single_insert(has_coords: bool) -> str:
    """The statement ``Corpus.add`` built before column detection existed.

    Reconstructed verbatim from the pre-fix code so the geom-present path is
    pinned byte-for-byte: any drift in the refactored builder fails here.
    """
    cols = ", ".join(_COLUMNS)
    placeholders = ", ".join(["%s"] * len(_COLUMNS))
    conflict_updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLUMNS if c != "id")
    geom_insert = "ST_SetSRID(ST_MakePoint(%s, %s), 4326)" if has_coords else "NULL"
    return "\n".join(
        [
            "INSERT INTO inscriptions",
            f"({cols}, geom)",
            "VALUES",
            f"({placeholders}, {geom_insert})",
            "ON CONFLICT (id) DO UPDATE SET",
            conflict_updates + ",",
            "geom = EXCLUDED.geom,",
            "updated_at = NOW()",
        ]
    )


def _legacy_batch_insert() -> tuple[str, str]:
    """The (query, template) pair ``Corpus.add_batch`` built before the fix."""
    cols = ", ".join(_COLUMNS)
    conflict_updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLUMNS if c != "id")
    col_placeholders = ", ".join(["%s"] * len(_COLUMNS))
    template = (
        f"({col_placeholders}, "
        f"CASE WHEN %s IS NOT NULL AND %s IS NOT NULL "
        f"THEN ST_SetSRID(ST_MakePoint(%s, %s), 4326) "
        f"ELSE NULL END)"
    )
    query = (
        f"INSERT INTO inscriptions ({cols}, geom) VALUES %s "
        f"ON CONFLICT (id) DO UPDATE SET {conflict_updates}, "
        f"geom = EXCLUDED.geom, updated_at = NOW()"
    )
    return query, template


def test_single_insert_sql_with_geom_is_byte_identical_to_legacy():
    assert _single_insert_sql(has_geom=True, has_coords=True) == _legacy_single_insert(True)
    assert _single_insert_sql(has_geom=True, has_coords=False) == _legacy_single_insert(False)


def test_batch_insert_sql_with_geom_is_byte_identical_to_legacy():
    legacy_query, legacy_template = _legacy_batch_insert()
    query, template = _batch_insert_sql(has_geom=True)
    assert query == legacy_query
    assert template == legacy_template


def test_single_insert_sql_without_geom_never_mentions_the_column():
    for has_coords in (True, False):
        sql = _single_insert_sql(has_geom=False, has_coords=has_coords)
        assert "geom" not in sql
        assert sql.count("%s") == len(_COLUMNS)


def test_batch_insert_sql_without_geom_never_mentions_the_column():
    query, template = _batch_insert_sql(has_geom=False)
    assert "geom" not in query
    assert "geom" not in template
    assert template.count("%s") == len(_COLUMNS)


class _RecordingCursor:
    def __init__(self, conn: _RecordingConn) -> None:
        self._conn = conn

    def execute(self, sql, params=None):
        self._conn.executed.append((sql, params))

    def fetchone(self):
        return (self._conn.geom_count,)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _RecordingConn:
    """Just enough psycopg2-connection surface for Corpus.add / detection."""

    def __init__(self, geom_count: int) -> None:
        self.geom_count = geom_count
        self.executed: list[tuple[str, object]] = []
        self.commits = 0

    def cursor(self):
        return _RecordingCursor(self)

    def commit(self):
        self.commits += 1


def _corpus_with_conn(conn: _RecordingConn) -> Corpus:
    # __new__ skips psycopg2.connect; the fake stands in for the connection.
    corpus = Corpus.__new__(Corpus)
    corpus._conn = conn  # type: ignore[assignment]
    corpus._has_geom = None
    return corpus


def test_geom_detection_probes_pg_attribute_once_and_caches():
    conn = _RecordingConn(geom_count=1)
    corpus = _corpus_with_conn(conn)
    assert corpus._geom_available is True
    assert corpus._geom_available is True
    probes = [sql for sql, _ in conn.executed if "pg_attribute" in sql]
    assert len(probes) == 1


def test_geom_detection_false_when_column_missing():
    conn = _RecordingConn(geom_count=0)
    corpus = _corpus_with_conn(conn)
    assert corpus._geom_available is False


def test_add_without_geom_column_builds_geomless_insert():
    conn = _RecordingConn(geom_count=0)
    corpus = _corpus_with_conn(conn)
    corpus.add(
        Inscription(id="GEO_U1", raw_text="mi larθa", findspot_lat=42.36, findspot_lon=11.99)
    )
    sql, params = conn.executed[-1]
    assert sql.startswith("INSERT INTO inscriptions")
    assert "geom" not in sql
    assert isinstance(params, tuple) and len(params) == len(_COLUMNS)
    # Coordinates still persist through their plain columns.
    assert params[_COLUMNS.index("findspot_lat")] == 42.36
    assert params[_COLUMNS.index("findspot_lon")] == 11.99
    assert conn.commits == 1


def test_add_with_geom_column_keeps_spatial_insert():
    conn = _RecordingConn(geom_count=1)
    corpus = _corpus_with_conn(conn)
    corpus.add(
        Inscription(id="GEO_U2", raw_text="mi larθa", findspot_lat=42.36, findspot_lon=11.99)
    )
    sql, params = conn.executed[-1]
    assert sql == _legacy_single_insert(has_coords=True)
    # lon, lat appended for ST_MakePoint after the _COLUMNS tuple.
    assert isinstance(params, tuple) and len(params) == len(_COLUMNS) + 2
    assert params[-2:] == (11.99, 42.36)


# ---------------------------------------------------------------------------
# Integration half — real Postgres without PostGIS
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL", "")

requires_postgres_dsn = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"),
    reason="needs a Postgres DSN in DATABASE_URL (CI provides one; the "
    "container has pgvector but no PostGIS — exactly the dev stack)",
)


@pytest.fixture()
def scratch_db_url():
    """A freshly created, empty database on the same server; dropped after.

    Same isolation rationale as ``test_migrations.py``: the shared test
    database carries the ORM-created schema, and this test must start from
    the state the dev stack starts from — empty, then ``alembic upgrade
    head``.
    """
    from sqlalchemy import create_engine, text

    admin = create_engine(
        DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://"),
        isolation_level="AUTOCOMMIT",
    )
    name = f"geomless_{uuid.uuid4().hex[:12]}"
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
    old = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(cfg, "head")
    finally:
        if old is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old


@requires_postgres_dsn
def test_import_succeeds_on_postgres_without_postgis(scratch_db_url):
    """The dev-stack repro: alembic bootstrap, then import — must not raise.

    Before the fix this died on the first row with
    ``psycopg2.errors.UndefinedColumn: column "geom" of relation
    "inscriptions" does not exist``.
    """
    _upgrade_head(scratch_db_url)

    corpus = Corpus.connect(scratch_db_url, init_schema=True)
    try:
        if corpus._geom_available:
            pytest.skip("server has PostGIS; the degraded path cannot be exercised here")

        corpus.add(
            Inscription(id="GEO_ADD", raw_text="mi larθa", findspot_lat=42.36, findspot_lon=11.99)
        )
        inserted = corpus.add_batch(
            [
                Inscription(
                    id="GEO_B1", raw_text="mi aviles", findspot_lat=42.5, findspot_lon=11.5
                ),
                Inscription(id="GEO_B2", raw_text="mi velus"),  # no coordinates
            ]
        )
        assert inserted == 2

        # The ON CONFLICT clause changed too — the upsert path must survive.
        corpus.add(
            Inscription(
                id="GEO_ADD", raw_text="mi larθa spurina", findspot_lat=42.36, findspot_lon=11.99
            )
        )

        with corpus._conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM inscriptions")
            assert cur.fetchone()[0] == 3
            # Spatial geometry is skipped, plain coordinates are not.
            cur.execute(
                "SELECT findspot_lat, findspot_lon FROM inscriptions WHERE id = %s", ("GEO_ADD",)
            )
            assert cur.fetchone() == (42.36, 11.99)
            cur.execute("SELECT raw_text FROM inscriptions WHERE id = %s", ("GEO_ADD",))
            assert cur.fetchone()[0] == "mi larθa spurina"
    finally:
        corpus._conn.close()
