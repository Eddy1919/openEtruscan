import sqlite3
import re
from pathlib import Path

# Paths
repo_root = Path(__file__).resolve().parent.parent.parent
ranges_db = repo_root / 'data' / 'cie' / 'databases' / 'cie_ranges.db'
report_path = repo_root / 'data' / 'cie' / 'range_decomposition_report.md'

def parse_range(val):
    val = val.strip().lower()
    
    # Ex: '486 et 487' or '486 e 487'
    et_match = re.search(r'^(\d+)\s+(?:et|e)\s+(\d+)$', val)
    if et_match:
        start, end = int(et_match.group(1)), int(et_match.group(2))
        return [str(start), str(end)]
        
    # Ex: '489-491' or '489 - 491'
    dash_match = re.search(r'^(\d+)\s*-\s*(\d+)$', val)
    if dash_match:
        start, end = int(dash_match.group(1)), int(dash_match.group(2))
        return [str(x) for x in range(start, end + 1)]
        
    # Ex: '489, 490, 491'
    comma_match = re.fullmatch(r'(\d+)(\s*,\s*\d+)+', val)
    if comma_match:
        pieces = re.findall(r'\d+', val)
        return pieces
        
    # Ex: '1000 a' or '1000 bis' (Not necessarily a range to split numerically, could just be one item, 
    # but we will only parse clean numeric expansions here).
    return []

def generate_report():
    if not ranges_db.exists():
        print(f"File not found: {ranges_db}")
        return
        
    conn = sqlite3.connect(ranges_db)
    cur = conn.cursor()
    cur.execute("SELECT cie_id, transliterated, latin_findspot FROM cie_review")
    rows = cur.fetchall()
    
    parsed_ranges = []
    unparseable = []
    
    for row in rows:
        cid_raw, text, findspot = row
        expanded = parse_range(cid_raw)
        
        if len(expanded) > 1:
            parsed_ranges.append({
                'raw': cid_raw,
                'children': expanded,
                'text_preview': str(text).replace('\n', ' ')[:40] if text else '',
                'findspot': findspot
            })
        else:
            unparseable.append(cid_raw)
            
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# [GATE 2] Range Decomposition Map\n\n")
        f.write(f"Parsed **{len(parsed_ranges)}** compound entries into individual unique inscriptions.\n")
        f.write(f"The child records will inherit the entire commentary and parent record context.\n\n")
        
        f.write("### Successful Decompositions\n")
        f.write("| Raw CIE ID | Unpacked IDs (Count) | Text Snippet | Findspot |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        
        total_children = 0
        for p in parsed_ranges:
            total_children += len(p['children'])
            children_str = f"**{len(p['children'])}** ({', '.join(p['children'])})"
            snip = p['text_preview']
            if len(snip) == 40: snip += "..."
            fs = str(p['findspot'])[:30]
            f.write(f"| `{p['raw']}` | {children_str} | {snip} | {fs} |\n")
            
        f.write(f"\\n**Total new individual records to be inserted:** {total_children}\\n\\n")    
        
        if unparseable:
            f.write("### Unparseable / Single Items\n")
            f.write("The following items contained non-standard syntax or were not split:\n")
            # Just print first 20
            f.write(", ".join([f"`{u}`" for u in unparseable[:20]]))
            if len(unparseable) > 20:
                f.write(f" ... and {len(unparseable)-20} more.")
                
    print(f"Report generated at {report_path} with {len(parsed_ranges)} parsable ranges yielding {total_children} records.")

if __name__ == "__main__":
    generate_report()
