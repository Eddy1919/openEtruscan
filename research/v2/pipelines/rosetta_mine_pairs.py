"""Bilingual-pair miner for Rosetta-eval-v2.

Extends the v1 pipeline (which only mined Greek glosses) to cover Latin
grammarians (Varro, Festus, Pliny, Servius) as well, and runs every raw
candidate through a multi-LLM-jury substring + assertion check before it
joins the candidate gold set.

This script is **stateless** — it reads passage text from a JSONL bundle and
writes raw / validated / rejected outputs. The expensive work (LLM
extraction) is the same as `scripts/research/llm_extract_anchors.py` but
reorganized so it can be re-run incrementally as new passages are added.

Passage bundles
---------------
Each passage bundle is a JSONL with rows of the form:

    {
      "passage_index": 167,
      "source": "Dionysius of Halicarnassus Antiquitates Romanae",
      "source_lang": "grc",          // "grc" or "lat"
      "text": "τύρσεις γὰρ καὶ παρὰ Τυρρηνοῖς αἱ ἐντείχιοι..."
    }

The script processes each passage independently. Output rows are:

    {
      "passage_index": 167,
      "source": "...",
      "etruscan_word": "τύρσεις",
      "equivalent": "αἱ ἐντείχιοι καὶ στεγαναὶ οἰκήσεις",
      "equivalent_language": "grc",
      "category": "civic",
      "evidence_quote": "...",
      "model": "claude-opus-4-7",
      "verbatim_substring_ok": true,
      "explicit_assertion_ok": true,
      "extracted_at": "2026-05-17T..."
    }

Passes are then merged in `rosetta_jury_merge` (separate utility): a row is
candidate-valid iff all jury models extract the same pair AND both gate
checks pass.

This script is the orchestrator; it delegates the per-passage LLM call to a
provider adapter shared with classify_jury.py.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Reuse the provider registry from classify_jury so we have one source of
# truth for model adapters.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_jury import PROVIDER_REGISTRY  # noqa: E402

SYSTEM_PROMPT = """You are extracting bilingual lexical equivalences between
Etruscan and {target_lang} from a classical text passage. The classical author
must explicitly assert the equivalence. Extract only verbatim glosses, never
inferred ones. Return a JSON array; empty array if no valid pair.
"""

USER_TEMPLATE = """Source: {source}
Source language: {source_lang}
Passage text:
\"\"\"
{text}
\"\"\"

Extract every (Etruscan word, {target_lang} equivalent) pair that the author
explicitly equates. For each pair return:

{{
  "etruscan_word": "<verbatim substring of the passage>",
  "equivalent": "<verbatim substring of the passage>",
  "equivalent_language": "{equiv_lang_code}",
  "category": "<one of: kinship, theonym, place, civic, funerary, cognate, gloss_only>",
  "evidence_quote": "<verbatim sentence that contains both words and the verb of equation>"
}}

Hard requirements (any violation: drop the pair, return empty array):
1. Both `etruscan_word` and `equivalent` must be verbatim substrings of `text`.
2. The `evidence_quote` must be a verbatim substring of `text`.
3. The author must use an explicit verb of equation (Greek: ὀνομάζονται, ἐκάλεσαν,
   λέγουσι, καλοῦσι; Latin: appellare, vocare, dicere, nominare).
4. Do not infer. If you are not sure both words appear verbatim, drop the pair.

Return a JSON object with a single field `pairs` containing the array, e.g.

  {{"pairs": [{{...}}, {{...}}]}}

