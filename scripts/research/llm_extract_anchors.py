#!/usr/bin/env python3
"""Extract bilingual gloss equivalences from the classical-passages corpus
using Gemini 2.5 Pro on Vertex AI (billed to `double-runway-465420-h9`).

Implements WBS task T4.1 — *LLM-as-parser*. The goal is to surface
**verbatim-attested** equivalences of the form

    "the Etruscans called X what we (Greeks / Romans) call Y"

from the 1,795 Greek + Latin passages in
`data/extracted/etruscan_passages.jsonl`, without the LLM drawing on
its outside knowledge of Etruscan. Every emitted equivalence carries
an `evidence_quote` that **must be a verbatim substring** of the
source passage — the script post-validates this and drops rows that
fail.

Originally specified to run on Claude via Anthropic-on-Vertex (per the
WBS), but that publisher hasn't been enabled in this project yet (a
manual Terms-of-Service acceptance in the GCP console is required and
this script does not have the IAM scope to flip it). Gemini 2.5 Pro is
substituted: same gcloud-native auth path, same billing to
double-runway, comparable structured-extraction quality on short
classical-prose passages, and a friendlier default cost envelope
(~$1.50 estimated for the full 1,795 passages versus ~$5 on Claude
Sonnet at the WBS pricing). The script is structured so the model can
be swapped out (`--model`) if Anthropic-on-Vertex gets enabled later.

USAGE
-----

```bash
# Dry-run: count what would be processed, estimate cost (no API calls).
python scripts/research/llm_extract_anchors.py --dry-run

# Pilot: process the first 20 passages, write to default output path.
python scripts/research/llm_extract_anchors.py --limit 20

# Full run (~1795 passages, ~3-4 minutes wall, ~$1.50 estimated).
python scripts/research/llm_extract_anchors.py

# Resume after interruption: re-run with the same output path; the
# script reads it back at start, skips passages already processed.
python scripts/research/llm_extract_anchors.py --output data/extracted/llm_anchors_raw.jsonl
```

OUTPUT SCHEMA
-------------

`data/extracted/llm_anchors_raw.jsonl` — one JSON object per emitted
gloss, with the shape:

    {
      "etruscan_word": "aesar",
      "equivalent": "deus",
      "equivalent_language": "lat",
      "evidence_quote": "Tuscique deos `aesares` vocabant",
      "source": "Suetonius Divus Augustus 97",
      "passage_index": 1234,                    # row index in input file
      "model": "gemini-2.5-pro",
      "extracted_at": "2026-05-11T09:15:00Z"
    }

If a passage yields zero glosses, no rows are written for that passage
(an empty `[]` is the model's expected response for "no gloss
present"). Resumability is keyed off the per-passage status sidecar
`<output>.passages.jsonl` which records `{"passage_index": N,
"status": "processed", "n_glosses": K}` for every passage the script
has seen (whether or not it produced output) — this is what lets a
re-run skip already-processed input.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any
from collections.abc import Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_INPUT = REPO_ROOT / "data" / "extracted" / "etruscan_passages.jsonl"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "extracted" / "llm_anchors_raw.jsonl"

DEFAULT_MODEL = "gemini-2.5-pro"
DEFAULT_PROJECT = "double-runway-465420-h9"
DEFAULT_REGION = "europe-west1"

# Gemini 2.5 Pro pricing (USD per million tokens) — used only for the
# end-of-run cost estimate. Update if pricing changes; this is signal,
# not billing.
PRICE_PER_MTOK_INPUT = 1.25
PRICE_PER_MTOK_OUTPUT = 10.00

logger = logging.getLogger("llm_extract_anchors")


SYSTEM_INSTRUCTION = """You extract bilingual gloss equivalences from classical Greek and Latin passages that mention the Etruscans (Τυρρηνοί / Tusci / Etrusci).

A **qualifying gloss** is a statement of the form:

    "the Etruscans call X what we call Y"

Three constraints, ALL required:

