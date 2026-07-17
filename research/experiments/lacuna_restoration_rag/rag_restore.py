"""Aeneas-style retrieval-augmented lacuna restoration.
Char-ngram retriever pulls k parallel inscriptions (leakage-excluded) into the
prompt. Holds the model constant vs the single-shot baseline so any lift is
attributable to retrieval. Modes: rag single-shot (temp 0), rag self-consistency."""

import json
import sys
import re
import math
from collections import Counter
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from google import genai
from google.genai import types

SP = Path(__file__).resolve().parent
POOL = [
    json.loads(line) for line in (SP / "blind_pool.jsonl").read_text().splitlines() if line.strip()
]
GOLD = json.loads((SP / "gold_map.json").read_text())
CORPUS = json.loads((SP / "corpus.json").read_text())

SYSTEM_PROMPT = """You are restoring damaged Etruscan inscriptions. You will see
an inscription with a single marked lacuna of known character width, plus a set
of PARALLEL inscriptions (similar known texts that may share formulae or names).
Use the parallels as evidence for what characters originally filled the lacuna,
in canonical philological transliteration.

Output a JSON object only. Do NOT change any character outside the lacuna span.
If you cannot make a confident restoration, set confidence = "low" and provide
your best guess anyway.
"""
USER_TEMPLATE = """## Inscription (single lacuna marked with ? of width {width})

```
{masked_text}
```

## Parallel inscriptions (most similar known texts; may share formulae/names)
{parallels}

Metadata:
- Width: {width} characters

Return JSON exactly:
{{
  "id": {id_json},
  "restored_lacuna": "<exactly {width} characters>",
  "restored_alternates": ["<alt 1>", "<alt 2>", "<alt 3>"],
  "restored_full": "<the entire inscription with the lacuna filled; everything else byte-identical to input>",
  "confidence": "high|medium|low",
  "rationale": "<2-3 sentences: cite which parallel(s) or formula drove the restoration>",
  "codebook_version": "v2.0"
}}

Hard rules:
- `restored_lacuna` must be EXACTLY {width} characters.
- `restored_full` = input with the `?` span replaced by `restored_lacuna`, nothing else changed.
"""


def ngrams(s, n=3):
    s = re.sub(r"[^\wθχφσśπ𐌀-𐌿]", "", (s or "").lower())
    return Counter(s[i : i + n] for i in range(len(s) - n + 1)) if len(s) >= n else Counter([s])


def cos(a, b):
    keys = set(a) | set(b)
    dot = sum(a[k] * b[k] for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


CORP_NG = [(c["id"], c["canonical"], ngrams(c["canonical"])) for c in CORPUS]


def visible(masked, width):
    start = masked.index("?")
    return masked[:start] + masked[start + width :]


def retrieve(row, k=8):
    """Top-k parallels by char-ngram cosine on the VISIBLE text; leakage-excluded."""
    q = ngrams(visible(row["masked"], row["width"]))
    gold_full = row["masked"].replace(
        "?" * row["width"], GOLD[row["key"]], 1
    )  # used ONLY to exclude the answer
    gnorm = re.sub(r"[^\wθχφσśπ𐌀-𐌿]", "", gold_full.lower())
    scored = []
    for cid, canon, cng in CORP_NG:
        cnorm = re.sub(r"[^\wθχφσśπ𐌀-𐌿]", "", canon.lower())
        # leakage guard: skip the target itself or near-duplicates that reveal gold
        if cid == str(row["id"]):
            continue
        if cnorm and (cnorm in gnorm or gnorm in cnorm):
            continue
        if cos(q, cng) > 0.9 and abs(len(cnorm) - len(gnorm)) <= 2:
            continue
        scored.append((cos(q, cng), canon))
    scored.sort(reverse=True)
    return [c for _, c in scored[:k]]


def check_hall(masked, rf, width):
    if not rf:
        return True
    try:
        start = masked.index("?")
    except ValueError:
        return True
    if len(rf) < start + width:
        return True
    return rf[:start] != masked[:start] or rf[start + width :] != masked[start + width :]


def parse(raw, width, masked):
    err = None
    payload = {}
    decoded = False
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    if not text:
        err = "empty"
    else:
        try:
            payload = json.loads(text)
            decoded = isinstance(payload, dict)
        except Exception as e:
            err = f"decode:{e}"
    if not isinstance(payload, dict):
        payload = {}
    restored = str(payload.get("restored_lacuna", ""))
    rf = str(payload.get("restored_full", ""))
    no_parse = (not decoded) or (not rf)
    return dict(
        restored_lacuna=restored,
        restored_full=rf,
        no_parse=no_parse,
        confidence=str(payload.get("confidence", "low")).lower(),
        hallucinated=check_hall(masked, rf, width) if not no_parse else False,
        parse_error=err,
    )


client = genai.Client(vertexai=True, project="tripcreator-prod", location="global")


def call(mid, up, temp):
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=temp,
        max_output_tokens=1024,
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    for _ in range(3):
        try:
            r = client.models.generate_content(model=mid, contents=up, config=cfg)
            if (r.text or "").strip():
                return r.text
        except Exception:
            pass
    return ""


def run_rag(mid, temp, tag):
    def one(row):
        pars = retrieve(row, k=8)
        parallels = "\n".join(f"{i+1}. {p}" for i, p in enumerate(pars)) or "(none found)"
        up = USER_TEMPLATE.format(
            width=row["width"],
            masked_text=row["masked"],
            parallels=parallels,
            id_json=json.dumps(row["id"]),
        )
        p = parse(call(mid, up, temp), row["width"], row["masked"])
        return dict(
            key=row["key"],
            id=row["id"],
            model=f"{mid}+{tag}",
            masked=row["masked"],
            width=row["width"],
            width_bucket=row["width_bucket"],
            gold_lacuna=GOLD[row["key"]],
            **p,
        )

    with ThreadPoolExecutor(max_workers=10) as ex:
        return list(ex.map(one, POOL))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "single"
    mid = sys.argv[2] if len(sys.argv) > 2 else "gemini-3.1-pro-preview"
    if mode == "single":
        rows = run_rag(mid, 0.0, "rag")
        (SP / f"rag_{mid}.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
        )
        print("wrote", len(rows))
