import sqlite3
from pathlib import Path

GEO_MAP = {
    '3067': ('Chiusi', 43.0174, 11.9492, 5000),
    '509': ('Chiusi', 43.0174, 11.9492, 5000),
    '3968': ('Palazzone (Perugia)', 43.0890, 12.4270, 5000),
    '4734': ('Castiglione del Lago', 43.1270, 12.0460, 5000)
}

def fix_rescued():
    repo_root = Path(__file__).resolve().parent.parent.parent
    rescued_db = repo_root / 'data' / 'cie' / 'databases' / 'cie_rescued.db'
    source_db = repo_root / 'data' / 'cie' / 'working' / 'cie_export_review.db'
    
    s_conn = sqlite3.connect(source_db)
    s_cur = s_conn.cursor()
    
    r_conn = sqlite3.connect(rescued_db)
    r_cur = r_conn.cursor()
    
    # Ensure table exists
    s_cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='cie_review'")
    schema = s_cur.fetchone()[0]
    try:
        r_cur.execute(schema)
        # Add spatial/modern columns
        r_cur.execute("ALTER TABLE cie_review ADD COLUMN findspot_modern TEXT")
        r_cur.execute("ALTER TABLE cie_review ADD COLUMN findspot_lat FLOAT")
        r_cur.execute("ALTER TABLE cie_review ADD COLUMN findspot_lon FLOAT")
        r_cur.execute("ALTER TABLE cie_review ADD COLUMN uncertainty_m FLOAT")
    except sqlite3.OperationalError:
        pass
        
    for cid, geo in GEO_MAP.items():
        s_cur.execute("SELECT * FROM cie_review WHERE cie_id=?", (cid,))
        row = s_cur.fetchone()
        if not row: continue
        
        col_names = [d[0] for d in s_cur.description]
        row_dict = dict(zip(col_names, row))
        
        modern, lat, lon, unc = geo
        row_dict['findspot_modern'] = modern
        row_dict['findspot_lat'] = lat
        row_dict['findspot_lon'] = lon
        row_dict['uncertainty_m'] = unc
        
        cols = list(row_dict.keys())
        placeholders = ','.join(['?']*len(cols))
        try:
            r_cur.execute(f"INSERT INTO cie_review ({','.join(cols)}) VALUES ({placeholders})", list(row_dict.values()))
            print(f"Recovered and geocoded {cid}")
        except sqlite3.IntegrityError:
            print(f"Already exists: {cid}")
            
    r_conn.commit()
    r_conn.close()
    s_conn.close()

if __name__ == "__main__":
    fix_rescued()
