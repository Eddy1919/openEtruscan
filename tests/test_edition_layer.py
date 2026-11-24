"""End-to-end backfill (scripts/data_pipeline/build_edition_layer.py) on SQLite."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from openetruscan.db.models import Base

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/data_pipeline/build_edition_layer.py"


@pytest.fixture(scope="module")
def bel():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("build_edition_layer", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


RECORDS = [
    # id, findspot, lat, lon, classification, canonical
    ("CIE 4538", "Perusiae", None, None, "legal", "eulat tanna larezul"),
    ("4538", "", None, None, "unknown", "aulesi velθinas arznal"),
    ("Ta 3.6", "Tarquinia", 42.2488, 11.7553, "votive", "cn turce murila hercnas"),
    ("10007", "", None, None, "unknown", "turce murila hercnas"),
    ("CIE 900", "in museo publico Clusino GA.", None, None, "unknown", "larθi"),
    ("14000", "", None, None, "unknown", "i ciuain"),
]


@pytest.fixture()
def engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    eng = create_engine(f"sqlite:///{tmp_path / 'e.db'}")
    Base.metadata.create_all(eng)
    with eng.begin() as c:
        for rid, fs, lat, lon, cls, can in RECORDS:
            c.execute(
                text(
                    "INSERT INTO inscriptions (id, canonical, phonetic, old_italic, raw_text, "
                    "findspot, findspot_lat, findspot_lon, classification, language, "
                    "script_system, completeness, provenance_status, provenance_flags, "
                    "source_code, is_codex) VALUES (:id, :can, '', '', :can, :fs, :lat, :lon, "
                    ":cls, 'etruscan', 'old_italic', 'complete', :prov, '', 'unknown', 0)"
                ),
                {
                    "id": rid,
                    "can": can,
                    "fs": fs,
                    "lat": lat,
                    "lon": lon,
                    "cls": cls,
                    "prov": "acquired_documented" if fs else "acquired_undocumented",
                },
            )
    return eng


def _run(bel, engine, clear: bool = True):  # type: ignore[no-untyped-def]
    refs = bel.load_references()
    with engine.begin() as conn:
        plan = bel.build_plan(bel.read_records(conn), refs, bel.DEFAULT_GLOSSES)
        bel.apply_plan(conn, plan, clear)
    return plan


def test_backfill_end_to_end(bel, engine) -> None:  # type: ignore[no-untyped-def]
    plan = _run(bel, engine)
    with engine.connect() as c:

        def one(sql: str, **kw):  # type: ignore[no-untyped-def]
            return c.execute(text(sql), kw).one()

        # Aliases: the Cippus Perusinus is reachable by every standard reference.
        ids = {
            r[0]
            for r in c.execute(
                text("SELECT inscription_id FROM inscription_aliases WHERE lookup_key='et:pe 8.4'")
            )
        }
        assert ids == {"CIE 4538", "4538"}

        # Text class beside, not instead of, classification.
        ed = one(
            "SELECT rix_siglum, rix_text_class, rix_class_basis FROM inscription_edition WHERE inscription_id='CIE 4538'"
        )
        assert tuple(ed) == ("Pe 8.4", "8", "concordance")
        assert one("SELECT classification FROM inscriptions WHERE id='4538'")[0] == "unknown"

        # The bare record whose text matches Ta 3.6 is confirmed, not just probable.
        conf = one(
            "SELECT confidence FROM inscription_aliases WHERE inscription_id='10007' AND lookup_key='cie:10007'"
        )
        assert conf[0] == "high"
        assert (
            one(
                "SELECT confidence FROM inscription_aliases WHERE inscription_id='4538' AND lookup_key='cie:4538'"
            )[0]
            == "probable"
        )

        # Coordinates: Perusiae → Perusia (city); existing coordinates untouched.
        lat, lon, unc, pl = one(
            "SELECT findspot_lat, findspot_lon, findspot_uncertainty_m, pleiades_id FROM inscriptions WHERE id='CIE 4538'"
        )
        assert pl == "413248" and unc == 3000.0 and lat == pytest.approx(43.11, abs=0.01)
        assert one("SELECT findspot_lat FROM inscriptions WHERE id='Ta 3.6'")[0] == 42.2488

        # Custody-only findspot moved out, with an audit row.
        fs, prov = one("SELECT findspot, provenance_status FROM inscriptions WHERE id='CIE 900'")
        assert fs == "" and prov == "acquired_undocumented"
        src, cur = one(
            "SELECT findspot_source_text, current_location FROM inscription_edition WHERE inscription_id='CIE 900'"
        )
        assert src == "in museo publico Clusino GA." and cur
        assert one("SELECT count(*) FROM provenance_audits WHERE inscription_id='CIE 900'")[0] == 1

        # CIEP-only number: own alias only, no class.
        assert one("SELECT count(*) FROM inscription_aliases WHERE inscription_id='14000'")[0] == 1

        # Readings seeded, coverage index and glosses loaded.
        assert one("SELECT count(*) FROM inscription_readings WHERE is_current")[0] == len(RECORDS)
        assert one("SELECT count(*) FROM indexed_documents")[0] > 10_000
        assert one("SELECT count(*) FROM lexicon_glosses")[0] == plan.stats["lexicon_glosses"]


def test_backfill_is_idempotent(bel, engine) -> None:  # type: ignore[no-untyped-def]
    _run(bel, engine)
    with engine.begin() as c:
        c.execute(
            text("UPDATE inscription_edition SET editor='curator' WHERE inscription_id='Ta 3.6'")
        )
    _run(bel, engine)
    with engine.connect() as c:
        counts = [
            c.execute(text(f"SELECT count(*) FROM {t}")).scalar()
            for t in (
                "inscription_aliases",
                "inscription_edition",
                "inscription_readings",
                "provenance_audits",
            )
        ]
        assert counts[1:] == [len(RECORDS), len(RECORDS), 1]
        assert (
            c.execute(
                text("SELECT editor FROM inscription_edition WHERE inscription_id='Ta 3.6'")
            ).scalar()
            == "curator"
        )
        assert c.execute(
            text(
                "SELECT findspot_source_text FROM inscription_edition WHERE inscription_id='CIE 900'"
            )
        ).scalar()
        # The custody clause survives a re-run although `findspot` is now empty.
        assert c.execute(
            text("SELECT current_location FROM inscription_edition WHERE inscription_id='CIE 900'")
        ).scalar()
        # Nothing is left pending: the string was moved on the first run.
        plan = _run(bel, engine)
        assert plan.stats.get("custody_or_description_findspots", 0) == 0


def test_dry_run_json(bel, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    refs = bel.load_references()
    recs = [
        bel.Record(
            id=r[0],
            findspot=r[1],
            findspot_lat=r[2],
            findspot_lon=r[3],
            pleiades_id=None,
            trismegistos_id=None,
            raw_text=r[5],
            canonical=r[5],
            classification=r[4],
            provenance_status="acquired_undocumented",
        )
        for r in RECORDS
    ]
    plan = bel.build_plan(recs, refs, bel.DEFAULT_GLOSSES)
    bel.write_reports(plan, tmp_path)
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["records"] == len(RECORDS)
    assert (tmp_path / "shared_cie_numbers.csv").exists()


def test_region_code_case_is_canonical(bel) -> None:  # type: ignore[no-untyped-def]
    """Record IDs write "At 1.100"; ET's code is AT (Ager Tarquiniensis)."""
    refs = bel.load_references()
    rec = bel.Record(
        id="At 1.100",
        findspot="",
        findspot_lat=None,
        findspot_lon=None,
        pleiades_id=None,
        trismegistos_id=None,
        raw_text="x",
        canonical="x",
        classification="unknown",
        provenance_status="acquired_undocumented",
    )
    rp = bel.plan_record(rec, refs, [])
    assert rp.edition["rix_siglum"] == "AT 1.100"
    assert rp.edition["findspot_place"] == "tarquinii"


