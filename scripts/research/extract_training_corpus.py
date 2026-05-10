#!/usr/bin/env python3
"""Extract the Etruscan training corpus from the production database as JSONL.

Reads from the `inscriptions` table using the cleaned `canonical_clean`
column (populated by normalize_inscriptions.py) and emits one JSON object
per line to stdout. The output is consumed by ByT5 v3/v5 training
(train_byt5_v3.py) which expects {"raw_text": ..., "has_brackets": bool}.

Usage:
    # Via SSH tunnel (localhost:5434 → Bastion → 10.50.0.3:5432):
    export DATABASE_URL=postgresql://corpus_reader:...@127.0.0.1:5434/corpus
    python scripts/research/extract_training_corpus.py > /tmp/etruscan-prod-rawtext-v2.jsonl

    # Or via Bastion psql pipe (no local dependencies):
    gcloud compute ssh openetruscan-eu ... --command="docker run ..."
"""

from __future__ import annotations

import json
import os
import sys

import psycopg2


def main() -> int:
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://user:password@localhost:5432/corpus",
    )

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    raw_text,
                    COALESCE(canonical_clean, canonical) AS canonical_clean,
                    data_quality,
                    translation,
                    year_from,
                    year_to,
                    intact_token_ratio
                FROM inscriptions
                WHERE language = 'etruscan'
                  AND COALESCE(canonical_clean, canonical) IS NOT NULL
                  AND length(COALESCE(canonical_clean, canonical)) >= 3
                ORDER BY id
            """)
            rows = cur.fetchall()
            cols = [desc[0] for desc in cur.description]
    finally:
        conn.close()

    n_brackets = 0
    for row in rows:
        rec = dict(zip(cols, row))
        # ByT5 training expects `raw_text` and `has_brackets`
        raw = rec.get("raw_text") or rec.get("canonical_clean") or ""
        has_brackets = "[" in raw and "]" in raw
        if has_brackets:
            n_brackets += 1

        obj = {
            "id": rec["id"],
            "raw_text": raw,
            "canonical_clean": rec["canonical_clean"],
            "has_brackets": has_brackets,
            "data_quality": rec.get("data_quality"),
            "translation": rec.get("translation"),
            "year_from": rec.get("year_from"),
            "year_to": rec.get("year_to"),
            "intact_token_ratio": float(rec["intact_token_ratio"]) if rec.get("intact_token_ratio") is not None else None,
        }
        print(json.dumps(obj, ensure_ascii=False))

    print(
        f"# Extracted {len(rows)} inscriptions, {n_brackets} with attested lacunae",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
