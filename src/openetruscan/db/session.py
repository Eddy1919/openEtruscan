"""
Async database session factory — provides AsyncSession instances via dependency injection.

Uses SQLAlchemy 2.0 async engine with asyncpg driver and connection pooling.
"""
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from openetruscan.core.config import settings

_engine = None
_session_maker = None


def get_engine():
    """Lazily initialize the SQLAlchemy async engine and sessionmaker."""
    global _engine, _session_maker
    if _engine is None:
        # We use the DATABASE_URL from settings, but replace postgresql with postgresql+asyncpg
        db_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")
        
        _engine = create_async_engine(
            db_url,
            echo=False,
            future=True,
            pool_size=20,
            max_overflow=10,
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
