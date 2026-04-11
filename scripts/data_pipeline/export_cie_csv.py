#!/usr/bin/env python3
"""
Export CIE VLM extractions to CSV for manual review.
Detects potential Latin intrusions based on phonological heuristics.
"""

import json
import csv
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CIE_DIR = REPO_ROOT / "data/cie"
OUTPUT_CSV = CIE_DIR / "cie_export_review.csv"

# Etruscan phonology: lacks B, D, G, O in transliteration.
LATIN_CHARS = {'b', 'd', 'g', 'o'}

def detect_language(text):
    """
    Returns 'latin' if the text contains characters known to be absent in Etruscan.
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

def main():
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
                    cie_id = entry.get("cie_id", "UNKNOWN")
                    transliterated = entry.get("etruscan_text_transliterated", "")
                    original = entry.get("etruscan_text_original", "")
                    findspot = entry.get("latin_findspot", "")
                    commentary = entry.get("latin_commentary", "")
                    biblio = entry.get("bibliography", "")
                    
                    lang_hint = detect_language(transliterated)
                    
                    all_rows.append({
                        "cie_id": cie_id,
                        "language_hint": lang_hint,
                        "transliterated": transliterated,
                        "latin_findspot": findspot,
                        "latin_commentary": commentary,
                        "bibliography": biblio,
                        "pdf_source": pdf_source,
                        "original_script": original
                    })
            except Exception as e:
                print(f"Error processing {json_file}: {e}")

    # Write to CSV
    fields = ["cie_id", "language_hint", "transliterated", "latin_findspot", "latin_commentary", "bibliography", "pdf_source", "original_script"]
    
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Successfully exported {len(all_rows)} entries to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
