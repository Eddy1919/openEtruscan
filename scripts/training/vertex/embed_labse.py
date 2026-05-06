"""Vertex AI custom job: embed Latin + Greek + Etruscan vocab using LaBSE
(Feng et al 2020), purpose-built for cross-language semantic similarity.

Why this replaces XLM-R-base for the Rosetta path:
  * XLM-R was pretrained on monolingual masked-LM, no parallel-data
    objective. Cross-language token equivalence (clan_ett ≡ filius_lat)
    is *not* a thing it learns directly — explains the 0% precision@k
    we measured.
  * LaBSE is trained with a translation-ranking objective on parallel
    sentences across 109 languages — semantically equivalent words/
    sentences across languages get cosine-close *by construction*.
  * Output dim is 768 (matches our pgvector schema; no migration).

What we DON'T have here:
  * Etruscan in LaBSE's pretraining (it's not in the 109 supported
    languages). The encoder's Etruscan representations come from
    sub-word fallback to the Latin / Greek script tokens it does know.
    Hopefully the morphology + character-level signal is enough to
    place known cognates near their Latin equivalents. Empirically TBD.
  * The etr-lora-v3 adapter — built for XLM-R, not architecturally
    compatible with LaBSE. We start with base LaBSE; if numbers are
    promising, the next step is a LaBSE-shaped LoRA fine-tune on the
    same Etruscan corpus.

Output JSONL has the same schema as before: ``{language, word, vector}``.
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


def _ensure_stack() -> None:
    """Same fixes as the XLM-R scripts + sentence-transformers."""
    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "-y", "torch_xla"],
        check=False,
    )
    pkgs = []
    for mod, pkg in [
        ("transformers", "transformers>=4.40,<4.47"),
        ("datasets", "datasets>=2.18,<3"),
        ("accelerate", "accelerate>=0.27,<1.0"),
        # SBERT 3.x supports torch>=1.11 + transformers>=4.32; we already
        # pinned transformers<4.47 above so 3.x is the safe upper bound.
        ("sentence_transformers", "sentence-transformers>=3.0,<4.0"),
    ]:
        try:
            __import__(mod)
        except ImportError:
            pkgs.append(pkg)
    if pkgs:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", *pkgs]
        )


WORD_RE = re.compile(r"\b[^\W\d_][^\W\d_'\-]{1,30}(?:['\-][^\W\d_]+){0,3}\b", re.UNICODE)
MIN_LEN = 2
MAX_LEN = 32
SCRIPT_REQUIRED = {
    "el": re.compile(r"[Ͱ-Ͽἀ-῿]"),
    "la": re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]"),
}


def _build_wikipedia_vocab(language_code: str, top_n: int,
                            log: logging.Logger) -> list[str]:
    from datasets import load_dataset
    script_gate = SCRIPT_REQUIRED.get(language_code)
    log.info("Loading Wikipedia[%s]...", language_code)
    ds = load_dataset("wikimedia/wikipedia", f"20231101.{language_code}",
                       split="train", streaming=True)
    counts: collections.Counter[str] = collections.Counter()
    n_articles = 0
    n_dropped = 0
    t0 = time.time()
    for row in ds:
        text = row.get("text") or ""
        for tok in WORD_RE.findall(text.lower()):
            if not (MIN_LEN <= len(tok) <= MAX_LEN):
                continue
            if script_gate is not None and not script_gate.search(tok):
                n_dropped += 1
                continue
            counts[tok] += 1
        n_articles += 1
        if n_articles % 5000 == 0:
            log.info("  [%s] %d articles, %d unique tokens, dropped=%d, %.0fs",
                     language_code, n_articles, len(counts), n_dropped,
                     time.time() - t0)
    log.info("[%s] DONE: %d articles → top %d of %d uniques",
             language_code, n_articles, top_n, len(counts))
    return [w for w, _ in counts.most_common(top_n)]


def _normalise_dividers(text: str) -> str:
    """Etruscan word-divider normalisation, must match LoRA training."""
    return " ".join(text.translate(str.maketrans({":": " ", "·": " ", "•": " "})).split())


def _build_etruscan_vocab(corpus_path: Path, log: logging.Logger) -> list[str]:
    counts: collections.Counter[str] = collections.Counter()
    n_inscs = 0
    with corpus_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            text = (row.get("text") or row.get("canonical") or "").strip()
            if not text:
                continue
            text = _normalise_dividers(text)
            for tok in text.lower().split():
                tok = tok.strip(",;!?\"'()[]\\.")
                # require ≥2 alphabetic chars to drop punctuation noise
                # ('.', '|', single letters) we saw in the v3 etr file.
                alpha = sum(1 for c in tok if c.isalpha())
                if alpha < 2:
                    continue
                counts[tok] += 1
            n_inscs += 1
    log.info("Etruscan vocab built from %d inscriptions: %d unique tokens",
             n_inscs, len(counts))
    return [w for w, _ in counts.most_common()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output_path", required=True)
    parser.add_argument("--etruscan_corpus_path", required=True)
    parser.add_argument("--top_n_per_lang", type=int, default=100_000)
    parser.add_argument("--model_name", default="sentence-transformers/LaBSE")
    parser.add_argument("--batch_size", type=int, default=64)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("embed_labse")

    _ensure_stack()

    import torch
    from sentence_transformers import SentenceTransformer

    log.info("torch=%s cuda=%s", torch.__version__, torch.cuda.is_available())
    if torch.cuda.is_available():
        log.info("device=%s", torch.cuda.get_device_name(0))

    log.info("Building vocabularies...")
    vocabs: dict[str, list[str]] = {
        "lat": _build_wikipedia_vocab("la", args.top_n_per_lang, log),
        "grc": _build_wikipedia_vocab("el", args.top_n_per_lang, log),
        "ett": _build_etruscan_vocab(Path(args.etruscan_corpus_path), log),
    }
    log.info("Vocab sizes: %s", {k: len(v) for k, v in vocabs.items()})

    log.info("Loading %s...", args.model_name)
    model = SentenceTransformer(args.model_name)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    log.info("model on %s, dim=%d", device, model.get_sentence_embedding_dimension())

    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    n_total = 0
    with output_path.open("w", encoding="utf-8") as f:
        for lang, words in vocabs.items():
            log.info("Embedding %d %s words...", len(words), lang)
            t0 = time.time()
            # SBERT handles batching, normalisation, and pooling internally.
            vectors = model.encode(
                words,
                batch_size=args.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            elapsed = time.time() - t0
            log.info("  %s embed done in %.1fs (%.0f w/s)",
                     lang, elapsed, len(words) / elapsed if elapsed else 0)
            for w, v in zip(words, vectors, strict=True):
                f.write(json.dumps(
                    {"language": lang, "word": w, "vector": v.tolist()},
                    ensure_ascii=False,
                ) + "\n")
                n_total += 1
    log.info("Wrote %d total embeddings to %s", n_total, output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
