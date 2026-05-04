import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from openetruscan.db.models import GeneticSample, Inscription
from sqlalchemy import text
import os

async def seed_data():
    db_url = "sqlite+aiosqlite:///data/test.db"
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Add a dummy inscription
        insc = Inscription(
            id="Ta.1.1",
            canonical="larth tharnie",
            phonetic="larθ θarnie",
            old_italic="𐌋𐌀𐌓𐌕𐌄 𐌕𐌀𐌓𐌍𐌈𐌄",
            raw_text="larth tharnie",
            findspot="Tarquinia",
            findspot_lat=42.254,
            findspot_lon=11.758,
            date_approx=-350,
            classification="epitaph",
            language="etruscan",
            script_system="old_italic",
            completeness="complete",
            provenance_status="unknown",
            provenance_flags="",
            source_code="unknown"
        )
        session.add(insc)

        # Add a dummy genetic sample near the inscription
        sample = GeneticSample(
            id="R101",
            findspot="Tarquinia, Necropolis",
            findspot_lat=42.2545,
            findspot_lon=11.7585,
            y_haplogroup="R1b-M269",
            mt_haplogroup="H1",
            date_approx=-350,
            biological_sex="M",
            c14_date_range="380-320 BCE",
            tomb_id="Tomb of the Shields"
        )
        session.add(sample)
        
        await session.commit()
    print("Seeded Ta.1.1 and R101")

if __name__ == "__main__":
    asyncio.run(seed_data())
