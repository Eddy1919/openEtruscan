#!/usr/bin/env python3
"""Fill the edition-layer tables (migration ``j5f6a7b8c9d0``).

Replaces ``integrate_burman.py``, which matched Burman's concordance on ET
sigla only and so reached about 150 records. This script:

1. builds ``inscription_aliases`` for every record — its own ID as a
   reference, plus everything Burman's concordance links to it (CIE, ET¹/ET²,
   TLE, TM, CII, CIL), each with the basis it was derived on;
2. writes ``inscription_edition``: the ET siglum and text class, the
   findspot resolved to a Pleiades place with a precision (from the
   findspot string, else from the ET region code), the current location
   split out of the findspot string, and the editor of the current reading;
3. never writes the location columns of ``inscriptions``
   (``findspot_lat``/``findspot_lon``/``findspot_uncertainty_m``,
   ``pleiades_id``, ``geom``): they hold what the source recorded. A place
   attribution stays in ``inscription_edition``, because a Pleiades
   representative point is not a find position and must not pass for one
   on the map;
4. seeds ``inscription_readings`` with the reading we show today,
   attributed to the edition it came from;
5. fills ``trismegistos_id`` where it is empty and the concordance gives
   exactly one TM number through a direct (not CIEP-inferred) link;
6. indexes the concordance rows no record matched in
   ``indexed_documents`` (known inscriptions the corpus does not hold);
7. loads ``lexicon_glosses`` from the gold-gloss file;
8. with ``--clear-custody-findspots``, moves findspot strings that only
   say where an object is kept (``in museo publico Clusino``) or that are
   object descriptions out of ``findspot`` into
   ``inscription_edition.findspot_source_text``, and re-derives
   ``provenance_status`` for those rows with a ``provenance_audits`` entry.

``classification`` is never touched: the ET class sits beside it.

Dry run by default; ``--apply`` writes in one transaction. Re-running is
safe: computed rows are replaced, ``basis = 'manual'`` aliases and
curator-set editor/autopsy values are kept.

Usage:
    DATABASE_URL=postgresql://… python scripts/data_pipeline/build_edition_layer.py \\
        --report-dir research/reports/edition_layer            # dry run
    DATABASE_URL=… python scripts/data_pipeline/build_edition_layer.py --apply \\
        --clear-custody-findspots
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import re
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from provenance_values import provenance_status_for_findspot  # noqa: E402

from openetruscan.core.concordance import (  # noqa: E402
    BURMAN_CITATION,
    Alias,
    ConcordanceIndex,
    ConcordanceRow,
    Ref,
    aliases_for_id,
    parse_reference,
    rix_class_of,
    rix_region_of,
    rix_siglum,
)
from openetruscan.core.findspots import (  # noqa: E402
    EtRegion,
    FindspotClass,
    Place,
    classify_findspot,
    load_et_regions,
    load_gazetteer,
    load_places,
)

REFERENCE = REPO / "reference"
DEFAULT_GLOSSES = REPO / "research/anchors/gold_glosses/gold_glosses.jsonl"
GLOSS_SOURCE = "research/anchors/gold_glosses/gold_glosses.jsonl"
SCRIPT_TAG = "build_edition_layer"


# ---------------------------------------------------------------------------
# Reading attribution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Attribution:
    edition: str
    editor: str | None
    year: int | None
    autopsy: bool | None
    note: str | None


_LARTH = "the Larth dataset (Vico & Spanakis 2023)"


def attribute_reading(record_id: str, source: str | None) -> Attribution:
    """Which edition the text we show comes from, decided by the record's origin.

    ``autopsy`` is ``False`` only for compilations whose editors worked from
    printed editions; it is ``None`` (not recorded) wherever the original
    editor may have seen the object.
    """
    rid = record_id.strip()
    if rid.isdigit():
        return Attribution(
            f"CIEP {rid} (Hill 2018), via {_LARTH}",
            "J. Hill",
            2018,
            False,
            "Compiled from printed editions; text extracted from the CIEP PDF by Larth.",
        )
    if rid.upper().startswith("CIE "):
        return Attribution(
            "CIE I (Pauli et al. 1893–1902), OpenEtruscan extraction from the scans",
            "C. Pauli, O. A. Danielsson",
            None,
            None,
            "Machine-read from the CIE Vol. I page images; check against the printed text.",
        )
    if rid.upper().startswith("ETP "):
        return Attribution(
            f"Etruscan Texts Project (Wallace et al.), via {_LARTH}",
            "R. E. Wallace et al.",
            None,
            False,
            "Compiled from printed editions.",
        )
    if rid.upper().startswith("CODEX_"):
        return Attribution(source or "OpenEtruscan codex transcription", None, None, None, None)
    if parse_reference(rid) is not None:
        return Attribution(
            f"ET (Rix 1991) as cited in Wallace, Zikh Rasna (2008), via {_LARTH}",
            "H. Rix",
            1991,
            None,
            None,
        )
    return Attribution(source or "unrecorded source", None, None, None, None)


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


@dataclass
class Record:
    id: str
    findspot: str | None
    findspot_lat: float | None
    findspot_lon: float | None
    trismegistos_id: str | None
    raw_text: str
    canonical: str
    classification: str
    provenance_status: str
    source: str | None = None
    #: The findspot string a previous ``--clear-custody-findspots`` run moved
    #: out of ``findspot``; classified in its place so a re-run keeps the
    #: current location it named.
    findspot_source_text: str | None = None


@dataclass
class RecordPlan:
    aliases: list[Alias]
    edition: dict[str, Any]
    trismegistos_id: str | None
    reading: dict[str, Any]
    clear_findspot: bool
    findspot_class: FindspotClass | None
    et_region_place: str | None


@dataclass
class Plan:
    records: dict[str, RecordPlan] = field(default_factory=dict)
    indexed: list[dict[str, Any]] = field(default_factory=list)
    glosses: list[dict[str, Any]] = field(default_factory=list)
    stats: collections.Counter[str] = field(default_factory=collections.Counter)
    reports: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: collections.defaultdict(list)
    )


@dataclass(frozen=True)
class References:
    index: ConcordanceIndex
    places: dict[str, Place]
    gazetteer: dict[str, FindspotClass]
    regions: dict[str, EtRegion]
    rix_site_labels: dict[str, str | None]

    def region(self, code: str | None) -> EtRegion | None:
        """The ET region for ``code`` in any case: record IDs write "At 1.100"
        for ET's "AT 1.100"."""
        if not code:
            return None
        hit = self.regions.get(code)
        if hit is not None:
            return hit
        low = code.lower()
        return next((r for c, r in self.regions.items() if c.lower() == low), None)

    def siglum(self, ref: Ref | None) -> str | None:
        """An ET siglum without the "ET " prefix, its region code in ET's case."""
        if ref is None:
            return None
        text = ref.display.removeprefix("ET ")
        code = rix_region_of(ref)
        reg = self.region(code)
        if code and reg is not None and reg.code != code:
            text = reg.code + text[len(code) :]
        return text


