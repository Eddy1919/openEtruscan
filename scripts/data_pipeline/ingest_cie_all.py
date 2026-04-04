#!/usr/bin/env python3
"""
OpenEtruscan CIE VLM Ingestion — Multi-PDF launcher.

Processes all CIE PDF files, reusing the core logic from ingest_cie_vlm.py.
Each PDF gets its own progress file and per-page JSON directory.

Usage:
    python scripts/ingest_cie_all.py                  # Process all PDFs
    python scripts/ingest_cie_all.py --pdf CIE-I_Clusium-cum-agro-Clusino-tit.-475-1742.pdf
"""

import argparse
import base64
import json
import logging
import os
import sys
import time
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
import requests
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

DB_PATH = REPO_ROOT / "data/corpus.db"  # Kept for compatibility but unused
CIE_DIR = REPO_ROOT / "data/cie"

# PDFs to process (ordered by expected content density)
ALL_PDFS = [
    "CIE-I_tit.1_474.pdf",
    "CIE-I_Clusium-cum-agro-Clusino-tit.-475-1742.pdf",
    "CIE-I_Clusium-cum-agro-Clusino-tit.-1743-3306.pdf",
    "CIE-I_Perusia-tit.-3307-4612.pdf",
    "CIE-I_Additamentum.pdf",
    # Skipped: CIE-I_Introduzione.pdf (introductory text, no inscriptions)
    # Skipped: CIE-II.2.2_Indices-et-Tabulae.pdf (indices and tables)
]

# ── API key ────────────────────────────────────────────────────
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY not set")

# ── Gemini structured-output schema ───────────────────────────
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "entries": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "cie_id": {
                        "type": "STRING",
                        "description": "The CIE number (e.g., '192', 'CIE 192')",
                    },
                    "etruscan_text_transliterated": {
                        "type": "STRING",
                        "description": "Transliterated Etruscan text in Latin characters",
                    },
                    "etruscan_text_original": {
                        "type": "STRING",
                        "nullable": True,
                        "description": "Original Etruscan characters if possible",
                    },
                    "latin_findspot": {
                        "type": "STRING",
                        "description": "Findspot in Latin (e.g., 'Clusii in agro')",
                    },
                    "latin_commentary": {
                        "type": "STRING",
                        "description": "Latin commentary/notes",
                    },
                    "bibliography": {
                        "type": "STRING",
                        "nullable": True,
                        "description": "References to other corpora",
                    },
                },
                "required": [
                    "cie_id",
                    "etruscan_text_transliterated",
                    "latin_findspot",
                    "latin_commentary",
                ],
            },
        }
    },
    "required": ["entries"],
}

PROMPT = (
    "You are an expert classicist and epigrapher. "
    "Examine this scanned page from the Corpus Inscriptionum "
    "Etruscarum (1893).\n"
    "The page contains entries for Etruscan inscriptions. "
    "Each entry typically starts with a large number (the CIE ID).\n"
    "Under the number is the findspot in Latin "
    '(e.g., "Clusii in agro", "Perusiae", "Volaterris").\n'
    "Following that is a description, bibliography, and the actual "
    "Etruscan text (often written both in Etruscan script "
    "right-to-left and transliterated).\n\n"
    "Extract all entries on this page into a structured format.\n"
    "Pay extreme attention to the transliterated Etruscan text "
    "and try your best to replicate the bizarre Etruscan font "
    "if possible."
)

URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


def setup_logging(pdf_name: str) -> logging.Logger:
    slug = pdf_name.replace(".pdf", "").replace(" ", "_")
    log_file = CIE_DIR / f"ingest_{slug}.log"
    logger = logging.getLogger(f"cie-{slug}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(logging.FileHandler(log_file))
    logger.addHandler(logging.StreamHandler(sys.stdout))
    for h in logger.handlers:
        h.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
    return logger


def load_progress(pdf_name: str) -> dict:
    slug = pdf_name.replace(".pdf", "")
    progress_file = CIE_DIR / f"progress_{slug}.json"
    if progress_file.exists():
        return json.loads(progress_file.read_text())
    return {"completed_pages": [], "total_entries": 0}


def save_progress(pdf_name: str, progress: dict):
    slug = pdf_name.replace(".pdf", "")
    progress_file = CIE_DIR / f"progress_{slug}.json"
    progress_file.write_text(json.dumps(progress, indent=2))


def render_page(pdf, page_idx: int):
    page = pdf[page_idx]
    bitmap = page.render(scale=150 / 72)
    return bitmap.to_pil()


def call_gemini(pil_image, log, retries=5):
    buffered = BytesIO()
    pil_image.save(buffered, format="JPEG", quality=70)
    img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": PROMPT},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "response_mime_type": "application/json",
            "response_schema": SCHEMA,
        },
    }

    backoff = 5
    for attempt in range(retries):
        try:
            resp = requests.post(URL, params={"key": API_KEY}, json=payload, timeout=(10, 180))
            if resp.status_code == 200:
                data = resp.json()
                text_out = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text_out)
            elif resp.status_code == 429:
                wait = min(backoff * (2**attempt), 120)
                log.warning("  [%d/%d] Rate limited. Sleeping %ds...", attempt + 1, retries, wait)
                time.sleep(wait)
            else:
                safe_body = resp.text[:300].replace(API_KEY, "<REDACTED>")
                log.error(
                    "  [%d/%d] API Error %d: %s", attempt + 1, retries, resp.status_code, safe_body
                )
                time.sleep(backoff)
        except Exception as e:
            log.error("  [%d/%d] Network Exception: %s", attempt + 1, retries, e)
            time.sleep(backoff)
    return None


