"""Vertex AI custom job: re-embed Latin vocabulary through XLM-R-base
so it can live in the (embedder='xlmr-lora', embedder_revision='v4')
partition alongside the existing Etruscan v4 vectors.

Why this exists
---------------
T2.3 introduced the v4 partition (xlmr-lora applied to Etruscan via LoRA).
T2.4 attempted a head-to-head LaBSE-vs-v4 eval and surfaced an empty
v4 column: 8,905 ett v4 rows but 0 lat v4 rows. The cross-language
retrieval query needs both source AND target language to live in the
same partition; the lat-side gap meant every eval pair was "skipped".

This script closes the gap. It:

1. Streams the existing ``labse-v1.jsonl`` from GCS (3.3 GB) and
   extracts the Latin word list (~100k unique tokens).
2. Embeds each word through XLM-R-base (mean-pool + L2-normalise,
   matching the recipe used by ``embed_vocab.py``).
3. Writes a new JSONL with ``{language: "lat", word, vector}`` rows
   intended to be ingested with ``--embedder xlmr-lora --revision v4``.

Naming caveat
-------------
The Latin half of the v4 partition is labelled ``xlmr-lora`` even
though Latin is NOT run through any LoRA adapter (LoRA training is
Etruscan-only). The label keeps the partition key consistent so the
route layer doesn't need a language-aware alias map. The v4 column in
``rosetta-eval-v1`` is therefore measuring "etr-side LoRA applied,
Latin-side vanilla XLM-R-base" — both compared against LaBSE's
parallel-data-trained shared space. That's a fair comparison of two
embedding strategies, just with a slightly misleading partition
label. See ``research/SOTA_ROADMAP.md`` for the larger context.

Cost / wall clock
-----------------
T4 GPU: ~$0.30 (~10-15 min for 100k Latin tokens).

Usage
-----
Submit via ``scripts/training/vertex/submit_lat_xlmr_v4.sh``; the
script handles uploading the code to GCS + configuring the Vertex
custom job.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import subprocess
import sys
import time
from pathlib import Path


def _ensure_hf_stack() -> None:
    """Same bootstrap as embed_etruscan.py / embed_vocab.py.

    The Vertex base image ships torch 2.2; transformers 4.47+ pins
    torch>=2.4; torch_xla intercepts nested_gather and slows steps to
    minutes each. Pin both, uninstall xla.
    """
    log = logging.getLogger("embed_lat_xlmr_v4.bootstrap")
    cmds = [
        ["pip", "install", "--quiet",
         "transformers>=4.40,<4.47", "tokenizers>=0.19,<0.21"],
        ["pip", "uninstall", "-y", "torch_xla"],
    ]
    for cmd in cmds:
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            log.warning("bootstrap %s exit=%d (often benign for pip uninstall)",
                        cmd, e.returncode)


def _stream_lat_words(gcs_uri: str, max_tokens: int | None, log: logging.Logger) -> list[str]:
    """Stream the labse-v1.jsonl file from GCS, keeping only rows with
    ``language == 'lat'``. De-duplicates and preserves insertion order.

    The JSONL is 3.3 GB on disk but we never materialise more than one
    decoded row at a time, so peak RAM is dominated by the final word
    list (~100k * ~10 bytes = ~1 MB).
    """
    log.info("Streaming %s for language=lat tokens", gcs_uri)
    proc = subprocess.Popen(
        ["gcloud", "storage", "cat", gcs_uri],
        stdout=subprocess.PIPE,
    )
    assert proc.stdout is not None
    seen: set[str] = set()
    words: list[str] = []
    n_rows = 0
    t0 = time.time()
    for raw in io.TextIOWrapper(proc.stdout, encoding="utf-8"):
        n_rows += 1
        if n_rows % 100_000 == 0:
            log.info("  scanned %d rows in %.0fs, lat words so far: %d",
                     n_rows, time.time() - t0, len(words))
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if row.get("language") != "lat":
            continue
        word = row.get("word")
        if not word or word in seen:
            continue
        seen.add(word)
        words.append(word)
        if max_tokens and len(words) >= max_tokens:
            break
    proc.wait()
    log.info("Final lat vocab size: %d (after scanning %d rows in %.0fs)",
             len(words), n_rows, time.time() - t0)
    return words


def _embed_and_write(words: list[str], output_path: Path, log: logging.Logger) -> int:
    """Mean-pool + L2-normalise each Latin word's XLM-R-base contextual
    representation. Stream-write to JSONL so peak RAM is BATCH * 768 floats.
    """
    import torch
    import torch.nn.functional as F
    from transformers import AutoModel, AutoTokenizer

    log.info("torch=%s cuda=%s", torch.__version__, torch.cuda.is_available())
    if torch.cuda.is_available():
        log.info("device=%s", torch.cuda.get_device_name(0))

    tok = AutoTokenizer.from_pretrained("xlm-roberta-base")
    model = AutoModel.from_pretrained("xlm-roberta-base")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device).eval()

    BATCH = 64
    output_path.parent.mkdir(parents=True, exist_ok=True)
    n_total = 0
    t0 = time.time()
    with output_path.open("w", encoding="utf-8") as f:
        for i in range(0, len(words), BATCH):
            batch = words[i : i + BATCH]
            enc = tok(
                batch, return_tensors="pt", padding=True,
                truncation=True, max_length=16,
            ).to(device)
            with torch.no_grad():
                out = model(**enc).last_hidden_state
            mask = enc.attention_mask.unsqueeze(-1).float()
            pooled = (out * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
            pooled = F.normalize(pooled, p=2, dim=1)
            vecs = pooled.cpu().tolist()
            for w, v in zip(batch, vecs, strict=True):
                f.write(json.dumps(
                    {"language": "lat", "word": w, "vector": v},
                    ensure_ascii=False,
                ) + "\n")
                n_total += 1
            if (i // BATCH) % 50 == 0:
                elapsed = time.time() - t0
                rate = (i + len(batch)) / elapsed if elapsed > 0 else 0
                log.info("  embedded %d/%d (%.0f w/s)", i + len(batch), len(words), rate)
    return n_total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source_uri",
        default="gs://openetruscan-rosetta/embeddings/labse-v1.jsonl",
        help="GCS URI of the JSONL containing the Latin vocab to re-embed.",
    )
    parser.add_argument(
        "--output_path", required=True,
        help="Where to write the new JSONL. Vertex mounts gs:// as /gcs/<bucket>/...",
    )
    parser.add_argument(
        "--max_tokens", type=int, default=None,
        help="Optional cap (for debugging).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("embed_lat_xlmr_v4")

    _ensure_hf_stack()
    words = _stream_lat_words(args.source_uri, args.max_tokens, log)
    if not words:
        log.error("No Latin words found in %s — refusing to write empty JSONL.",
                  args.source_uri)
        return 1
    output_path = Path(args.output_path)
    n = _embed_and_write(words, output_path, log)
    log.info("Wrote %d embeddings to %s", n, output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