1. An **explicit verb of naming** — `vocant`, `appellant`, `nominant`, `dicunt`, `dicitur apud`, `καλοῦσι`, `ἐκάλεσαν`, `λέγεται`, `ὀνομάζουσιν`, or a clear semantic equivalent.

2. The **subject of that verb must be Etruscans / Tuscans / Tyrrhenians explicitly** — `Tusci vocant`, `Etrusci appellant`, `Τυρρηνοὶ καλοῦσι`, `apud Tuscos … dicitur`, `Etrusca lingua … uocatur`, `Τυρρηνῶν φωνῇ`. If the naming verb's subject is unspecified ("they call X"), implicit, or refers to Greeks / Romans / fishermen / locals / anyone-else, output `[]`. The Etruscan attribution must be **on the page**, not inferred from "the passage mentions Etruscans somewhere".

3. The Etruscan word (X) must be **transliterated or quoted as an Etruscan token**, not a Greek or Latin noun used in a Greek or Latin sentence. If the only words present are Greek-or-Latin nouns modified by a "Tyrrhenian" adjective, that is NOT a gloss — it is a normal phrase. Output `[]`.

Common false-positive traps to reject:

- "καλοῦσιν αὐτόν Y" — subject implicit, **not** explicitly Etruscan → `[]`
- A Latin technical term being explained in Greek prose ("ἰγκουιλῖνον … καλοῦσι τοὺς ἐνοικοῦντας") — that's Greek-glossing-Latin, not Etruscan → `[]`
- An ethnographic claim ("Tusci hominum sapientissimi") — no gloss → `[]`
- A toponym etymology where no Etruscan word is named ("derived from the Etruscans") → `[]`

Qualifying examples (these produce output):

    "aesar enim Etrusca lingua deus uocaretur"
        — explicit verb `uocaretur`; aesar is an Etruscan token; deus is Latin gloss.
    "Τυρρηνοὶ ἰταλὸν τὸν ταῦρον ἐκάλεσαν"
        — explicit verb `ἐκάλεσαν`; ἰταλόν is an Etruscan-origin token; ταῦρον is its Greek gloss.
    "histriones Etrusca lingua appellati sunt, quod hister apud Tuscos ludio dicitur"
        — explicit verb `dicitur`; hister is Etruscan; ludio is Latin.

NON-qualifying examples (these MUST produce `[]`):

    "Τυρσηνικὴ σάλπιγξ" — "Tyrrhenian trumpet" is a regular adjective + noun, no naming verb, no Etruscan token.
    "οἱ Τυρρηνοὶ τὴν Καίριον προσέλαβον" — narrative; no gloss.
    "Tusci ... antiqui ritus servabant" — Etruscans did something; not a gloss.
    "Αὐσονίης ἀκτὰς Τυρσηνίδας" — poetry equating regions; not a gloss.
    "Τυρρηνῶν στρατός" — "army of Tyrrhenians" — no gloss.

You MUST NOT use any outside knowledge of Etruscan. The equivalence must be **stated in the passage**. If you find yourself thinking "I know `lautn` means `familia`" — that's your outside knowledge talking; output `[]` unless the passage itself says `lautn` and `familia` and pairs them with a naming verb.

Output format: **strict JSON only**, a list of objects. If no qualifying gloss appears, output exactly `[]`. The vast majority of input passages should produce `[]` — that is correct. False positives are worse than false negatives here.

