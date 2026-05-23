"""Multi-model lacuna restoration jury for Stream C.

Reads the candidate pool from `lacuna_mine.py` and asks each frontier model
to fill in the lacuna. The model is presented the *masked* form of the
inscription (gold replaced with `?` characters of the correct count) and
must return a single best-guess fill, three alternatives, and a confidence.

Hallucination detection happens here too: if a model's `restored_full`
output deviates from the input outside the marked lacuna span, we record
`hallucinated=True` for that row.

Like classify_jury, this is the orchestrator. The eval metrics
(top-1 char accuracy, hallucination rate, etc.) live in
`eval/lacuna_metrics.py`.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_jury import PROVIDER_REGISTRY  # noqa: E402

def _resolve_codebook(language: str) -> Path:
    return Path(__file__).resolve().parent.parent / "codebooks" / language / "lacunae.md"


# Default to Etruscan for backward compatibility.
CODEBOOK_PATH = _resolve_codebook("etr")

SYSTEM_PROMPT = """You are restoring damaged Etruscan inscriptions. You will see
an inscription with a single marked lacuna of known character width. Your job
is to predict the characters that originally filled the lacuna, in canonical
philological transliteration.

Output a JSON object only. Do NOT change any character outside the lacuna span.
If you cannot make a confident restoration, set confidence = "low" and provide
your best guess anyway; we will analyze low-confidence restorations separately.
"""

USER_TEMPLATE = """## Inscription (single lacuna marked with ? of width {width})

```
{masked_text}
```

Metadata:
- Width: {width} characters
- Inscription type (silver label, may be wrong): {inscription_type}
- Translation (English, may be empty): {translation!r}

Return JSON exactly:
{{
  "id": {id_json},
  "restored_lacuna": "<exactly {width} characters>",
  "restored_alternates": ["<alt 1>", "<alt 2>", "<alt 3>"],
  "restored_full": "<the entire inscription with the lacuna filled in; everything else is byte-identical to the input>",
  "confidence": "high|medium|low",
  "rationale": "<2-3 sentences: parallels, formulaic context, or phonological reasoning>",
  "codebook_version": "v2.0"
}}

Hard rules:
- `restored_lacuna` must be EXACTLY {width} characters.
- `restored_full` must equal the input except that the `?` span is replaced
  by `restored_lacuna`. Do not change any other character. We programmatically
  check this; any deviation counts as hallucination.
"""


def make_masked(row: dict) -> str:
    width = row["width"]
    return f"{row['context_before']} {'?' * width} {row['context_after']}".strip()


def check_hallucination(masked: str, restored_full: str, width: int) -> bool:
    """Return True iff restored_full deviates from masked outside the ? span."""
    if not restored_full:
        return True
    # Replace the ?...? span in masked with the same length placeholder, then
    # do a strict outside-of-span comparison.
    try:
        start = masked.index("?")
    except ValueError:
        return True
    end = start + width
    masked_before = masked[:start]
    masked_after = masked[end:]
    if len(restored_full) < start + width:
        return True
    restored_before = restored_full[:start]
    restored_after = restored_full[start + width :]
    return restored_before != masked_before or restored_after != masked_after


def parse_response(insc_id: str, raw: str, width: int, masked: str) -> dict:
    payload: dict = {}
    err: str | None = None
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        err = f"json_decode_error: {e}"
    if not isinstance(payload, dict):
        err = err or "not_a_dict"
        payload = {}
    restored = str(payload.get("restored_lacuna", ""))
    if len(restored) != width:
        err = err or f"wrong_width: got {len(restored)}, expected {width}"
    restored_full = str(payload.get("restored_full", ""))
    hallucinated = check_hallucination(masked, restored_full, width) if restored_full else True
    return {
        "id": insc_id,
        "restored_lacuna": restored,
        "restored_alternates": list(payload.get("restored_alternates") or []),
        "restored_full": restored_full,
        "confidence": str(payload.get("confidence", "low")).lower(),
        "rationale": str(payload.get("rationale", "")),
        "hallucinated": hallucinated,
        "parse_error": err,
        "codebook_version": str(payload.get("codebook_version", "v2.0")),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pool", type=Path, required=True,
                    help="Mined candidate pool from lacuna_mine.py")
    ap.add_argument("--out", type=Path, required=True,
                    help="Append-mode JSONL of jury outputs.")
    ap.add_argument("--providers", nargs="+",
                    default=["claude-haiku-4-5", "gemini-2.5-pro", "llama-4-maverick"])
    ap.add_argument("--language", default="etr",
                    help="ISO-639-3 code selecting which lacunae codebook to use.")
    ap.add_argument("--max-rows", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=0.5)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    # Resolve codebook based on --language (defaults to etr for back-compat).
    codebook_path = _resolve_codebook(args.language)
    if not codebook_path.exists():
        print(f"ERROR: codebook not found at {codebook_path}", file=sys.stderr)
        return 1

    candidates = [json.loads(line) for line in args.pool.read_text().splitlines() if line.strip()]
    if args.max_rows:
        candidates = candidates[: args.max_rows]
    if not candidates:
        print(f"ERROR: empty pool at {args.pool}", file=sys.stderr)
        return 1

    providers = []
    if not args.dry_run:
        for name in args.providers:
            factory = PROVIDER_REGISTRY.get(name)
            if factory is None:
                print(f"unknown provider {name}", file=sys.stderr)
                return 1
            try:
                providers.append(factory())
            except ImportError as e:
                print(f"provider {name} needs SDK: {e}", file=sys.stderr)
                return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    sink = args.out.open("a")
    halluc_count = 0
    completed = 0
    try:
        for row in candidates:
            masked = make_masked(row)
            user_prompt = USER_TEMPLATE.format(
                width=row["width"],
                masked_text=masked,
                inscription_type=row.get("inscription_type", ""),
                translation=row.get("translation", ""),
                id_json=json.dumps(row["id"]),
            )
            if args.dry_run:
                print(f"--- DRY :: {row['id']} ---")
                print(user_prompt[:400] + "...")
                continue
            for provider_name, provider in zip(args.providers, providers, strict=False):
                try:
                    raw = provider.invoke(SYSTEM_PROMPT, user_prompt)
                except Exception as e:  # noqa: BLE001
                    print(f"  api_error [{provider_name} {row['id']}]: {e}",
                          file=sys.stderr)
                    time.sleep(args.sleep)
                    continue
                parsed = parse_response(row["id"], raw, row["width"], masked)
                parsed["model"] = provider_name
                parsed["width"] = row["width"]
                parsed["width_bucket"] = row["width_bucket"]
                parsed["gold_lacuna"] = row["lacuna_gold"]
                parsed["masked"] = masked
                if parsed["hallucinated"]:
                    halluc_count += 1
                sink.write(json.dumps(parsed, ensure_ascii=False) + "\n")
                sink.flush()
                completed += 1
                if completed % 25 == 0:
                    print(f"  progress: {completed} (hallucinated so far: {halluc_count})",
                          file=sys.stderr)
                time.sleep(args.sleep)
    finally:
        sink.close()

    print(f"Done. completed={completed} hallucinated={halluc_count}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
