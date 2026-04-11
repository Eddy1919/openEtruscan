import sqlite3
import re
from pathlib import Path

def normalize(t):
    if not t: return ""
    return re.sub(r"\W+", "", t.lower()).replace("ś", "s")

def execute_quarantine():
    db_path = Path("data/cie/databases/cie_etruscan.db")
    larth_file = Path("data/cie/working/larth_canonical_normalized.txt")
    
    if not db_path.exists():
        print(f"Error: {db_path} not found.")
        return

    # Load Larth Canonicals for remote overlap check
    larth_set = set()
    if larth_file.exists():
        with open(larth_file, "r") as f:
            larth_set = set(line.strip() for line in f if line.strip())
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # 1. Create discarded table mirroring cie_review but with a reason column
    cur.execute("DROP TABLE IF EXISTS cie_discarded")
    cur.execute("""
        CREATE TABLE cie_discarded AS SELECT * FROM cie_review WHERE 1=0
    """)
    cur.execute("ALTER TABLE cie_discarded ADD COLUMN discard_reason TEXT")
    
    # 2. Fetch all records
    cur.execute("SELECT cie_id, transliterated, latin_findspot, canonical FROM cie_review")
    rows = cur.fetchall()
    
    seen_norm = {} # norm_text -> first_id
    to_discard_internal = []
    to_discard_remote = []
    
    for cid, trans, find, can in rows:
        norm = normalize(can if can else trans)
        if not norm: continue
        
        # Internal Overlap
        if norm in seen_norm:
            to_discard_internal.append(cid)
            continue
        
        seen_norm[norm] = cid
        
        # Remote Overlap
        if norm in larth_set:
            to_discard_remote.append(cid)
            
    # 3. Move Internal Duplicates
    print(f"Moving {len(to_discard_internal)} internal duplicates...")
    for cid in to_discard_internal:
        cur.execute("INSERT INTO cie_discarded SELECT *, 'Internal Duplicate' FROM cie_review WHERE cie_id = ?", (cid,))
        cur.execute("DELETE FROM cie_review WHERE cie_id = ?", (cid,))
        
    # 4. Move Remote Overlaps
    print(f"Moving {len(to_discard_remote)} remote overlaps...")
    for cid in to_discard_remote:
        # Check if it wasn't already deleted by internal check
        cur.execute("SELECT 1 FROM cie_review WHERE cie_id = ?", (cid,))
        if cur.fetchone():
            cur.execute("INSERT INTO cie_discarded SELECT *, 'Remote Overlap (Larth Dataset)' FROM cie_review WHERE cie_id = ?", (cid,))
            cur.execute("DELETE FROM cie_review WHERE cie_id = ?", (cid,))
            
    conn.commit()
    
    # 5. Final Counts
    cur.execute("SELECT COUNT(*) FROM cie_review")
    remaining = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM cie_discarded")
    discarded = cur.fetchone()[0]
    
    print(f"Quarantine Complete.")
    print(f"Records Remaining (Unique): {remaining}")
    print(f"Records Quarantined (Discarded): {discarded}")
    
    conn.close()

if __name__ == "__main__":
    execute_quarantine()