Each object:
- `etruscan_word`: the Etruscan token as it appears in the passage.
- `equivalent`: the Greek / Latin word the passage glosses it as.
- `equivalent_language`: `"lat"` or `"grc"` — match the language of the equivalent.
- `evidence_quote`: 5–40-word verbatim substring of the passage containing both `etruscan_word` and `equivalent` and the naming verb. Must match the passage character-for-character including diacritics and orthographic variants (u/v, σ/ς)."""


FEW_SHOT_EXAMPLES: list[dict[str, Any]] = [
    {
        "input_passage": (
            "AUTHOR: Suetonius Tranquillus\n"
            "WORK: De Vita Caesarum: Divus Augustus\n"
            "LANGUAGE: Latin\n"
            "TEXT: prosperum ac salutarem sibi praesumebat, quod gentile illi cognomen "
            "erat, vel quia eo verbo Tusci deum significant; aesar enim Etrusca lingua "
            "deus vocatur."
        ),
        "output_json": [
            {
                "etruscan_word": "aesar",
                "equivalent": "deus",
                "equivalent_language": "lat",
                "evidence_quote": "aesar enim Etrusca lingua deus vocatur",
            }
        ],
    },
    {
        "input_passage": (
            "AUTHOR: Diodorus Siculus\n"
            "WORK: Historical Library\n"
            "LANGUAGE: Greek\n"
            "TEXT: οἱ Τυρρηνοὶ τὴν χώραν τὴν λεγομένην Καίριον προσέλαβον καὶ πολλὰς "
            "πόλεις ἔκτισαν ἐν αὐτῇ."
        ),
        "output_json": [],
    },
    {
        "input_passage": (
            "AUTHOR: Servius\n"
            "WORK: In Vergilii Aeneidem\n"
            "LANGUAGE: Latin\n"
            "TEXT: histriones Etrusca lingua appellati sunt, quod hister apud Tuscos "
            "ludio dicitur."
        ),
        "output_json": [
            {
                "etruscan_word": "hister",
                "equivalent": "ludio",
                "equivalent_language": "lat",
                "evidence_quote": "hister apud Tuscos ludio dicitur",
            }
        ],
    },
]


def _setup_logging(verbose: bool) -> None:
    fmt = "%(asctime)s %(levelname)s %(message)s"
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format=fmt)


def _iter_passages(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    with path.open(encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                yield idx, json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("skipping bad JSON at line %d: %s", idx, exc)


_ETRUSCAN_KEYWORDS = re.compile(
    r"(?i)\b(tyrrhen|tursen|tursin|tyrsen|tyrrh|τυρρην|τυρσην|τυρσιν|tusc|etrusc|aesar|aisar)"
)
_MAX_PASSAGE_CHARS = 4000
_CONTEXT_WINDOW_CHARS = 1500  # before + after each keyword hit


def _smart_truncate(text: str) -> tuple[str, bool]:
    """Long passages cost a lot but only a small window around each
    Etruscan-mention is relevant for gloss extraction. For passages over
    _MAX_PASSAGE_CHARS, return the union of ±_CONTEXT_WINDOW_CHARS windows
    around every keyword hit, separated by `[...]` markers.

    Returns (truncated_text, was_truncated).
    """
    if len(text) <= _MAX_PASSAGE_CHARS:
        return text, False
    hits = list(_ETRUSCAN_KEYWORDS.finditer(text))
    if not hits:
        # No keyword hits but huge passage — fall back to head + tail.
        head = text[: _MAX_PASSAGE_CHARS // 2]
        tail = text[-_MAX_PASSAGE_CHARS // 2 :]
        return f"{head}\n[... truncated ...]\n{tail}", True
    # Merge overlapping windows.
    windows: list[tuple[int, int]] = []
    for m in hits:
        start = max(0, m.start() - _CONTEXT_WINDOW_CHARS)
        end = min(len(text), m.end() + _CONTEXT_WINDOW_CHARS)
        if windows and start <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(windows[-1][1], end))
        else:
            windows.append((start, end))
    chunks: list[str] = []
    prev_end = 0
    for start, end in windows:
        if start > prev_end:
            chunks.append("[...]")
        chunks.append(text[start:end])
        prev_end = end
    if prev_end < len(text):
        chunks.append("[...]")
    return "\n".join(chunks), True


def _format_passage(row: dict[str, Any]) -> str:
    """Format a passage row into the model's expected input shape."""
    text = (row.get("text") or "").strip()
    text, truncated = _smart_truncate(text)
    notice = " (windowed: only ±1500 chars around each Etruscan-mention shown)" if truncated else ""
    return (
        f"AUTHOR: {row.get('author', '?')}\n"
        f"WORK: {row.get('work', '?')}\n"
        f"LANGUAGE: {row.get('language', '?')}\n"
        f"TEXT{notice}: {text}"
    )


