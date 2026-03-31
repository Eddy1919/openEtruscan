import os
import psycopg2
from dotenv import load_dotenv

def run_migration():
    load_dotenv()
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("Required DATABASE_URL not set.")
        return

    print(f"Connecting to database...")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    
    with conn.cursor() as cur:
        # Check if fts_canonical exists
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='inscriptions' AND column_name='fts_canonical'
        """)
        if cur.fetchone():
            print("fts_canonical already exists.")
        else:
            print("Adding fts_canonical column...")
            cur.execute("SET statement_timeout = 5000")
            cur.execute("""
                ALTER TABLE inscriptions ADD COLUMN fts_canonical tsvector 
                GENERATED ALWAYS AS (to_tsvector('simple', coalesce(canonical, ''))) STORED
            """)
            print("Adding GIN index...")
            cur.execute("CREATE INDEX idx_fts_canonical ON inscriptions USING GIN (fts_canonical)")
            print("Migration successful.")

if __name__ == "__main__":
    run_migration()
