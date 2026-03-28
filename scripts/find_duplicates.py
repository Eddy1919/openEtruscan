#!/usr/bin/env python3
import difflib
import re
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "corpus.db"
OUTPUT_REPORT = REPO_ROOT / "data" / "cie_larth_duplicates.md"

def normalize_text(text):
    if not text:
        return ""
    # Lowercase, remove spaces, and strip punctuation
    text = text.lower()
    text = re.sub(r'[\s\.\:\,\;\|\-\[\]\(\)]', '', text)
    # the Etruscan texts might have specific characters like θ (theta), χ (chi), σ (sigma), φ (phi)
    # and unicode variants. We leave them as is, just removing non-alphanumeric separators.
    return text

def find_duplicates(similarity_threshold=0.85):
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    print("Loading Larth dataset...")
    c.execute("SELECT id, canonical, raw_text FROM inscriptions WHERE source LIKE '%Larth%'")
    larth_records = c.fetchall()

    # Pre-compute normalized texts for Larth
    larth_normalized = []
    for row in larth_records:
        text_to_compare = row[1] if row[1] else row[2]
        larth_normalized.append((row[0], row[1], row[2], normalize_text(text_to_compare)))

    print(f"Loaded {len(larth_records)} Larth records.")

    print("Loading CIE VLM Explored dataset...")
    c.execute("SELECT id, canonical, raw_text FROM inscriptions WHERE source LIKE '%CIE%VLM%'")
    cie_records = c.fetchall()
    print(f"Loaded {len(cie_records)} CIE records.\n")

    conn.close()

    exact_matches = []
    fuzzy_matches = []

    print("Comparing texts to find duplicates...")

    for cie_id, cie_canon, cie_raw in cie_records:
        text_to_compare = cie_canon if cie_canon else cie_raw
        if not text_to_compare:
            continue

        cie_norm = normalize_text(text_to_compare)
        if len(cie_norm) < 3: # Skip very short inscriptions to avoid false positives
            continue

        best_match = None
        highest_ratio = 0.0

        for larth_id, larth_canon, _larth_raw, larth_norm in larth_normalized:
            # Exact match check
            if cie_norm == larth_norm:
                exact_matches.append((cie_id, cie_canon, larth_id, larth_canon))
                best_match = None # Reset so we don't also add to fuzzy
                break

            # Fuzzy match check
            ratio = difflib.SequenceMatcher(None, cie_norm, larth_norm).ratio()
            if ratio > highest_ratio:
                highest_ratio = ratio
                best_match = (larth_id, larth_canon, ratio)

        if best_match and highest_ratio >= similarity_threshold:
            fuzzy_matches.append((cie_id, cie_canon, best_match[0], best_match[1], highest_ratio))

    print(f"\nFound {len(exact_matches)} exact matches.")
    print(f"Found {len(fuzzy_matches)} fuzzy matches (>= {similarity_threshold*100}% similarity).")

    # Generate Report
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.write("# CIE vs Larth Overlap Report\n\n")
        f.write(
            "This report identifies potential duplicates between the new CIE VLM ingestion "
            "and the existing Larth (Etruskische Texte) dataset base on text similarity.\n\n"
        )

        f.write("## Exact Matches\n")
        f.write(
            "Documents whose text, after removing spaces and punctuation, "
            "is completely identical.\n\n"
        )
        f.write("| CIE ID | CIE Text | Larth ID | Larth Text |\n")
        f.write("|--------|----------|----------|------------|\n")
        for cie_id, cie_txt, larth_id, larth_txt in exact_matches:
            # simple escaping for markdown pipe
            c_t = str(cie_txt).replace('|', '\\|').replace('\n', ' ')
            l_t = str(larth_txt).replace('|', '\\|').replace('\n', ' ')
            f.write(f"| {cie_id} | {c_t} | {larth_id} | {l_t} |\n")

        f.write("\n## Fuzzy Matches\n")
        f.write(
            f"Documents whose normalized text is at least "
            f"{similarity_threshold*100}% similar.\n\n"
        )
        f.write("| CIE ID | CIE Text | Larth ID | Larth Text | Similarity |\n")
        f.write("|--------|----------|----------|------------|------------|\n")

        # Sort fuzzy matches by ratio (highest first)
        fuzzy_matches.sort(key=lambda x: x[4], reverse=True)
        for cie_id, cie_txt, larth_id, larth_txt, ratio in fuzzy_matches:
            c_t = str(cie_txt).replace('|', '\\|').replace('\n', ' ')
            l_t = str(larth_txt).replace('|', '\\|').replace('\n', ' ')
            f.write(f"| {cie_id} | {c_t} | {larth_id} | {l_t} | {ratio:.2f} |\n")

    print(f"\nReport written to: {OUTPUT_REPORT}")

if __name__ == "__main__":
    find_duplicates()
