#!/usr/bin/env python3
"""Human verification worksheet for the gold-gloss queue.

    python verification_queue.py build    # write verification_queue.csv
    python verification_queue.py apply    # copy filled verdicts into gold_glosses.jsonl
    python verification_queue.py report   # audit-sample error rate with an exact CI

Order of work (tiers, in this order):

  1 audit        50 records drawn at random from every usable record. Their
                 rejection rate estimates how often an llm_checked record is
                 wrong, which decides how far the unverified tier can be
                 trusted. Stopping anywhere inside the tier still leaves a
                 uniform random sample.
  2 silver_eval  the rest of the WP10 silver eval (the only gold-gloss items
                 no gold-gloss model trained on). Verifying all of them turns
                 the silver eval into a verified one. Note the power analysis
                 (hybrid_embed/power_gloss.py): 71 items cannot certify the
                 current effect; this tier removes the "silver" caveat, it does
                 not settle the claim.
  3 witness      remaining ancient_gloss and bilingual records: the witness
                 evidence the research roadmap prefers for training.
  4 remaining    other usable records, low confidence first (most likely to be
                 rejected, so the most training noise removed per hour).
  5 seeded       never web-checked; need a full check from scratch.
  - excluded     rosetta TEST overlaps. Verify only for the record's own sake;
                 they never enter a new eval or training set (README rule 3).

Tiers are computed from the population of web-checked records (those with a
check_url), never from adjudication status, and order inside each tier is a
fixed hash of the form. Rebuilding after verdicts land keeps every row in its
tier and in the same order.

Nothing here sets a record to verified on its own: `apply` copies decisions a
human wrote into the worksheet, and refuses rows without a name and a date.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

from scipy.stats import beta

HERE = Path(__file__).parent
REPO = HERE.parent.parent.parent
sys.path.insert(0, str(REPO / "eval/harness"))
sys.path.insert(0, str(HERE))
from gloss_splits import (  # noqa: E402
    GG_SILVER,
    GG_TRAIN,
    ROSETTA_TRAIN_OVERLAP,
    assign_splits,
    clean_surface,
    gloss_head,
)
from rosetta_eval_pairs import eval_pairs  # noqa: E402

GLOSSES = HERE / "gold_glosses.jsonl"
WORKSHEET = HERE / "verification_queue.csv"
AUDIT_N = 50
SALT = "gold-gloss-verification-v1"
VERDICTS = {"verified", "rejected"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CORRECTION_NOTE = "gloss corrected at verification"

INFO_COLS = [
    "queue_rank",
    "tier",
    "split",
    "current_status",
    "etr",
    "gloss_en",
    "lat",
    "source_type",
    "confidence",
    "citation_primary",
    "citation_modern",
    "check_url",
    "notes",
]
HUMAN_COLS = ["verdict", "corrected_gloss", "verified_by", "verified_date", "verifier_notes"]
CONF_ORDER = {"low": 0, "medium": 1, "high": 2}


def load_records(path: Path = GLOSSES) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def write_records(records: list[dict], path: Path = GLOSSES) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))


def hash_key(etr: str) -> str:
    return hashlib.sha1(f"{SALT}:{etr}".encode()).hexdigest()


def rosetta_sets() -> tuple[set[str], set[str]]:
    test = {p.etr for p in eval_pairs(min_confidence="low", split="test")}
    train = {p.etr for p in eval_pairs(min_confidence="low", split="train")}
    return test, train


def population_splits(records: list[dict], test: set[str], train: set[str]) -> dict[str, str]:
    """Splits as if every web-checked record were usable.

    A verdict changes a record's status (a rejected record leaves the usable
    pool) and may correct its gloss, but never touches its form or check_url.
    The view reads only those two, so tiers don't move when verdicts land.
    """
    view = [
        {
            **r,
            "gloss_en": "-",
            "adjudication": {"status": "llm_checked" if r.get("check_url") else "seeded"},
        }
        for r in records
    ]
    return assign_splits(view, test, train)


def assign_tiers(records: list[dict], test: set[str], train: set[str]) -> list[tuple[str, dict]]:
    """Return (tier, record) pairs in work order."""
    pop = population_splits(records, test, train)
    is_test = {r["etr"]: clean_surface(r["etr"]) in test for r in records}
    checked = [r for r in records if pop[r["etr"]] in {GG_TRAIN, GG_SILVER, ROSETTA_TRAIN_OVERLAP}]
    checked.sort(key=lambda r: hash_key(r["etr"]))
    audit = checked[:AUDIT_N]
    taken = {r["etr"] for r in audit}

    def rest(pred) -> list[dict]:
        rows = [r for r in checked if r["etr"] not in taken and pred(r)]
        taken.update(r["etr"] for r in rows)
        return rows

    silver = rest(lambda r: pop[r["etr"]] == GG_SILVER)
    witness = rest(lambda r: r["source_type"] in {"ancient_gloss", "bilingual"})
    remaining = sorted(
        rest(lambda r: True), key=lambda r: (CONF_ORDER[r["confidence"]], hash_key(r["etr"]))
    )
    excluded = sorted((r for r in records if is_test[r["etr"]]), key=lambda r: hash_key(r["etr"]))
    taken.update(r["etr"] for r in excluded)
    # never web-checked, plus anything the population view set aside (empty or
    # duplicate surfaces): all of it needs a full check
    seeded = sorted((r for r in records if r["etr"] not in taken), key=lambda r: hash_key(r["etr"]))
    out = [("audit", r) for r in audit]
    out += [("silver_eval", r) for r in silver]
    out += [("witness", r) for r in witness]
    out += [("remaining", r) for r in remaining]
    out += [("seeded", r) for r in seeded]
    out += [("excluded", r) for r in excluded]
    return out


def build(
    worksheet: Path, records: list[dict], test: set[str], train: set[str], force: bool
) -> int:
    if worksheet.exists() and not force:
        pending = unapplied(worksheet, {r["etr"]: r for r in records})
        if pending:
            print(
                f"{worksheet.name} has {len(pending)} verdict(s) not yet in "
                f"{GLOSSES.name}. Run `apply` first, or pass --force to discard them.",
                file=sys.stderr,
            )
            return 1
    splits = assign_splits(records, test, train)
    rows = []
    for rank, (tier, r) in enumerate(assign_tiers(records, test, train), start=1):
        rows.append(
            {
                "queue_rank": rank,
                "tier": tier,
                "split": splits[r["etr"]],
                "current_status": r["adjudication"]["status"],
                **{k: r.get(k) or "" for k in INFO_COLS[4:]},
                **dict.fromkeys(HUMAN_COLS, ""),
            }
        )
    with worksheet.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=INFO_COLS + HUMAN_COLS)
        w.writeheader()
        w.writerows(rows)
    tiers: dict[str, int] = {}
    for row in rows:
        tiers[row["tier"]] = tiers.get(row["tier"], 0) + 1
    print(f"wrote {worksheet.name}: {len(rows)} rows | {tiers}")
    return 0


def unapplied(worksheet: Path, by_etr: dict[str, dict]) -> list[dict]:
    """Worksheet rows the JSONL does not reflect yet: a new verdict, or a
    correction written after the verdict was applied."""
    pending = []
    with worksheet.open() as f:
        for row in csv.DictReader(f):
            if not row.get("verdict", "").strip():
                continue
            rec = by_etr.get(row["etr"], {})
            status = rec.get("adjudication", {}).get("status")
            corrected = row.get("corrected_gloss", "").strip()
            if status != row["verdict"].strip().lower() or (
                corrected and corrected != rec.get("gloss_en")
            ):
                pending.append(row)
    return pending


def apply(worksheet: Path, glosses: Path) -> int:
    records = load_records(glosses)
    by_etr = {r["etr"]: r for r in records}
    errors, changes, already = [], [], 0
    with worksheet.open() as f:
        for row in csv.DictReader(f):
            verdict = row["verdict"].strip().lower()
            if not verdict:
                continue
            where = f"rank {row['queue_rank']} ({row['etr']})"
            if verdict not in VERDICTS:
                errors.append(f"{where}: verdict must be one of {sorted(VERDICTS)}")
                continue
            if not row["verified_by"].strip() or not DATE_RE.match(row["verified_date"].strip()):
                errors.append(f"{where}: verified_by and verified_date (YYYY-MM-DD) are required")
                continue
            if verdict == "rejected" and not row["verifier_notes"].strip():
                errors.append(f"{where}: a rejection needs its reason in verifier_notes")
                continue
            corrected = row["corrected_gloss"].strip()
            if corrected and not gloss_head(corrected):
                errors.append(f"{where}: corrected_gloss must start with the sense itself")
                continue
            rec = by_etr.get(row["etr"])
            if rec is None:
                errors.append(f"{where}: no such record in {glosses.name}")
                continue
            status = rec["adjudication"]["status"]
            if status == verdict:
                if corrected and corrected != rec["gloss_en"]:
                    errors.append(
                        f"{where}: already {status}; a correction added after the verdict "
                        "was applied must be made in the JSONL by hand"
                    )
                    continue
                already += 1  # applied on an earlier run; never write it twice
                continue
            if status in VERDICTS:
                errors.append(f"{where}: already {status}; fix the record by hand")
                continue
            changes.append((rec, verdict, row))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        print(f"{len(errors)} problem(s); nothing written.", file=sys.stderr)
        return 1
    for rec, verdict, row in changes:
        rec["adjudication"] = {
            "status": verdict,
            "by": row["verified_by"].strip(),
            "date": row["verified_date"].strip(),
        }
        extra = []
        corrected = row["corrected_gloss"].strip()
        if verdict == "verified" and corrected and corrected != rec["gloss_en"]:
            extra.append(f"{CORRECTION_NOTE} (was: {rec['gloss_en']})")
            rec["gloss_en"] = corrected
        if row["verifier_notes"].strip():
            prefix = "rejected at verification" if verdict == "rejected" else "verifier"
            extra.append(f"{prefix}: {row['verifier_notes'].strip()}")
        if extra:
            rec["notes"] = "; ".join(filter(None, [rec.get("notes") or "", *extra]))
    if changes:
        write_records(records, glosses)
    print(
        f"applied {len(changes)} verdict(s) to {glosses.name} "
        f"({already} already applied); now run validate.py"
    )
    return 0


def clopper_pearson(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    a = (1 - level) / 2
    lo = 0.0 if k == 0 else float(beta.ppf(a, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - a, k + 1, n - k))
    return lo, hi


def report(records: list[dict], test: set[str], train: set[str]) -> int:
    tiered = assign_tiers(records, test, train)
    audit = [r for t, r in tiered if t == "audit"]
    done = [r for r in audit if r["adjudication"]["status"] in VERDICTS]
    rejected = sum(r["adjudication"]["status"] == "rejected" for r in done)
    # a verified record whose gloss had to be corrected was also wrong as checked
    corrected = sum(
        r["adjudication"]["status"] == "verified" and CORRECTION_NOTE in (r.get("notes") or "")
        for r in done
    )
    print(f"audit sample: {len(done)}/{len(audit)} adjudicated")
    if done:
        n, k = len(done), rejected + corrected
        lo, hi = clopper_pearson(k, n)
        print(
            f"llm_checked error rate: {k}/{n} = {k / n:.1%} (95% exact CI {lo:.1%} to {hi:.1%}); "
            f"{rejected} rejected, {corrected} verified only after a gloss correction"
        )
    counts: dict[str, int] = {}
    for r in records:
        counts[r["adjudication"]["status"]] = counts.get(r["adjudication"]["status"], 0) + 1
    print(f"all records by status: {counts}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["build", "apply", "report"])
    ap.add_argument("--force", action="store_true", help="build: discard filled verdicts")
    args = ap.parse_args(argv)
    if args.command == "apply":
        return apply(WORKSHEET, GLOSSES)
    records = load_records()
    test, train = rosetta_sets()
    if args.command == "build":
        return build(WORKSHEET, records, test, train, args.force)
    return report(records, test, train)


if __name__ == "__main__":
    raise SystemExit(main())