If no valid pair found, return {{"pairs": []}}. Do not include prose.
"""


def _check_substring(needle: str, haystack: str) -> bool:
    if not needle:
        return False
    return needle in haystack


def _check_assertion(quote: str, lang: str) -> bool:
    quote_l = quote.lower()
    if lang == "grc":
        verbs = ("ὀνομάζο", "ἐκάλεσ", "λέγου", "καλοῦ", "ὀνομάζε", "καλεῖ", "καλοῦντα")
    else:
        verbs = ("appell", "vocav", "vocat", "voca", "dicit", "dicunt", "nominat", "dixere")
    return any(v in quote_l for v in verbs)


def iter_passages(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--passages", type=Path, required=True,
                    help="JSONL of source passages.")
    ap.add_argument("--out", type=Path, required=True,
                    help="Output JSONL of candidate pairs (append-mode).")
    ap.add_argument("--providers", nargs="+",
                    default=["claude-haiku-4-5", "gemini-2.5-pro", "llama-4-maverick"])
    ap.add_argument("--max-passages", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=0.5)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    passages = iter_passages(args.passages)
    if args.max_passages:
        passages = passages[: args.max_passages]
    if not passages:
        print(f"ERROR: empty passage file {args.passages}", file=sys.stderr)
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
    kept = dropped_substring = dropped_assertion = parse_errors = 0
    try:
        for passage in passages:
            text = passage.get("text", "")
            source_lang = passage.get("source_lang", "grc")
            target_lang = "Latin" if source_lang == "lat" else "Greek"
            equiv_lang_code = source_lang  # the equivalent is in the source's language
            user = USER_TEMPLATE.format(
                source=passage.get("source", ""),
                source_lang=source_lang,
                text=text,
                target_lang=target_lang,
                equiv_lang_code=equiv_lang_code,
            )
            system = SYSTEM_PROMPT.format(target_lang=target_lang)

            if args.dry_run:
                print(f"--- DRY :: passage {passage['passage_index']} ---")
                print(user[:400] + "...")
                continue
            for provider_name, provider in zip(args.providers, providers, strict=False):
                try:
                    raw = provider.invoke(system, user)
                except Exception as e:  # noqa: BLE001
                    print(f"  [{provider_name} #{passage['passage_index']}] api_error: {e}",
                          file=sys.stderr)
                    time.sleep(args.sleep)
                    continue
                text_resp = raw.strip()
                if text_resp.startswith("```"):
                    text_resp = text_resp.strip("`").strip()
                    if text_resp.startswith("json"):
                        text_resp = text_resp[4:].strip()
                try:
                    payload = json.loads(text_resp)
                except json.JSONDecodeError:
                    parse_errors += 1
                    continue
                # Accept either {"pairs": [...]} envelope or bare array.
                # JSON-mode-enforcing providers (Llama, etc.) require object
                # so the prompt now asks for the envelope; bare-array
                # responses from older outputs still parse.
                if isinstance(payload, dict) and "pairs" in payload:
                    candidates = payload["pairs"]
                elif isinstance(payload, list):
                    candidates = payload
                else:
                    parse_errors += 1
                    continue
                if not isinstance(candidates, list):
                    parse_errors += 1
                    continue
                for cand in candidates:
                    if not isinstance(cand, dict):
                        continue
                    et = str(cand.get("etruscan_word", ""))
                    eq = str(cand.get("equivalent", ""))
                    ev = str(cand.get("evidence_quote", ""))
                    cat = str(cand.get("category", "gloss_only"))
                    substr_ok = _check_substring(et, text) and _check_substring(eq, text) and _check_substring(ev, text)
                    assert_ok = _check_assertion(ev, source_lang)
                    record = {
                        "passage_index": passage.get("passage_index"),
                        "source": passage.get("source"),
                        "etruscan_word": et,
                        "equivalent": eq,
                        "equivalent_language": source_lang,
                        "category": cat,
                        "evidence_quote": ev,
                        "model": provider_name,
                        "verbatim_substring_ok": substr_ok,
                        "explicit_assertion_ok": assert_ok,
                        "extracted_at": datetime.now(tz=timezone.utc).isoformat(),
                    }
                    if not substr_ok:
                        dropped_substring += 1
                    elif not assert_ok:
                        dropped_assertion += 1
                    else:
                        kept += 1
                    sink.write(json.dumps(record, ensure_ascii=False) + "\n")
                    sink.flush()
                time.sleep(args.sleep)
    finally:
        sink.close()

    print(f"kept={kept} dropped_substring={dropped_substring} "
          f"dropped_assertion={dropped_assertion} parse_errors={parse_errors}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
