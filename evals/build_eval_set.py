#!/usr/bin/env python3
"""Build a multi-category eval set for the hybrid search NDCG@K harness.

This is the v2 build script. The v1 used a single relevance rule (substring
match in canonical / raw_text), which is a fine *regression* detector but a
poor *quality* measure: it rewards lexical overlap and ignores the structured
linked-data we've built (Pleiades place IDs, Trismegistos cross-corpus IDs,
date_approx, findspot vocabularies). A model that retrieves "Caere" rows for
a "Cerveteri" query is *correct* under semantic-equivalence-via-Pleiades but
wrong under substring matching.

Categories
----------
``place_pleiades``  — Pelagios-aligned. Gold set = rows sharing a Pleiades ID.
                      Query is the canonical place name. Tests semantic place
                      retrieval across name variants (Lat. Caere ↔ It. Caere).
``place_findspot``  — Free-text findspot column. Gold set = rows with the
                      same findspot string. Covers rows without pleiades_id.
``chronology``       — date_approx bucketed into archaic / classical / late.
                      Tests whether the index can retrieve period-typical
                      vocabulary when given a period name.
``cross_corpus``    — rows with a Trismegistos ID. Query is "trismegistos"
                      and the gold set is every TM-aligned row, testing
                      whether linked-data is reachable in normal search.
``lexical``          — the v1 substring rule, kept as a baseline category.

Each query carries explicit ``methodology`` metadata so eval consumers can
decide which categories they trust.

Run from repo root:
    python evals/build_eval_set.py [--api-url https://api.openetruscan.com]

Writes ``evals/search_eval_queries.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx

EVAL_FILE = Path(__file__).parent / "search_eval_queries.jsonl"
PAGE_SIZE = 500
MAX_GOLD_PER_QUERY = 250

# Pleiades ID → preferred query string for tests. Derived from the most
# frequent name in modern usage (e.g. Italian "Tarquinia" rather than the
# Latin variants stored alongside it). One Pleiades ID can match several
# findspot strings — that's the *point* of the category.
PLEIADES_QUERY_NAMES: dict[str, str] = {
    "413332": "Tarquinia",          # Tarchna / Tarquinii
    "422859": "Caere",              # = Cerveteri
    "413096": "Clusium",            # = Chiusi
    "432742": "Campania",
    "433061": "Pyrgi",              # Cerveteri's port
    "413389": "Volsinii",           # = Orvieto / Bolsena
    "413106": "Cortona",
    "423116": "Veii",
    "413393": "Vulci",              # Ager Volcentanus
    "393498": "Spina",
    "403292": "Volaterrae",         # = Volterra
    "413044": "Saena",              # = Siena
    "413105": "Perusia",            # = Perugia
    "413095": "Falerii",
    "423025": "Roma",
}


def fetch_corpus(api_url: str) -> list[dict[str, Any]]:
    """Page through /search and collect every row's structured metadata."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        resp = httpx.get(
            f"{api_url}/search",
            params={"limit": PAGE_SIZE, "offset": offset},
            timeout=30.0,
        )
        resp.raise_for_status()
        chunk = resp.json().get("results", [])
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        print(f"  fetched {len(rows)}", file=sys.stderr)
    return rows


def normalise(s: str) -> str:
    return unicodedata.normalize("NFC", s).lower().strip()


# ---------------------------------------------------------------------------
# Category builders
# ---------------------------------------------------------------------------


def queries_lexical(rows: list[dict]) -> list[dict]:
    """v1 baseline: pick the most discriminating canonical bigrams/trigrams.

    Generates queries from the canonical text rather than a hand-curated list
    so the lexical baseline scales with the corpus rather than with our
    epigraphic vocabulary intuition. Each query has between 3 and 200 matches.
    """
    canonicals = [normalise(r.get("canonical") or "") for r in rows]
    grams: Counter[str] = Counter()
    for text in canonicals:
        seen: set[str] = set()
        for n in (4, 5, 6):
            if len(text) < n:
                continue
            for i in range(len(text) - n + 1):
                g = text[i : i + n]
                if " " in g or any(c in g for c in ":.,-"):
                    continue
                if g in seen:
                    continue
                seen.add(g)
                grams[g] += 1

    queries: list[dict] = []
    for gram, count in grams.most_common(200):
        if count < 5 or count > 150:
            continue
        relevant = [r["id"] for r, c in zip(rows, canonicals, strict=True) if gram in c]
        if not (5 <= len(relevant) <= MAX_GOLD_PER_QUERY):
            continue
        queries.append(
            {
                "query": gram,
                "relevant_ids": sorted(set(relevant))[:MAX_GOLD_PER_QUERY],
                "category": "lexical",
                "methodology": "substring match in normalised canonical text",
                "n_relevant": len(set(relevant)),
            }
        )
        if len(queries) >= 40:
            break
    return queries