def load_references(refdir: Path = REFERENCE) -> References:
    with open(refdir / "rix_text_classes.csv", encoding="utf-8", newline="") as fh:
        rix = {r["class"]: (r["site_label"] or None) for r in csv.DictReader(fh)}
    return References(
        index=ConcordanceIndex.from_csv(refdir / "burman/burman_concordance_1.0.3.csv"),
        places=load_places(refdir / "places.csv"),
        gazetteer=load_gazetteer(refdir / "findspot_gazetteer.csv"),
        regions=load_et_regions(refdir / "et_regions.csv"),
        rix_site_labels=rix,
    )


def _classify(raw: str | None, refs: References) -> FindspotClass | None:
    s = (raw or "").strip()
    if not s:
        return None
    hit = refs.gazetteer.get(s)
    if hit is not None:
        return hit
    return classify_findspot(s, {k: p.kind for k, p in refs.places.items()})


def plan_record(rec: Record, refs: References, used_rows: list[ConcordanceRow]) -> RecordPlan:
    aliases = aliases_for_id(rec.id, refs.index, rows_out=used_rows)
    siglum, siglum_basis = rix_siglum(aliases)
    rix_class = rix_class_of(siglum) if siglum else None
    region_code = rix_region_of(siglum) if siglum else None

    live_findspot = (rec.findspot or "").strip()
    fc = _classify(live_findspot or rec.findspot_source_text, refs)
    place_key: str | None = None
    precision: str | None = None
    basis: str | None = None
    if fc is not None and fc.role in ("findspot", "findspot_and_current") and fc.place_key:
        place_key, precision, basis = fc.place_key, fc.precision, "findspot_string"

    et_place: str | None = None
    region = refs.region(region_code)
    if region is not None and region.place_key:
        et_place = region.place_key
        et_basis = "et_region" if siglum_basis != "ciep_cie_numbering" else "et_region_probable"
        # A bare town name ("Florentiae", "Cortonae") is often where the object
        # was kept, not where it was found. When it disagrees with a direct ET
        # region code, Rix's attribution wins; explicit find phrases ("Clusii in
        # agro") keep the string's place. Both cases go to the report.
        overrides = (
            place_key is not None
            and place_key != et_place
            and precision == "city"
            and et_basis == "et_region"
        )
        if place_key is None or overrides:
            place_key, precision, basis = region.place_key, region.precision, et_basis

    if basis is None and rec.findspot_lat is not None and rec.findspot_lon is not None:
        basis = "existing"

    # Only a string still sitting in `findspot` is pending; one an earlier run
    # moved out is already in findspot_source_text.
    clear = (
        bool(live_findspot) and fc is not None and fc.role in ("current_location", "description")
    )

    tm_direct = sorted(
        {a.value.split()[1] for a in aliases if a.scheme == "tm" and a.basis == "concordance"}
    )
    new_tm = tm_direct[0] if not rec.trismegistos_id and len(tm_direct) == 1 else None

    current = fc.current_location if fc is not None else None
    if current is None and live_findspot and rec.findspot_source_text:
        # A curator refilled `findspot` with a find place; the custody note
        # moved out earlier still says where the object is kept.
        src = _classify(rec.findspot_source_text, refs)
        current = src.current_location if src is not None else None

    att = attribute_reading(rec.id, rec.source)
    edition = {
        "inscription_id": rec.id,
        "rix_siglum": refs.siglum(siglum),
        "rix_text_class": rix_class,
        "rix_class_basis": siglum_basis if siglum else None,
        "findspot_place": place_key,
        "findspot_precision": precision,
        "findspot_basis": basis,
        "findspot_source_text": None,
        "current_location": current,
        "editor": att.editor,
        "autopsy": att.autopsy,
    }
    reading = {
        "inscription_id": rec.id,
        "reading": rec.raw_text or rec.canonical,
        "edition": att.edition,
        "editor": att.editor,
        "year": att.year,
        "autopsy": att.autopsy,
        "is_current": True,
        "source": SCRIPT_TAG,
        "note": att.note,
    }
    return RecordPlan(aliases, edition, new_tm, reading, clear, fc, et_place)


