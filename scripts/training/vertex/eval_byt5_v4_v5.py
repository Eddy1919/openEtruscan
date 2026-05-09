#!/usr/bin/env python3
"""ByT5 v4 vs v5 lacuna-restoration evaluation — Vertex AI edition.

Runs on the same pytorch-gpu image + pinned HF stack that trained the
adapters. This avoids any peft/torch version mismatch.

Reads 100 test inscriptions from a JSONL file on GCS, runs inference
with both adapters, and writes results to GCS.

Usage (submitted via submit_byt5_eval.sh):
  python eval_byt5_v4_v5.py \
    --test_data /gcs/openetruscan-rosetta/eval/byt5_eval_100.jsonl \
    --v4_adapter /gcs/openetruscan-rosetta/adapters/byt5-lacunae-v4 \
    --v5_adapter /gcs/openetruscan-rosetta/adapters/byt5-lacunae-v5 \
    --output /gcs/openetruscan-rosetta/eval/byt5_v4_v5_results.json
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path


def _ensure_deps():
    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "-y", "torch_xla"],
        check=False,
    )
    pkgs = []
    for mod, pkg in [
        ("transformers", "transformers>=4.40,<4.47"),
        ("peft", "peft>=0.10,<0.13"),
        ("editdistance", "editdistance"),
        ("sentencepiece", "sentencepiece>=0.2"),
    ]:
        try:
            __import__(mod)
        except ImportError:
            pkgs.append(pkg)
    if pkgs:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", *pkgs]
        )


def extract_prediction(text: str) -> str:
    start = text.find("<extra_id_0>")
    if start == -1:
        return text.strip()
    start += len("<extra_id_0>")
    end = text.find("<extra_id_1>", start)
    if end == -1:
        return text[start:].strip()
    return text[start:end].strip()


def run_eval(adapter_path: str, examples: list[dict], tokenizer, device) -> dict:
    import torch
    from transformers import AutoModelForSeq2SeqLM
    from peft import PeftModel
    import editdistance

    log = logging.getLogger("byt5_eval")

    base = AutoModelForSeq2SeqLM.from_pretrained("google/byt5-small")
    model = PeftModel.from_pretrained(base, adapter_path)
    model.to(device)
    model.eval()

    exact_matches = 0
    total_edit_dist = 0
    total_target_len = 0
    preds = []

    for i, ex in enumerate(examples):
        inputs = tokenizer(ex["masked"], return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=32,
                num_beams=1,
                do_sample=False,
            )
        raw = tokenizer.decode(outputs[0], skip_special_tokens=False)
        pred = extract_prediction(raw)

        dist = editdistance.eval(pred, ex["target"])
        total_edit_dist += dist
        total_target_len += len(ex["target"])
        if pred == ex["target"]:
            exact_matches += 1

        preds.append({
            "id": ex["id"],
            "target": ex["target"],
            "pred": pred,
            "dist": dist,
            "exact": pred == ex["target"],
        })

        if i < 5:
            log.info("  [%d] target=%s  pred=%s  dist=%d", i, ex["target"], pred, dist)

    em = exact_matches / len(examples)
    cer = total_edit_dist / max(total_target_len, 1)

    del model
    import torch as _torch
    if _torch.cuda.is_available():
        _torch.cuda.empty_cache()

    return {"em": em, "cer": cer, "exact_matches": exact_matches, "n": len(examples), "preds": preds}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test_data", required=True)
    parser.add_argument("--v4_adapter", required=True)
    parser.add_argument("--v5_adapter", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("byt5_eval")

    _ensure_deps()

    import torch
    from transformers import AutoTokenizer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    log.info("torch=%s device=%s", torch.__version__, device)

    # Load test data
    examples = []
    with open(args.test_data) as f:
        for line in f:
            examples.append(json.loads(line))
    log.info("Loaded %d evaluation examples", len(examples))

    tokenizer = AutoTokenizer.from_pretrained("google/byt5-small")

    results = {}
    for version, path in [("v4", args.v4_adapter), ("v5", args.v5_adapter)]:
        log.info("=" * 60)
        log.info("Evaluating ByT5 %s from %s", version, path)
        log.info("=" * 60)
        results[version] = run_eval(path, examples, tokenizer, device)
        log.info("ByT5 %s — EM: %.1f%%  CER: %.1f%%",
                 version, results[version]["em"] * 100, results[version]["cer"] * 100)

    # Delta
    delta_em = results["v5"]["em"] - results["v4"]["em"]
    delta_cer = results["v5"]["cer"] - results["v4"]["cer"]
    log.info("DELTA (v5 - v4): ΔEM=%+.1f%%  ΔCER=%+.1f%%", delta_em * 100, delta_cer * 100)

    summary = {
        "v4": {k: v for k, v in results["v4"].items() if k != "preds"},
        "v5": {k: v for k, v in results["v5"].items() if k != "preds"},
        "delta_em": delta_em,
        "delta_cer": delta_cer,
        "v4_preds": results["v4"]["preds"],
        "v5_preds": results["v5"]["preds"],
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    log.info("Results written to %s", output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
