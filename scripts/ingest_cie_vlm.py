#!/usr/bin/env python3
import os
import json
import sqlite3
import time
import base64
import requests
from io import BytesIO
from typing import List, Optional
from pathlib import Path

import pypdfium2 as pdfium

# Setup paths
REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data/corpus.db"
PDF_PATH = REPO_ROOT / "data/cie/CIE-I_tit.1_474.pdf"

# Load API Key securely from environment (e.g., in .env)
import os
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set. Please set it securely in .env")

# We define the JSON schema to pass to the REST API
SCHEMA = {
  "type": "OBJECT",
  "properties": {
    "entries": {
      "type": "ARRAY",
      "items": {
        "type": "OBJECT",
        "properties": {
          "cie_id": { "type": "STRING", "description": "The CIE number (e.g., '192', 'CIE 192')" },
          "etruscan_text_transliterated": { "type": "STRING", "description": "Transliterated Etruscan text in Latin characters" },
          "etruscan_text_original": { "type": "STRING", "nullable": True, "description": "Original Etruscan characters if possible" },
          "latin_findspot": { "type": "STRING", "description": "Findspot in Latin (e.g., 'Clusii in agro', 'Perusiae')" },
          "latin_commentary": { "type": "STRING", "description": "Latin commentary/notes" },
          "bibliography": { "type": "STRING", "nullable": True, "description": "References to other corpora" }
        },
        "required": ["cie_id", "etruscan_text_transliterated", "latin_findspot", "latin_commentary"]
      }
    }
  },
  "required": ["entries"]
}

def extract_page_images(pdf_path: Path, start_page: int, num_pages: int):
    print(f"Loading PDF: {pdf_path}")
    pdf = pdfium.PdfDocument(str(pdf_path))
    images = []
    total_pages = len(pdf)
    end_page = min(start_page + num_pages, total_pages)
    
    for i in range(start_page, end_page):
        page = pdf[i]
        bitmap = page.render(scale=200/72)
        pil_image = bitmap.to_pil()
        images.append((i, pil_image))
    return images

def process_with_gemini_rest(pil_image, retries=3):
    # Convert PIL to base64 jpeg
    buffered = BytesIO()
    pil_image.save(buffered, format="JPEG")
    img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    
    prompt = """
    You are an expert classicist and epigrapher. Examine this scanned page from the Corpus Inscriptionum Etruscarum (1893).
    The page contains entries for Etruscan inscriptions. Each entry typically starts with a large number (the CIE ID).
    Under the number is the findspot in Latin (e.g., "Clusii in agro", "Perusiae", "Volaterris").
    Following that is a description, bibliography, and the actual Etruscan text (often written both in Etruscan script right-to-left and transliterated).
    
    Extract all entries on this page into a structured format.
    Pay extreme attention to the transliterated Etruscan text and try your best to replicate the bizarre Etruscan font if possible.
    """
    
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "response_mime_type": "application/json",
            "response_schema": SCHEMA
        }
    }
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"
    
    for attempt in range(retries):
        try:
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                text_out = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text_out)
            elif resp.status_code == 429:
                print(f"    [Retry {attempt+1}] Rate limited (429). Sleeping 10s...")
                time.sleep(10)
            else:
                print(f"    [Retry {attempt+1}] API Error {resp.status_code}: {resp.text[:200]}")
                time.sleep(5)
        except Exception as e:
            print(f"    [Retry {attempt+1}] Network Exception: {e}")
            time.sleep(5)
            
    return None

def ingest_into_db(entries):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    inserted = 0
    for entry in entries:
        canonical_id = entry.get("cie_id", "").replace("CIE ", "").replace("CIE", "").strip()
        formatted_id = f"CIE {canonical_id}"
        
        cursor.execute("SELECT id FROM inscriptions WHERE id=?", (formatted_id,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO inscriptions (
                    id, canonical, raw_text, findspot, notes, bibliography, source, provenance_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                formatted_id, 
                entry.get("etruscan_text_transliterated", ""),
                entry.get("etruscan_text_original") or entry.get("etruscan_text_transliterated", ""),
                entry.get("latin_findspot", ""),
                entry.get("latin_commentary", ""),
                entry.get("bibliography", ""),
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
        print(f"Processing page {page_num} with Gemini 2.5 Flash REST API...")
        extraction = process_with_gemini_rest(img)
        
        if extraction and "entries" in extraction:
            count = len(extraction["entries"])
            total_entries += count
            print(f"  ✅ Found {count} entries on page {page_num}")
            all_extracted_data.extend(extraction["entries"])
        else:
            print(f"  ⚠️ No entries found or error on page {page_num}")
            
        time.sleep(2) # Normal polite delay
            
    if all_extracted_data:
        print(f"\nIngesting {total_entries} extracted records into DB...")
        inserted = ingest_into_db(all_extracted_data)
        print(f"✅ Ingested {inserted} new records into corpus.db")
        
        dump_path = REPO_ROOT / "data/cie/sample_extraction.json"
        with open(dump_path, "w") as f:
            json.dump(all_extracted_data, f, indent=2)
        print(f"Raw JSON output saved to {dump_path}")

if __name__ == "__main__":
    main()