def _run_with(bel, engine, refs, clear: bool = True):  # type: ignore[no-untyped-def]
    with engine.begin() as conn:
        plan = bel.build_plan(bel.read_records(conn), refs, bel.DEFAULT_GLOSSES)
        bel.apply_plan(conn, plan, clear)
    return plan


def test_corrected_place_moves_a_placed_point(bel, engine) -> None:  # type: ignore[no-untyped-def]
    """README workflow: fix a gazetteer row, re-run, the point follows."""
    from openetruscan.core.findspots import FindspotClass

    _run(bel, engine)
    refs = bel.load_references()
    refs.gazetteer["Perusiae"] = FindspotClass("findspot", "clusium", "territory", None, "manual")
    plan = _run_with(bel, engine, refs)
    assert plan.stats["placed_coords_moved"] == 1
    clusium = refs.places["clusium"]
    with engine.connect() as c:
        lat, lon, unc, pl = c.execute(
            text(
                "SELECT findspot_lat, findspot_lon, findspot_uncertainty_m, pleiades_id "
                "FROM inscriptions WHERE id='CIE 4538'"
            )
        ).one()
        place = c.execute(
            text("SELECT findspot_place FROM inscription_edition WHERE inscription_id='CIE 4538'")
        ).scalar()
    assert (lat, lon) == (clusium.lat, clusium.lon)
    assert unc == float(bel.UNCERTAINTY_M["territory"])
    assert pl == clusium.pleiades_id and place == "clusium"
    # A third run with the same references changes nothing.
    assert _run_with(bel, engine, refs).stats.get("placed_coords_moved", 0) == 0


