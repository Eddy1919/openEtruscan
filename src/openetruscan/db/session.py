"""
Async database session factory — provides AsyncSession instances via dependency injection.

Uses SQLAlchemy 2.0 async engine with asyncpg driver and connection pooling.
"""

from collections.abc import AsyncGenerator
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from openetruscan.core.config import settings

_engine = None
_session_maker = None


def _strip_ssl_to_connect_args(db_url: str) -> tuple[str, dict[str, object]]:
    """Move libpq-style `?ssl=` / `?sslmode=` URL params into asyncpg connect_args.

    asyncpg.connect() takes ``ssl`` as a keyword (bool / SSLContext / str) but
    SQLAlchemy's asyncpg dialect forwards arbitrary URL query keys as kwargs
    directly, which makes ``?sslmode=require`` end up as
    ``asyncpg.connect(sslmode='require')`` and crash with
    ``TypeError: unexpected keyword argument 'sslmode'``. Same shape with
    ``?ssl=require`` on some SQLAlchemy versions. Strip it here and add it
    to the engine's ``connect_args``.
    """
    parsed = urlparse(db_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    ssl_value = query.pop("ssl", None) or query.pop("sslmode", None)
    new_url = urlunparse(parsed._replace(query=urlencode(query)))
    connect_args: dict[str, object] = {}
    if ssl_value and ssl_value not in ("disable", "false", "0"):
        # asyncpg accepts the libpq mode strings directly.
        connect_args["ssl"] = ssl_value
    return new_url, connect_args


def get_engine():
    """Lazily initialize the SQLAlchemy async engine and sessionmaker."""
    global _engine, _session_maker
    if _engine is None:
        # We use the DATABASE_URL from settings, but replace postgresql with postgresql+asyncpg
        db_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")
        if db_url.startswith("sqlite://"):
            db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://")

        connect_args: dict[str, object] = {}
        if db_url.startswith("postgresql+asyncpg://"):
            db_url, connect_args = _strip_ssl_to_connect_args(db_url)

        _engine = create_async_engine(
            db_url,
            echo=False,
            future=True,
            pool_size=20,
            max_overflow=10,
            connect_args=connect_args,
        )
        _session_maker = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _engine, _session_maker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database sessions."""
    _, session_maker = get_engine()
    async with session_maker() as session:
        yield session
