import sqlite3
import re
from pathlib import Path

# Paths
repo_root = Path(__file__).resolve().parent.parent.parent
ranges_db = repo_root / 'data' / 'cie' / 'databases' / 'cie_ranges.db'
rescued_db = repo_root / 'data' / 'cie' / 'databases' / 'cie_rescued.db'

def parse_range(val):
    val = val.strip().lower()
    
    # Ex: '486 et 487'
    et_match = re.search(r'^(\d+)\s+(?:et|e)\s+(\d+)$', val)
    if et_match:
        start, end = int(et_match.group(1)), int(et_match.group(2))
        return [str(start), str(end)]
        
    # Ex: '489-491'
    dash_match = re.search(r'^(\d+)\s*-\s*(\d+)$', val)
    if dash_match:
        start, end = int(dash_match.group(1)), int(dash_match.group(2))
        return [str(x) for x in range(start, end + 1)]
        
    # Ex: '489, 490, 491'
    comma_match = re.fullmatch(r'(\d+)(\s*,\s*\d+)+', val)
    if comma_match:
        pieces = re.findall(r'\d+', val)
        return pieces
    
    return []

def execute_split():
    if not ranges_db.exists():
        print(f"File not found: {ranges_db}")
        return
        
    r_conn = sqlite3.connect(ranges_db)
    r_cur = r_conn.cursor()
    
    res_conn = sqlite3.connect(rescued_db)
    res_cur = res_conn.cursor()
    
    # Ensure rescued table exists and has correct columns (copy schema from ranges if needed)
    r_cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='cie_review'")
    schema = r_cur.fetchone()[0]
    try:
        res_cur.execute(schema)
    except sqlite3.OperationalError:
        pass
    
    # Ensure notes column exists for traceability
    try:
        res_cur.execute("ALTER TABLE cie_review ADD COLUMN notes TEXT")
    except sqlite3.OperationalError:
        pass

    r_cur.execute("SELECT * FROM cie_review")
    col_names = [d[0] for d in r_cur.description]
    rows = r_cur.fetchall()
    
    split_count = 0
    total_new = 0
    
    for row in rows:
        row_dict = dict(zip(col_names, row))
        cid_raw = str(row_dict['cie_id'])
        expanded = parse_range(cid_raw)
        
        if len(expanded) > 1:
            split_count += 1
            for child_id in expanded:
                child_dict = row_dict.copy()
                child_dict['cie_id'] = child_id
                # Traceability
                notes = child_dict.get('notes') or ""
                child_dict['notes'] = f"{notes} [Decomposed from range {cid_raw}]".strip()
                
                cols = list(child_dict.keys())
                placeholders = ",".join(["?"] * len(cols))
                res_cur.execute(f"INSERT INTO cie_review ({','.join(cols)}) VALUES ({placeholders})", list(child_dict.values()))
                total_new += 1
            
            # Delete original from ranges_db
            r_cur.execute("DELETE FROM cie_review WHERE cie_id = ?", (cid_raw,))
        
    r_conn.commit()
    res_conn.commit()
    
    print(f"Range Decomposition Complete.")
    print(f"  Compound entries split: {split_count}")
    print(f"  Individual records created in cie_rescued.db: {total_new}")
    
    r_conn.close()
    res_conn.close()

if __name__ == "__main__":
    execute_split()
