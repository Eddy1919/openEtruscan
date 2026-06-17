#!/usr/bin/env python3
"""
Export the v2 adjudication queue to a Recogito-importable CSV.

Turns the LLM-jury split decisions (research/v2 .../adjudication_queue.csv, or a
jury JSONL) into a tabular CSV a philologist can upload to Recogito
(https://recogito.pelagios.org). On upload they point Recogito at the `text`
column, then tag each row with the correct class and/or annotate the places and
people in it. Their export comes back via import_recogito.py.

    python scripts/research/export_recogito.py \
        --queue research/v2/handoff/v2.0-etr/adjudication_queue.csv \
        --text-field canonical_transliterated \
        --output /tmp/recogito_upload.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from openetruscan.core.recogito import UploadRow, build_upload_table  # noqa: E402

# Columns from the jury that ride along as context for the annotator.
DEFAULT_CONTEXT = ["silver_label_v1", "gemini_label", "llama_label", "translation"]


def load_rows(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return list(csv.DictReader(path.open(encoding="utf-8")))


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--queue", type=Path, required=True, help="adjudication_queue.csv or jury .jsonl"
    )
    ap.add_argument("--text-field", default="canonical_transliterated", help="Column to annotate.")
    ap.add_argument("--id-field", default="id")
    ap.add_argument("--context", nargs="*", default=DEFAULT_CONTEXT, help="Extra context columns.")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    rows = load_rows(args.queue)
    context_cols = [c for c in args.context if any(c in r for r in rows)]

    upload_rows = []
    for r in rows:
        text = (r.get(args.text_field) or "").strip()
        if not text:
            continue
        upload_rows.append(
            UploadRow(
                id=str(r.get(args.id_field, "")),
                text=text,
                extra={c: str(r.get(c, "")) for c in context_cols},
            )
        )

    args.output.write_text(
        build_upload_table(upload_rows, extra_columns=context_cols), encoding="utf-8"
    )
    print(f"Wrote {len(upload_rows)} rows to {args.output}")
    print(f"Upload to Recogito; annotate the 'text' column. Context columns: {context_cols}")


if __name__ == "__main__":
    main()
