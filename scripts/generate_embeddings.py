#!/usr/bin/env python3
"""
OpenEtruscan Vector Embedding Pipeline.

Generates multi-vector embeddings for all inscriptions using Gemini
text-embedding-004 and stores them in PostgreSQL via pgvector.

Three vectors per inscription:
  1. emb_text     — Etruscan canonical text only
  2. emb_context  — Findspot + classification + notes + bibliography (Latin/Italian)
  3. emb_combined — All fields concatenated for general similarity search

Usage:
    python scripts/generate_embeddings.py --db-url postgresql://...
    python scripts/generate_embeddings.py --db-url postgresql://... --batch-size 50 --delay 0.1
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
log = logging.getLogger("embed")

# ── Gemini Embedding API ──────────────────────────────────────
API_KEY = os.getenv("GEMINI_API_KEY")
EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-embedding-001:embedContent"
)
BATCH_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-embedding-001:batchEmbedContents"
)
EMBED_DIM = 3072
MAX_BATCH = 100  # Gemini batch limit


def embed_single(text: str, retries: int = 3) -> list[float] | None:
    """Embed a single text string using Gemini text-embedding-004."""
    if not text or not text.strip():
        return None

    for attempt in range(retries):
        try:
            resp = requests.post(
                EMBED_URL,
                params={"key": API_KEY},
                json={"content": {"parts": [{"text": text[:2048]}]}},
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()["embedding"]["values"]
            elif resp.status_code == 429:
                wait = min(5 * (2 ** attempt), 60)
                log.warning("Rate limited. Sleeping %ds...", wait)
                time.sleep(wait)
            else:
                log.error("API Error %d: %s", resp.status_code, resp.text[:200])
                time.sleep(2)
        except Exception as e:
            log.error("Network error: %s", e)
            time.sleep(2)
    return None


def embed_batch(texts: list[str], retries: int = 3) -> list[list[float] | None]:
    """Embed a batch of texts using Gemini batch embed API."""
    results: list[list[float] | None] = [None] * len(texts)

    # Filter out empty texts but track positions
    requests_list = []
    positions = []
    for i, text in enumerate(texts):
        if text and text.strip():
            requests_list.append({
                "model": "models/gemini-embedding-001",
                "content": {"parts": [{"text": text[:2048]}]},
            })
            positions.append(i)

    if not requests_list:
        return results

    for attempt in range(retries):
        try:
            resp = requests.post(
                BATCH_EMBED_URL,
                params={"key": API_KEY},
                json={"requests": requests_list},
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                embeddings = data.get("embeddings", [])
                for idx, emb in enumerate(embeddings):
                    results[positions[idx]] = emb["values"]
                return results
            elif resp.status_code == 429:
                wait = min(5 * (2 ** attempt), 60)
                log.warning("Rate limited (batch). Sleeping %ds...", wait)
                time.sleep(wait)
            else:
                log.error("Batch API Error %d: %s", resp.status_code, resp.text[:200])
                time.sleep(2)
        except Exception as e:
            log.error("Batch network error: %s", e)
            time.sleep(2)

    # Fallback: embed individually
    log.warning("Batch failed. Falling back to individual embedding...")
    for i, text in enumerate(texts):
        if text and text.strip():
            results[i] = embed_single(text)
            time.sleep(0.05)
    return results


def build_text_input(row: dict) -> str:
    """Build the Etruscan text input for embedding."""
    parts = []
    if row.get("canonical"):
        parts.append(row["canonical"])
    elif row.get("raw_text"):
        parts.append(row["raw_text"])
    return " ".join(parts).strip()


def build_context_input(row: dict) -> str:
    """Build the contextual embedding input (Latin commentary, findspot, etc.)."""
    parts = []
    if row.get("findspot"):
        parts.append(f"findspot: {row['findspot']}")
    if row.get("classification") and row["classification"] != "unknown":
        parts.append(f"type: {row['classification']}")
    if row.get("medium"):
        parts.append(f"medium: {row['medium']}")
    if row.get("object_type"):
        parts.append(f"object: {row['object_type']}")
    if row.get("notes"):
        parts.append(row["notes"][:500])
    if row.get("bibliography"):
        parts.append(row["bibliography"][:300])
    return " | ".join(parts).strip()


def build_combined_input(row: dict) -> str:
    """Build the combined input that merges text + context."""
    text = build_text_input(row)
    context = build_context_input(row)
    parts = []
    if text:
        parts.append(f"inscription: {text}")
    if context:
        parts.append(context)
    return " | ".join(parts).strip()


def vector_to_pg(vec: list[float] | None) -> str | None:
    """Format a vector list as pgvector's TEXT representation."""
    if vec is None:
        return None
    return "[" + ",".join(f"{v:.8f}" for v in vec) + "]"


