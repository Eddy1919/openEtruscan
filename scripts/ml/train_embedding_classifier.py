#!/usr/bin/env python3
import os
import csv
import json
import numpy as np
from pathlib import Path
import psycopg2
from psycopg2.extras import DictCursor
from dotenv import load_dotenv

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType

def main():
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
    db_url = os.getenv("DATABASE_URL")
    
    # 1. Fetch training data
    print("Fetching training data...")
    conn = psycopg2.connect(db_url)
    with conn.cursor(cursor_factory=DictCursor) as cur:
        # Fetch the 184 human-labeled rows
        cur.execute(
            "SELECT id, classification, emb_combined "
            "FROM inscriptions "
            "WHERE classification != 'unknown' AND emb_combined IS NOT NULL"
        )
        train_rows = cur.fetchall()
        
    if not train_rows:
        print("Error: No training data found.")
        return

    X_train = []
    y_train = []
    for r in train_rows:
        try:
            # emb_combined is a string representation of the vector, or a list if pgvector adapts it
            vec = r["emb_combined"]
            if isinstance(vec, str):
                vec = json.loads(vec)
            X_train.append(vec)
            y_train.append(r["classification"])
        except Exception as e:
            print(f"Skipping {r['id']}: {e}")

    X_train = np.array(X_train, dtype=np.float32)
    y_train = np.array(y_train)
    print(f"Loaded {X_train.shape[0]} training samples with {X_train.shape[1]} features.")

    # 2. Train Logistic Regression
    print("\nTraining Logistic Regression...")
    clf = LogisticRegression(class_weight="balanced", C=1.0, max_iter=1000)
    clf.fit(X_train, y_train)

    train_preds = clf.predict(X_train)
    train_f1 = f1_score(y_train, train_preds, average="macro")
    print(f"Training Macro F1: {train_f1:.4f}")

    # 3. Evaluate on held-out set
    csv_path = Path("/home/edoardo/.gemini/antigravity/brain/7ea9c352-8bd4-4ac2-829f-a3132d56a091/scratch/held_out_labels.csv")
    held_out_ids = []
    held_out_labels = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["label"].upper() == "SKIP" or row["id"] == "14650":
                continue
            held_out_ids.append(row["id"])
            held_out_labels[row["id"]] = row["label"]

    with conn.cursor(cursor_factory=DictCursor) as cur:
        format_strings = ','.join(['%s'] * len(held_out_ids))
        cur.execute(f"SELECT id, emb_combined FROM inscriptions WHERE id IN ({format_strings})", tuple(held_out_ids))
        test_rows = cur.fetchall()
        
    conn.close()

    X_test = []
    y_test = []
    for r in test_rows:
        rid = str(r["id"])
        vec = r["emb_combined"]
        if isinstance(vec, str):
            vec = json.loads(vec)
        X_test.append(vec)
        y_test.append(held_out_labels[rid])

    X_test = np.array(X_test, dtype=np.float32)
    y_test = np.array(y_test)

    print(f"\nLoaded {X_test.shape[0]} held-out testing samples.")
    
    test_preds = clf.predict(X_test)
    test_f1 = f1_score(y_test, test_preds, average="macro", zero_division=0)
    
    print("\n" + "="*50)
    print("HELD-OUT EVALUATION (EMBEDDING + LR)")
    print("="*50)
    print(f"Macro F1: {test_f1:.4f}\n")
    print(classification_report(y_test, test_preds, zero_division=0))

    # 4. Export to ONNX
    output_dir = Path(__file__).resolve().parent.parent.parent / "data/models/v3"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    onnx_path = output_dir / "embedding_head.onnx"
    initial_type = [('float_input', FloatTensorType([None, X_train.shape[1]]))]
    onx = convert_sklearn(clf, initial_types=initial_type)
    
    with open(onnx_path, "wb") as f:
        f.write(onx.SerializeToString())
        
    # Also save the classes list for inference mapping
    meta = {
        "classes": list(clf.classes_)
    }
    with open(output_dir / "embedding_head_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"\n💾 Exported ONNX to {onnx_path}")
    print(f"💾 Saved metadata to {output_dir / 'embedding_head_meta.json'}")

if __name__ == "__main__":
    main()
