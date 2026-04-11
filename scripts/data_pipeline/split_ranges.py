import sqlite3
import re
from pathlib import Path

def main():
    etruscan_db_path = Path("data/cie/cie_etruscan.db")
    ranges_db_path = Path("data/cie/cie_ranges.db")

    if ranges_db_path.exists():
        ranges_db_path.unlink()

    # Connect to both DBs
    conn_et = sqlite3.connect(etruscan_db_path)
    # create table in ranges
    conn_rg = sqlite3.connect(ranges_db_path)
    
    # Mirror schema
    conn_et.backup(conn_rg)
    conn_rg.execute("DELETE FROM cie_review")
    conn_rg.commit()

    cur_et = conn_et.cursor()
    cur_rg = conn_rg.cursor()

    # Find all ranges
    # Matches '1339-1341', '486 et 487', '486 e 487' etc.
    range_regex = re.compile(r'^(\d+)\s*(?:-|et|e)\s*(\d+)$')
    
    cur_et.execute("SELECT rowid, cie_id, * FROM cie_review")
    all_rows = cur_et.fetchall()

    rows_to_move = set()
    rows_to_delete = set()
    
    # 1. Identify ranges
    for row in all_rows:
        rowid = row[0]
        cie_id = str(row[1]).strip()
        
        # Check for bad IDs (no digits at all, e.g. MAVCIA)
        if not any(char.isdigit() for char in cie_id):
            print(f"Nuking bad row '{cie_id}'...")
            rows_to_delete.add(rowid)
            continue
            
        match = range_regex.search(cie_id)
        if match:
            start_num = int(match.group(1))
            end_num = int(match.group(2))
            
            # Move the container itself
            rows_to_move.add(rowid)
            
            # Find any rows underneath that range
            for sub_row in all_rows:
                sub_rowid = sub_row[0]
                sub_cie_id = str(sub_row[1]).strip()
                # Check if sub_cie_id is exactly a number within the range
                if sub_cie_id.isdigit():
                    sub_num = int(sub_cie_id)
                    if start_num <= sub_num <= end_num:
                        rows_to_move.add(sub_rowid)

    print(f"Found {len(rows_to_move)} rows related to hyphen/et ranges.")
    
    # Copy to ranges DB
    if rows_to_move:
        cur_et.execute(f"SELECT * FROM cie_review WHERE rowid IN ({','.join('?' * len(rows_to_move))})", list(rows_to_move))
        copy_rows = cur_et.fetchall()
        
        columns = "?, ?, ?, ?, ?, ?, ?, ?"
        cur_rg.executemany(f"INSERT INTO cie_review VALUES ({columns})", copy_rows)
        conn_rg.commit()
    
    # Delete from Etruscan DB
    if rows_to_delete or rows_to_move:
        all_del = rows_to_delete.union(rows_to_move)
        cur_et.execute(f"DELETE FROM cie_review WHERE rowid IN ({','.join('?' * len(all_del))})", list(all_del))
        conn_et.commit()
        
    conn_et.close()
    conn_rg.close()

if __name__ == "__main__":
    main()