def _indexed_row(row: ConcordanceRow, refs: References) -> dict[str, Any]:
    displays = [r.display for r, _ in row.refs]
    et2 = [r for r, label in row.refs if r.scheme == "et" and "ET²" in label]
    et1 = [r for r, label in row.refs if r.scheme == "et" and "ET²" not in label]
    numbered = [r for r in et2 + et1 if rix_class_of(r)]
    siglum = numbered[0] if numbered else None
    order = ("et", "cie", "tle", "tm", "cii", "cil", "bakkum")
    primary = siglum or min(row.refs, key=lambda rl: order.index(rl[0].scheme))[0]
    region = rix_region_of(siglum) if siglum else None
    reg = refs.region(region)
    place = refs.places.get(reg.place_key) if reg and reg.place_key else None
    tm = [r.display.split()[1] for r, _ in row.refs if r.scheme == "tm"]
    notes = row.note or None
    if not any(r.scheme in ("et", "cie", "tle", "cii") for r, _ in row.refs):
        notes = "; ".join(
            x for x in (notes, "No Etruscan corpus reference: may be Latin or Faliscan.") if x
        )
    return {
        "primary_ref": primary.display,
        "refs": "; ".join(dict.fromkeys(displays)),
        "trismegistos_id": tm[0] if tm else None,
        "rix_siglum": refs.siglum(siglum),
        "rix_text_class": rix_class_of(siglum) if siglum else None,
        "region_code": reg.code if reg else region,
        "findspot_place": place.key if place else None,
        "pleiades_id": place.pleiades_id if place else None,
        "date_text": None,
        "source": BURMAN_CITATION,
        "source_row": f"row {row.row_no}",
        "notes": notes,
    }