def _few_shot_block() -> str:
    parts = ["Worked examples — same task, three reference passages:\n"]
    for ex in FEW_SHOT_EXAMPLES:
        parts.append("INPUT:\n" + ex["input_passage"])
        parts.append("OUTPUT:\n" + json.dumps(ex["output_json"], ensure_ascii=False))
        parts.append("")
    parts.append(
        "Now extract for the next passage. Reply with ONLY the JSON list, "
        "nothing else. No prose preamble. No markdown fence."
    )
    return "\n".join(parts)


def _parse_model_output(raw: str) -> list[dict[str, Any]] | None:
    """Strip markdown fences if the model emitted any, then parse JSON."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        # Strip first line + last fence
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("model returned non-JSON: %s ; raw=%r", exc, raw[:200])
        return None
    if not isinstance(parsed, list):
        logger.warning("model returned non-list JSON: %r", parsed)
        return None
    return parsed


def _validate_gloss(
    gloss: dict[str, Any], passage_text: str
) -> tuple[bool, str | None]:
    """Reject glosses missing required fields or whose evidence_quote isn't a verbatim substring."""
    required = ("etruscan_word", "equivalent", "equivalent_language", "evidence_quote")
    for key in required:
        v = gloss.get(key)
        if not isinstance(v, str) or not v.strip():
            return False, f"missing/empty {key}"
    lang = gloss["equivalent_language"]
    if lang not in ("lat", "grc"):
        return False, f"invalid equivalent_language={lang!r}"
    quote = gloss["evidence_quote"].strip()
    # The passage text we send the model includes the "TEXT: " prefix and
    # AUTHOR/WORK headers; validate against the underlying text only.
    if quote not in passage_text:
        return False, "evidence_quote not a verbatim substring of passage"
    return True, None