def queries_place_pleiades(rows: list[dict]) -> list[dict]:
    """Each Pleiades ID with ≥3 inscriptions becomes one query.

    The query is the canonical modern name (cf ``PLEIADES_QUERY_NAMES``); the
    gold set is every row sharing the Pleiades ID, *not* every row whose
    findspot equals the name. That's how Pelagios alignment works: the same
    place can have many local-language strings but one canonical IRI.
    """
    grouped: dict[str, list[str]] = {}
    for r in rows:
        pid = r.get("pleiades_id")
        if not pid:
            continue
        grouped.setdefault(str(pid), []).append(r["id"])

    out: list[dict] = []
    for pid, ids in grouped.items():
        if len(ids) < 3:
            continue
        name = PLEIADES_QUERY_NAMES.get(pid)
        if not name:
            # We have a Pleiades-linked place but no canonical-name override.
            # Fall back to the most common findspot string for this group.
            findspots = Counter(
                r.get("findspot")
                for r in rows
                if str(r.get("pleiades_id")) == pid and r.get("findspot")
            )
            if not findspots:
                continue
            name = findspots.most_common(1)[0][0]
        out.append(
            {
                "query": name,
                "relevant_ids": sorted(set(ids))[:MAX_GOLD_PER_QUERY],
                "category": "place_pleiades",
                "methodology": f"shared pleiades_id={pid}",
                "n_relevant": len(set(ids)),
                "pleiades_id": pid,
            }
        )
    return out


# Canonical groupings of findspot string variants.
#
# The corpus stores findspots in their source-faithful Latin forms, often as
# full prepositional phrases (genitive "Clusii", locative "Clusino", territorial
# "Clusii in agro"). All of these refer to the same place. A user typing
# "Chiusi" or "Clusium" should retrieve every variant. The eval query is the
# canonical name; the gold set is the union of every variant's rows.
#
# Names that already appear as a `place_pleiades` query are intentionally
# *excluded* here so the same query doesn't show up in two categories with
# different gold sets.
FINDSPOT_CANONICAL_GROUPS: dict[str, list[str]] = {
    # Largest single place in the corpus by row count: the CIE Volume I
    # Clusium ingest. Latin variants alone account for >800 rows.
    "Clusium": [
        "Clusii in agro",
        "Clusii",
        "Clusium cum agro",
        "Clusino",
        "Clusium",
        "in museo publico Clusino",
        "in museo publico Clusino GA.",
        "in museo publico Clusino (succ.) DA.",
        "in museo publico Clusino (succ.) Da.",
        "Bettolle in oppidum, 5 km remotum",
    ],
    "Volterra": ["Volaterris", "Volaterrae"],
}


def queries_place_findspot(rows: list[dict], min_n: int = 10) -> list[dict]:
    """Generate place queries from the findspot column.

    Two flavours:

    * **Canonical groups** (FINDSPOT_CANONICAL_GROUPS): the query is the
      canonical modern/Latin nominative name; gold = every row whose findspot
      matches one of the listed variants. Tests semantic-equivalence retrieval
      across spelling and case variants without leaning on Pleiades alignment.
    * **Solo high-frequency findspots**: any remaining findspot with ≥``min_n``
      rows whose canonical form does not already appear in ``place_pleiades``
      gets its own query, using the literal findspot string. This is the v1
      behaviour and exists for places we haven't curated a canonical group for.

    Names already covered by ``place_pleiades`` are skipped to avoid
    double-counting between the two categories.
    """
    pleiades_findspots: set[str] = set()
    for r in rows:
        if r.get("pleiades_id") and r.get("findspot"):
            pleiades_findspots.add(normalise(r["findspot"]))

    out: list[dict] = []
    consumed_variants: set[str] = set()

    # Pass 1: canonical groups first — they're hand-curated and take priority.
    for canon, variants in FINDSPOT_CANONICAL_GROUPS.items():
        ids = sorted({r["id"] for r in rows if r.get("findspot") in variants})
        if len(ids) < min_n:
            continue
        out.append(
            {
                "query": canon,
                "relevant_ids": ids[:MAX_GOLD_PER_QUERY],
                "category": "place_findspot",
                "methodology": (
                    "canonical group: rows with findspot in "
                    + str(variants)
                ),
                "n_relevant": len(ids),
            }
        )
        consumed_variants.update(variants)

    # Pass 2: solo findspots that aren't already pleiades-linked or grouped.
    findspot_counts: Counter[str] = Counter()
    for r in rows:
        fs = r.get("findspot")
        if not fs:
            continue
        findspot_counts[fs] += 1

    for fs, count in findspot_counts.most_common():
        if count < min_n:
            continue
        if normalise(fs) in pleiades_findspots:
            continue
        if fs in consumed_variants:
            continue
        ids = [r["id"] for r in rows if r.get("findspot") == fs]
        out.append(
            {
                "query": fs,
                "relevant_ids": sorted(set(ids))[:MAX_GOLD_PER_QUERY],
                "category": "place_findspot",
                "methodology": "exact findspot string match",
                "n_relevant": len(set(ids)),
            }
        )
    return out


