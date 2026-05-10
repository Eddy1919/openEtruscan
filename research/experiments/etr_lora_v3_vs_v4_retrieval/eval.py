#!/usr/bin/env python3
import os
import psycopg2
from psycopg2.extras import DictCursor
from scipy.spatial.distance import cdist
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

# Ensure we can import XLMREmbedder
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
from openetruscan.ml.embeddings import XLMREmbedder

def main():
    load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")
    db_url = os.getenv("DATABASE_URL")
    
    # We will do an in-memory A/B test of retrieval quality
    # Fetch 500 rows (including rows with sibilants) to act as the corpus
    conn = psycopg2.connect(db_url)
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute("""
            SELECT id, canonical_clean, emb_combined
            FROM inscriptions
            WHERE language = 'etruscan'
              AND canonical_clean IS NOT NULL
              AND length(canonical_clean) > 10
              AND emb_combined IS NOT NULL
            ORDER BY RANDOM()
            LIMIT 500
        """)
        corpus = cur.fetchall()
        
        # Pick 10 specific query inscriptions (e.g., containing sibilants or names)
        cur.execute("""
            SELECT id, canonical_clean, emb_combined
            FROM inscriptions
            WHERE (canonical_clean LIKE '%θania%' 
               OR canonical_clean LIKE '%ś%' 
               OR canonical_clean LIKE '%š%')
              AND emb_combined IS NOT NULL
            LIMIT 10
        """)
        queries = cur.fetchall()
    conn.close()

    print(f"Loaded {len(corpus)} corpus rows and {len(queries)} queries.")

    # 1. Prepare v3 Embeddings
    print("Preparing v3 embeddings (from DB)...")
    import json
    def parse_vec(v):
        if isinstance(v, str):
            return np.array(json.loads(v), dtype=np.float32)
        return np.array(v, dtype=np.float32)

    v3_corpus_vecs = np.array([parse_vec(r["emb_combined"]) for r in corpus])
    v3_query_vecs = np.array([parse_vec(r["emb_combined"]) for r in queries])

    # 2. Prepare v4 Embeddings
    v4_adapter_path = Path(__file__).resolve().parent.parent.parent.parent / "data/models/v4"
    if not v4_adapter_path.exists():
        print(f"Error: {v4_adapter_path} not found. Ensure etr-lora-v4 has finished and is downloaded.")
        return

    print("Loading v4 embedder and generating embeddings...")
    embedder_v4 = XLMREmbedder(adapter_path=str(v4_adapter_path))
    
    # We embed 'canonical_clean' for v4
    v4_corpus_vecs = embedder_v4.embed_words([r["canonical_clean"] for r in corpus])
    v4_query_vecs = embedder_v4.embed_words([r["canonical_clean"] for r in queries])

    print("\n" + "="*80)
    print("A/B RETRIEVAL COMPARISON (v3 vs v4)")
    print("="*80)

    for i, q in enumerate(queries):
        print(f"\n[Query {i+1}] ID: {q['id']} | Text: {q['canonical_clean']}")
        
        # v3 NN
        v3_dists = cdist([v3_query_vecs[i]], v3_corpus_vecs, metric="cosine")[0]
        v3_topk = np.argsort(v3_dists)[1:6] # Skip 0 which is self if present
        
        print("  --- v3 Neighbors ---")
        for idx in v3_topk:
            print(f"    (dist: {v3_dists[idx]:.3f}) {corpus[idx]['canonical_clean']}")

        # v4 NN
        v4_dists = cdist([v4_query_vecs[i]], v4_corpus_vecs, metric="cosine")[0]
        v4_topk = np.argsort(v4_dists)[1:6]
        
        print("  --- v4 Neighbors ---")
        for idx in v4_topk:
            print(f"    (dist: {v4_dists[idx]:.3f}) {corpus[idx]['canonical_clean']}")

if __name__ == "__main__":
    main()
