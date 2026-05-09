#!/usr/bin/env python3
"""ByT5 v4 vs v5 lacuna-restoration evaluation.

Picks 100 clean inscriptions (intact_token_ratio=1.0, multi-word),
masks one random token per row with <extra_id_0>, and compares
exact-match accuracy + character error rate between the two adapters.

CPU-safe: loads a fresh base model per adapter, merges LoRA weights
with merge_and_unload(), and forces fp32 + greedy decoding.
"""
import os
import random
import json
import sys
from pathlib import Path

import editdistance
import numpy as np
import psycopg2
from psycopg2.extras import DictCursor
from dotenv import load_dotenv

import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, GenerationConfig
from peft import PeftModel


def extract_prediction(text: str) -> str:
    """Extract the span between <extra_id_0> and <extra_id_1>."""
    # ByT5 span-corruption format: <extra_id_0> TOKEN <extra_id_1>
    start = text.find("<extra_id_0>")
    if start == -1:
        return text.strip()
    start += len("<extra_id_0>")
    end = text.find("<extra_id_1>", start)
    if end == -1:
        return text[start:].strip()
    return text[start:end].strip()


def load_merged_model(adapter_path: str):
    """Load a fresh byt5-small base, attach LoRA, merge, and return fp32 model."""
    base = AutoModelForSeq2SeqLM.from_pretrained(
        "google/byt5-small", torch_dtype=torch.float32
    )
    peft_model = PeftModel.from_pretrained(base, adapter_path)
    merged = peft_model.merge_and_unload()
    merged.eval()
    return merged


def main():
    load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")
    db_url = os.getenv("DATABASE_URL")

    conn = psycopg2.connect(db_url)
    with conn.cursor(cursor_factory=DictCursor) as cur:
        # Deterministic 100-row sample: multi-word, fully intact, reasonably long
        cur.execute("""
            SELECT id, canonical_clean
            FROM inscriptions
            WHERE language = 'etruscan'
              AND intact_token_ratio = 1.0
              AND length(canonical_clean) > 20
              AND canonical_clean LIKE '%% %%'
            ORDER BY md5(id::text)
            LIMIT 100
        """)
        rows = cur.fetchall()
    conn.close()

    # Build masked examples
    random.seed(42)
    examples = []
    for r in rows:
        text = r["canonical_clean"]
        words = text.split()
        if len(words) < 2:
            continue
        mask_idx = random.randint(0, len(words) - 1)
        target = words[mask_idx]
        words_masked = words.copy()
        words_masked[mask_idx] = "<extra_id_0>"
        masked_text = " ".join(words_masked)
        examples.append({
            "id": r["id"],
            "original": text,
            "masked": masked_text,
            "target": target,
        })

    print(f"Prepared {len(examples)} evaluation examples.\n")

    tokenizer = AutoTokenizer.from_pretrained("google/byt5-small")

    gen_config = GenerationConfig(
        max_new_tokens=32,
        num_beams=1,          # greedy — avoids beam-search early-stop artifacts
        do_sample=False,
        decoder_start_token_id=0,
    )

    all_results = {}

    for version, adapter_path in [
        ("v4", "data/models/byt5-v4"),
        ("v5", "data/models/byt5-v5"),
    ]:
        print(f"{'='*60}")
        print(f"Loading ByT5 {version} — merge_and_unload from {adapter_path}")
        print(f"{'='*60}")
        model = load_merged_model(adapter_path)

        exact_matches = 0
        total_edit_dist = 0
        total_target_len = 0
        preds = []

        for i, ex in enumerate(examples):
            inputs = tokenizer(ex["masked"], return_tensors="pt")
            with torch.no_grad():
                outputs = model.generate(**inputs, generation_config=gen_config)

            raw = tokenizer.decode(outputs[0], skip_special_tokens=False)
            pred = extract_prediction(raw)

            dist = editdistance.eval(pred, ex["target"])
            total_edit_dist += dist
            total_target_len += len(ex["target"])
            if pred == ex["target"]:
                exact_matches += 1

            preds.append({"id": ex["id"], "target": ex["target"], "pred": pred, "dist": dist})

            # Print first 5 examples for sanity
            if i < 5:
                print(f"  [{i}] {ex['masked']}")
                print(f"       target={ex['target']}  pred={pred}  raw={raw[:80]}  dist={dist}")

        em_acc = exact_matches / len(examples)
        cer = total_edit_dist / max(total_target_len, 1)
        print(f"\n--- ByT5 {version} ---")
        print(f"  Exact-Match Accuracy : {em_acc:.1%}  ({exact_matches}/{len(examples)})")
        print(f"  Char Error Rate (CER): {cer:.1%}")
        all_results[version] = {"em": em_acc, "cer": cer, "preds": preds}

        # Free memory before loading next adapter
        del model
        torch.cuda.empty_cache() if torch.cuda.is_available() else None

    # Summary delta
    print(f"\n{'='*60}")
    print("DELTA (v5 − v4)")
    print(f"{'='*60}")
    delta_em = all_results["v5"]["em"] - all_results["v4"]["em"]
    delta_cer = all_results["v5"]["cer"] - all_results["v4"]["cer"]
    print(f"  ΔEM  = {delta_em:+.1%}")
    print(f"  ΔCER = {delta_cer:+.1%}")
    if delta_em > 0:
        print("  → v5 wins on exact match")
    elif delta_em < 0:
        print("  → v4 wins on exact match (cleaning didn't help ByT5)")
    else:
        print("  → tie on exact match")


if __name__ == "__main__":
    main()