def test_hand_set_coordinates_are_kept(bel, engine) -> None:  # type: ignore[no-untyped-def]
    from openetruscan.core.findspots import FindspotClass

    _run(bel, engine)
    with engine.begin() as c:
        c.execute(
            text("UPDATE inscriptions SET findspot_lat=43.1, findspot_lon=12.4 WHERE id='CIE 4538'")
        )
    refs = bel.load_references()
    refs.gazetteer["Perusiae"] = FindspotClass("findspot", "clusium", "territory", None, "manual")
    _run_with(bel, engine, refs)
    with engine.connect() as c:
        assert tuple(
            c.execute(
                text("SELECT findspot_lat, findspot_lon FROM inscriptions WHERE id='CIE 4538'")
            ).one()
        ) == (43.1, 12.4)


def test_refilled_findspot_keeps_the_custody_note(bel, engine) -> None:  # type: ignore[no-untyped-def]
    _run(bel, engine)
    with engine.begin() as c:
        c.execute(text("UPDATE inscriptions SET findspot='Clusii in agro' WHERE id='CIE 900'"))
    _run(bel, engine)
    with engine.connect() as c:
        src, cur, place = c.execute(
            text(
                "SELECT findspot_source_text, current_location, findspot_place "
                "FROM inscription_edition WHERE inscription_id='CIE 900'"
            )
        ).one()
    assert src == "in museo publico Clusino GA."
    assert cur and "Clusino" in cur
    assert place == "clusium"


def test_named_text_parts_are_not_indexed_as_missing(bel) -> None:  # type: ignore[no-untyped-def]
    """Burman lists the Tabula Cortonensis twice (Co 8.3, and a TM-only row);
    holding it as CODEX_TCo_A must keep both out of the coverage index."""
    refs = bel.load_references()
    rec = bel.Record(
        id="CODEX_TCo_A",
        findspot="",
        findspot_lat=None,
        findspot_lon=None,
        pleiades_id=None,
        trismegistos_id=None,
        raw_text="et petruiś",
        canonical="et petruiś",
        classification="unknown",
        provenance_status="acquired_undocumented",
    )
    plan = bel.build_plan([rec], refs, bel.DEFAULT_GLOSSES)
    assert not [r for r in plan.indexed if "173868" in (r["trismegistos_id"] or r["refs"])]
    assert plan.stats["concordance_rows_held_via_other_reference"] >= 1


