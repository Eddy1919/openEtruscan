#!/usr/bin/env python3
"""
Exports PostgreSQL records into the static JSON file used by the Next.js frontend.
"""
import os
import sys
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ.get("DATABASE_URL", "postgresql://corpus_reader:etruscan_secret@127.0.0.1:5432/corpus")
OUTPUT_PATH = "frontend/public/data/corpus.json"

def main():
    conn = psycopg2.connect(DB_URL)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Only export verified data or ALL data based on config?
        # The frontend wants the expanded well-provenanced corpus. We include rejected but mark them?
        # The user requested "expanded, well-provenanced corpus" indicating all records.
        cur.execute("SELECT * FROM inscriptions ORDER BY id;")
        rows = cur.fetchall()

    for r in rows:
        # Serialize vectors / nulls gracefully if they exist
        for key in list(r.keys()):
            val = r[key]
            if "vector" in str(type(val)).lower():
                r[key] = None  # don't send heavy embeddings to frontend JSON!
            if key == "created_at" or key == "updated_at":
                r[key] = str(val) if val else None

    with open(OUTPUT_PATH, "w") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    print(f"[SUCCESS] Exported {len(rows)} records to {OUTPUT_PATH}")
    conn.close()

if __name__ == "__main__":
    main()
