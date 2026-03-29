import os
import sys
import re
import csv
import json
import sqlite3
import yaml
import asyncio
import psycopg2
from psycopg2.extras import DictCursor, execute_values
from concurrent.futures import ThreadPoolExecutor
import sys
sys.path.append(os.path.abspath(os.curdir))
from scripts.migrate_to_postgres import validate_extracted_record
import os
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ.get("DATABASE_URL", "postgresql://corpus_reader:etruscan_secret@127.0.0.1:5432/corpus")


def connect_pg():
    return psycopg2.connect(DB_URL)

def run_migrations():
    conn = connect_pg()
    with conn.cursor() as cur:
        print("[MIGRATION] Applying structural schema upgrades...")
        
        # Ensure table exists with 3072 dimensions for embeddings
        cur.execute("""
            CREATE TABLE IF NOT EXISTS inscriptions (
                id TEXT PRIMARY KEY,
                raw_text TEXT NOT NULL,
                canonical TEXT NOT NULL,
                phonetic TEXT NOT NULL,
                old_italic TEXT NOT NULL,
                findspot TEXT DEFAULT '',
                findspot_lat DOUBLE PRECISION,
                findspot_lon DOUBLE PRECISION,
                date_approx INTEGER,
                date_uncertainty INTEGER,
                medium TEXT DEFAULT '',
                object_type TEXT DEFAULT '',
                source TEXT DEFAULT '',
                bibliography TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                language TEXT NOT NULL DEFAULT 'etruscan',
                classification TEXT NOT NULL DEFAULT 'unknown',
                script_system TEXT NOT NULL DEFAULT 'old_italic',
                completeness TEXT NOT NULL DEFAULT 'complete',
                provenance_status TEXT NOT NULL DEFAULT 'verified',
                provenance_flags TEXT NOT NULL DEFAULT '',
                geom geometry(Point, 4326),
                emb_text vector(3072),
                emb_context vector(3072),
                emb_combined vector(3072),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)

        # Add provenience columns safely
        cur.execute("ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS trismegistos_id TEXT;")
        cur.execute("ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS eagle_id TEXT;")
        cur.execute("ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS pleiades_id TEXT;")
        cur.execute("ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS is_codex BOOLEAN DEFAULT FALSE;")
        
        print("[MIGRATION] Wiping previous inscriptions state for clean unification...")
        cur.execute("TRUNCATE TABLE inscriptions CASCADE;")
        
    conn.commit()
    conn.close()

def load_yaml_mappings():
    base = "data/"
    with open(f"{base}trismegistos_mapping.yaml", "r") as f:
        trism = yaml.safe_load(f)
    with open(f"{base}eagle_mapping.yaml", "r") as f:
        eagle = yaml.safe_load(f)
    with open(f"{base}pleiades_mapping.yaml", "r") as f:
        pleiades = yaml.safe_load(f)
        
    codex_ids = set()
    with open(f"{base}codex_texts.yaml", "r") as f:
        codex_data = yaml.safe_load(f)
        if codex_data and "texts" in codex_data:
            for text in codex_data["texts"]:
                codex_ids.add(text["source"])  # Matches TLE or CIE
    
    return trism or {}, eagle or {}, pleiades or {}, codex_ids

def ingest_larth(trism, eagle, pleiades, codex_ids):
    sqlite_db = "data/corpus.db"
    if not os.path.exists(sqlite_db):
        print(f"[FATAL] Missing golden Larth dataset: {sqlite_db}")
        sys.exit(1)
        
    conn_sq = sqlite3.connect(sqlite_db)
    conn_sq.row_factory = sqlite3.Row
    cur_sq = conn_sq.cursor()
    cur_sq.execute("SELECT * FROM inscriptions")
    
    rows = []
    for row in cur_sq.fetchall():
        d = dict(row)
        
        cid = d["id"]
        t_id = trism.get(cid, None)
        e_id = eagle.get(cid, None)
        p_id = pleiades.get(d.get("findspot", ""), None)
        
        # Determine if codex
        is_codex = any(c_id in cid or c_id in d.get("source", "") for c_id in codex_ids)
        
        pg_row = (
            cid,
            d.get("canonical", ""),
            d.get("phonetic", ""),
            d.get("old_italic", ""),
            d.get("raw_text", ""),
            d.get("findspot", ""),
            d.get("findspot_lat", None),
            d.get("findspot_lon", None),
            d.get("date_approx", None),
            d.get("date_uncertainty", None),
            d.get("medium", ""),
            d.get("object_type", ""),
            d.get("source", ""),
            d.get("bibliography", ""),
            d.get("notes", ""),
            d.get("language", "etruscan"),
            d.get("classification", "unknown"),
            d.get("script_system", "old_italic"),
            d.get("completeness", "complete"),
            "verified", # Golden Larth is perfectly clean!
            "",
            t_id,
            e_id,
            p_id,
            is_codex
        )
        rows.append(pg_row)
        
    conn_pg = connect_pg()
    cur_pg = conn_pg.cursor()
    
    print(f"[LARTH] Ingesting {len(rows)} verified golden records into Postgres...")
    
    insert_query = """
        INSERT INTO inscriptions (
            id, canonical, phonetic, old_italic, raw_text, findspot,
            findspot_lat, findspot_lon, date_approx, date_uncertainty,
            medium, object_type, source, bibliography, notes,
            language, classification, script_system, completeness,
            provenance_status, provenance_flags, trismegistos_id,
            eagle_id, pleiades_id, is_codex, geom
        ) VALUES %s
        ON CONFLICT (id) DO NOTHING
    """
    
    # Custom template to handle geom postgis injection during executemany
    template = """(
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        CASE WHEN %s IS NOT NULL AND %s IS NOT NULL 
             THEN ST_SetSRID(ST_MakePoint(%s, %s), 4326) 
             ELSE NULL END
    )"""
    
    # We must append the lat/lon explicitly twice at the end for the geom CASE statement binding
    values_with_geom = [
        (*r, r[7], r[6], r[7], r[6]) for r in rows
    ]
    
    execute_values(cur_pg, insert_query, values_with_geom, template=template)
    conn_pg.commit()
    conn_pg.close()


def ingest_cie(trism, eagle, pleiades, codex_ids):
    sqlite_db = "data/vm_corpus.db"
    
    conn_sq = sqlite3.connect(sqlite_db)
    conn_sq.row_factory = sqlite3.Row
    cur_sq = conn_sq.cursor()
    cur_sq.execute("SELECT * FROM inscriptions")
    
    rows = []
    for row in cur_sq.fetchall():
        d = dict(row)
        
        cid = d["id"]
        
        # Apply standard strict Regex ML Validation
        # Based on user intent we omit LLM destructive filter since it ate good data
        flags = validate_extracted_record(cid, d.get("canonical", ""))
        is_clean = len(flags) == 0
        
        status = "verified" if is_clean else "rejected"
        flag_str = ",".join(flags)
        
        t_id = trism.get(cid, None)
        e_id = eagle.get(cid, None)
        p_id = pleiades.get(d.get("findspot", ""), None)
        
        # Determine if codex
        is_codex = any(c_id in cid or c_id in d.get("source", "") for c_id in codex_ids)
        
        pg_row = (
            cid,
            d.get("canonical", ""),
            d.get("phonetic", ""),
            d.get("old_italic", ""),
            d.get("raw_text", ""),
            d.get("findspot", ""),
            d.get("findspot_lat", None),
            d.get("findspot_lon", None),
            d.get("date_approx", None),
            d.get("date_uncertainty", None),
            d.get("medium", ""),
            d.get("object_type", ""),
            d.get("source", ""),
            d.get("bibliography", ""),
            d.get("notes", ""),
            d.get("language", "etruscan"),
            d.get("classification", "unknown"),
            d.get("script_system", "old_italic"),
            d.get("completeness", "complete"),
            status,
            flag_str,
            t_id,
            e_id,
            p_id,
            is_codex
        )
        rows.append(pg_row)
        
    conn_pg = connect_pg()
    cur_pg = conn_pg.cursor()
    
    print(f"[CIE] Ingesting {len(rows)} VM records into Postgres...")
    
    insert_query = """
        INSERT INTO inscriptions (
            id, canonical, phonetic, old_italic, raw_text, findspot,
            findspot_lat, findspot_lon, date_approx, date_uncertainty,
            medium, object_type, source, bibliography, notes,
            language, classification, script_system, completeness,
            provenance_status, provenance_flags, trismegistos_id,
            eagle_id, pleiades_id, is_codex, geom
        ) VALUES %s
        ON CONFLICT (id) DO NOTHING
    """
    
    template = """(
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        CASE WHEN %s IS NOT NULL AND %s IS NOT NULL 
             THEN ST_SetSRID(ST_MakePoint(%s, %s), 4326) 
             ELSE NULL END
    )"""
    
    values_with_geom = [
        (*r, r[7], r[6], r[7], r[6]) for r in rows
    ]
    
    execute_values(cur_pg, insert_query, values_with_geom, template=template)
    conn_pg.commit()
    conn_pg.close()


if __name__ == "__main__":
    t, e, p, codex = load_yaml_mappings()
    run_migrations()
    ingest_larth(t, e, p, codex)
    ingest_cie(t, e, p, codex)
    
    # Verification
    conn = connect_pg()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM inscriptions;")
        total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM inscriptions WHERE provenance_status='verified';")
        verified = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM inscriptions WHERE trismegistos_id IS NOT NULL;")
        mapped = cur.fetchone()[0]
        print(f"[SUCCESS] Unified Database Population Complete.")
        print(f"Total Rows: {total}")
        print(f"Verified & Clean: {verified}")
        print(f"Rows enriched with external YAML metadata: {mapped}")