def _confirm_ciep_aliases(plan: Plan, ids: list[str], cie_key: str) -> None:
    """Raise CIEP-derived aliases to ``high`` when the texts agree.

    A bare CIEP record whose text matches the record that carries the same
    CIE number directly (its own ID, or an ET siglum the concordance ties to
    it) is individually confirmed: the CIEP number is that CIE number.
    """
    anchors = [
        i
        for i in ids
        if any(
            a.lookup_key == cie_key and a.basis in ("own_id", "concordance")
            for a in plan.records[i].aliases
        )
    ]
    if not anchors:
        return
    for rid in ids:
        rp = plan.records[rid]
        if not any(a.basis == "ciep_cie_numbering" for a in rp.aliases):
            continue
        note = (
            f"Text matches record {anchors[0]}, which carries {cie_key.replace('cie:', 'CIE ')} "
            "directly; CIEP number confirmed for this record."
        )
        rp.aliases = [
            Alias(**{**a.__dict__, "confidence": "high", "note": note})
            if a.basis == "ciep_cie_numbering"
            else a
            for a in rp.aliases
        ]
        plan.stats["ciep_aliases_text_confirmed_records"] += 1


def _letters(text: str) -> str:
    return re.sub(r"[^a-zθχφσśšçξ]", "", (text or "").lower())


def _max_pair_similarity(texts: list[str]) -> float:
    """Best containment-aware similarity between any two texts (0–1).

    Larth's CIEP rows are often fragments of the full text, so a short text
    wholly contained in a longer one counts as a match.
    """
    import difflib

    best = 0.0
    norm = [_letters(t) for t in texts]
    for i in range(len(norm)):
        for j in range(i + 1, len(norm)):
            a, b = sorted((norm[i], norm[j]), key=len)
            if not a or not b:
                continue
            if len(a) >= 4 and a in b:
                return 1.0
            m = difflib.SequenceMatcher(None, a, b)
            matched = sum(block.size for block in m.get_matching_blocks())
            best = max(best, matched / len(a))
    return best


def load_glosses(path: Path) -> list[dict[str, Any]]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        g = json.loads(line)
        status = (g.get("adjudication") or {}).get("status", "seeded")
        if status == "rejected":
            continue
        etr = (g.get("etr") or "").strip()
        if not etr or not g.get("gloss_en"):
            continue
        out.append(
            {
                "form": etr.lower().rstrip("-"),
                "headword": etr,
                "gloss_en": g["gloss_en"],
                "latin": g.get("lat") or None,
                "source_type": g.get("source_type"),
                "confidence": g.get("confidence"),
                "citation_primary": g.get("citation_primary"),
                "citation_modern": g.get("citation_modern"),
                "status": status,
                "notes": g.get("notes") or None,
                "source": GLOSS_SOURCE,
            }
        )
    return out


