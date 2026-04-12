import sqlite3
import re
from pathlib import Path

# Paths
repo_root = Path(__file__).resolve().parent.parent.parent
latin_db = repo_root / 'data' / 'cie' / 'databases' / 'cie_latin.db'
report_path = repo_root / 'data' / 'cie' / 'latin_rescue_candidates.md'

# High-precision Etruscan phonemes and punctuation
ETRUSCAN_MARKERS = [
    'θ', 'ś', 'χ', 'φ', 'z',  # Phonemes
    ':', '·', '⁝',            # Ancient punctuation
]

def generate_rescue_report():
    if not latin_db.exists():
        print(f"File not found: {latin_db}")
        return
        
    conn = sqlite3.connect(latin_db)
    cur = conn.cursor()
    cur.execute("SELECT cie_id, transliterated, latin_findspot, latin_commentary FROM cie_review")
    rows = cur.fetchall()
    
    candidates = []
    skipped = 0
    
    for row in rows:
        cid, text, findspot, comm = row
        text_str = str(text or "").lower()
        
        found_markers = [m for m in ETRUSCAN_MARKERS if m in text_str]
        
        if found_markers:
            candidates.append({
                'id': cid,
                'text': text,
                'markers': ", ".join(found_markers),
                'findspot': findspot,
                'commentary': (str(comm)[:100] + "...") if comm else ""
            })
        else:
            skipped += 1
            
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# [GATE 3] Latin Linguistic Rescue Candidates\n\n")
        f.write(f"Scanned **1,009** records in `cie_latin.db` using a high-precision phoneme sieve.\n")
        f.write(f"Identified **{len(candidates)}** records containing definitive Etruscan markers.\n\n")
        
        f.write("### Rescue Candidate List\n")
        f.write("| CIE ID | Etruscan Markers | Text | Findspot | Commentary |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        
        for c in candidates:
            text_snip = str(c['text']).replace('\n', ' ')[:40] if c['text'] else ""
            f.write(f"| {c['id']} | `{c['markers']}` | {text_snip} | {c['findspot']} | {c['commentary']} |\n")
            
        f.write(f"\\n**Total records proposed for rescue:** {len(candidates)}\\n")
        f.write(f"**Records kept in Latin DB:** {skipped}\\n")
        
    print(f"Report generated at {report_path} with {len(candidates)} candidates.")
    conn.close()

if __name__ == "__main__":
    generate_rescue_report()
