"""Pytest fixtures shared across the suite.

The default test backend used to be ``sqlite+aiosqlite:///:memory:``, which
silently bypassed every PostGIS, pgvector, and FTS feature the production code
depends on. Tests passed; prod surprises followed (see ROADMAP.md).

This module provides a real-Postgres fixture with three modes, in priority
order:

1. **CI / explicit DSN** — if ``DATABASE_URL`` is set to a Postgres URL we use
   it directly. This is the path GitHub Actions takes (the ``services:`` block
   in ``.github/workflows/ci.yml`` boots a Postgres + pgvector container).

2. **Local testcontainer** — if ``DATABASE_URL`` is unset and the
   ``testcontainers`` package is installed, we spin a one-shot
   ``pgvector/pgvector:pg16`` container per test session and tear it down at
   the end. Engineers don't need to run ``docker run`` themselves.

3. **SQLite fallback** — only when neither (1) nor (2) applies, fall back to
   SQLite. Tests that exercise PostGIS / pgvector / FTS are marked with
   ``pytest.mark.requires_postgres`` and are skipped here.

The chosen URL is exported as ``OE_TEST_DATABASE_URL`` and the
``Base.metadata.create_all`` is run against it once per session. Per-test
isolation is delivered by truncating user tables in ``db_session``.
"""

from __future__ import annotations

import os

# Force test environment BEFORE any openetruscan import. settings() captures
# os.environ at first import, so anything set later (e.g. inside an individual
# test module) is too late and CORS / docs / debug toggles end up wrong.
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("ENABLE_DOCS", "1")

import socket  # noqa: E402
import time  # noqa: E402
from collections.abc import AsyncGenerator, Generator  # noqa: E402
from contextlib import suppress  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


_USER_TABLES = (
    # Order matters for FK cascade — children first.
    "relationships",
    "entities",
    "clans",
    "genetic_samples",
    "inscriptions",
    "data_sources",
    "provenance_audits",
    "language_word_embeddings",
)


def _is_postgres_url(url: str | None) -> bool:
    return bool(url) and url.startswith(("postgres://", "postgresql://", "postgresql+asyncpg://"))


def _to_async_url(url: str) -> str:
    """Normalise a sync DSN to the asyncpg driver."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def _wait_for_port(host: str, port: int, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        with suppress(OSError), socket.create_connection((host, port), timeout=1.0):
            return
        time.sleep(0.5)
    raise TimeoutError(f"Postgres at {host}:{port} did not accept connections within {timeout_s}s")


@pytest.fixture(scope="session")
def database_url() -> Generator[str, None, None]:
    """Resolve the DSN for the test session, booting a testcontainer if needed."""

    explicit = os.environ.get("DATABASE_URL")
    if _is_postgres_url(explicit):
        # CI path: Postgres container already up via `services:`.
        yield _to_async_url(explicit)
        return

    # Local path: try testcontainers. Skip silently if the package is missing
    # so the SQLite fallback can take over.
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        # No testcontainers — leave it to the SQLite fallback.
        yield "sqlite+aiosqlite:///:memory:"
        return

    # `pgvector/pgvector:pg16` ships pgvector. PostGIS is NOT in this image,
    # so tests that need PostGIS still need a manual setup or a dedicated
    # image — see `requires_postgis` marker.
    container = PostgresContainer("pgvector/pgvector:pg16")
    container.start()
    try:
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(5432))
        _wait_for_port(host, port)
        url = (
            f"postgresql+asyncpg://{container.username}:{container.password}"
            f"@{host}:{port}/{container.dbname}"
        )
        yield url
    finally:
        container.stop()


@pytest.fixture(scope="session")
def has_pgvector(database_url: str) -> bool:
    """True when the test backend supports pgvector."""
    # SQLite fallback obviously does not.
    if database_url.startswith("sqlite"):
        return False
    return True


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine(database_url: str) -> AsyncGenerator[Any, None]:
    """One async engine per test session."""

    eng = create_async_engine(database_url, future=True)

    if not database_url.startswith("sqlite"):
        # Best-effort extension setup. CI's postgis image does not have
        # pgvector; the testcontainer image does not have postgis. Both
        # CREATE EXTENSION calls are wrapped in their own connection so
        # one failure does not poison the other.
        for ext in ("vector", "postgis"):
            try:
                async with eng.begin() as conn:
                    await conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
            except Exception:  # noqa: BLE001 -- extension may not be available
                pass

    # Build the schema. We use ORM metadata.create_all (rather than alembic)
    # because the test container starts empty and we want a single, fast
    # bootstrap. Migrations are exercised by a dedicated `test_migrations.py`.
    from openetruscan.db.models import Base

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # The multilingual `language_word_embeddings` table uses pgvector
    # (vector(768) — XLM-R-base hidden dim), which has no SQLAlchemy
    # ORM type without an extra dep. Create it manually here so
    # multilingual-using tests have somewhere to write.
    if not database_url.startswith("sqlite"):
        try:
            async with eng.begin() as conn:
                await conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS language_word_embeddings (
                            language          TEXT       NOT NULL,
                            word              TEXT       NOT NULL,
                            vector            vector(768) NOT NULL,
                            frequency         INTEGER,
                            source            TEXT,
                            embedder          TEXT       NOT NULL DEFAULT 'mock',
                            embedder_revision TEXT       NOT NULL DEFAULT 'test',
                            created_at        TIMESTAMPTZ DEFAULT now(),
                            -- Post-T2.3: PK includes (embedder, embedder_revision) so
                            -- two partitions can coexist for the same (language, word).
                            -- The NOT NULL DEFAULT on embedder_revision lets older
                            -- tests that didn't specify it keep passing — they all
                            -- land in the implicit 'mock'/'test' partition.
                            PRIMARY KEY (language, word, embedder, embedder_revision)
                        )
                        """
                    )
                )
        except Exception:  # noqa: BLE001 -- pgvector may not be available
            pass

    try:
        yield eng
    finally:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await eng.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """A clean AsyncSession per test, truncating user tables on entry.

    The truncation runs through a *separate* short-lived session and is
    committed up-front. Mixing it into the test's session ran into asyncpg's
    "another operation is in progress" error when the test code expected a
    fresh transaction state.

    ``loop_scope="session"`` is required because the ``engine`` fixture is
    session-scoped and its asyncpg connection pool is bound to the session
    event loop. Without this, pytest-asyncio gives this fixture a
    function-scoped loop and the pooled connections cross loops, which
    asyncpg refuses with "another operation is in progress".
    """
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    # Pre-test cleanup in its own session so the test's session starts clean.
    async with sessionmaker() as cleanup:
        for tbl in _USER_TABLES:
            try:
                await cleanup.execute(text(f"DELETE FROM {tbl}"))
            except Exception:  # noqa: BLE001 -- table may not exist on this backend
                await cleanup.rollback()
        await cleanup.commit()

    async with sessionmaker() as session:
        yield session