def main():
    parser = argparse.ArgumentParser(description="Generate embeddings for OpenEtruscan corpus")
    parser.add_argument("--db-url", required=True, help="PostgreSQL connection URL")
    parser.add_argument("--batch-size", type=int, default=20, help="Embeddings per batch")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between batches (seconds)")
    parser.add_argument("--field", type=str, default="all",
                        choices=["text", "context", "combined", "all"],
                        help="Which embedding field(s) to generate")
    parser.add_argument("--force", action="store_true", help="Re-embed even if already present")
    args = parser.parse_args()

    if not API_KEY:
        log.error("GEMINI_API_KEY not set")
        sys.exit(1)

    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(args.db_url)
    log.info("Connected to PostgreSQL")

    # Fetch all inscriptions
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if args.force:
            cur.execute("SELECT * FROM inscriptions ORDER BY id")
        else:
            # Only fetch rows missing at least one embedding
            if args.field == "text":
                cur.execute("SELECT * FROM inscriptions WHERE emb_text IS NULL ORDER BY id")
            elif args.field == "context":
                cur.execute("SELECT * FROM inscriptions WHERE emb_context IS NULL ORDER BY id")
            elif args.field == "combined":
                cur.execute("SELECT * FROM inscriptions WHERE emb_combined IS NULL ORDER BY id")
            else:
                cur.execute("SELECT * FROM inscriptions WHERE emb_text IS NULL OR emb_context IS NULL OR emb_combined IS NULL ORDER BY id")
        rows = cur.fetchall()

    total = len(rows)
    log.info("Found %d inscriptions to embed", total)
    if total == 0:
        log.info("Nothing to do!")
        conn.close()
        return

    embedded = 0
    batch_size = args.batch_size

    for batch_start in range(0, total, batch_size):
        batch = rows[batch_start : batch_start + batch_size]

        # Build input texts for each field
        text_inputs = [build_text_input(r) for r in batch]
        context_inputs = [build_context_input(r) for r in batch]
        combined_inputs = [build_combined_input(r) for r in batch]

        # Generate embeddings
        text_vecs = [None] * len(batch)
        context_vecs = [None] * len(batch)
        combined_vecs = [None] * len(batch)

        if args.field in ("text", "all"):
            text_vecs = embed_batch(text_inputs)
            time.sleep(args.delay)

        if args.field in ("context", "all"):
            context_vecs = embed_batch(context_inputs)
            time.sleep(args.delay)

        if args.field in ("combined", "all"):
            combined_vecs = embed_batch(combined_inputs)
            time.sleep(args.delay)

        # Write to DB
        with conn.cursor() as cur:
            for i, row in enumerate(batch):
                updates = []
                params = []

                if text_vecs[i] is not None:
                    updates.append("emb_text = %s::vector")
                    params.append(vector_to_pg(text_vecs[i]))
                if context_vecs[i] is not None:
                    updates.append("emb_context = %s::vector")
                    params.append(vector_to_pg(context_vecs[i]))
                if combined_vecs[i] is not None:
                    updates.append("emb_combined = %s::vector")
                    params.append(vector_to_pg(combined_vecs[i]))

                if updates:
                    updates.append("updated_at = NOW()")
                    params.append(row["id"])
                    sql = f"UPDATE inscriptions SET {', '.join(updates)} WHERE id = %s"
                    # nosemgrep
                    cur.execute(sql, params)

        conn.commit()
        embedded += len(batch)
        log.info(
            "  Embedded %d/%d (%.1f%%)",
            embedded, total, embedded / total * 100,
        )

    # Create HNSW indexes if they don't exist
    log.info("Creating/verifying HNSW indexes...")
    with conn.cursor() as cur:
        try:
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_emb_text_hnsw
                    ON inscriptions USING hnsw (emb_text vector_cosine_ops);
                CREATE INDEX IF NOT EXISTS idx_emb_context_hnsw
                    ON inscriptions USING hnsw (emb_context vector_cosine_ops);
                CREATE INDEX IF NOT EXISTS idx_emb_combined_hnsw
                    ON inscriptions USING hnsw (emb_combined vector_cosine_ops);
            """)
            conn.commit()
            log.info("HNSW indexes ready.")
        except Exception as e:
            log.warning("Index creation skipped: %s", e)
            conn.rollback()

    conn.close()
    log.info("Done! Embedded %d inscriptions.", embedded)


if __name__ == "__main__":
    main()
