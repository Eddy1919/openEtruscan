import sqlite3
import re
from pathlib import Path

def normalize_etruscan(text):
    if not text:
        return ""
    # Lowercase
    text = text.lower()
    # Normalize s and ś
    text = text.replace("ś", "s")
    # Strip non-alphanumeric
    text = re.sub(r"[^a-z0-9]", "", text)
    return text

def flag_duplicates():
    db_path = Path("data/cie/databases/cie_etruscan.db")
    report_path = Path("data/cie/duplicate_flag_report.md")
    
    if not db_path.exists():
        print(f"Error: {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute("SELECT cie_id, transliterated, latin_findspot, latin_commentary, pdf_source FROM cie_review")
    rows = cur.fetchall()
    
    # Grouping logic
    clusters = {}
    for r in rows:
        cid, trans, find, comm, pdf = r
        key = (normalize_etruscan(trans), normalize_etruscan(find))
        
        # Skip grouped ranges or N/A placeholders if they are the only ones
        if not key[0] and not key[1]:
            continue
            
        if key not in clusters:
            clusters[key] = []
        clusters[key].append({
            "id": cid,
            "text": trans,
            "findspot": find,
            "comment": comm,
            "pdf": pdf
        })
        
    # Filtering for actual duplicates
    duplicate_clusters = {k: v for k, v in clusters.items() if len(v) > 1}
    
    with open(report_path, "w") as f:
        f.write("# CIE Duplicate Flag Report\n\n")
        f.write(f"Found **{len(duplicate_clusters)}** clusters of potential duplicates using fuzzy text normalization (s == ś).\n\n")
        
        for i, (key, cluster) in enumerate(duplicate_clusters.items(), 1):
            f.write(f"### Cluster {i}: `{key[0] if key[0] else '[Empty Text]'}`\n")
            f.write(f"Location: `{cluster[0]['findspot']}`\n\n")
            f.write("| CIE ID | Original Text | Commentary | PDF |\n")
            f.write("| :--- | :--- | :--- | :--- |\n")
            for item in cluster:
                # Truncate comment for readability
                comm = (item['comment'][:50] + "...") if item['comment'] and len(item['comment']) > 50 else item['comment']
                f.write(f"| {item['id']} | {item['text']} | {comm} | {item['pdf']} |\n")
            f.write("\n---\n")
            
    print(f"Report generated: {report_path} with {len(duplicate_clusters)} clusters.")
    conn.close()

if __name__ == "__main__":
    flag_duplicates()
