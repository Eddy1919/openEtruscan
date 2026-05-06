"""Vertex AI custom job: extract top-N Latin + Greek vocab from Wikipedia,
embed each token with XLM-R-base (mean-pool + L2-normalise), and write a
JSONL per-row of ``{language, word, vector}`` to GCS.

Self-contained — no openetruscan package import. Runs inside the prebuilt
``us-docker.pkg.dev/vertex-ai/training/pytorch-gpu.2-2.py310`` image, with
the same bootstrap fixes the LoRA training script needs:

  * pip uninstall torch_xla       — Trainer routes nested_gather through
                                    XLA's CPU rendezvous and steps slow to
                                    minutes/each. Inference doesn't hit
                                    that path BUT we keep parity with the
                                    training image.
  * transformers>=4.40,<4.47      — 4.47+ requires torch>=2.4; image has 2.2.
  * datasets>=2.18,<3             — for streaming Wikipedia.

Inputs:
    --output_path     /gcs/openetruscan-rosetta/embeddings/lat-grc-xlmr-v2.jsonl
    --top_n           per-language token count cap (default 100000)
    --max_articles    safety cap on articles streamed per language

Output:
    JSONL, one row per token: {"language": "lat"|"grc", "word": "...",
    "vector": [768 floats]}.
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
    """Same fixes the LoRA training script uses; keeps the two jobs in
    lockstep so a bug found in one is a bug fixed in both."""
    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "-y", "torch_xla"],
        check=False,
    )
    pkgs = []
    for mod, pkg in [
        ("transformers", "transformers>=4.40,<4.47"),
        ("datasets", "datasets>=2.18,<3"),
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


# Keep tokens that are "real-looking words" — at least 2 unicode-letter chars,
# no digits anywhere, alphabetics + apostrophe + interior hyphen only.
WORD_RE = re.compile(r"\b[^\W\d_][^\W\d_'\-]{1,30}(?:['\-][^\W\d_]+){0,3}\b", re.UNICODE)
MIN_LEN = 2
MAX_LEN = 32

# Per-language script gate: a token is "really" in this language only if it
# contains at least one character from the language's script block. Without
# this, English loanwords + Latin-letter brand names that pepper every modern
# Wikipedia leak into the vocab (e.g. `protect` ranks high in Greek WP because
# it appears in tech articles).
SCRIPT_REQUIRED = {
    # Greek block + Greek Extended (polytonic). Modern Greek pages also embed
    # Latin-script English; we filter those out here.
    "el": re.compile(r"[Ͱ-Ͽἀ-῿]"),
    # Latin pages can embed Cyrillic / Greek place names; require at least one
    # Latin letter as a sanity gate (still permissive — any Latin char passes).
    "la": re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]"),
}


def _build_vocab(language_code: str, top_n: int, max_articles: int | None,
                 log: logging.Logger) -> list[str]:
    """Stream Wikipedia for ``language_code`` (HF 2-letter), tokenise, return
    top-``top_n`` tokens by raw frequency.

    Tokens that don't contain at least one character from the language's
    expected script block are dropped — they're cross-language contamination
    (English loanwords, brand names, transliterated proper nouns) that would
    otherwise occupy slots that should hold real native vocabulary.
    """
    from datasets import load_dataset

    script_gate = SCRIPT_REQUIRED.get(language_code)

    # wikimedia/wikipedia hosts pre-extracted parquet snapshots — no
    # apache_beam dependency, supports streaming. The 20231101 snapshot is
    # the most recent stable one with parquet output.
    log.info("Loading Wikipedia[%s] in streaming mode...", language_code)
    ds = load_dataset(
        "wikimedia/wikipedia",
        f"20231101.{language_code}",
        split="train",
        streaming=True,
    )
    counts: collections.Counter[str] = collections.Counter()
    n_dropped_offscript = 0
    n_articles = 0
    t0 = time.time()
    for row in ds:
        text = row.get("text") or ""
        for tok in WORD_RE.findall(text.lower()):
            if not (MIN_LEN <= len(tok) <= MAX_LEN):
                continue
            if script_gate is not None and not script_gate.search(tok):
                n_dropped_offscript += 1
                continue
            counts[tok] += 1
        n_articles += 1
        if n_articles % 5000 == 0:
            log.info(
                "  [%s] %d articles, %d unique tokens, off-script dropped=%d, elapsed=%.0fs",
                language_code, n_articles, len(counts), n_dropped_offscript,
                time.time() - t0,
            )
        if max_articles is not None and n_articles >= max_articles:
            break

    log.info(
        "[%s] DONE: %d articles, %d unique tokens, off-script dropped=%d; taking top %d",
        language_code, n_articles, len(counts), n_dropped_offscript, top_n,
    )
    return [w for w, _ in counts.most_common(top_n)]


def _embed_and_write(words_by_lang: dict[str, list[str]], output_path: Path,
                     log: logging.Logger) -> int:
    """Mean-pool + L2-normalise every word's XLM-R-base contextual rep.
    Stream-writes to ``output_path`` so RAM stays bounded (200k * 768 * 4
    = 614 MB if held in memory)."""
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
    with output_path.open("w", encoding="utf-8") as f:
        for lang_code, words in words_by_lang.items():
            log.info("Embedding %d words for language=%s", len(words), lang_code)
            t0 = time.time()
            for i in range(0, len(words), BATCH):
                batch = words[i : i + BATCH]
                # max_length=16 is plenty — these are single words, XLM-R
                # SentencePiece will rarely split a word into >10 pieces.
                enc = tok(
                    batch, return_tensors="pt", padding=True,
                    truncation=True, max_length=16,
                ).to(device)
                with torch.no_grad():
                    out = model(**enc).last_hidden_state
                # Mean-pool over real tokens only (not pad).
                mask = enc.attention_mask.unsqueeze(-1).float()
                pooled = (out * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
                pooled = F.normalize(pooled, p=2, dim=1)
                vecs = pooled.cpu().tolist()
                for w, v in zip(batch, vecs, strict=True):
                    f.write(json.dumps(
                        {"language": lang_code, "word": w, "vector": v},
                        ensure_ascii=False,
                    ) + "\n")
                    n_total += 1
                if (i // BATCH) % 50 == 0:
                    elapsed = time.time() - t0
                    rate = (i + len(batch)) / elapsed if elapsed > 0 else 0
                    log.info(
                        "  [%s] %d/%d (%.0f w/s)",
                        lang_code, i + len(batch), len(words), rate,
                    )
    return n_total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output_path", required=True)
    parser.add_argument("--top_n", type=int, default=100_000)
    parser.add_argument(
        "--max_articles", type=int, default=None,
        help="Optional safety cap on articles per language (debugging).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("embed_vocab")

    _ensure_hf_stack()

    # HF 2-letter → ISO 639-3 mapping (matches openetruscan registry).
    # Greek Wikipedia is *modern* Greek; XLM-R was trained on modern
    # Greek; we label it "grc" (ancient Greek) per the registry's
    # alignable=True flag, with the proxy caveat documented there.
    lang_map = {"la": "lat", "el": "grc"}

    vocabs = {}
    for hf_code, iso_code in lang_map.items():
        vocabs[iso_code] = _build_vocab(hf_code, args.top_n, args.max_articles, log)

    output_path = Path(args.output_path)
    n = _embed_and_write(vocabs, output_path, log)
    log.info("Wrote %d total embeddings to %s", n, output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
