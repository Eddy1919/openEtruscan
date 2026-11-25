"""End-to-end Name Index build (scripts/data_pipeline/build_name_index.py) on SQLite."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from openetruscan.core.onomastics import load_lexicon
from openetruscan.db.models import Base

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/data_pipeline/build_name_index.py"
RECORDS = [
    ("CIE 1881", "θana : cainei : velus"),
    ("CIE 2830", "aθ:tetina:helial"),
    ("ETP 208", "mi larθus"),
    ("CIE 22", "L CAECINA L F TLABONI VIX ANN S XXX"),
]


@pytest.fixture(scope="module")
def bni():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("build_name_index", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    eng = create_engine(f"sqlite:///{tmp_path / 'n.db'}")
    Base.metadata.create_all(eng)
    with eng.begin() as c:
        for rid, can in RECORDS:
            c.execute(
                text(
                    "INSERT INTO inscriptions (id, canonical, phonetic, old_italic, raw_text, "
                    "classification, language, script_system, completeness, provenance_status, "
                    "provenance_flags, source_code, is_codex) VALUES (:id, :can, '', '', :can, "
                    "'unknown', 'etruscan', 'old_italic', 'complete', 'acquired_undocumented', "
                    "'', 'unknown', 0)"
                ),
                {"id": rid, "can": can},
            )
    return eng


def _run(bni, engine):  # type: ignore[no-untyped-def]
    with engine.begin() as conn:
        plan = bni.build_plan(bni.read_records(conn), load_lexicon())
        bni.apply_plan(conn, plan)
    return plan


def test_build_and_rerun(bni, engine, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    plan = _run(bni, engine)
    assert plan.stats["records_with_a_name"] == 3
    with engine.connect() as c:
        rows = c.execute(
            text(
                "SELECT inscription_id, form, lemma, name_type, confidence "
                "FROM name_attestations ORDER BY inscription_id, position"
            )
        ).all()
    assert ("ETP 208", "larθus", "larθ", "praenomen", "high") in [tuple(r) for r in rows]
    assert ("CIE 1881", "cainei", "cainei", "gentilicium", "probable") in [tuple(r) for r in rows]
    assert not [r for r in rows if r[0] == "CIE 22"]
    _run(bni, engine)
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM name_attestations")).scalar() == len(rows)
    bni.write_reports(plan, tmp_path)
    assert (tmp_path / "names.csv").read_text(encoding="utf-8").startswith("lemma,name_type")


@pytest.mark.parametrize(
    ("url", "batched"),
    [
        ("postgresql://u@localhost/db", True),
        ("postgres://u@localhost/db", True),
        ("postgresql+psycopg2://u@localhost/db", True),
        ("sqlite://", False),
    ],
)
def test_make_engine_batches_psycopg2_only(bni, url: str, batched: bool) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy.dialects.postgresql.psycopg2 import EXECUTEMANY_VALUES_PLUS_BATCH

    eng = bni.make_engine(url)
    mode = getattr(eng.dialect, "executemany_mode", None)
    assert (mode is EXECUTEMANY_VALUES_PLUS_BATCH) is batched
