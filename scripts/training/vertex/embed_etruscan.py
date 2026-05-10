"""Vertex AI custom job: extract the Etruscan vocabulary from the prod
inscriptions corpus, embed each token through XLM-R-base + the
``etr-lora-v3`` adapter, write JSONL of ``{language: 'ett', word, vector}``.

Mirrors ``embed_vocab.py`` (Latin/Greek) but:
  * Source vocab is the prod inscriptions JSONL (not Wikipedia)
  * Word-divider normalisation matches train_etruscan_lora.py (`:` and `·`
    convert to space; `.` and `-` kept) — must match or the embeddings
    won't align with what the LoRA learned.
  * Loads the PEFT adapter via ``peft.PeftModel.from_pretrained``.
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path


def _ensure_hf_stack() -> None:
    """Same fixes as the LoRA training + Wikipedia embed scripts."""
    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "-y", "torch_xla"],
        check=False,
    )
    pkgs = []
    for mod, pkg in [
        ("transformers", "transformers>=4.40,<4.47"),
        ("datasets", "datasets>=2.18,<3"),
        ("peft", "peft>=0.10,<0.13"),
        ("accelerate", "accelerate>=0.27,<1.0"),
    ]:
        try:
            __import__(mod)
        except ImportError:
            pkgs.append(pkg)
    if pkgs:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", *pkgs]
        )


def _normalise_dividers(text: str) -> str:
    """Same divider normalisation as train_etruscan_lora.py — must match."""
    text = text.translate(str.maketrans({":": " ", "·": " "}))
    return " ".join(text.split())


def _read_etruscan_vocab(corpus_path: Path, log: logging.Logger) -> list[str]:
    """Build the Etruscan vocab from the prod inscriptions JSONL.

    For each canonical:
      1. Apply Etruscan word-divider normalisation (must match LoRA training)
      2. Lowercase + split on whitespace
      3. Strip edge punctuation (NOT `.` or `-` — those are intra-word)
      4. Take unique tokens, frequency-sorted
    """
    counts: collections.Counter[str] = collections.Counter()
    n_inscs = 0
    with corpus_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            text = row.get("text") or row.get("canonical") or ""
            if not text:
                continue
            text = _normalise_dividers(text)
            for tok in text.lower().split():
                tok = tok.strip(",;!?\"'()[]")
                if len(tok) >= 1:
                    counts[tok] += 1
            n_inscs += 1
    log.info(
        "Etruscan vocab built from %d inscriptions: %d unique tokens",
        n_inscs, len(counts),
    )
    return [w for w, _ in counts.most_common()]


def _embed_with_adapter(words: list[str], base_model: str, adapter_path: Path,
                        log: logging.Logger) -> list[list[float]]:
    """Load XLM-R-base + LoRA adapter, mean-pool + L2-normalise each word.

    The adapter weights compose with the base — same encoder forward as
    embeddings.py's XLMREmbedder.
    """
    import torch
    import torch.nn.functional as F
    from peft import PeftModel
    from transformers import AutoModel, AutoTokenizer

    log.info("Loading base=%s adapter=%s", base_model, adapter_path)
    tok = AutoTokenizer.from_pretrained(base_model)
    model = AutoModel.from_pretrained(base_model)
    model = PeftModel.from_pretrained(model, str(adapter_path))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device).eval()
    log.info("device=%s", device)
    if torch.cuda.is_available():
        log.info("gpu=%s", torch.cuda.get_device_name(0))

    BATCH = 64
    out: list[list[float]] = []
    t0 = time.time()
    for i in range(0, len(words), BATCH):
        batch = words[i : i + BATCH]
        enc = tok(
            batch, return_tensors="pt", padding=True,
            truncation=True, max_length=16,
        ).to(device)
        with torch.no_grad():
            output = model(**enc).last_hidden_state
        mask = enc.attention_mask.unsqueeze(-1).float()
        pooled = (output * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
        pooled = F.normalize(pooled, p=2, dim=1)
        out.extend(pooled.cpu().tolist())
        if (i // BATCH) % 20 == 0:
            elapsed = time.time() - t0
            rate = (i + len(batch)) / elapsed if elapsed > 0 else 0
            log.info("  ett %d/%d (%.0f w/s)", i + len(batch), len(words), rate)
    return out


def _download_gcs_uri(uri: str, dest_dir: Path, is_dir: bool = False) -> Path:
    """Download a gs:// URI using gcloud storage. Returns local path."""
    if not uri.startswith("gs://"):
        return Path(uri)
    import subprocess
    import tempfile
    
    local_path = dest_dir / uri.split("/")[-1]
    if is_dir:
        local_path.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {uri} to {local_path} ...", file=sys.stderr)
        subprocess.check_call(["gcloud", "storage", "cp", "-r", f"{uri}/*", str(local_path)])
    else:
        print(f"Downloading {uri} to {local_path} ...", file=sys.stderr)
        subprocess.check_call(["gcloud", "storage", "cp", uri, str(local_path)])
    return local_path


def main() -> int:
    parser = argparse.ArgumentParser()
    # Backwards compatibility and new arguments
    parser.add_argument("--corpus_path", help="Local path to corpus JSONL")
    parser.add_argument("--corpus-uri", default="gs://openetruscan-rosetta/corpus/etruscan-prod-v2.jsonl", help="GCS URI to corpus JSONL")
    parser.add_argument("--adapter_path", help="Local path to adapter dir")
    parser.add_argument("--adapter-uri", help="GCS URI to adapter dir")
    parser.add_argument("--output_path", help="Legacy output path")
    parser.add_argument("--output", help="Output path")
    parser.add_argument("--base_model", default="xlm-roberta-base")
    parser.add_argument("--limit", type=int, help="Limit number of words to embed (for dry runs)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("embed_etruscan")

    _ensure_hf_stack()

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Resolve corpus path
        corpus = args.corpus_path
        if not corpus:
            corpus = _download_gcs_uri(args.corpus_uri, tmp_path, is_dir=False)
        else:
            corpus = Path(corpus)

        # Resolve adapter path
        adapter = args.adapter_path
        if not adapter:
            if not args.adapter_uri:
                raise ValueError("Must provide --adapter_path or --adapter-uri")
            adapter = _download_gcs_uri(args.adapter_uri, tmp_path, is_dir=True)
        else:
            adapter = Path(adapter)

        output_path = Path(args.output or args.output_path)

        words = _read_etruscan_vocab(corpus, log)
        if not words:
            raise ValueError(f"Empty vocabulary from {corpus}")

        if args.limit:
            log.info("Limiting to first %d words", args.limit)
            words = words[:args.limit]

        vectors = _embed_with_adapter(
            words, args.base_model, adapter, log,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            for w, v in zip(words, vectors, strict=True):
                f.write(json.dumps(
                    {"language": "ett", "word": w, "vector": v},
                    ensure_ascii=False,
                ) + "\n")
        log.info("Wrote %d Etruscan embeddings to %s", len(words), output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
