import asyncio, asyncpg, os

SQL_CREATE = """
CREATE TABLE IF NOT EXISTS provenance_audits (
    id SERIAL PRIMARY KEY,
    inscription_id TEXT NOT NULL REFERENCES inscriptions(id) ON DELETE CASCADE,
    old_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    notes TEXT,
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_provenance_audits_inscription_id ON provenance_audits(inscription_id);
"""

async def run_migration():
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL not set. Skipping migration.")
        return
    # Convert sqlalchemy asyncpg url to asyncpg url
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://")
        
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(SQL_CREATE)
        print("Created provenance_audits table successfully.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(run_migration())
