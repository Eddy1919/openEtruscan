import sqlite3
from pathlib import Path

def setup_unknown_db(source_conn, target_path):
    source_cur = source_conn.cursor()
    source_cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='cie_review'")
    create_sql = source_cur.fetchone()[0]
    
    target_conn = sqlite3.connect(target_path)
    target_cur = target_conn.cursor()
    # Ensure table exists in target
    target_cur.execute(f"{create_sql.replace('CREATE TABLE', 'CREATE TABLE IF NOT EXISTS')}")
    target_conn.commit()
    return target_conn

def move_placeholders(source_conn, target_conn):
    source_cur = source_conn.cursor()
    target_cur = target_conn.cursor()
    
    # Identify placeholder symbols or empty strings
    # We look for: empty, whitespace-only, single quote, double quote, etc.
    # The user specifically mentioned the double quote "
    placeholders = ['', '"', '""', "'", '.', ',', '?', '-', 'null', 'NULL']
    
    query_select = "SELECT * FROM cie_review WHERE trim(latin_findspot) IN (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    source_cur.execute(query_select, placeholders)
    rows = source_cur.fetchall()
    
    if not rows:
        return 0
        
    cols_count = len(rows[0])
    placeholders_cols = ",".join(["?"] * cols_count)
    
    target_cur.executemany(f"INSERT INTO cie_review VALUES ({placeholders_cols})", rows)
    target_conn.commit()
    
    source_cur.execute("DELETE FROM cie_review WHERE trim(latin_findspot) IN (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", placeholders)
    source_conn.commit()
    
    return len(rows)

def main():
    base_dir = Path("data/cie/databases")
    dbs_to_clean = ["cie_etruscan.db", "cie_latin.db", "cie_ranges.db", "cie_range_latin.db"]
    
    for db_name in dbs_to_clean:
        source_path = base_dir / db_name
        if not source_path.exists(): continue
            
        target_name = db_name.replace(".db", "_unknown.db")
        target_path = base_dir / target_name
        
        print(f"Cleaning placeholders in {db_name} -> {target_name}...")
        
        source_conn = sqlite3.connect(source_path)
        target_conn = setup_unknown_db(source_conn, target_path)
        
        count = move_placeholders(source_conn, target_conn)
        print(f"  Moved {count} placeholder rows.")
        
        source_conn.close()
        target_conn.close()

if __name__ == "__main__":
    main()
