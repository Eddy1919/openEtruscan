import asyncio
from openetruscan.db.session import engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

async def main():
    async with AsyncSession(engine) as session:
        await session.execute(text(
            "UPDATE inscriptions SET zotero_id = '8B4X9V2Q' WHERE id IN (SELECT id FROM inscriptions LIMIT 5);"
        ))
        await session.commit()
    print("Successfully populated 5 inscriptions with Zotero ID 8B4X9V2Q")

if __name__ == "__main__":
    asyncio.run(main())
