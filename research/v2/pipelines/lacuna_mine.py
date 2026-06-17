"""Mine editor-restored lacunae from the cleaned corpus.

Walks the cleaned corpus CSV and extracts every `[restoration]` span found
in `raw_text` or `canonical_transliterated`. Each restoration becomes a
candidate test row whose structure is:

    {
      "id": "...",
      "context_before": "...",
      "lacuna_gold": "...",
      "context_after": "...",
      "width": 5,
      "width_bucket": "w4_6",
      "raw_text": "...",
      "canonical_transliterated": "...",
      "inscription_type": "...",   // from silver labels if available
      "lacuna_source_field": "raw_text" or "canonical_transliterated"
    }

Filtering rules:
- Brackets containing only `.` characters (`[.]`, `[..]`, `[...]`) are gaps of
  known width with NO editor restoration — these are EXCLUDED from gold.
- Brackets containing `---` are unknown-width gaps — EXCLUDED.
- Brackets containing `?` mark conjectural restorations — EXCLUDED (philologist
  rates as uncertain).
- Only rows with `data_quality == "clean"` are kept.
- Rows where the lacuna lies at the very start or end (no context on one side)
  are EXCLUDED — we need context on both sides to score hallucination.
- Multi-lacuna rows are EXCLUDED — defer to v3.

This script does NOT call LLMs. It produces the raw candidate pool that
`pipelines/lacuna_jury.py` then processes.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from collections.abc import Iterator

# Matches [content] where content is one or more chars that are not just dots
# or dashes. Lazy match prevents grabbing across multiple brackets.
RESTORATION_RE = re.compile(r"\[([^\[\]]+?)\]")

DOTS_ONLY = re.compile(r"^[.\s]+$")
DASHES_ONLY = re.compile(r"^[-\s−–—]+$")


def _is_excluded_content(content: str) -> bool:
    c = content.strip()
    if not c:
        return True
    if DOTS_ONLY.match(c):
        return True
    if DASHES_ONLY.match(c):
        return True
    if "?" in c:
        return True
    return False


def _width_bucket(width: int) -> str:
    if width == 1:
        return "w1"
    if 2 <= width <= 3:
        return "w2_3"
    if 4 <= width <= 6:
        return "w4_6"
    return "w7_plus"


def _load_silver_types(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            out[row["id"].strip()] = row["label"].strip()
    return out


def _normalize_lacuna_row(row: dict) -> dict:
    """Coalesce corpus-JSONL schema variants into v1 CSV shape (see
    classify_split._normalize_corpus_row for the full table).
    """
    if "raw_text" not in row and "text" in row:
        row["raw_text"] = row["text"]
    if "canonical_transliterated" not in row:
        if "canonical_clean" in row:
            row["canonical_transliterated"] = row["canonical_clean"]
        elif "text" in row:
            row["canonical_transliterated"] = row["text"]
    # prod-v2 lean schema has no data_quality column. Treat as clean — the
    # bucket's prod-v2 export is already a curated dataset.
    if "data_quality" not in row:
        row["data_quality"] = "clean"
    return row


def _walk_corpus(path: Path) -> Iterator[dict]:
    """Yield corpus rows from CSV or JSONL (.jsonl / .ndjson)."""
    if not path.exists():
        return
    suffix = path.suffix.lower()
    if suffix in (".jsonl", ".ndjson"):
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield _normalize_lacuna_row(json.loads(line))
    else:
        with path.open() as f:
            reader = csv.DictReader(f)
            yield from reader


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--corpus",
        type=Path,
        action="append",
        required=True,
        help="Corpus file path. Pass multiple times to scan across "
        "id namespaces (publication-id JSONL + integer-DB-id "
        "JSONL). Each file is mined independently.",
    )
    ap.add_argument(
        "--silver-labels",
        type=Path,
        default=Path("research/data/openetruscan_labels.csv"),
        help="v1 silver labels for inscription_type annotation.",
    )
    ap.add_argument("--out", type=Path, required=True, help="Output JSONL of mined candidate rows.")
    ap.add_argument(
        "--prefer-field",
        choices=("raw_text", "canonical_transliterated"),
        default="canonical_transliterated",
        help="Which corpus column to scan for restorations.",
    )
    args = ap.parse_args(argv)

    silver_types = _load_silver_types(args.silver_labels)
    missing = [p for p in args.corpus if not p.exists()]
    if missing:
        print(f"WARN: missing corpus path(s): {missing}", file=sys.stderr)
        if all(not p.exists() for p in args.corpus):
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text("")
            return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    sink = args.out.open("w")
    n_kept = n_skipped_quality = n_skipped_multi = n_skipped_edge = 0
    n_skipped_content = 0

    def _walk_all() -> Iterator[dict]:
        for p in args.corpus:
            yield from _walk_corpus(p)

    try:
        for row in _walk_all():
            if row.get("data_quality", "").strip() != "clean":
                n_skipped_quality += 1
                continue
            text = row.get(args.prefer_field, "") or row.get("raw_text", "")
            if not text:
                continue
            matches = list(RESTORATION_RE.finditer(text))
            if not matches:
                continue
            # Single-lacuna only
            usable = [m for m in matches if not _is_excluded_content(m.group(1))]
            if len(usable) == 0:
                n_skipped_content += 1
                continue
            if len(usable) > 1:
                n_skipped_multi += 1
                continue
            m = usable[0]
            gold = m.group(1).strip()
            context_before = text[: m.start()].rstrip()
            context_after = text[m.end() :].lstrip()
            if not context_before or not context_after:
                n_skipped_edge += 1
                continue
            width = len(gold.replace(" ", "").replace("·", "").replace("•", ""))
            insc_id = row.get("id", "").strip()
            record = {
                "id": insc_id,
                "context_before": context_before,
                "lacuna_gold": gold,
                "context_after": context_after,
                "width": width,
                "width_bucket": _width_bucket(width),
                "raw_text": row.get("raw_text", ""),
                "canonical_transliterated": row.get("canonical_transliterated", ""),
                "translation": row.get("translation", ""),
                "inscription_type": silver_types.get(insc_id, ""),
                "lacuna_source_field": args.prefer_field,
                "codebook_version": "v2.0",
            }
            sink.write(json.dumps(record, ensure_ascii=False) + "\n")
            n_kept += 1
    finally:
        sink.close()

    print(f"Kept:                 {n_kept}", file=sys.stderr)
    print(f"Skipped non-clean:    {n_skipped_quality}", file=sys.stderr)
    print(f"Skipped multi-lacuna: {n_skipped_multi}", file=sys.stderr)
    print(f"Skipped edge lacuna:  {n_skipped_edge}", file=sys.stderr)
    print(f"Skipped empty-content: {n_skipped_content}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
