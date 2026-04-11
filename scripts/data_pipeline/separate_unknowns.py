import sqlite3
from pathlib import Path

def setup_unknown_db(source_conn, target_path):
    # Get schema from source
    source_cur = source_conn.cursor()
    source_cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='cie_review'")
    create_sql = source_cur.fetchone()[0]
    
    target_conn = sqlite3.connect(target_path)
    target_cur = target_conn.cursor()
    # Ensure a fresh start for the unknown table in the target
    target_cur.execute("DROP TABLE IF EXISTS cie_review")
    target_cur.execute(create_sql)
    target_conn.commit()
    return target_conn

def migrate_unknowns(source_conn, target_conn, unknown_findspots):
    source_cur = source_conn.cursor()
    target_cur = target_conn.cursor()
    
    if not unknown_findspots:
        return 0
        
    placeholders = ",".join(["?"] * len(unknown_findspots))
    
    # Select rows to move
    query = f"SELECT * FROM cie_review WHERE trim(latin_findspot) IN ({placeholders})"
    source_cur.execute(query, unknown_findspots)
    rows = source_cur.fetchall()
    
    if not rows:
        return 0
        
    cols_count = len(rows[0])
    placeholders_cols = ",".join(["?"] * cols_count)
    
    target_cur.executemany(f"INSERT INTO cie_review VALUES ({placeholders_cols})", rows)
    target_conn.commit()
    
    # Delete from source
    source_cur.execute(f"DELETE FROM cie_review WHERE trim(latin_findspot) IN ({placeholders})", unknown_findspots)
    source_conn.commit()
    
    return len(rows)

def main():
    base_dir = Path("data/cie/databases")
    geo_db_path = Path("data/cie/geocoding/findspots_geocoding.db")
    
    # 1. Get unknown findspots
    geo_conn = sqlite3.connect(geo_db_path)
    geo_cur = geo_conn.cursor()
    
    # Fetch all strings mapped to 'Unknown, Italy' or other unknown indicators
    geo_cur.execute("""
        SELECT original_string 
        FROM unique_findspots 
        WHERE cluster_name = 'Unknown, Italy' 
           OR cluster_name IS NULL 
           OR cluster_name = '' 
           OR cluster_name = 'Unknown'
           OR status = 'MANUAL_REVIEW_NEEDED'
    """)
    # We include MANUAL_REVIEW_NEEDED just in case, or keep it strict?
    # Actually, the user said "unknown as per report". The report put Unknowns in their own section.
    # Manual reviews also need checking, but maybe the user wants them separate.
    # I will stick to explicitly "Unknown" and NULL for now to be safe.
    unknown_findspots = [row[0].strip() for row in geo_cur.fetchall()]
    geo_conn.close()
    
    print(f"Identified {len(unknown_findspots)} findspot strings categorized as 'Unknown'.")
    
    dbs_to_process = [
        "cie_etruscan.db",
        "cie_latin.db",
        "cie_ranges.db",
        "cie_range_latin.db"
    ]
    
    for db_name in dbs_to_process:
        source_path = base_dir / db_name
        if not source_path.exists():
            print(f"Skipping {db_name} (Not found).")
            continue
            
        target_name = db_name.replace(".db", "_unknown.db")
        target_path = base_dir / target_name
        
        print(f"Processing {db_name} -> {target_name}...")
        
        source_conn = sqlite3.connect(source_path)
        target_conn = setup_unknown_db(source_conn, target_path)
        
        count = migrate_unknowns(source_conn, target_conn, unknown_findspots)
        
        print(f"  Moved {count} rows.")
        
        source_conn.close()
        target_conn.close()

if __name__ == "__main__":
    main()
