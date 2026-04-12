import os
import sqlite3
import psycopg2
from psycopg2.extras import execute_values
from pathlib import Path

# Setup Path to include src for core imports
repo_root = Path(__file__).resolve().parent.parent.parent
import sys
sys.path.append(str(repo_root / "src"))

from openetruscan.core.normalizer import normalize

sqlite_db_path = repo_root / "data" / "cie" / "databases" / "cie_rescued.db"

# Manual .env loading
pg_url = None
os_env_path = repo_root / ".env"
gemini_key = None

if os_env_path.exists():
    with open(os_env_path, 'r') as f:
        for line in f:
            if line.startswith("DATABASE_URL="):
                pg_url = line.strip().split('=', 1)[1].strip().strip('"').strip("'")
            if line.startswith("GEMINI_API_KEY="):
                gemini_key = line.strip().split('=', 1)[1].strip().strip('"').strip("'")

def ingest_batch():
    if not sqlite_db_path.exists():
        print(f"SQLite DB not found: {sqlite_db_path}")
        return

    if not pg_url:
        print("DATABASE_URL not found in .env")
        return

    # Connect to PostgreSQL
    try:
        p_conn = psycopg2.connect(pg_url)
        p_conn.autocommit = True
        print("Connected to PostgreSQL Production DB.")
    except Exception as e:
        print(f"PostgreSQL Connection Error: {e}")
        return

    # Connect to SQLite
    s_conn = sqlite3.connect(sqlite_db_path)
    s_cur = s_conn.cursor()

    # Filter for high-confidence Etruscan records
    s_cur.execute("""
        SELECT cie_id, transliterated, findspot_modern, findspot_lat, findspot_lon, 
               uncertainty_m, bibliography, latin_commentary, notes, rescue_source
        FROM cie_review 
        WHERE classification = 'Etruscan' 
        AND (confidence >= 0.8 OR confidence IS NULL)
    """)
    rows = s_cur.fetchall()
    print(f"Ingesting {len(rows)} verified records into production...")

    count = 0
    with p_conn.cursor() as p_cur:
        for row in rows:
            (cie_id, translit, modern_loc, lat, lon, unc_m, bib, latin_comm, ai_notes, source) = row
            
            # 1. Normalize phonological representation
            norm = normalize(translit or "", language="etruscan")
            
            # 2. Build Notes
            full_notes = []
            if latin_comm:
                full_notes.append(f"[Commentary] {latin_comm}")
            if ai_notes:
                full_notes.append(ai_notes)
            
            # 3. UPSERT into inscriptions
            sql = """
                INSERT INTO inscriptions (
                    id, canonical, phonetic, old_italic, raw_text, 
                    findspot, findspot_lat, findspot_lon, findspot_uncertainty_m,
                    bibliography, notes, language, classification, 
                    source, provenance_status, provenance_flags, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, 
                    %s, %s, %s, %s, 
                    %s, %s, %s, %s, 
                    %s, %s, %s, NOW()
                ) ON CONFLICT (id) DO UPDATE SET
                    canonical = EXCLUDED.canonical,
                    phonetic = EXCLUDED.phonetic,
                    old_italic = EXCLUDED.old_italic,
                    raw_text = EXCLUDED.raw_text,
                    findspot = EXCLUDED.findspot,
                    findspot_lat = EXCLUDED.findspot_lat,
                    findspot_lon = EXCLUDED.findspot_lon,
                    findspot_uncertainty_m = EXCLUDED.findspot_uncertainty_m,
                    notes = EXCLUDED.notes,
                    updated_at = NOW()
            """
            
            p_cur.execute(sql, (
                f"CIE {cie_id}", norm.canonical, norm.phonetic, norm.old_italic, translit or "",
                modern_loc or "", lat, lon, unc_m,
                bib or "", "\n\n".join(full_notes), "etruscan", "etruscan",
                f"CIE Rescued ({source})" if source else "CIE Rescued", "verified", "rescued,ai-verified"
            ))
            
            count += 1
            if count % 100 == 0:
                print(f"  Ingested {count}/{len(rows)}...")

    print(f"Ingestion complete. Total records merged: {count}")
    
    # Post-process: Update geometry column from lat/lon for PostGIS
    try:
        with p_conn.cursor() as p_cur:
            print("Syncing PostGIS geometry columns...")
            p_cur.execute("""
                UPDATE inscriptions 
                SET geom = ST_SetSRID(ST_MakePoint(findspot_lon, findspot_lat), 4326)
                WHERE (id LIKE 'CIE %') AND findspot_lat IS NOT NULL AND findspot_lon IS NOT NULL;
            """)
            print("PostGIS sync successful.")
    except Exception as e:
        print(f"PostGIS Update Error (skipping): {e}")

    p_conn.close()
    s_conn.close()

if __name__ == "__main__":
    ingest_batch()
