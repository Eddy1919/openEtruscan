#!/usr/bin/env python3
"""
OpenEtruscan CIE VLM Ingestion — Full PDF overnight runner.

Features:
  - Processes ALL pages of the PDF (skips first ~4 title/index pages)
  - Resume support: tracks completed pages in a progress file
  - Per-page JSON dump for safety (data/cie/pages/*.json)
  - File logging + stdout for monitoring via nohup
  - Exponential backoff on rate limits
"""

import base64
import json
import logging
import os
import sqlite3
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

DB_PATH = REPO_ROOT / "data/corpus.db"
PDF_PATH = REPO_ROOT / "data/cie/CIE-I_tit.1_474.pdf"
PAGES_DIR = REPO_ROOT / "data/cie/pages"
PROGRESS_FILE = REPO_ROOT / "data/cie/progress.json"
LOG_FILE = REPO_ROOT / "data/cie/ingest.log"

PAGES_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("cie-ingest")

# ── API key ────────────────────────────────────────────────────
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError(
        "GEMINI_API_KEY environment variable is not set. Please set it securely in .env"
    )

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
                        "description": ("The CIE number (e.g., '192', 'CIE 192')"),
                    },
                    "etruscan_text_transliterated": {
                        "type": "STRING",
                        "description": ("Transliterated Etruscan text in Latin characters"),
                    },
                    "etruscan_text_original": {
                        "type": "STRING",
                        "nullable": True,
                        "description": ("Original Etruscan characters if possible"),
                    },
                    "latin_findspot": {
                        "type": "STRING",
                        "description": ("Findspot in Latin (e.g., 'Clusii in agro', 'Perusiae')"),
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

# Pages to skip (title pages, index, plates, etc.)
SKIP_PAGES = set(range(0, 4))

# ── Progress tracking ─────────────────────────────────────────


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"completed_pages": [], "total_entries": 0}


def save_progress(progress: dict):
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))


# ── PDF extraction ─────────────────────────────────────────────


def render_page(pdf, page_idx: int):
    """Render a single PDF page to a PIL image."""
    page = pdf[page_idx]
    bitmap = page.render(scale=150 / 72)  # 150 DPI
    return bitmap.to_pil()


# ── Gemini API ─────────────────────────────────────────────────

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


def call_gemini(pil_image, retries=5):
    """Send a page image to Gemini and return parsed entries."""
    buffered = BytesIO()
    pil_image.save(buffered, format="JPEG", quality=70)
    img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": PROMPT},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": img_b64,
                        }
                    },
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
            resp = requests.post(
                URL,
                params={"key": API_KEY},
                json=payload,
                timeout=(10, 180),
            )
            if resp.status_code == 200:
                data = resp.json()
                text_out = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text_out)
            elif resp.status_code == 429:
                wait = min(backoff * (2**attempt), 120)
                log.warning(
                    "  [%d/%d] Rate limited (429). Sleeping %ds...",
                    attempt + 1,
                    retries,
                    wait,
                )
                time.sleep(wait)
            else:
                # Sanitise response to avoid logging the API key
                safe_body = resp.text[:300].replace(API_KEY, "<REDACTED>")
                log.error(
                    "  [%d/%d] API Error %d: %s",
                    attempt + 1,
                    retries,
                    resp.status_code,
                    safe_body,
                )
                time.sleep(backoff)
        except Exception as e:
            log.error(
                "  [%d/%d] Network Exception: %s",
                attempt + 1,
                retries,
                e,
            )
            time.sleep(backoff)

    return None


# ── DB ingestion ───────────────────────────────────────────────


def ingest_into_db(entries: list[dict]) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    inserted = 0
    for entry in entries:
        canonical_id = entry.get("cie_id", "").replace("CIE ", "").replace("CIE", "").strip()
        formatted_id = f"CIE {canonical_id}"

        cursor.execute(
            "SELECT id FROM inscriptions WHERE id=?",
            (formatted_id,),
        )
        if not cursor.fetchone():
            cursor.execute(
                """
                INSERT INTO inscriptions (
                    id, canonical, raw_text, findspot,
                    notes, bibliography, source,
                    provenance_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    formatted_id,
                    entry.get("etruscan_text_transliterated", ""),
                    entry.get("etruscan_text_original")
                    or entry.get("etruscan_text_transliterated", ""),
                    entry.get("latin_findspot", ""),
                    entry.get("latin_commentary", ""),
                    entry.get("bibliography") or "",
                    "CIE Volume I (VLM Extracted)",
                    "extracted",
                ),
            )
            inserted += 1
    conn.commit()
    conn.close()
    return inserted


# ── Main loop ──────────────────────────────────────────────────


def main():
    if not PDF_PATH.exists():
        log.error("PDF not found at %s", PDF_PATH)
        return

    pdf = pdfium.PdfDocument(str(PDF_PATH))
    total_pages = len(pdf)
    log.info("PDF loaded: %d pages", total_pages)

    progress = load_progress()
    done = set(progress["completed_pages"])
    log.info(
        "Resume: %d pages already completed, %d entries so far",
        len(done),
        progress["total_entries"],
    )

    total_new_entries = 0
    total_inserted = 0

    for page_idx in range(total_pages):
        if page_idx in SKIP_PAGES:
            continue
        if page_idx in done:
            continue

        log.info(
            "── Page %d / %d ──────────────────────────",
            page_idx,
            total_pages - 1,
        )

        pil_image = render_page(pdf, page_idx)
        result = call_gemini(pil_image)

        if result and "entries" in result:
            entries = result["entries"]
            count = len(entries)
            log.info("  ✅ Extracted %d entries", count)

            # Save per-page JSON for safety
            page_file = PAGES_DIR / f"page_{page_idx:04d}.json"
            page_file.write_text(json.dumps(entries, indent=2, ensure_ascii=False))

            # Ingest into DB
            inserted = ingest_into_db(entries)
            log.info("  💾 Inserted %d new records (DB)", inserted)

            total_new_entries += count
            total_inserted += inserted
        else:
            log.warning("  ⚠️  No entries / error on page %d", page_idx)

        # Mark page done & persist progress
        done.add(page_idx)
        progress["completed_pages"] = sorted(done)
        progress["total_entries"] += len(result.get("entries", [])) if result else 0
        save_progress(progress)

        # Polite delay between API calls
        time.sleep(2)

    # ── Final summary ──
    log.info("=" * 50)
    log.info("INGESTION COMPLETE")
    log.info("  Pages processed this run: %d", len(done))
    log.info("  Entries extracted this run: %d", total_new_entries)
    log.info("  New DB records this run: %d", total_inserted)
    log.info("=" * 50)

    # Merge all per-page JSONs into one file
    all_entries = []
    for p in sorted(PAGES_DIR.glob("page_*.json")):
        all_entries.extend(json.loads(p.read_text()))
    merged = REPO_ROOT / "data/cie/full_extraction.json"
    merged.write_text(json.dumps(all_entries, indent=2, ensure_ascii=False))
    log.info("Merged %d entries → %s", len(all_entries), merged)


if __name__ == "__main__":
    main()