def _load_resume_state(sidecar_path: Path) -> set[int]:
    """Re-read the per-passage status sidecar; return indices already processed."""
    if not sidecar_path.is_file():
        return set()
    seen: set[int] = set()
    with sidecar_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if row.get("status") == "processed":
                    seen.add(int(row["passage_index"]))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return seen


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="If set, process at most N new passages (after resume skip).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count work, estimate cost, no API calls.",
    )
    parser.add_argument(
        "--rate-sleep",
        type=float,
        default=0.25,
        help="Seconds to sleep between API calls (default 0.25 = ~4 rps).",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    _setup_logging(args.verbose)

    if not args.input.is_file():
        logger.error("input not found: %s", args.input)
        return 2

    sidecar_path = args.output.with_suffix(args.output.suffix + ".passages.jsonl")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    seen_indices = _load_resume_state(sidecar_path)
    if seen_indices:
        logger.info(
            "resume: %d passages already processed (per %s)",
            len(seen_indices),
            sidecar_path.name,
        )

    all_passages = list(_iter_passages(args.input))
    pending = [(i, r) for i, r in all_passages if i not in seen_indices]
    if args.limit is not None:
        pending = pending[: args.limit]

    logger.info(
        "input has %d passages; %d already done; %d to process this run",
        len(all_passages),
        len(seen_indices),
        len(pending),
    )

    # Cost estimate (rough): assume ~600 input tokens / passage (system +
    # few-shots + the passage), ~80 output tokens average.
    est_in = len(pending) * 600
    est_out = len(pending) * 80
    est_usd = (
        est_in * PRICE_PER_MTOK_INPUT / 1_000_000
        + est_out * PRICE_PER_MTOK_OUTPUT / 1_000_000
    )
    logger.info(
        "estimated tokens: in=%d out=%d ; estimated cost: $%.3f (USD, %s pricing)",
        est_in,
        est_out,
        est_usd,
        args.model,
    )

    if args.dry_run:
        logger.info("dry-run; not calling the model.")
        return 0

    if not pending:
        logger.info("nothing to do (all passages already processed)")
        return 0

    # Lazy import so dry-run + --help don't pay the cold-start.
    from google import genai
    from google.genai import types

    client = genai.Client(vertexai=True, project=args.project, location=args.region)
    system_payload = SYSTEM_INSTRUCTION + "\n\n" + _few_shot_block()

    n_glosses = 0
    n_validate_drops = 0
    n_parse_drops = 0
    total_in_tokens = 0
    total_out_tokens = 0
    t0 = time.time()

    for k, (idx, row) in enumerate(pending):
        prompt = _format_passage(row)
        try:
            # Gemini 2.5 Pro defaults to "thinking" mode that consumes the
            # output budget *before* it emits the actual JSON. For this task
            # the prompt is well-scoped enough that we don't need it, so cap
            # the thinking budget at 128 (the documented minimum for 2.5 Pro)
            # to avoid truncating the visible output. Bump max_output_tokens
            # to 2048 to leave generous headroom for longer extraction lists.
            cfg_kwargs: dict[str, Any] = {
                "system_instruction": system_payload,
                "max_output_tokens": 2048,
                "temperature": 0.0,
                "response_mime_type": "application/json",
            }
            if "2.5-pro" in args.model or "2.5-flash" in args.model:
                cfg_kwargs["thinking_config"] = types.ThinkingConfig(
                    thinking_budget=128 if "pro" in args.model else 0,
                )
            resp = client.models.generate_content(
                model=args.model,
                contents=[prompt],
                config=types.GenerateContentConfig(**cfg_kwargs),
            )
        except Exception as exc:
            logger.warning("API error on idx=%d: %s", idx, exc)
            _append_jsonl(
                sidecar_path,
                {"passage_index": idx, "status": "api_error", "error": str(exc)[:200]},
            )
            time.sleep(args.rate_sleep)
            continue

        usage = resp.usage_metadata
        total_in_tokens += (usage.prompt_token_count or 0) if usage else 0
        total_out_tokens += (usage.candidates_token_count or 0) if usage else 0

        parsed = _parse_model_output(resp.text or "")
        if parsed is None:
            n_parse_drops += 1
            _append_jsonl(
                sidecar_path,
                {"passage_index": idx, "status": "parse_error", "n_glosses": 0},
            )
            time.sleep(args.rate_sleep)
            continue

        kept = 0
        for gloss in parsed:
            ok, why = _validate_gloss(gloss, row.get("text", ""))
            if not ok:
                n_validate_drops += 1
                logger.debug("dropped on idx=%d: %s ; gloss=%r", idx, why, gloss)
                continue
            out_row = {
                **gloss,
                "source": f"{row.get('author', '?')} {row.get('work', '?')}".strip(),
                "passage_index": idx,
                "model": args.model,
                "extracted_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            }
            _append_jsonl(args.output, out_row)
            n_glosses += 1
            kept += 1

        _append_jsonl(
            sidecar_path,
            {"passage_index": idx, "status": "processed", "n_glosses": kept},
        )

        if (k + 1) % 50 == 0:
            logger.info(
                "%d/%d processed ; glosses=%d ; drops parse=%d validate=%d",
                k + 1,
                len(pending),
                n_glosses,
                n_parse_drops,
                n_validate_drops,
            )

        time.sleep(args.rate_sleep)

    elapsed = time.time() - t0
    actual_usd = (
        total_in_tokens * PRICE_PER_MTOK_INPUT / 1_000_000
        + total_out_tokens * PRICE_PER_MTOK_OUTPUT / 1_000_000
    )
    logger.info(
        "done: %d passages in %.1f s ; %d glosses kept ; drops parse=%d validate=%d",
        len(pending),
        elapsed,
        n_glosses,
        n_parse_drops,
        n_validate_drops,
    )
    logger.info(
        "actual tokens: in=%d out=%d ; actual cost: $%.3f (USD, billed to %s)",
        total_in_tokens,
        total_out_tokens,
        actual_usd,
        args.project,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
