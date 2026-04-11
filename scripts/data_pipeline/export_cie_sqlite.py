#!/usr/bin/env python3
"""
Export CIE VLM extractions to a local SQLite database for clean manual review.
This avoids the CSV newline pollution problem while maintaining strict tabular formats.
"""

import json
import sqlite3
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CIE_DIR = REPO_ROOT / "data/cie"
OUTPUT_DB = CIE_DIR / "cie_export_review.db"

# Etruscan phonology: lacks B, D, G, O in transliteration.
LATIN_CHARS = {'b', 'd', 'g', 'o'}

def detect_language(text):
    """
    Returns 'likely_latin' if the text contains characters known to be absent in Etruscan.
    Otherwise returns 'etruscan_candidate'.
    """
    if not text:
        return "unknown"
    
    text_lower = text.lower()
    for char in LATIN_CHARS:
        if char in text_lower:
            return "likely_latin"
    
    # Simple check for common Etruscan keywords to boost confidence
    keywords = {'mi', 'larth', 'avil', 'clan', 'sec', 'turan', 'tin', 'uni'}
    words = set(text_lower.replace('•', ' ').replace('.', ' ').split())
    if words.intersection(keywords):
        return "etruscan_confident"
        
    return "etruscan_candidate"

def clean_text(text):
    """Clean string for DB insertion."""
    if not text:
        return ""
    # Optional: replace newlines with a special character or space if you want strict 1-line-per-row visually
    # text = text.replace('\n', ' | ').replace('\r', '')
    return text.strip()

def main():
    # Setup DB
    if OUTPUT_DB.exists():
        OUTPUT_DB.unlink()
        
    conn = sqlite3.connect(OUTPUT_DB)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE cie_review (
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
    
    all_rows = []
    
    # Iterate through all pages folders
    for pages_dir in CIE_DIR.glob("pages_*"):
        if not pages_dir.is_dir():
            continue
            
        pdf_source = pages_dir.name.replace("pages_", "")
        
        for json_file in sorted(pages_dir.glob("page_*.json")):
            try:
                content = json_file.read_text().strip()
                if not content or content == "[]":
                    continue
                
                entries = json.loads(content)
                if not isinstance(entries, list):
                    continue
                    
                for entry in entries:
                    cie_id = clean_text(entry.get("cie_id", "UNKNOWN"))
                    transliterated = clean_text(entry.get("etruscan_text_transliterated", ""))
                    original = clean_text(entry.get("etruscan_text_original", ""))
                    findspot = clean_text(entry.get("latin_findspot", ""))
                    commentary = clean_text(entry.get("latin_commentary", ""))
                    biblio = clean_text(entry.get("bibliography", ""))
                    
                    lang_hint = detect_language(transliterated)
                    
                    all_rows.append((
                        cie_id,
                        lang_hint,
                        transliterated,
                        findspot,
                        commentary,
                        biblio,
                        pdf_source,
                        original
                    ))
            except Exception as e:
                print(f"Error processing {json_file}: {e}")

    # Bulk insert
    cursor.executemany("""
        INSERT INTO cie_review (
            cie_id, language_hint, transliterated, latin_findspot, latin_commentary, bibliography, pdf_source, original_script
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, all_rows)
    
    conn.commit()
    conn.close()

    print(f"Successfully exported {len(all_rows)} entries to SQLite at: {OUTPUT_DB}")

if __name__ == "__main__":
    main()