# Period boundaries — keep in sync with `_PERIOD_RANGES` in
# `src/openetruscan/api/server.py`. The structured-query parser uses those
# bounds to translate period tokens into date_min/date_max filters; the
# eval generator uses these same bounds to build the matching gold set.
# A row is "relevant" to a period query iff its date_approx falls in
# [lo, hi] inclusive.
_PERIOD_BOUNDS: dict[str, tuple[int, int]] = {
    "archaic":       (-700, -500),
    "classical":     (-499, -300),
    "late":          (-299,  -50),
    # Pre-archaic Etruscan: 720–580 BCE. Overlaps archaic on purpose
    # (rows in -700..-580 are relevant to both queries).
    "orientalising": (-720, -580),
    # Standard Etruscan-studies alias for `late`. Same bounds → same gold.
    "hellenistic":   (-299,  -50),
}


def queries_chronology(rows: list[dict]) -> list[dict]:
    """Period-name queries with date-bucketed gold sets.

    Each period in ``_PERIOD_BOUNDS`` becomes a query whose gold set is every
    row whose ``date_approx`` falls within the period's bounds. Periods can
    overlap (orientalising overlaps archaic; hellenistic == late), which is
    the academic convention — the same row may be relevant to multiple
    period queries.
    """
    out: list[dict] = []
    for period, (lo, hi) in _PERIOD_BOUNDS.items():
        ids = sorted(
            r["id"] for r in rows
            if r.get("date_approx") is not None and lo <= r["date_approx"] <= hi
        )
        if len(ids) < 5:
            continue
        out.append(
            {
                "query": period,
                "relevant_ids": ids[:MAX_GOLD_PER_QUERY],
                "category": "chronology",
                "methodology": f"date_approx in [{lo}, {hi}] inclusive",
                "n_relevant": len(ids),
            }
        )
    return out


def queries_cross_corpus(rows: list[dict]) -> list[dict]:
    """One query for the rows aligned with Trismegistos."""
    ids = [r["id"] for r in rows if r.get("trismegistos_id")]
    if len(ids) < 5:
        return []
    return [
        {
            "query": "trismegistos",
            "relevant_ids": sorted(set(ids))[:MAX_GOLD_PER_QUERY],
            "category": "cross_corpus",
            "methodology": "row has a trismegistos_id",
            "n_relevant": len(set(ids)),
        }
    ]


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="https://api.openetruscan.com")
    args = parser.parse_args()

    print(f"Downloading corpus from {args.api_url}", file=sys.stderr)
    rows = fetch_corpus(args.api_url)
    print(f"  {len(rows)} rows", file=sys.stderr)

    builders: list[tuple[str, callable[..., Iterable[dict]]]] = [
        ("place_pleiades", queries_place_pleiades),
        ("place_findspot", queries_place_findspot),
        ("chronology", queries_chronology),
        ("cross_corpus", queries_cross_corpus),
        ("lexical", queries_lexical),
    ]

    queries: list[dict] = []
    for name, fn in builders:
        c = list(fn(rows))
        print(f"  {name:18s} {len(c):3d} queries", file=sys.stderr)
        queries.extend(c)

    # Drop duplicate query strings (keep the first by category priority).
    seen: set[str] = set()
    deduped: list[dict] = []
    for q in queries:
        key = (q["category"], normalise(q["query"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(q)

    with EVAL_FILE.open("w") as fh:
        for q in deduped:
            fh.write(json.dumps(q, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(deduped)} queries to {EVAL_FILE}", file=sys.stderr)
    by_cat = Counter(q["category"] for q in deduped)
    for cat, n in sorted(by_cat.items()):
        print(f"  {cat:18s} {n}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
