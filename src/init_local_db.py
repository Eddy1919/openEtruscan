import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from openetruscan.db.models import Base
import os

async def init_db():
    db_url = "sqlite+aiosqlite:///data/test.db"
    os.makedirs("data", exist_ok=True)
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database initialized at data/test.db")

if __name__ == "__main__":
    asyncio.run(init_db())
