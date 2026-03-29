#!/usr/bin/env python3
"""
Migrate OpenEtruscan corpus from SQLite to PostgreSQL (Cloud SQL).

Usage:
    python scripts/migrate_to_postgres.py \\
        --source data/corpus.db \\
        --target "postgresql://postgres:PASSWORD@IP/corpus"

    # Skip LLM validation (regex-only cleaning):
    python scripts/migrate_to_postgres.py \\
        --source data/corpus.db \\
        --target "postgresql://postgres:PASSWORD@IP/corpus" \\
        --no-llm-filter

Features:
    - Two-pass hallucination filtering:
        Pass 1: Deterministic regex rules (character set, length, stop-words)
        Pass 2: Concurrent LLM validation via Gemini 2.5 Flash (batches of 50)
    - Auto-classification by keyword heuristics
    - Creates read-only 'corpus_reader' user for public access
    - Shows classification distribution after migration
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from dotenv import load_dotenv

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from openetruscan.corpus import (  # noqa: E402
    _COLUMNS,
    PostgresCorpus,
)

# ---------------------------------------------------------------------------
# Classification heuristics for Etruscan inscriptions
# ---------------------------------------------------------------------------

# Common Etruscan funerary terms (name suffixes, family markers)
FUNERARY_PATTERNS = re.compile(
    r"(clan|sec|puia|ati|zilath|avil|sval|lupu|suth|hinth|"
    r"clen|neft|lautni|etera)",
    re.IGNORECASE,
)

# Votive / dedicatory terms
VOTIVE_PATTERNS = re.compile(
    r"(turce|mlac|alpan|tinia|uni|menrva|turan|"
    r"fufluns|nethuns|sethlans|thesan)",
    re.IGNORECASE,
)

# Boundary markers
BOUNDARY_PATTERNS = re.compile(
    r"(tular|tularu|rasna|spura|mechi)",
    re.IGNORECASE,
)

# Ownership marks
OWNERSHIP_PATTERNS = re.compile(
    r"(mi\s|mini\s|mina\s)",
    re.IGNORECASE,
)

# Commercial / numerical
COMMERCIAL_PATTERNS = re.compile(
    r"(zathrum|ci|huth|mach|semph|thu|cezp)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Pass 1: Deterministic Hallucination Validation Rules
# ---------------------------------------------------------------------------

CIE_PATTERN = re.compile(r"^CIE\s+\d+[a-zA-Z]?$")
# Etruscan has no B, D, G, J, O, W, X, Y
INVALID_CHARS_PATTERN = re.compile(r"[bdgjowxy]", re.IGNORECASE)
LATIN_STOP_WORDS = re.compile(
    r"\b(inscriptio|sepulcrum|titulus|lectus|pagina|tabula|tab|figuram|etruscorum)\b",
    re.IGNORECASE,
)


def validate_extracted_record(cie_id: str, canonical: str) -> list[str]:
    """Pass 1: Deterministic validation to catch obvious hallucinations."""
    flags = []

    if not CIE_PATTERN.match(cie_id.strip()):
        flags.append("invalid_id_format")

    if not canonical or len(canonical.strip()) == 0:
        flags.append("empty_text")
        return flags

    canonical_clean = canonical.lower()
    if INVALID_CHARS_PATTERN.search(canonical_clean):
        flags.append("hallucinated_latin_characters")

    if len(canonical_clean) > 250 or len(canonical_clean.split()) > 30:
        flags.append("exceeds_length_limit")

    if LATIN_STOP_WORDS.search(canonical_clean):
        flags.append("contains_latin_stop_words")

    return flags


# ---------------------------------------------------------------------------
# Pass 2: LLM-Based Validation via Gemini 2.5 Flash
# ---------------------------------------------------------------------------

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

VALIDATION_PROMPT = """\
You are a senior Etruscologist and digital epigrapher reviewing records extracted \
by an automated OCR/VLM pipeline from the Corpus Inscriptionum Etruscarum (CIE), \
the definitive 1893 printed catalogue of Etruscan inscriptions.

## Background on the CIE layout
Each CIE page contains numbered entries. Each entry has:
  1. A bold CIE number (e.g., "1742", "2301a").
  2. A Latin findspot line (e.g., "Clusii in agro", "Perusiae in hypogaeo").
  3. A Latin descriptive commentary discussing the object, medium, and provenance.
  4. The actual Etruscan inscription text, typically transliterated into Latin script.