def build_plan(records: Iterable[Record], refs: References, glosses_path: Path) -> Plan:
    plan = Plan()
    used: list[ConcordanceRow] = []
    record_list = list(records)
    cie_keys: dict[str, list[str]] = collections.defaultdict(list)
    for rec in record_list:
        rp = plan_record(rec, refs, used)
        plan.records[rec.id] = rp
        s = plan.stats
        s["records"] += 1
        if any(a.basis != "own_id" for a in rp.aliases):
            s["records_with_concordance_alias"] += 1
        for a in rp.aliases:
            s[f"aliases:{a.basis}"] += 1
            if a.scheme == "cie":
                cie_keys[a.lookup_key].append(rec.id)
        e = rp.edition
        if e["rix_text_class"]:
            s[f"rix_class_via:{e['rix_class_basis']}"] += 1
            if rec.classification == "unknown":
                s["rix_class_for_unknown_label"] += 1
            site = refs.rix_site_labels.get(e["rix_text_class"])
            if rec.classification != "unknown" and site and site != rec.classification:
                plan.reports["rix_vs_site_label"].append(
                    {
                        "id": rec.id,
                        "rix_siglum": e["rix_siglum"],
                        "rix_text_class": e["rix_text_class"],
                        "rix_suggests": site,
                        "site_label": rec.classification,
                        "basis": e["rix_class_basis"],
                        "canonical": rec.canonical[:80],
                    }
                )
            elif rec.classification != "unknown" and not site:
                plan.reports["rix_vs_site_label"].append(
                    {
                        "id": rec.id,
                        "rix_siglum": e["rix_siglum"],
                        "rix_text_class": e["rix_text_class"],
                        "rix_suggests": "",
                        "site_label": rec.classification,
                        "basis": e["rix_class_basis"],
                        "canonical": rec.canonical[:80],
                    }
                )
        # Points recorded at source, and records with no point that are
        # attributed to a place (a place layer, not points).
        if rec.findspot_lat is not None:
            s["coords_at_source"] += 1
        elif e["findspot_place"]:
            s[f"place_without_coords:{e['findspot_precision']}"] += 1
            s[f"place_without_coords_via:{e['findspot_basis']}"] += 1
        if rp.trismegistos_id:
            s["new_trismegistos_id"] += 1
        if rp.clear_findspot:
            s["custody_or_description_findspots"] += 1
        if e["current_location"]:
            s["current_location"] += 1
        fc = rp.findspot_class
        if (
            fc is not None
            and fc.place_key
            and rp.et_region_place
            and fc.place_key != rp.et_region_place
        ):
            plan.reports["findspot_vs_et_region"].append(
                {
                    "id": rec.id,
                    "findspot": rec.findspot,
                    "string_place": fc.place_key,
                    "et_region_place": rp.et_region_place,
                    "rix_siglum": e["rix_siglum"],
                }
            )
        if fc is not None and fc.role == "unknown":
            plan.reports["unmapped_findspots"].append({"id": rec.id, "findspot": rec.findspot})

    by_id = {r.id: r for r in record_list}
    for key, ids in sorted(cie_keys.items()):
        if len(ids) > 1:
            ids = sorted(ids)
            sim = _max_pair_similarity([by_id[i].canonical for i in ids])
            plan.reports["shared_cie_numbers"].append(
                {
                    "cie": key.removeprefix("cie:"),
                    "records": " | ".join(ids),
                    "n": len(ids),
                    "text_similarity": f"{sim:.2f}",
                    "texts": " | ".join(by_id[i].canonical[:40] for i in ids),
                }
            )
            plan.stats["shared_cie_numbers"] += 1
            if sim >= 0.6:
                plan.stats["shared_cie_numbers_same_text"] += 1
            if sim >= 0.8:
                _confirm_ciep_aliases(plan, ids, key)

    used_ids = {id(r) for r in used}
    # A row no record matched through its own reference is still held when
    # it names a text a record holds under another reference. An ET siglum
    # names one text, so a row with ET sigla is held only through one of
    # them: a TM number can cover several ET inscriptions (TM 145365 is
    # Ve 3.1, 6.1, 9.1 and 9.2). A row without ET sigla is held through its
    # TM number (the Tabula Cortonensis's TM-only row, TM 173868). CII, TLE
    # and CIL numbers group several inscriptions and never count.
    held = {
        a.lookup_key for rp in plan.records.values() for a in rp.aliases if a.scheme in ("tm", "et")
    }
    for row in refs.index.rows:
        if id(row) in used_ids:
            continue
        et_keys = [r.key for r, _ in row.refs if r.scheme == "et"]
        keys = et_keys or [r.key for r, _ in row.refs if r.scheme == "tm"]
        if any(k in held for k in keys):
            plan.stats["concordance_rows_held_via_other_reference"] += 1
            continue
        plan.indexed.append(_indexed_row(row, refs))
    plan.stats["indexed_documents"] = len(plan.indexed)
    plan.glosses = load_glosses(glosses_path)
    plan.stats["lexicon_glosses"] = len(plan.glosses)
    return plan


# ---------------------------------------------------------------------------
# Database I/O
# ---------------------------------------------------------------------------


def read_records(conn) -> list[Record]:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    rows = conn.execute(
        text(
            "SELECT i.id, i.findspot, i.findspot_lat, i.findspot_lon, "
            "i.trismegistos_id, i.raw_text, i.canonical, i.classification, "
            "i.provenance_status, i.source, e.findspot_source_text "
            "FROM inscriptions i LEFT JOIN inscription_edition e ON e.inscription_id = i.id"
        )
    ).mappings()
    return [Record(**dict(r)) for r in rows]


