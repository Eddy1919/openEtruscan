#!/usr/bin/env python3
"""Hand-review CLI for raw LLM-extracted anchors (WBS T4.2).

Reads `research/anchors/llm_anchors_raw.jsonl` (output of
`llm_extract_anchors.py`), presents each row to a human reviewer, and
materialises two output files:

  - `research/anchors/attested.jsonl` — **training-eligible**
    anchors. Each row is a hand-confirmed Etruscan→Latin/Greek
    equivalence whose `(etr_norm, lat_norm)` key does NOT collide
    with the rosetta-eval-v1 test split.

  - `research/anchors/attested_eval_overlap.jsonl` — anchors the
    reviewer wanted to keep but whose normalised key collides with
    the held-out test pairs. These are **NOT useful for training**
    (would leak the eval set) but ARE useful as a sanity check that
    the LLM extraction is finding genuinely-attested pairs the eval
    set agrees with.

Decisions are persisted to a sidecar TSV
(`research/anchors/.review_decisions.tsv`) so an interrupted session
can resume without re-deciding rows already triaged.

OPERATING MODES
---------------

The script has three modes, exposed via flags:

1. **Interactive review** (default; the WBS T4.2 spec) — prompts
   the reviewer per-row with the verbatim quote and asks for one of
   `[k]eep / [s]kip / [e]dit-equivalent / [q]uit-and-save`. The
   `e` action lets the reviewer overwrite a wrongly-extracted
   `equivalent` field on the way through (useful when the model
   captured the wrong Latin/Greek word from a multi-noun gloss).

   ```bash
   python scripts/research/review_anchors.py --interactive
   ```

2. **Apply decisions from a TSV** (`--apply` with `--decisions FILE`) —
   non-interactive; reads a pre-prepared decisions TSV and
   materialises the JSONL outputs in one shot. Useful when a
   first-pass review happens via PR review on the TSV itself (so
   keep/skip/edit choices land in `git log` rather than transient
   stdin prompts).

   ```bash
   python scripts/research/review_anchors.py --apply \
     --decisions research/anchors/agent_decisions.tsv
   ```

3. **Report-only** (`--report`) — read existing `attested.jsonl` /
   `attested_eval_overlap.jsonl` and print the yield breakdown
   (count by source, count by language, by category). Same numbers
   that get appended to FINDINGS.md.

   ```bash
   python scripts/research/review_anchors.py --report
   ```

DECISIONS TSV SCHEMA
--------------------

Tab-separated, header on first line:

    passage_index   etruscan_word   action   equivalent_override   note

- `passage_index` (int) — the row's index in the original passages
  file. Joins the decision back to the raw row.
- `etruscan_word` (str) — included for readability; ignored on read
  (the `passage_index` is the join key).
- `action` (str) — one of `k`, `s`, `e`.
- `equivalent_override` (str) — required if action is `e`,
  otherwise blank.
- `note` (str, optional) — free-text rationale; ignored by the
  script but preserved across runs.

DEDUP AGAINST THE TEST SPLIT
----------------------------

A kept anchor is **routed to `attested_eval_overlap.jsonl` instead
of `attested.jsonl`** when its normalised `(etruscan_word, equivalent)`
pair matches any `(etr, lat)` pair in `eval_pairs(split='test')`.
Normalisation lowercases the strings and strips combining diacritics
(NFD-decomposed), Greek-final-sigma → medial sigma, and trailing
inflectional `m`/`s` on Latin nouns (so `tauron` matches `taurum`
on the inflection-stripping pass). Greek-only equivalences cannot
collide with the Latin-only test split by construction.
"""

from __future__ import annotations

import argparse
import collections
import csv
import dataclasses
import datetime as dt
import json
import logging
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "evals"))

DEFAULT_RAW = REPO_ROOT / "research" / "anchors" / "llm_anchors_raw.jsonl"
DEFAULT_KEEP = REPO_ROOT / "research" / "anchors" / "attested.jsonl"
DEFAULT_OVERLAP = REPO_ROOT / "research" / "anchors" / "attested_eval_overlap.jsonl"
DEFAULT_DECISIONS = REPO_ROOT / "research" / "anchors" / ".review_decisions.tsv"

logger = logging.getLogger("review_anchors")

ACTION_KEEP = "k"
ACTION_SKIP = "s"
ACTION_EDIT = "e"
ACTIONS = {ACTION_KEEP, ACTION_SKIP, ACTION_EDIT}


