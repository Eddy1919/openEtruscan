#!/usr/bin/env python3
"""
Benchmark Epigraphic ML Pipelines.
Runs comparative benchmarks on Classification and Lacunae Restoration.

Usage:
    python scripts/ml/benchmark_pipelines.py
"""
import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

# setup path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from openetruscan.ml.neural import NeuralClassifier
from openetruscan.ml.embedding_classifier import EmbeddingMLPClassifier

load_dotenv(Path(__file__).parent.parent.parent / ".env")

def test_classification(db_url):
    print("\n" + "="*50)
    print("🚀 BENCHMARK: CLASSIFICATION")
    print("="*50)
    
    # 1. Legacy CNN
    print("\n--- Training Legacy CharCNN (~50k params) ---")
    legacy = NeuralClassifier(arch="cnn")
    try:
        res_legacy = legacy.train_from_corpus(db_url, epochs=10, verbose=False)
        print(f"CharCNN F1-Macro:     {res_legacy['val_f1_macro']:.4f} ({res_legacy['train_time_s']}s)")
    except Exception as e:
        print(f"CharCNN failed: {e}")
        res_legacy = {"val_f1_macro": 0.0, "train_time_s": 0.0}
    
    # 2. Embedding MLP
    print("\n--- Training Embedding MLP (from Gemini pgvectors) ---")
    mlp = EmbeddingMLPClassifier()
    try:
        res_mlp = mlp.train_from_db(db_url, verbose=False)
        print(f"Embedding MLP F1:     {res_mlp['val_f1_macro']:.4f} ({res_mlp['train_time_s']}s)")
    except Exception as e:
        print(f"Embedding MLP failed: {e}")
        res_mlp = {"val_f1_macro": 0.0, "train_time_s": 0.0}
    
    print("\n" + "-"*50)
    print("🏆 RESULTS: CLASSIFICATION")
    print(f"CharCNN F1-Macro:     {res_legacy['val_f1_macro']:.4f} ({res_legacy['train_time_s']}s)")
    print(f"Embedding MLP F1:     {res_mlp['val_f1_macro']:.4f} ({res_mlp['train_time_s']}s)")
    
    diff = res_mlp['val_f1_macro'] - res_legacy['val_f1_macro']
    if diff > 0:
        print(f"✅ Embedding MLP out-performed CharCNN by +{diff:.4f}")
    else:
        print(f"❌ Embedding MLP under-performed CharCNN by {diff:.4f}")

def test_restoration(db_url, test_byt5=False):
    print("\n" + "="*50)
    print("🚀 BENCHMARK: RESTORATION (Classification context used for metric proxy)")
    print("="*50)
    
    print("\n--- Training Ithaca-style MicroTransformer ---")
    try:
        ithaca = NeuralClassifier(arch="ithaca")
        res_ithaca = ithaca.train_from_corpus(db_url, epochs=10, verbose=False)
        print(f"Ithaca F1-Macro: {res_ithaca['val_f1_macro']:.4f} ({res_ithaca['train_time_s']}s)")
    except Exception as e:
        print(f"Ithaca Transformer failed: {e}")
    
    if test_byt5:
        print("\n--- Training ByT5 Transfer Learning Restorer ---")
        try:
            from openetruscan.ml.byt5_restorer import ByT5Restorer
            restorer = ByT5Restorer()
            res_byt5 = restorer.train_from_db(db_url, epochs=1) # 1 epoch for fast bench
            print(f"ByT5 Time to Train: {res_byt5['train_time_s']}s")
            print(f"ByT5 Final Loss: {res_byt5['loss']:.4f}")
        except Exception as e:
            print(f"ByT5 failed: {e}")
            raise e

def main():
    parser = argparse.ArgumentParser(description="Run complete ML Benchmark suite.")
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL"), help="Database URL")
    parser.add_argument("--no-byt5", action="store_true", help="Skip the ByT5 Fine-tuning test")
    args = parser.parse_args()

    if not args.db_url:
        print("DATABASE_URL not set in env or arguments!")
        sys.exit(1)

    test_classification(args.db_url)
    test_restoration(args.db_url, test_byt5=not args.no_byt5)
    print("\n🎉 Benchmarks Complete!")

if __name__ == "__main__":
    main()