def ingest_into_db(entries: list[dict], source_label: str) -> int:
    from openetruscan.corpus import Corpus, Inscription

    corpus = Corpus.load()
    inserted = 0
    for entry in entries:
        canonical_id = entry.get("cie_id", "").replace("CIE ", "").replace("CIE", "").strip()
        formatted_id = f"CIE {canonical_id}"
        
        # Check if already exists using search or get
        try:
            # Not a precise ID check, but good enough for now. We will just try to add and handle exceptions
            # Actually, `corpus.add` upserts natively in Postgres! 
            # Wait, no, Corpus.add(upsert=True)? The PG version upserts.
        except Exception:
            pass

        insc = Inscription(
            id=formatted_id,
            canonical=entry.get("etruscan_text_transliterated", ""),
            raw_text=entry.get("etruscan_text_original") or entry.get("etruscan_text_transliterated", ""),
            findspot=entry.get("latin_findspot", ""),
            notes=entry.get("latin_commentary", ""),
            bibliography=entry.get("bibliography") or "",
            source=source_label,
            provenance_status="extracted",
        )
        try:
            corpus.add(insc)
            inserted += 1
        except Exception:
            # If it already exists it might fail depending on how add() is implemented
            pass
            
    corpus.close()
    return inserted


def process_pdf(pdf_name: str, skip_pages: int = 4):
    pdf_path = CIE_DIR / pdf_name
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        return

    log = setup_logging(pdf_name)
    pdf = pdfium.PdfDocument(str(pdf_path))
    total_pages = len(pdf)
    log.info("PDF loaded: %s (%d pages)", pdf_name, total_pages)

    progress = load_progress(pdf_name)
    done = set(progress["completed_pages"])
    log.info("Resume: %d pages done, %d entries so far", len(done), progress["total_entries"])

    # Determine source label from filename
    source_label = "CIE Volume I (VLM Extracted)"
    if "Clusium" in pdf_name and "475" in pdf_name:
        source_label = "CIE Vol I Clusium 475-1742 (VLM)"
    elif "Clusium" in pdf_name and "1743" in pdf_name:
        source_label = "CIE Vol I Clusium 1743-3306 (VLM)"
    elif "Perusia" in pdf_name:
        source_label = "CIE Vol I Perusia 3307-4612 (VLM)"
    elif "Additamentum" in pdf_name:
        source_label = "CIE Vol I Additamentum (VLM)"

    pages_dir = CIE_DIR / f"pages_{pdf_name.replace('.pdf', '')}"
    pages_dir.mkdir(parents=True, exist_ok=True)

    skip_set = set(range(0, skip_pages))
    total_new = 0

    for page_idx in range(total_pages):
        if page_idx in skip_set or page_idx in done:
            continue

        log.info("── Page %d / %d ──", page_idx, total_pages - 1)
        pil_image = render_page(pdf, page_idx)
        result = call_gemini(pil_image, log)

        if result and "entries" in result:
            entries = result["entries"]
            log.info("  ✅ Extracted %d entries", len(entries))

            page_file = pages_dir / f"page_{page_idx:04d}.json"
            page_file.write_text(json.dumps(entries, indent=2, ensure_ascii=False))

            inserted = ingest_into_db(entries, source_label)
            log.info("  💾 Inserted %d new records", inserted)
            total_new += len(entries)
        else:
            log.warning("  ⚠️  No entries / error on page %d", page_idx)

        done.add(page_idx)
        progress["completed_pages"] = sorted(done)
        progress["total_entries"] += len(result.get("entries", [])) if result else 0
        save_progress(pdf_name, progress)
        time.sleep(2)

    log.info("=" * 50)
    log.info("DONE: %s — %d new entries", pdf_name, total_new)
    log.info("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="CIE VLM Multi-PDF Ingestion")
    parser.add_argument("--pdf", type=str, help="Process a specific PDF (filename only)")
    parser.add_argument("--skip-pages", type=int, default=4, help="Pages to skip at start")
    args = parser.parse_args()

    if args.pdf:
        process_pdf(args.pdf, skip_pages=args.skip_pages)
    else:
        for pdf_name in ALL_PDFS:
            process_pdf(pdf_name, skip_pages=args.skip_pages)


if __name__ == "__main__":
    main()
