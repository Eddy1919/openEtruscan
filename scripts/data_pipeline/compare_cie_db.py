#!/usr/bin/env python3
import csv
import psycopg2
import re
from pathlib import Path
from openetruscan.core.normalizer import normalize

DB_URL = "postgresql://corpus_reader:etruscan_secret@34.76.146.115/corpus"
CSV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cie" / "cie_export_review.csv"

def main():
    print("Connecting to live database to fetch canonical texts...")
    conn = psycopg2.connect(DB_URL)
    with conn.cursor() as cur:
        cur.execute("SELECT id, canonical FROM inscriptions WHERE canonical != ''")
        db_records = cur.fetchall()
        
    print(f"Fetched {len(db_records)} records from the database.")
    
    # Pre-process DB records for faster substring searching
    db_list = [{"id": r[0], "canonical": r[1]} for r in db_records]
    
    print("Reading CSV and comparing...")
    matches_found = 0
    total_checked = 0
    
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["language_hint"] == "likely_latin":
                continue # Skip Latin for now
                
            translit = row["transliterated"]
            if not translit or len(translit) < 3:
                continue
                
            try:
                # Normalize the entry to Etruscan canonical format
                norm_res = normalize(translit, language="etruscan")
                candidate_canon = norm_res.canonical
                
                # Require exact match of normalized string or significant substring
                # To prevent tiny DB fragments like 'ti' matching 'titi'
                
                # Tokenize normalized candidate
                cand_words = set(candidate_canon.lower().replace('-', ' ').replace(':', ' ').split())
                cand_words = {w for w in cand_words if len(w) > 3} # Only meaningful words
                
                if not cand_words:
                    continue
                
                total_checked += 1
                
                # Check against DB
                for db_rec in db_list:
                    db_words = set(db_rec["canonical"].lower().replace('-', ' ').replace(':', ' ').split())
                    db_words = {w for w in db_words if len(w) > 3}
                    
                    if not db_words:
                        continue
                    
                    intersection = cand_words.intersection(db_words)
                    
                    # If they share at least 2 meaningful words, OR they share 1 word that is > 6 chars
                    if len(intersection) >= 2 or any(len(w) >= 6 for w in intersection):
                        print(f"------------")
                        print(f"POTENTIAL MATCH DETECTED:")
                        print(f"  Shared Words: {intersection}")
                        print(f"  CSV ID:    {row['cie_id']}")
                        print(f"  CSV Text:  {row['transliterated']} -> {candidate_canon}")
                        print(f"  DB ID:     {db_rec['id']}")
                        print(f"  DB Text:   {db_rec['canonical']}")
                        matches_found += 1
                        break

            except Exception as e:
                pass
                
    print(f"\nChecked {total_checked} Etruscan candidates from CSV. Found {matches_found} potential similarities in DB.")

if __name__ == "__main__":
    main()
