#!/usr/bin/env python3
import os
import sys
import logging
from pathlib import Path
import psycopg2
from psycopg2.extras import DictCursor
from dotenv import load_dotenv

# Ensure we can import from src
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "src"))

from openetruscan.ml.classifier import InscriptionClassifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("augment")

def main():
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
    db_url = os.getenv("DATABASE_URL")
    
    conn = psycopg2.connect(db_url)
    clf = InscriptionClassifier()
    
    with conn.cursor(cursor_factory=DictCursor) as cur:
        # Fetch unknown inscriptions
        cur.execute("SELECT id, canonical, canonical_clean, raw_text FROM inscriptions WHERE classification = 'unknown'")
        rows = cur.fetchall()
        
    log.info("Classifying %d unknown inscriptions...", len(rows))
    
    augmented = {"votive": [], "boundary": [], "legal": []}
    
    for row in rows:
        text = row["canonical_clean"] or row["canonical"] or row["raw_text"]
        if not text:
            continue
            
        result = clf.predict(text)
        if result.label in augmented:
            # We use the raw score (average of keyword presence) as confidence
            confidence = sum(result.probabilities.values()) if result.probabilities else 0
            augmented[result.label].append({
                "id": row["id"],
                "confidence": confidence,
                "label": result.label
            })
            
    # Sort by confidence and take top 30
    to_apply = []
    for label, samples in augmented.items():
        samples.sort(key=lambda x: x["confidence"], reverse=True)
        top_30 = samples[:30]
        to_apply.extend(top_30)
        log.info("  Augmented %d samples for class: %s", len(top_30), label)
        
    if not to_apply:
        log.info("No samples found to augment.")
        conn.close()
        return
        
    with conn.cursor() as cur:
        print("Applying augmented labels to database...")
        for sample in to_apply:
            cur.execute(
                "UPDATE inscriptions SET classification = %s WHERE id = %s",
                (sample["label"], sample["id"])
            )
        conn.commit()
    
    conn.close()
    log.info("Done!")

if __name__ == "__main__":
    main()
