#!/usr/bin/env python3
import os
import sys
import logging
import time
from pathlib import Path
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Ensure we can import from src
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "src"))

from openetruscan.ml.embeddings import XLMREmbedder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
log = logging.getLogger("neural_embed")

def build_text_input(row: dict) -> str:
    return row.get("canonical_clean") or row.get("canonical") or row.get("raw_text") or ""

def build_context_input(row: dict) -> str:
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
    return " | ".join(parts).strip()

def build_combined_input(row: dict) -> str:
    text = build_text_input(row)
    context = build_context_input(row)
    return f"inscription: {text} | {context}" if context else f"inscription: {text}"

def vector_to_pg(vec: list[float] | None) -> str | None:
    if vec is None:
        return None
    return "[" + ",".join(f"{v:.8f}" for v in vec) + "]"

def main():
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
    db_url = os.getenv("DATABASE_URL")
    
    # Initialize the XLM-R + LoRA embedder
    log.info("Initializing XLMREmbedder with etr-lora-v4 adapter...")
    embedder = XLMREmbedder(
        model_id="xlm-roberta-base",
        adapter_path=Path(__file__).resolve().parent.parent.parent / "data/models/v4",
        batch_size=32
    )
    
    conn = psycopg2.connect(db_url)
    log.info("Connected to PostgreSQL")

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT id, canonical, canonical_clean, raw_text, findspot, classification, medium, object_type, notes FROM inscriptions ORDER BY id")
        rows = cur.fetchall()

    total = len(rows)
    log.info("Found %d inscriptions to embed", total)
    if total == 0:
        log.info("Nothing to do!")
        conn.close()
        return

    batch_size = 64
    for i in range(0, total, batch_size):
        batch = rows[i : i + batch_size]
        
        text_inputs = [build_text_input(r) for r in batch]
        context_inputs = [build_context_input(r) for r in batch]
        combined_inputs = [build_combined_input(r) for r in batch]
        
        log.info("  Processing batch %d/%d...", i + len(batch), total)
        
        # XLMREmbedder.embed_words handles the pooling and normalization
        text_vecs = embedder.embed_words(text_inputs)
        context_vecs = embedder.embed_words(context_inputs)
        combined_vecs = embedder.embed_words(combined_inputs)
        
        update_data = []
        for idx, row in enumerate(batch):
            update_data.append((
                row["id"],
                vector_to_pg(text_vecs[idx].tolist()),
                vector_to_pg(context_vecs[idx].tolist()),
                vector_to_pg(combined_vecs[idx].tolist())
            ))
            
        with conn.cursor() as cur:
            sql = """
                UPDATE inscriptions 
                SET 
                    emb_text = v.emb_text::vector,
                    emb_context = v.emb_context::vector,
                    emb_combined = v.emb_combined::vector,
                    updated_at = NOW()
                FROM (VALUES %s) AS v(id, emb_text, emb_context, emb_combined)
                WHERE inscriptions.id = v.id
            """
            psycopg2.extras.execute_values(cur, sql, update_data)
        conn.commit()

    log.info("Recreating HNSW indexes (768 dims)...")
    with conn.cursor() as cur:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_emb_text_hnsw ON inscriptions USING hnsw (emb_text vector_cosine_ops)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_emb_context_hnsw ON inscriptions USING hnsw (emb_context vector_cosine_ops)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_emb_combined_hnsw ON inscriptions USING hnsw (emb_combined vector_cosine_ops)")
    conn.commit()
    
    conn.close()
    log.info("Done!")

if __name__ == "__main__":
    main()