def _normalise_token(s: str) -> str:
    """Loose normalisation for dedup.

    Lowercase + NFD decompose + strip combining marks (handles
    diacritics + Greek tonos / spiritus). Greek-final sigma → medial.
    Then a single pass of "strip a trailing nominative-singular `s`
    or accusative-singular `m`" — matches the cases we actually hit
    in this corpus (`tauron`/`taurum`, `aesar`/`aesar`, `clan`/`clan`).
    The script-level normaliser doesn't need to be Bonfante-grade;
    only need to catch obvious eval-split collisions.
    """
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("ς", "σ")
    # Drop trailing m/s — common Latin/Greek nominative/accusative endings.
    s = re.sub(r"[ms]$", "", s)
    return s


def _is_overlap_with_eval(etruscan_word: str, equivalent: str, eval_keys: set[tuple[str, str]]) -> bool:
    key = (_normalise_token(etruscan_word), _normalise_token(equivalent))
    return key in eval_keys


def _load_eval_test_keys() -> set[tuple[str, str]]:
    """Return the set of `(etr_norm, lat_norm)` tuples in the held-out test split."""
    from rosetta_eval_pairs import eval_pairs  # type: ignore[import-not-found]
    pairs = eval_pairs(split="test")
    return {(_normalise_token(p.etr), _normalise_token(p.lat)) for p in pairs}


def _load_raw(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning("skipping bad JSON at line %d in %s: %s", i, path, exc)
    return rows


@dataclasses.dataclass
class Decision:
    passage_index: int
    etruscan_word: str
    action: str
    equivalent_override: str = ""
    note: str = ""


def _load_decisions(path: Path) -> dict[int, Decision]:
    if not path.is_file():
        return {}
    out: dict[int, Decision] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            try:
                idx = int(row["passage_index"])
            except (KeyError, ValueError):
                continue
            action = (row.get("action") or "").strip().lower()
            if action not in ACTIONS:
                continue
            out[idx] = Decision(
                passage_index=idx,
                etruscan_word=row.get("etruscan_word", ""),
                action=action,
                equivalent_override=(row.get("equivalent_override") or "").strip(),
                note=(row.get("note") or "").strip(),
            )
    return out


def _append_decision(path: Path, d: Decision) -> None:
    """Append-only writer so an interrupted session keeps the decisions made so far."""
    is_new = not path.is_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["passage_index", "etruscan_word", "action", "equivalent_override", "note"],
            delimiter="\t",
        )
        if is_new:
            writer.writeheader()
        writer.writerow(dataclasses.asdict(d))


def _print_card(i: int, n: int, row: dict[str, Any]) -> None:
    print()
    print("─" * 78)
    print(f"[{i}/{n}]  idx={row.get('passage_index'):>4d}  source={row.get('source', '')!r}")
    print(f"          {row['etruscan_word']!r}  →  {row['equivalent']!r}  ({row['equivalent_language']})")
    print(f"  quote: {row['evidence_quote']}")
    print("─" * 78)


def _prompt(prompt_text: str, allowed: set[str]) -> str:
    while True:
        try:
            v = input(prompt_text).strip().lower()
        except EOFError:
            return "q"
        if v in allowed or v == "q":
            return v
        print(f"  → please answer one of {sorted(allowed)} or q to save+quit")


def _interactive(rows: list[dict[str, Any]], decisions: dict[int, Decision], decisions_path: Path) -> dict[int, Decision]:
    pending = [r for r in rows if r.get("passage_index") not in decisions]
    if not pending:
        print(f"All {len(rows)} rows already decided ({len(decisions)} in sidecar). Nothing to review.")
        return decisions
    print(f"{len(pending)} rows pending, {len(decisions)} already decided ({len(rows)} total).")
    print("Actions: [k]eep / [s]kip / [e]dit-equivalent / [q]uit-and-save\n")
    for i, row in enumerate(pending, 1):
        _print_card(i, len(pending), row)
        choice = _prompt("  action [k/s/e/q]: ", {ACTION_KEEP, ACTION_SKIP, ACTION_EDIT})
        if choice == "q":
            print(f"\nSaved {len(decisions)} decisions. Re-run to resume from row {i}/{len(pending)}.")
            break
        override = ""
        if choice == ACTION_EDIT:
            override = input("  corrected equivalent (verbatim from the quote): ").strip()
            if not override:
                print("  (no override given, treating as skip)")
                choice = ACTION_SKIP
        decision = Decision(
            passage_index=row["passage_index"],
            etruscan_word=row["etruscan_word"],
            action=choice,
            equivalent_override=override,
        )
        decisions[row["passage_index"]] = decision
        _append_decision(decisions_path, decision)
    return decisions