def test_source_pleiades_id_survives_a_moved_point(bel, engine) -> None:  # type: ignore[no-untyped-def]
    """A Pleiades link recorded at source is not the script's to rewrite."""
    from openetruscan.core.findspots import FindspotClass

    with engine.begin() as c:
        c.execute(text("UPDATE inscriptions SET pleiades_id='413248' WHERE id='CIE 4538'"))
    _run(bel, engine)
    refs = bel.load_references()
    refs.gazetteer["Perusiae"] = FindspotClass("findspot", "clusium", "territory", None, "manual")
    _run_with(bel, engine, refs)
    with engine.connect() as c:
        lat, pl = c.execute(
            text("SELECT findspot_lat, pleiades_id FROM inscriptions WHERE id='CIE 4538'")
        ).one()
        flag = c.execute(
            text(
                "SELECT pleiades_from_place FROM inscription_edition "
                "WHERE inscription_id='CIE 4538'"
            )
        ).scalar()
    assert lat == refs.places["clusium"].lat  # the point moved
    assert pl == "413248" and not flag  # the source link stayed


def test_pleiades_id_stays_ours_after_the_point_is_cleared(bel, engine) -> None:  # type: ignore[no-untyped-def]
    """An ID the script wrote is still the script's to move when someone
    cleared the coordinates in between."""
    from openetruscan.core.findspots import FindspotClass

    _run(bel, engine)
    with engine.begin() as c:
        c.execute(
            text("UPDATE inscriptions SET findspot_lat=NULL, findspot_lon=NULL WHERE id='CIE 4538'")
        )
    refs = bel.load_references()
    refs.gazetteer["Perusiae"] = FindspotClass("findspot", "clusium", "territory", None, "manual")
    _run_with(bel, engine, refs)
    with engine.connect() as c:
        pl = c.execute(text("SELECT pleiades_id FROM inscriptions WHERE id='CIE 4538'")).scalar()
        flag = c.execute(
            text(
                "SELECT pleiades_from_place FROM inscription_edition "
                "WHERE inscription_id='CIE 4538'"
            )
        ).scalar()
    assert pl == refs.places["clusium"].pleiades_id and flag


def test_shared_group_number_does_not_hide_a_missing_text(bel) -> None:  # type: ignore[no-untyped-def]
    """CIE 5256 and CIE 5257 (ET Vc 7.15) share CII 2162. Holding 5256 says
    nothing about 5257, which stays in the coverage index."""
    refs = bel.load_references()
    rec = bel.Record(
        id="5256",
        findspot="",
        findspot_lat=None,
        findspot_lon=None,
        pleiades_id="",
        trismegistos_id=None,
        raw_text="x",
        canonical="x",
        classification="unknown",
        provenance_status="acquired_undocumented",
    )
    assert rec.pleiades_id is None  # '' means no ID
    plan = bel.build_plan([rec], refs, bel.DEFAULT_GLOSSES)
    assert any("Vc 7.15" in (r["refs"] or "") for r in plan.indexed)


def test_shared_tm_number_does_not_hide_another_et_text(bel) -> None:  # type: ignore[no-untyped-def]
    """TM 145365 covers ET Ve 3.1, 6.1, 9.1 and 9.2. Holding Ve 9.2 (CIE 6673c,
    reached from record 6673) leaves the other three in the coverage index:
    a row with an ET siglum is held only through that siglum."""
    refs = bel.load_references()
    rec = bel.Record(
        id="6673",
        findspot="",
        findspot_lat=None,
        findspot_lon=None,
        pleiades_id=None,
        trismegistos_id=None,
        raw_text="x",
        canonical="x",
        classification="unknown",
        provenance_status="acquired_undocumented",
    )
    plan = bel.build_plan([rec], refs, bel.DEFAULT_GLOSSES)
    assert "tm:145365" in {a.lookup_key for a in plan.records["6673"].aliases}
    indexed = [r["refs"] or "" for r in plan.indexed if "TM 145365" in (r["refs"] or "")]
    for siglum in ("ET Ve 3.1;", "ET Ve 6.1;", "ET Ve 9.1;"):
        assert any(siglum in r for r in indexed), siglum
    assert not any("ET Ve 9.2;" in r for r in indexed)
