import sqlite3
from pathlib import Path

# Coordinates based on standard archaeological locations
GEO_MAP = {
    '3067': ('Chiusi', 43.0174, 11.9492, 5000),
    '509': ('Chiusi', 43.0174, 11.9492, 5000),
    '3968': ('Palazzone (Perugia)', 43.0890, 12.4270, 5000),
    '4734': ('Castiglione del Lago', 43.1270, 12.0460, 5000)
}

repo_root = Path(__file__).resolve().parent.parent.parent
unknown_db = repo_root / 'data' / 'cie' / 'databases' / 'cie_etruscan_unknown.db'
rescued_db = repo_root / 'data' / 'cie' / 'databases' / 'cie_rescued.db'

def process_salvaged():
    if not unknown_db.exists():
        print(f"File not found: {unknown_db}")
        return

    # Attach unknown db
    u_conn = sqlite3.connect(unknown_db)
    u_cur = u_conn.cursor()
    
    # Check if we have the targeted rows
    u_cur.execute(f"SELECT * FROM cie_review WHERE cie_id IN ({','.join(['?']*4)})", list(GEO_MAP.keys()))
    col_names = [description[0] for description in u_cur.description]
    rows = u_cur.fetchall()
    
    if not rows:
        print("Rows already moved or missing.")
        u_conn.close()
        return

    # Create rescued db
    r_conn = sqlite3.connect(rescued_db)
    r_cur = r_conn.cursor()
    
    # Get schema from unknown_db
    u_cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='cie_review'")
    schema = u_cur.fetchone()[0]
    
    try:
        r_cur.execute(schema)
    except sqlite3.OperationalError:
        pass
    # Ensure it has the geocoding columns since unknown might not have them fully populated
    try:
        r_cur.execute("ALTER TABLE cie_review ADD COLUMN findspot_modern TEXT")
        r_cur.execute("ALTER TABLE cie_review ADD COLUMN findspot_lat FLOAT")
        r_cur.execute("ALTER TABLE cie_review ADD COLUMN findspot_lon FLOAT")
        r_cur.execute("ALTER TABLE cie_review ADD COLUMN uncertainty_m FLOAT")
    except sqlite3.OperationalError:
        pass # Already exists
        
    r_conn.commit()

    # Move rows
    
    for row in rows:
        row_dict = dict(zip(col_names, row))
        cid = str(row_dict['cie_id'])
        modern, lat, lon, unc = GEO_MAP[cid]
        
        row_dict['findspot_modern'] = modern
        row_dict['findspot_lat'] = lat
        row_dict['findspot_lon'] = lon
        row_dict['uncertainty_m'] = unc
        row_dict['original_script_entry'] = row_dict.get('original_script', '')
        
        # Prepare insert into rescued
        cols = list(row_dict.keys())
        # filter out columns that might not exist in rescued if schema varied, but they use the same schema.
        # Actually simplest to just do INSERT INTO cie_review (...)
        
        placeholders = ','.join(['?']*len(cols))
        try:
            r_cur.execute(f"INSERT INTO cie_review ({','.join(cols)}) VALUES ({placeholders})", list(row_dict.values()))
            print(f"Moved and geocoded {cid}")
        except Exception as e:
            # Maybe column doesn't exist, just update if it failed?
            print(f"Error inserting {cid}: {e}")
            pass
            
        # Delete from unknown
        u_cur.execute("DELETE FROM cie_review WHERE cie_id = ?", (cid,))
        
    u_conn.commit()
    r_conn.commit()
    
    u_conn.close()
    r_conn.close()
    print("Process complete.")

if __name__ == "__main__":
    process_salvaged()