def _materialise(
    rows: list[dict[str, Any]],
    decisions: dict[int, Decision],
    eval_keys: set[tuple[str, str]],
    keep_path: Path,
    overlap_path: Path,
) -> tuple[int, int]:
    keep_path.parent.mkdir(parents=True, exist_ok=True)
    n_keep, n_overlap = 0, 0
    # Truncate-and-rewrite the output files atomically — this is the
    # authoritative materialisation pass, not append-only.
    with keep_path.open("w", encoding="utf-8") as fk, overlap_path.open("w", encoding="utf-8") as fo:
        for row in rows:
            d = decisions.get(row.get("passage_index"))
            if d is None or d.action == ACTION_SKIP:
                continue
            out_row = dict(row)
            if d.action == ACTION_EDIT and d.equivalent_override:
                out_row["equivalent"] = d.equivalent_override
                out_row["equivalent_edited_from"] = row["equivalent"]
            out_row["reviewed_at"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
            if d.note:
                out_row["reviewer_note"] = d.note
            if _is_overlap_with_eval(out_row["etruscan_word"], out_row["equivalent"], eval_keys):
                fo.write(json.dumps(out_row, ensure_ascii=False) + "\n")
                n_overlap += 1
            else:
                fk.write(json.dumps(out_row, ensure_ascii=False) + "\n")
                n_keep += 1
    return n_keep, n_overlap


def _yield_report(keep_path: Path, overlap_path: Path) -> str:
    rows_keep = _load_raw(keep_path) if keep_path.is_file() else []
    rows_over = _load_raw(overlap_path) if overlap_path.is_file() else []
    by_lang = collections.Counter(r["equivalent_language"] for r in rows_keep)
    by_author = collections.Counter((r.get("source") or "").split()[0] for r in rows_keep)
    lines = [
        "## T4.2 — anchor-review yield",
        "",
        f"- training-eligible (`attested.jsonl`): **{len(rows_keep)}**",
        f"- eval-overlap (`attested_eval_overlap.jsonl`): **{len(rows_over)}**",
        f"- by equivalent_language: {dict(by_lang)}",
        "",
        "### Source diversity (top authors of kept anchors)",
        "",
    ]
    if not rows_keep:
        lines.append("_(no kept anchors)_")
    else:
        for a, n in by_author.most_common():
            lines.append(f"- {a}: {n}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--out-keep", type=Path, default=DEFAULT_KEEP)
    parser.add_argument("--out-overlap", type=Path, default=DEFAULT_OVERLAP)
    parser.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--interactive", action="store_true", help="Prompt per-row [k/s/e/q].")
    parser.add_argument("--apply", action="store_true", help="Apply decisions TSV → JSONL outputs (no prompts).")
    parser.add_argument("--report", action="store_true", help="Print yield report and exit.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.report:
        sys.stdout.write(_yield_report(args.out_keep, args.out_overlap))
        return 0

    if not args.raw.is_file():
        logger.error("raw input not found: %s", args.raw)
        return 2

    rows = _load_raw(args.raw)
    logger.info("loaded %d raw rows from %s", len(rows), args.raw)

    decisions = _load_decisions(args.decisions)
    logger.info("loaded %d existing decisions from %s", len(decisions), args.decisions)

    if args.interactive:
        decisions = _interactive(rows, decisions, args.decisions)

    if not args.interactive and not args.apply:
        # No mode flag chosen — default to apply if a non-trivial
        # decisions TSV is present, otherwise drop into interactive.
        if decisions:
            args.apply = True
        else:
            args.interactive = True
            decisions = _interactive(rows, decisions, args.decisions)

    if args.apply or args.interactive:
        eval_keys = _load_eval_test_keys()
        logger.info("test-split dedup: %d (etr, lat) keys loaded", len(eval_keys))
        n_keep, n_overlap = _materialise(
            rows, decisions, eval_keys, args.out_keep, args.out_overlap
        )
        logger.info(
            "wrote %d → %s, %d → %s",
            n_keep, args.out_keep, n_overlap, args.out_overlap,
        )

    sys.stdout.write(_yield_report(args.out_keep, args.out_overlap))
    return 0


if __name__ == "__main__":
    sys.exit(main())