The VLM sometimes confuses the Latin commentary or findspot with the Etruscan \
inscription text. Your task is to determine whether the `text` field below is \
genuinely an Etruscan inscription or a hallucinated extraction of commentary.

## Key Etruscan linguistic facts
- The Etruscan alphabet **lacks the letters B, D, G, O** (and J, W, X, Y in \
  transliteration). Their presence strongly indicates Latin, not Etruscan.
- Etruscan inscriptions are overwhelmingly short: personal names + patronymics + \
  a few formulaic words (e.g., "clan", "sec", "avil", "lupu", "suth", "zilath").
- Common Etruscan phonemes in transliteration: /a/, /e/, /i/, /u/, /c/, /θ/ (th), \
  /φ/ (ph), /χ/ (ch), /s/, /ś/, /z/, /f/, /h/, /l/, /m/, /n/, /p/, /r/, /t/, /v/.
- Typical patterns: "vel : laris : arnth : larth : ramtha : thana : fasti" (praenomina), \
  "velus" / "larisal" (genitive), "-al" / "-sa" / "-isa" (genitive suffixes), \
  "-ni" / "-na" (belonging-to suffixes).
- An Etruscan text should NOT contain full Latin words like "est", "hic", "ille", \
  "cum", "quod", "in", "et", "sub", "ad", "ex".
- An Etruscan text should NOT read like a Latin sentence with verbs, prepositions, \
  and case endings (-us, -um, -ae, -is, -orum).

## Your task
Examine the following record and determine if the `text` field contains a plausible \
Etruscan transliteration.

CIE ID: {cie_id}
Findspot: {findspot}
Text: {text}

Respond with a JSON object:
{{
  "valid_etruscan": true or false,
  "confidence": 0.0 to 1.0,
  "reason": "Brief explanation of your judgement"
}}

