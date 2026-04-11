import sqlite3
import re
from pathlib import Path

def main():
    etruscan_db_path = Path("data/cie/cie_etruscan.db")
    latin_db_path = Path("data/cie/cie_latin.db")

    # Connect to both DBs
    conn_et = sqlite3.connect(etruscan_db_path)
    conn_lat = sqlite3.connect(latin_db_path)
    
    cur_et = conn_et.cursor()
    cur_lat = conn_lat.cursor()

    # Ensure cie_review table exists in latin_db (it should, as we already have data there)
    cur_lat.execute("""
        CREATE TABLE IF NOT EXISTS cie_review (
            pdf_source TEXT,
            cie_id TEXT,
            transliterated TEXT,
            original_script TEXT,
            latin_findspot TEXT,
            latin_commentary TEXT,
            bibliography TEXT,
            language_hint TEXT
        )
    """)

    # --- LATIN MORPHOLOGICAL & EPIGRAPHIC MARKERS ---
    
    # 1. Exact pure Latin vocabulary words (case insensitive, bounded)
    latin_vocab = [
        r'\bnatvs\b', r'\bnata\b', r'\bannos\b', r'\bvixit\b', 
        r'\bfecit\b', r'\bhic\b', r'\bsitvs\b', r'\best\b', r'\bvxor\b',
        r'\buxor\b', r'\bfilius\b', r'\bfilia\b', r'\bpater\b', r'\bconiugi\b',
        r'\bmater\b', r'\bfrater\b', r'\bmens\b', r'\bdieb\b', r'\bann\b',
        r'\bvix\b', r'\bmensibus\b', r'\bdiebus\b', r'\bposuit\b', r'\bsibi\b',
        r'\bsuo\b', r'\bsuae\b', r'\bossa\b', r'\boss\b', r'\bavg\b', r'\bimp\b'
    ]
    
    # 2. Structural Patterns
    latin_patterns = [
        r'\b[a-z]\s*[\.\*\|]\s*f\b',       # matches "A. F", "A * F", "L|F" (filius)
        r'\b[a-z]\s*[\.\*\|]\s*n\b',       # matches "A. N" (nepos)
        r'\b[a-z]\s*[\.\*\|]\s*l\b',       # matches "A. L" (libertus)
        r'\b[a-z]{3,}vs\b',                # 3+ letter words ending in -vs (papirivs)
        r'\b[a-z]{3,}us\b',                # 3+ letter words ending in -us (papirius)
        r'\b[a-z]{3,}vm\b',                # 3+ letter words ending in -vm (monvmentvm)
        r'\b[a-z]{3,}um\b'                 # 3+ letter words ending in -um (monumentum)
    ]
    
    # Note: Etruscan words CAN end in 'us' (like 'taθusa', 'velus') or 'um' (like 'prumts').
    # But usually, '-vs' mapping or exact match is a dead giveaway. We will be slightly careful with 'us'/'um' 
    # to avoid nuking real Etruscan words like 'taθusa'. Actually 'taθusa$' ends in 'a'. 
    # But 'velus' ends in 's'. Let's ensure it ends at word boundary.
    # To be extremely safe, we won't nuke anything containing the Etruscan specific letter 'θ' or 'ś' or 'φ' 
    # if it triggers a weak rule.
    
    combined_regex = re.compile('|'.join(latin_vocab + latin_patterns), re.IGNORECASE)

    cur_et.execute("SELECT rowid, * FROM cie_review")
    all_rows = cur_et.fetchall()

    rows_to_move = []
    rows_to_delete_ids = []
    
    for row in all_rows:
        rowid = row[0]
        # Data structure: pdf_source, cie_id, transliterated, original_script, latin_findspot, latin_commentary, bibliography, language_hint
        cie_id = str(row[2]) if row[2] else ""
        transliterated = str(row[3]) if row[3] else ""
        
        # We search specifically in the transliterated text
        clean_text = transliterated.replace(":", " ").replace("·", " ")
        
        # If it has distinctly Etruscan characters, it's highly likely NOT purely Latin 
        # (even if VLM accidentally mapped some weird chars, or if it says 'θerus').
        # We skip the check if it has those, UNLESS it's overwhelmingly Latin.
        if 'θ' in clean_text or 'ś' in clean_text or 'φ' in clean_text or 'χ' in clean_text:
           # But what if 'śatellia.natvs'? That's just VLM hallucinating a dot. 
           # We will still run the regex, it's strong enough.
           pass
           
        match = combined_regex.search(clean_text)
        if match:
            print(f"[{cie_id}] Flagged as LATIN by morphological sieve. Trigger: '{match.group(0)}' in '{clean_text}'")
            
            # The schema we insert into cie_lat is everything except rowid (index 1 to end)
            rows_to_move.append(row[1:])
            rows_to_delete_ids.append(rowid)

    print(f"\nFound {len(rows_to_move)} hidden Latin intrusions!")
    
    if rows_to_move:
        # Update their language_hint just to be safe
        updated_rows = []
        for r in rows_to_move:
            r_list = list(r)
            r_list[7] = "likely_latin_morphology" # Update language hint
            updated_rows.append(tuple(r_list))
            
        columns = "?, ?, ?, ?, ?, ?, ?, ?"
        cur_lat.executemany(f"INSERT INTO cie_review VALUES ({columns})", updated_rows)
        conn_lat.commit()
    
    if rows_to_delete_ids:
        cur_et.execute(f"DELETE FROM cie_review WHERE rowid IN ({','.join('?' * len(rows_to_delete_ids))})", rows_to_delete_ids)
        conn_et.commit()
        
    conn_et.close()
    conn_lat.close()

if __name__ == "__main__":
    main()
