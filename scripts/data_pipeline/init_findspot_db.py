import sqlite3
from pathlib import Path

def main():
    etruscan_db_path = Path("data/cie/cie_etruscan.db")
    geocoding_db_path = Path("data/cie/findspots_geocoding.db")

    if geocoding_db_path.exists():
        geocoding_db_path.unlink()

    conn_et = sqlite3.connect(etruscan_db_path)
    cur_et = conn_et.cursor()

    conn_geo = sqlite3.connect(geocoding_db_path)
    cur_geo = conn_geo.cursor()

    cur_geo.execute("""
        CREATE TABLE IF NOT EXISTS unique_findspots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_string TEXT UNIQUE,
            frequency_count INTEGER,
            cluster_name TEXT,
            gemini_lat REAL,
            gemini_lon REAL,
            mapbox_lat REAL,
            mapbox_lon REAL,
            distance_km REAL,
            status TEXT DEFAULT 'PENDING'
        )
    """)

    # We skip empty/NULL findspots if any
    cur_et.execute("""
        SELECT latin_findspot, COUNT(*) 
        FROM cie_review 
        WHERE latin_findspot IS NOT NULL AND trim(latin_findspot) != ''
        GROUP BY latin_findspot
    """)
    rows = cur_et.fetchall()

    insert_data = []
    for row in rows:
        findspot = str(row[0]).strip()
        count = row[1]
        insert_data.append((findspot, count))

    cur_geo.executemany("""
        INSERT INTO unique_findspots (original_string, frequency_count)
        VALUES (?, ?)
    """, insert_data)

    conn_geo.commit()
    
    cur_geo.execute("SELECT COUNT(*) FROM unique_findspots")
    count = cur_geo.fetchone()[0]
    print(f"Successfully initialized findspots_geocoding.db with {count} distinct findspots.")

    conn_et.close()
    conn_geo.close()

if __name__ == "__main__":
    main()