def apply_plan(conn, plan: Plan, clear_custody: bool) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    ids = list(plan.records)

    # 1. aliases: replace computed rows, keep manual ones.
    conn.execute(text("DELETE FROM inscription_aliases WHERE basis <> 'manual'"))
    manual = {
        (r[0], r[1])
        for r in conn.execute(text("SELECT inscription_id, lookup_key FROM inscription_aliases"))
    }
    alias_rows = [
        {
            k: v
            for k, v in asdict(a).items()
            if k
            in (
                "inscription_id",
                "scheme",
                "lookup_key",
                "value",
                "edition",
                "basis",
                "confidence",
                "source",
                "note",
            )
        }
        for rp in plan.records.values()
        for a in rp.aliases
        if (a.inscription_id, a.lookup_key) not in manual
    ]
    for row in alias_rows:
        row["note"] = row["note"] or None
    if alias_rows:
        conn.execute(
            text(
                "INSERT INTO inscription_aliases (inscription_id, scheme, lookup_key, value, "
                "edition, basis, confidence, source, note) VALUES (:inscription_id, :scheme, "
                ":lookup_key, :value, :edition, :basis, :confidence, :source, :note)"
            ),
            alias_rows,
        )

    # 2. inscription_edition: upsert computed columns; keep curator editor/autopsy.
    existing = {
        r[0]: (r[1], r[2], r[3])
        for r in conn.execute(
            text(
                "SELECT inscription_id, editor, autopsy, findspot_source_text "
                "FROM inscription_edition"
            )
        )
    }
    conn.execute(text("DELETE FROM inscription_edition"))
    ed_rows = []
    for rid, rp in plan.records.items():
        row = dict(rp.edition)
        if rid in existing:
            ed, au, src = existing[rid]
            if ed is not None:
                row["editor"] = ed
            if au is not None:
                row["autopsy"] = au
            if src is not None:
                row["findspot_source_text"] = src
        ed_rows.append(row)
    if ed_rows:
        conn.execute(
            text(
                "INSERT INTO inscription_edition (inscription_id, rix_siglum, rix_text_class, "
                "rix_class_basis, findspot_place, findspot_precision, findspot_basis, "
                "findspot_source_text, current_location, editor, autopsy) "
                "VALUES (:inscription_id, :rix_siglum, :rix_text_class, :rix_class_basis, "
                ":findspot_place, :findspot_precision, :findspot_basis, :findspot_source_text, "
                ":current_location, :editor, :autopsy)"
            ),
            ed_rows,
        )

    # 3. Trismegistos ids from direct concordance links.
    tm_rows = [
        {"id": rid, "tm": rp.trismegistos_id}
        for rid, rp in plan.records.items()
        if rp.trismegistos_id
    ]
    if tm_rows:
        conn.execute(
            text(
                "UPDATE inscriptions SET trismegistos_id = :tm "
                "WHERE id = :id AND (trismegistos_id IS NULL OR trismegistos_id = '')"
            ),
            tm_rows,
        )

    # 4. seed reading for records without any reading.
    have = {
        r[0] for r in conn.execute(text("SELECT DISTINCT inscription_id FROM inscription_readings"))
    }
    reading_rows = [rp.reading for rid, rp in plan.records.items() if rid not in have]
    if reading_rows:
        conn.execute(
            text(
                "INSERT INTO inscription_readings (inscription_id, reading, edition, editor, year, "
                "autopsy, is_current, source, note) VALUES (:inscription_id, :reading, :edition, "
                ":editor, :year, :autopsy, :is_current, :source, :note)"
            ),
            reading_rows,
        )

    # 5. coverage index and glosses: replace this script's rows.
    conn.execute(text("DELETE FROM indexed_documents WHERE source = :s"), {"s": BURMAN_CITATION})
    if plan.indexed:
        conn.execute(
            text(
                "INSERT INTO indexed_documents (primary_ref, refs, trismegistos_id, rix_siglum, "
                "rix_text_class, region_code, findspot_place, pleiades_id, date_text, source, "
                "source_row, notes) VALUES (:primary_ref, :refs, :trismegistos_id, :rix_siglum, "
                ":rix_text_class, :region_code, :findspot_place, :pleiades_id, :date_text, "
                ":source, :source_row, :notes)"
            ),
            plan.indexed,
        )
    conn.execute(text("DELETE FROM lexicon_glosses WHERE source = :s"), {"s": GLOSS_SOURCE})
    if plan.glosses:
        conn.execute(
            text(
                "INSERT INTO lexicon_glosses (form, headword, gloss_en, latin, source_type, "
                "confidence, citation_primary, citation_modern, status, notes, source) VALUES "
                "(:form, :headword, :gloss_en, :latin, :source_type, :confidence, "
                ":citation_primary, :citation_modern, :status, :notes, :source)"
            ),
            plan.glosses,
        )

    # 6. custody-only / description findspots out of `findspot`.
    if clear_custody:
        rows = conn.execute(
            text("SELECT id, findspot, provenance_status FROM inscriptions WHERE findspot <> ''")
        ).all()
        for rid, fs, status in rows:
            rp = plan.records.get(rid)
            if rp is None or not rp.clear_findspot:
                continue
            new_status = provenance_status_for_findspot("")
            conn.execute(
                text(
                    "UPDATE inscription_edition SET findspot_source_text = :s WHERE inscription_id = :id"
                ),
                {"s": fs, "id": rid},
            )
            conn.execute(text("UPDATE inscriptions SET findspot = '' WHERE id = :id"), {"id": rid})
            if status == "acquired_documented":
                conn.execute(
                    text("UPDATE inscriptions SET provenance_status = :n WHERE id = :id"),
                    {"n": new_status, "id": rid},
                )
                conn.execute(
                    text(
                        "INSERT INTO provenance_audits (inscription_id, old_status, new_status, "
                        "notes, created_by) VALUES (:id, :o, :n, :notes, :by)"
                    ),
                    {
                        "id": rid,
                        "o": status,
                        "n": new_status,
                        "notes": (
                            "The findspot field named only where the object is kept, or "
                            f"described the object: {fs[:300]!r}. Moved to "
                            "inscription_edition.findspot_source_text / current_location."
                        ),
                        "by": SCRIPT_TAG,
                    },
                )
    del ids


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def write_reports(plan: Plan, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    for name, rows in plan.reports.items():
        if not rows:
            continue
        with open(outdir / f"{name}.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    with open(outdir / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(dict(sorted(plan.stats.items())), fh, indent=1)
        fh.write("\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write to the database")
    ap.add_argument(
        "--clear-custody-findspots",
        action="store_true",
        help="move custody-only and description findspot strings out of `findspot`",
    )
    ap.add_argument("--reference-dir", type=Path, default=REFERENCE)
    ap.add_argument("--glosses", type=Path, default=DEFAULT_GLOSSES)
    ap.add_argument("--report-dir", type=Path, default=None)
    ap.add_argument(
        "--from-json",
        type=Path,
        default=None,
        help="plan from a JSON list of records instead of the database (dry run only)",
    )
    args = ap.parse_args()
    refs = load_references(args.reference_dir)

    if args.from_json:
        if args.apply:
            raise SystemExit("--from-json is dry-run only")
        raw = json.loads(args.from_json.read_text(encoding="utf-8"))
        fields = Record.__dataclass_fields__
        records = [
            Record(**{k: r.get(k) for k in fields if k != "source"}, source=r.get("source"))
            for r in raw
        ]
        for r in records:
            r.raw_text = r.raw_text or ""
            r.canonical = r.canonical or ""
        plan = build_plan(records, refs, args.glosses)
    else:
        from sqlalchemy import create_engine

        url = os.environ.get("DATABASE_URL")
        if not url:
            raise SystemExit("DATABASE_URL is not set")
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        engine = create_engine(url)
        with engine.begin() as conn:
            plan = build_plan(read_records(conn), refs, args.glosses)
            if args.apply:
                apply_plan(conn, plan, args.clear_custody_findspots)
    for k, v in sorted(plan.stats.items()):
        print(f"{k:42} {v:>7}")
    if args.report_dir:
        write_reports(plan, args.report_dir)
        print(f"reports in {args.report_dir}")
    print("applied" if args.apply else "dry run: nothing written (use --apply)")


if __name__ == "__main__":
    main()