# ---------------------------------------------------------------------------
# Shared API-test fixtures
# ---------------------------------------------------------------------------
#
# `client` and `sample_data` were originally defined inside test_server.py.
# Promoted to conftest.py so other test modules (test_multilingual.py,
# anything new) can mount the FastAPI app + a Postgres-backed repository
# without duplicating fixture wiring. Per-test turnaround is unchanged.


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session):
    """Mounted FastAPI ASGI client backed by the per-test session."""
    from httpx import ASGITransport, AsyncClient
    from openetruscan.api.server import app
    from openetruscan.db.session import get_session

    def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(loop_scope="session")
async def sample_data(db_session):
    """Three canonical inscriptions used across multiple test modules."""
    from openetruscan.db.repository import InscriptionData, InscriptionRepository

    repo = InscriptionRepository(db_session)
    test_data = [
        InscriptionData(
            id="ETR_001",
            raw_text="LARTHAL",
            canonical="larθal",
            findspot="Cerveteri",
            findspot_lat=42.0,
            findspot_lon=12.0,
            language="etruscan",
            classification="funerary",
        ),
        InscriptionData(
            id="ETR_002",
            raw_text="ARNTH",
            canonical="arnθ",
            findspot="Tarquinia",
            findspot_lat=42.5,
            findspot_lon=11.5,
            language="etruscan",
            classification="funerary",
            # ETR_002 carries a date and TM id so the structured-query
            # tests can exercise chronology + cross-corpus paths against
            # the same fixture.
            date_approx=-600,
            trismegistos_id="TM_12345",
        ),
        InscriptionData(
            id="ETR_003",
            raw_text="TEST",
            canonical="test",
            findspot="Rome",
            findspot_lat=41.9,
            findspot_lon=12.5,
            language="latin",
            classification="legal",
        ),
    ]
    for item in test_data:
        await repo.add(item)
    await db_session.commit()
    return test_data


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_postgres: skip if the test backend is SQLite",
    )
    config.addinivalue_line(
        "markers",
        "requires_postgis: skip if the PostGIS extension is unavailable",
    )
    config.addinivalue_line(
        "markers",
        "requires_pgvector: skip if the pgvector extension is unavailable",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip postgres-only tests when running on SQLite."""
    explicit = os.environ.get("DATABASE_URL", "")
    on_postgres = _is_postgres_url(explicit) or _testcontainers_available()
    if on_postgres:
        return
    skip_pg = pytest.mark.skip(reason="requires Postgres backend (set DATABASE_URL or install testcontainers)")
    for item in items:
        if any(m.name in {"requires_postgres", "requires_postgis", "requires_pgvector"} for m in item.iter_markers()):
            item.add_marker(skip_pg)


def _testcontainers_available() -> bool:
    try:
        import testcontainers.postgres  # noqa: F401
    except ImportError:
        return False
    return True