Rules for your judgement:
- If the text looks like an Etruscan name formula or short inscription → valid_etruscan: true
- If the text is clearly Latin commentary, a findspot description, or bibliography → valid_etruscan: false
- If you are uncertain but the text plausibly *could* be Etruscan → valid_etruscan: true (err on the side of inclusion)
- If the text is empty, nonsensical, or a page number → valid_etruscan: false
"""

VALIDATION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "valid_etruscan": {
            "type": "BOOLEAN",
            "description": "True if the text is a plausible Etruscan inscription",
        },
        "confidence": {
            "type": "NUMBER",
            "description": "Confidence score from 0.0 to 1.0",
        },
        "reason": {
            "type": "STRING",
            "description": "Brief explanation of the judgement",
        },
    },
    "required": ["valid_etruscan", "confidence", "reason"],
}


def llm_validate_single(
    cie_id: str,
    text: str,
    findspot: str,
    api_key: str,
) -> dict:
    """Call Gemini to validate a single inscription. Returns judgement dict."""
    prompt = VALIDATION_PROMPT.format(
        cie_id=cie_id,
        findspot=findspot,
        text=text,
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "response_mime_type": "application/json",
            "response_schema": VALIDATION_SCHEMA,
        },
    }

    for attempt in range(3):
        try:
            resp = requests.post(
                GEMINI_URL,
                params={"key": api_key},
                json=payload,
                timeout=(10, 60),
            )
            if resp.status_code == 200:
                data = resp.json()
                text_out = data["candidates"][0]["content"]["parts"][0]["text"]
                result = json.loads(text_out)
                result["cie_id"] = cie_id
                return result
            elif resp.status_code == 429:
                time.sleep(2 ** (attempt + 1))
            else:
                return {
                    "cie_id": cie_id,
                    "valid_etruscan": True,  # fail-open on API error
                    "confidence": 0.0,
                    "reason": f"API error {resp.status_code}: fail-open",
                }
        except Exception as e:
            if attempt == 2:
                return {
                    "cie_id": cie_id,
                    "valid_etruscan": True,  # fail-open on network error
                    "confidence": 0.0,
                    "reason": f"Network error: {e}: fail-open",
                }
            time.sleep(2 ** (attempt + 1))

    return {
        "cie_id": cie_id,
        "valid_etruscan": True,
        "confidence": 0.0,
        "reason": "Max retries exceeded: fail-open",
    }


def llm_validate_batch(
    records: list[dict],
    api_key: str,
    batch_size: int = 50,
) -> dict[str, dict]:
    """
    Validate records concurrently in batches of `batch_size`.
    Returns a dict mapping cie_id -> validation result.
    """
    results: dict[str, dict] = {}
    total = len(records)

    for batch_start in range(0, total, batch_size):
        batch = records[batch_start : batch_start + batch_size]
        batch_end = min(batch_start + batch_size, total)
        print(f"  🤖 LLM validating batch {batch_start + 1}–{batch_end} / {total}...")

        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = {
                executor.submit(
                    llm_validate_single,
                    rec["cie_id"],
                    rec["text"],
                    rec["findspot"],
                    api_key,
                ): rec["cie_id"]
                for rec in batch
            }

            for future in as_completed(futures):
                cie_id = futures[future]
                try:
                    result = future.result()
                    results[result["cie_id"]] = result
                except Exception as e:
                    results[cie_id] = {
                        "cie_id": cie_id,
                        "valid_etruscan": True,
                        "confidence": 0.0,
                        "reason": f"Future exception: {e}: fail-open",
                    }

        # Small courtesy pause between batches
        if batch_end < total:
            time.sleep(1)

    return results


# ---------------------------------------------------------------------------
# Classification heuristics
# ---------------------------------------------------------------------------


def classify_inscription(text: str) -> str:
    """
    Auto-classify an Etruscan inscription by keyword heuristics.

    Priority order: boundary > votive > ownership > commercial > funerary.
    Most unclassified texts default to funerary (majority of corpus).
    """
    if not text:
        return "unknown"

    canonical = text.lower().strip()

    if BOUNDARY_PATTERNS.search(canonical):
        return "boundary"
    if VOTIVE_PATTERNS.search(canonical):
        return "votive"
    if OWNERSHIP_PATTERNS.search(canonical):
        return "ownership"
    if COMMERCIAL_PATTERNS.search(canonical):
        return "commercial"
    if FUNERARY_PATTERNS.search(canonical):
        return "funerary"

    # Default: most Etruscan inscriptions are funerary
    # Only mark as unknown if very short or illegible
    if len(canonical) < 3:
        return "unknown"
    return "funerary"


def detect_completeness(text: str) -> str:
    """Detect if an inscription is fragmentary."""
    if not text:
        return "illegible"
    if "[" in text or "]" in text or "..." in text or "---" in text:
        return "fragmentary"
    return "complete"


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def migrate(
    source_path: str,
    target_url: str,
    use_llm_filter: bool = True,
) -> None:
    """Migrate SQLite corpus to PostgreSQL with dual-layer cleaning."""
    # Connect to source SQLite
    src = sqlite3.connect(source_path)
    src.row_factory = sqlite3.Row

    # Check source has data
    count = src.execute("SELECT COUNT(*) FROM inscriptions").fetchone()[0]
    if count == 0:
        print("Source database is empty. Nothing to migrate.")
        return

    print(f"Source: {source_path} ({count} inscriptions)")
    print(f"Target: {target_url.split('@')[1] if '@' in target_url else target_url}")

    # Connect to PostgreSQL
    pg = PostgresCorpus.from_url(target_url)
    print("Connected to PostgreSQL. Schema created.")

    # Read all source columns
    src_cursor = src.execute("PRAGMA table_info(inscriptions)")
    src_columns = [row[1] for row in src_cursor.fetchall()]

    # Migrate inscriptions
    rows = src.execute("SELECT * FROM inscriptions").fetchall()

    # ── Pass 1: Deterministic regex filtering ──
    print("\n── Pass 1: Deterministic regex filtering ──")
    candidates = []
    rejected_regex = 0

    for row in rows:
        canonical = row["canonical"]
        raw_text = row["raw_text"]
        cie_id = row["id"]

        validation_flags = validate_extracted_record(cie_id, canonical or raw_text)
        if validation_flags:
            rejected_regex += 1
            print(f"  ✗ [REGEX] {cie_id}: {validation_flags}")
            continue

        candidates.append(row)

    print(f"  Pass 1 result: {len(candidates)} passed, {rejected_regex} rejected")

    # ── Pass 2: LLM validation (optional) ──
    rejected_llm = 0
    llm_verdicts: dict[str, dict] = {}

    if use_llm_filter:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print(
                "\n⚠️  GEMINI_API_KEY not set. Skipping LLM validation. "
                "Set it in .env or export it."
            )
        else:
            print(f"\n── Pass 2: LLM validation ({len(candidates)} records, batches of 50) ──")

            # Prepare records for LLM
            llm_records = [
                {
                    "cie_id": row["id"],
                    "text": row["canonical"] or row["raw_text"],
                    "findspot": row["findspot"] or "",
                }
                for row in candidates
            ]

            llm_verdicts = llm_validate_batch(llm_records, api_key, batch_size=50)

            # Filter out LLM-rejected records
            filtered_candidates = []
            for row in candidates:
                cie_id = row["id"]
                verdict = llm_verdicts.get(cie_id)
                if verdict and not verdict.get("valid_etruscan", True):
                    rejected_llm += 1
                    conf = verdict.get("confidence", 0)
                    reason = verdict.get("reason", "no reason")
                    print(f"  ✗ [LLM] {cie_id} (conf={conf:.2f}): {reason}")
                else:
                    filtered_candidates.append(row)

            candidates = filtered_candidates
            print(
                f"  Pass 2 result: {len(candidates)} passed, {rejected_llm} rejected"
            )

    # ── Insert validated records into PostgreSQL ──
    print(f"\n── Inserting {len(candidates)} validated records into PostgreSQL ──")
    migrated = 0
    classifications: dict[str, int] = {}

    for row in candidates:
        canonical = row["canonical"]
        raw_text = row["raw_text"]

        # Auto-classify
        classification = classify_inscription(canonical or raw_text)
        completeness = detect_completeness(canonical or raw_text)

        # Build values tuple matching _COLUMNS order
        values = (
            row["id"],
            row["raw_text"],
            row["canonical"],
            row["phonetic"],
            row["old_italic"],
            row["findspot"],
            row["findspot_lat"],
            row["findspot_lon"],
            row["date_approx"],
            row["date_uncertainty"],
            row["medium"],
            row["object_type"],
            row["source"],
            row["bibliography"],
            row["notes"],
            (row["language"] if "language" in src_columns else "etruscan"),
            classification,
            (row["script_system"] if "script_system" in src_columns else "old_italic"),
            completeness,
            (row["provenance_status"] if "provenance_status" in src_columns else "extracted"),
            (row["provenance_flags"] if "provenance_flags" in src_columns else ""),
        )

        # Insert into PostgreSQL
        cols = ", ".join(_COLUMNS)
        placeholders = ", ".join(["%s"] * len(_COLUMNS))
        conflict_updates = ", ".join(
            f"{c} = EXCLUDED.{c}" for c in _COLUMNS if c != "id"
        )
        sql = (
            f"INSERT INTO inscriptions ({cols}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT (id) DO UPDATE SET {conflict_updates}"
        )

        with pg._conn.cursor() as cur:
            cur.execute(sql, values)

        classifications[classification] = classifications.get(classification, 0) + 1
        migrated += 1

        if migrated % 500 == 0:
            pg._conn.commit()
            print(f"  Migrated {migrated}/{len(candidates)}...")

    pg._conn.commit()

    # ── Summary ──
    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)
    print(f"  Source records:         {count}")
    print(f"  Rejected (regex):       {rejected_regex}")
    print(f"  Rejected (LLM):         {rejected_llm}")
    print(f"  Migrated to PostgreSQL: {migrated}")
    print()

    # Show classification distribution
    print("Classification distribution:")
    for cls_name, cls_count in sorted(
        classifications.items(),
        key=lambda x: -x[1],
    ):
        pct = cls_count / migrated * 100 if migrated > 0 else 0
        bar = "█" * int(pct / 2)
        print(f"  {cls_name:15s} {cls_count:5d} ({pct:5.1f}%) {bar}")

    # Create read-only user
    print("\nCreating read-only user 'corpus_reader'...")
    reader_pass = os.environ.get(
        "POSTGRES_READER_PASSWORD", "openetruscan_readonly_user_pass"
    )
    pg.create_readonly_user(reader_pass)
    print("Done. Public read-only access configured.")

    # Final count check
    pg_count = pg.count()
    print(f"\nPostgreSQL total count: {pg_count}")

    src.close()
    pg.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate OpenEtruscan corpus to PostgreSQL with hallucination filtering",
    )
    parser.add_argument(
        "--source",
        default="src/openetruscan/data/corpus.db",
        help="Path to source SQLite database",
    )
    parser.add_argument(
        "--target",
        required=True,
        help="PostgreSQL connection URL",
    )
    parser.add_argument(
        "--no-llm-filter",
        action="store_true",
        default=False,
        help="Skip LLM validation (use regex-only cleaning)",
    )
    args = parser.parse_args()

    if not Path(args.source).exists():
        print(f"Error: Source database not found: {args.source}")
        sys.exit(1)

    migrate(args.source, args.target, use_llm_filter=not args.no_llm_filter)


if __name__ == "__main__":
    main()
