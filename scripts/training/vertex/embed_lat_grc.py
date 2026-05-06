"""
Embed top-50k Latin + 50k Greek words using XLM-R base.

Reads word-frequency lists from Wikipedia dumps, encodes each word
through xlm-roberta-base, and writes {lang, word, vector} JSONL lines
to GCS.

Usage (Vertex AI):
    python embed_lat_grc.py \
        --output_path=/gcs/openetruscan-rosetta/embeddings/lat-grc-xlmr.jsonl \
        --top_n=50000

Local test (first 100 words):
    python embed_lat_grc.py --output_path=/tmp/test.jsonl --top_n=100
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

import requests
import torch
from transformers import AutoTokenizer, AutoModel


# ---------------------------------------------------------------------------
# Wikipedia frequency extraction
# ---------------------------------------------------------------------------

def fetch_wiki_words(lang_code: str, top_n: int = 50_000) -> list[str]:
    """
    Fetch the most frequent words from a Wikipedia language edition.

    Uses the Wikimedia REST API to pull random articles in batches,
    tokenize them, and count word frequencies. For Latin (la) and
    Greek (el) Wikipedias, ~2000 articles gives good frequency coverage
    for the top 50k lemmas.
    """
    print(f"[{lang_code}] Fetching word frequencies from {lang_code}.wikipedia.org ...")
    word_counts: Counter = Counter()
    session = requests.Session()
    session.headers.update({"User-Agent": "OpenEtruscanRosetta/1.0 (Contact: edpanichi@gmail.com)"})

    # Pull articles via the REST API (more reliable than the action API
    # for bulk text extraction). We request HTML and strip tags.
    api_url = f"https://{lang_code}.wikipedia.org/w/api.php"
    batch_size = 50  # max titles per query
    total_articles = 0
    target_articles = 2000  # enough for 50k unique words

    # Step 1: Get random article titles
    titles = []
    while len(titles) < target_articles:
        resp = session.get(api_url, params={
            "action": "query",
            "list": "random",
            "rnnamespace": 0,
            "rnlimit": batch_size,
            "format": "json",
        }, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        titles.extend([r["title"] for r in data["query"]["random"]])
        print(f"  [{lang_code}] Collected {len(titles)} titles ...", end="\r")

    print(f"\n  [{lang_code}] Fetching text for {len(titles)} articles ...")

    # Step 2: Fetch extracts in batches
    for i in range(0, len(titles), batch_size):
        batch = titles[i : i + batch_size]
        resp = session.get(api_url, params={
            "action": "query",
            "titles": "|".join(batch),
            "prop": "extracts",
            "explaintext": True,
            "exlimit": batch_size,
            "format": "json",
        }, timeout=60)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            text = page.get("extract", "")
            if not text:
                continue
            total_articles += 1
            # Tokenize: keep only alphabetic words >= 2 chars
            words = re.findall(r"[a-zA-ZÀ-ÿα-ωά-ώΑ-Ω]{2,}", text.lower())
            word_counts.update(words)

        if (i // batch_size) % 10 == 0:
            print(f"  [{lang_code}] Processed {i + len(batch)}/{len(titles)} articles, "
                  f"{len(word_counts)} unique words so far ...")

    print(f"  [{lang_code}] Done. {total_articles} articles, "
          f"{len(word_counts)} unique words. Taking top {top_n}.")

    return [word for word, _ in word_counts.most_common(top_n)]


# ---------------------------------------------------------------------------
# XLM-R embedding
# ---------------------------------------------------------------------------

def embed_words(
    words: list[str],
    lang: str,
    tokenizer,
    model,
    device: torch.device,
    batch_size: int = 256,
) -> list[dict]:
    """
    Encode a list of words through XLM-R and return {lang, word, vector} dicts.

    Uses mean-pooling over subword tokens (excluding [CLS] and [SEP])
    to produce a single 768-d vector per word.
    """
    results = []
    model.eval()

    for i in range(0, len(words), batch_size):
        batch = words[i : i + batch_size]
        inputs = tokenizer(
            batch,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=32,
        ).to(device)

        with torch.no_grad():
            outputs = model(**inputs)

        # Mean-pool over non-padding tokens (skip CLS/SEP via attention_mask)
        mask = inputs["attention_mask"].unsqueeze(-1).float()
        token_embeds = outputs.last_hidden_state
        summed = (token_embeds * mask).sum(dim=1)
        counts = mask.sum(dim=1).clamp(min=1)
        pooled = (summed / counts).cpu()

        for j, word in enumerate(batch):
            results.append({
                "lang": lang,
                "word": word,
                "vector": pooled[j].tolist(),
            })

        if (i // batch_size) % 50 == 0:
            print(f"  [{lang}] Embedded {i + len(batch)}/{len(words)} words ...")

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output_path", required=True,
                        help="Path to write JSONL (local or /gcs/...)")
    parser.add_argument("--top_n", type=int, default=50_000,
                        help="Top-N words per language")
    parser.add_argument("--model_name", default="xlm-roberta-base")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    print(f"Loading {args.model_name} ...")
    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = AutoModel.from_pretrained(args.model_name).to(device)

    # --- Latin ---
    lat_words = fetch_wiki_words("la", args.top_n)
    lat_embeddings = embed_words(lat_words, "lat", tokenizer, model, device)

    # --- Greek ---
    grc_words = fetch_wiki_words("el", args.top_n)
    grc_embeddings = embed_words(grc_words, "grc", tokenizer, model, device)

    # --- Write JSONL ---
    all_embeddings = lat_embeddings + grc_embeddings
    print(f"Writing {len(all_embeddings)} embeddings to {args.output_path} ...")

    # Handle /gcs/ paths (Vertex AI GCSFuse) or local paths
    os.makedirs(os.path.dirname(args.output_path) or ".", exist_ok=True)
    with open(args.output_path, "w") as f:
        for record in all_embeddings:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Done. {len(all_embeddings)} embeddings written.")


if __name__ == "__main__":
    main()
