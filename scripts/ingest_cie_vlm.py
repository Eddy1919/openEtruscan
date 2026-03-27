import os
import json
import sqlite3
import time
import sqlite3
from typing import List, Optional
from pathlib import Path

import pypdfium2 as pdfium
from pydantic import BaseModel, Field
from google import genai

# Setup paths
REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data/corpus.db"
PDF_PATH = REPO_ROOT / "data/cie/CIE-I_tit.1_474.pdf"

# Initialize Gemini Client
API_KEY = "AIzaSyDxTslfmx-B54r6uIOhWhEcCYNBOaqISY4"
client = genai.Client(api_key=API_KEY)

class CIEEntry(BaseModel):
    cie_id: str = Field(description="The CIE number of the inscription (e.g., '192', 'CIE 192')")
    etruscan_text_transliterated: str = Field(description="The transliterated Etruscan text in Latin characters")
    etruscan_text_original: Optional[str] = Field(description="The original text in Etruscan characters, if possible to transcribe")
    latin_findspot: str = Field(description="The findspot written in Latin (e.g., 'Clusii in agro', 'Perusiae')")
    latin_commentary: str = Field(description="The Latin commentary / notes describing the inscription context")
    bibliography: Optional[str] = Field(description="References to other corpora (e.g., Fabretti, Gamurrini) mentioned in the commentary")

class PageExtraction(BaseModel):
    entries: List[CIEEntry] = Field(description="List of all Etruscan inscription entries found on the page")

def extract_page_images(pdf_path: Path, start_page: int, num_pages: int):
    print(f"Loading PDF: {pdf_path}")
    pdf = pdfium.PdfDocument(str(pdf_path))
    images = []
    
    # Safely handle page bounds
    total_pages = len(pdf)
    end_page = min(start_page + num_pages, total_pages)
    
    for i in range(start_page, end_page):
        page = pdf[i]
        # Render at 200 DPI
        bitmap = page.render(scale=200/72)
        pil_image = bitmap.to_pil()
        images.append((i, pil_image))
    return images

def process_with_gemini(pil_image) -> PageExtraction:
    prompt = """
    You are an expert classicist and epigrapher. Examine this scanned page from the Corpus Inscriptionum Etruscarum (1893).
    The page contains entries for Etruscan inscriptions. Each entry typically starts with a large number (the CIE ID).
    Under the number is the findspot in Latin (e.g., "Clusii in agro", "Perusiae", "Volaterris").
    Following that is a description, bibliography, and the actual Etruscan text (often written both in Etruscan script right-to-left and transliterated).
    
    Extract all entries on this page into a structured format.
    Pay extreme attention to the transliterated Etruscan text and try your best to replicate the bizarre Etruscan font if possible, though the transliteration is most important.
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[pil_image, prompt],
        config={
            'response_mime_type': 'application/json',
            'response_schema': PageExtraction,
            'temperature': 0.1
        },
    )
    
    return response.parsed

def ingest_into_db(entries: List[CIEEntry]):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    inserted = 0
    for entry in entries:
        canonical_id = entry.cie_id.replace("CIE ", "").replace("CIE", "").strip()
        formatted_id = f"CIE {canonical_id}"
        
        # Check if exists
        cursor.execute("SELECT id FROM inscriptions WHERE id=?", (formatted_id,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO inscriptions (
                    id, canonical, raw_text, findspot, notes, bibliography, source, provenance_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                formatted_id, 
                entry.etruscan_text_transliterated,
                entry.etruscan_text_original or entry.etruscan_text_transliterated,
                entry.latin_findspot,
                entry.latin_commentary,
                entry.bibliography or "",
                "CIE Volume I (VLM Extracted)",
                "extracted"
            ))
            inserted += 1
            
    conn.commit()
    conn.close()
    return inserted

def main():
    if not PDF_PATH.exists():
        print("PDF not found!")
        return
        
    print("Extracting 10 pages for sample (pages 50 to 59)...")
    images = extract_page_images(PDF_PATH, start_page=50, num_pages=10)
    
    total_entries = 0
    all_extracted_data = []
    
    for page_num, img in images:
        print(f"Processing page {page_num} with Gemini 2.5 Flash...")
        try:
            extraction = process_with_gemini(img)
            
            if extraction.entries:
                count = len(extraction.entries)
                total_entries += count
                print(f"  ✅ Found {count} entries on page {page_num}")
                all_extracted_data.extend(extraction.entries)
            else:
                print(f"  ⚠️ No entries found on page {page_num}")
                
        except Exception as e:
            print(f"  ❌ Error on page {page_num}: {e}")
            
        time.sleep(5) # Prevent rate limiting
            
    if all_extracted_data:
        print(f"\nIngesting {total_entries} extracted records into DB...")
        inserted = ingest_into_db(all_extracted_data)
        print(f"✅ Ingested {inserted} new records into corpus.db")
        
        # Save raw JSON dump for verification
        dump_path = REPO_ROOT / "data/cie/sample_extraction.json"
        
        # Convert pydantic models to dicts for dumping
        dump_data = [e.model_dump() for e in all_extracted_data]
        
        with open(dump_path, "w") as f:
            json.dump(dump_data, f, indent=2)
        print(f"Raw JSON output saved to {dump_path}")

if __name__ == "__main__":
    main()
