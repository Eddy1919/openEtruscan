import csv
import os

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()
DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql://corpus_reader:etruscan_secret@127.0.0.1:5432/corpus"
)
OUTPUT_CSV = "data/rejected_inscriptions.csv"


def main():
    print("Connecting to Postgres to fetch rejected records...")
    conn = psycopg2.connect(DB_URL)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT id, canonical, classification, provenance_status"
            " FROM inscriptions"
            " WHERE provenance_status = 'rejected' ORDER BY id;"
        )
        rows = cur.fetchall()

    if not rows:
        print("No rejected records found!")
        conn.close()
        return

    keys = list(rows[0].keys())
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[SUCCESS] Exported {len(rows)} rejected records to {OUTPUT_CSV}")
    conn.close()


if __name__ == "__main__":
    main()
