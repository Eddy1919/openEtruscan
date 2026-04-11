import sqlite3
import re
from pathlib import Path

def main():
    ranges_db_path = Path("data/cie/cie_ranges.db")
    range_latin_db_path = Path("data/cie/cie_range_latin.db")

    # Connect to both DBs
    conn_rg = sqlite3.connect(ranges_db_path)
    conn_rglat = sqlite3.connect(range_latin_db_path)
    
    cur_rg = conn_rg.cursor()
    cur_rglat = conn_rglat.cursor()

    # Mirror schema
    cur_rglat.execute("""
        CREATE TABLE IF NOT EXISTS cie_review (
            cie_id TEXT,
            language_hint TEXT,
            transliterated TEXT,
            latin_findspot TEXT,
            latin_commentary TEXT,
            bibliography TEXT,
            pdf_source TEXT,
            original_script TEXT
        )
    """)

    # 1. Phonological Sieve Pattern (B, D, G, O)
    phonological_regex = re.compile(r'[bdgo]', re.IGNORECASE)

    # 2. Morphological & Epigraphic Sieve Patterns
    latin_vocab = [
        r'\bnatvs\b', r'\bnata\b', r'\bannos\b', r'\bvixit\b', 
        r'\bfecit\b', r'\bhic\b', r'\bsitvs\b', r'\best\b', r'\bvxor\b',
        r'\buxor\b', r'\bfilius\b', r'\bfilia\b', r'\bpater\b', r'\bconiugi\b',
        r'\bmater\b', r'\bfrater\b', r'\bmens\b', r'\bdieb\b', r'\bann\b',
        r'\bvix\b', r'\bmensibus\b', r'\bdiebus\b', r'\bposuit\b', r'\bsibi\b',
        r'\bsuo\b', r'\bsuae\b', r'\bossa\b', r'\boss\b', r'\bavg\b', r'\bimp\b'
    ]
    
    latin_patterns = [
        r'\b[a-z]\s*[\.\*\|]\s*f\b',       
        r'\b[a-z]\s*[\.\*\|]\s*n\b',       
        r'\b[a-z]\s*[\.\*\|]\s*l\b',       
        r'\b[a-z]{3,}vs\b',                
        r'\b[a-z]{3,}us\b',                
        r'\b[a-z]{3,}vm\b',                
        r'\b[a-z]{3,}um\b'                 
    ]
    
    combined_morph_regex = re.compile('|'.join(latin_vocab + latin_patterns), re.IGNORECASE)

    # 3. Etruscan Genitive Rescue Words
    safe_words = ['velus', 'venelus', 'pumpus', 'fusumus', 'secus', 'cecus', 'cicus', 'farus', 'haltus', 'chius', 'plaus', 'krutpuus', 'seius', 'anxvilus', 'uelus']

    cur_rg.execute("SELECT rowid, * FROM cie_review")
    all_rows = cur_rg.fetchall()

    rows_to_move = []
    rows_to_delete_ids = []
    
    for row in all_rows:
        rowid = row[0]
        # Schema: cie_id, language_hint, transliterated, latin_findspot, latin_commentary, bibliography, pdf_source, original_script
        transliterated = str(row[3]) if row[3] else ""
        clean_text = transliterated.replace(":", " ").replace("·", " ")
        
        # Check Phonological (B, D, G, O)
        is_latin = False
        trigger = ""
        
        if phonological_regex.search(clean_text):
            is_latin = True
            trigger = "phonological (bdgo)"
            
        # Check Morphological
        if not is_latin:
            match = combined_morph_regex.search(clean_text)
            if match:
                is_latin = True
                trigger = f"morphological ('{match.group(0)}')"

        # Apply Rescue for Authentic Etruscan Genitives
        if is_latin:
            # If it was caught by a trigger, check if it's a safe genitive rescue
            # but only if it lacks hardcore Latin markers (natus, vixit, .f)
            if not any(x in clean_text.lower() for x in ['natus', 'nata', '. f', '* f', 'vixit']):
                if any(w in clean_text.lower() for w in safe_words):
                    is_latin = False

        if is_latin:
            print(f"[{row[1]}] Flagged as LATIN by sieve. Trigger: {trigger} in '{clean_text}'")
            # Update hint
            r_list = list(row[1:])
            r_list[1] = "likely_latin_range"
            rows_to_move.append(tuple(r_list))
            rows_to_delete_ids.append(rowid)

    print(f"\nMoving {len(rows_to_move)} rows to cie_range_latin.db...")
    
    if rows_to_move:
        columns = "?, ?, ?, ?, ?, ?, ?, ?"
        cur_rglat.executemany(f"INSERT INTO cie_review VALUES ({columns})", rows_to_move)
        conn_rglat.commit()
    
    if rows_to_delete_ids:
        cur_rg.execute(f"DELETE FROM cie_review WHERE rowid IN ({','.join('?' * len(rows_to_delete_ids))})", rows_to_delete_ids)
        conn_rg.commit()
        
    conn_rg.close()
    conn_rglat.close()

if __name__ == "__main__":
    main()
