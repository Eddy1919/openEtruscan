import sqlite3
import sys
import os
from pathlib import Path

# Ensure we can import from src
sys.path.append(str(Path.cwd() / "src"))

try:
    from openetruscan.core.normalizer import normalize, load_adapter
except ImportError:
    print("Error: Could not import openetruscan modules. Ensure you are in the project root.")
    sys.exit(1)

def enrich_cie():
    db_path = Path("data/cie/databases/cie_etruscan.db")
    geo_db_path = Path("data/cie/geocoding/findspots_geocoding.db")
    
    if not db_path.exists():
        print(f"Error: {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # 1. Add SOTA Columns
    new_columns = [
        ("canonical", "TEXT"),
        ("phonetic", "TEXT"),
        ("old_italic", "TEXT"),
        ("findspot_modern", "TEXT"),
        ("findspot_lat", "FLOAT"),
        ("findspot_lon", "FLOAT"),
        ("uncertainty_m", "FLOAT"),
        ("source_code", "TEXT"),
        ("source_detail", "TEXT"),
        ("original_script_entry", "TEXT"),
        ("notes", "TEXT")
    ]
    
    for col_name, col_type in new_columns:
        try:
            cur.execute(f"ALTER TABLE cie_review ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            print(f"Column {col_name} already exists, skipping.")

    conn.commit()

    # 2. Attach geocoding DB for join
    cur.execute(f"ATTACH DATABASE '{geo_db_path}' AS geo")
    
    # Update geographic fields
    print("Joining geodata...")
    cur.execute("""
        UPDATE cie_review
        SET 
            findspot_modern = (SELECT cluster_name FROM geo.unique_findspots WHERE trim(cie_review.latin_findspot) = trim(geo.unique_findspots.original_string)),
            findspot_lat = (SELECT mapbox_lat FROM geo.unique_findspots WHERE trim(cie_review.latin_findspot) = trim(geo.unique_findspots.original_string)),
            findspot_lon = (SELECT mapbox_lon FROM geo.unique_findspots WHERE trim(cie_review.latin_findspot) = trim(geo.unique_findspots.original_string)),
            uncertainty_m = (SELECT CASE WHEN distance_km IS NOT NULL THEN distance_km * 1000 ELSE 2000 END 
                            FROM geo.unique_findspots 
                            WHERE trim(cie_review.latin_findspot) = trim(geo.unique_findspots.original_string)),
            source_code = 'CIE'
    """)
    conn.commit()
    
    # 3. Philological Normalization
    print("Running normalization pipeline...")
    # Load adapter once
    adapter = load_adapter("etruscan")
    
    cur.execute("SELECT cie_id, transliterated, original_script, pdf_source, latin_commentary FROM cie_review")
    rows = cur.fetchall()
    
    total = len(rows)
    for i, row in enumerate(rows):
        cie_id, translit, orig_script, pdf, notes = row
        
        # Normalize
        norm = normalize(translit, "etruscan")
        
        # Prepare source detail
        source_detail = f"CIE Volume: {pdf}"
        
        # Handle warnings
        updated_notes = notes if notes else ""
        if norm.warnings:
            warning_text = " [Normalization Warning: " + "; ".join(norm.warnings) + "]"
            updated_notes += warning_text
            
        cur.execute("""
            UPDATE cie_review
            SET 
                canonical = ?,
                phonetic = ?,
                old_italic = ?,
                original_script_entry = ?,
                source_detail = ?,
                notes = ?
            WHERE cie_id = ?
        """, (norm.canonical, norm.phonetic, norm.old_italic, orig_script, source_detail, updated_notes, cie_id))
        
        if i % 100 == 0:
            print(f"Progress: {i}/{total} records normalized.")
            conn.commit()

    conn.commit()
    print(f"Enrichment complete for {total} records.")
    conn.close()

if __name__ == "__main__":
    enrich_cie()
