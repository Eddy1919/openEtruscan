"""Invariant tests for the research/v2 science harness.

The v2.0.2 lacuna retraction (PRE_REGISTRATION.md Deviation §B) was caused by
a scorer bug — empty API responses counted as hallucinations. In a tiny-n
field one harness bug is a paper-level event, so the invariants that fix was
built on are pinned here permanently:

  1. no_parse / empty responses are NEVER scored as hallucinations,
  2. API errors are missing data, not model abstentions, and never
     contribute to candidate-gold unanimity,
  3. the frozen-split generator refuses to emit text-less rows,
  4. bootstrap statistics are seed-stable,
  5. the two Krippendorff α implementations agree,
  6. the committed evidence files match what the published tables claim.

research/ is an importable package (it ships __init__.py) but lives outside
the installed src/ tree, so the repo root is put on sys.path explicitly —
same approach as test_llm_extract_anchors.py uses for scripts/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from research.v2.eval import bootstrap, lacuna_metrics  # noqa: E402
from research.v2.pipelines import classify_adjudicate, classify_kfold, classify_split  # noqa: E402


def _lacuna_row(**overrides):
    row = {
        "id": "x1",
        "model": "m",
        "gold_lacuna": "a",
        "masked": "mi [?] avil",
        "restored_lacuna": "a",
        "restored_full": "mi a avil",
        "hallucinated": False,
        "no_parse": False,
    }
    row.update(overrides)
    return row


class TestNoParseNeverHallucination:
    """The exact bug behind the retracted Finding C, pinned forever."""

    def test_answered_drops_no_parse_rows(self):
        rows = [_lacuna_row(), _lacuna_row(id="x2", no_parse=True, hallucinated=True)]
        kept = lacuna_metrics.answered(rows)
        assert [r["id"] for r in kept] == ["x1"]

    def test_hallucination_rate_excludes_no_parse(self):
        # 1 honest row + 9 no_parse rows flagged hallucinated=True: under the
        # buggy v2.0.2 scorer this read 0.9; the correct rate over answered
        # rows is 0.0.
        rows = [_lacuna_row()] + [
            _lacuna_row(id=f"e{i}", no_parse=True, hallucinated=True) for i in range(9)
        ]
        assert lacuna_metrics.hallucination_rate(lacuna_metrics.answered(rows)) == 0.0

    def test_dirty_gold_is_filtered(self):
        # Trailing dash markers ("more destroyed text continues") and
        # editorial digits are unscoreable and must not enter denominators.
        rows = [
            _lacuna_row(),
            _lacuna_row(id="d1", gold_lacuna="reri---"),
            _lacuna_row(id="d2", gold_lacuna="a2"),
            _lacuna_row(id="d3", gold_lacuna=""),
        ]
        assert [r["id"] for r in lacuna_metrics.filter_clean(rows)] == ["x1"]


class TestApiErrorIsMissingData:
    """classify_jury writes label='api_error' on transport failure; the
    adjudicator must treat it as missing data, never as an abstention."""

    def _jury(self, *labels, confidence="high"):
        return [
            {"model": f"m{i}", "label": lab, "confidence": confidence, "rationale": ""}
            for i, lab in enumerate(labels)
        ]

    def test_unanimous_clean_panel_promotes(self):
        disposition, summary = classify_adjudicate.classify_row(
            self._jury("funerary", "funerary", "funerary")
        )
        assert disposition == "candidate_gold"
        assert summary["n_api_error"] == 0

    def test_api_error_blocks_candidate_gold(self):
        # 2-of-2 agreement over an incomplete panel is not unanimity.
        disposition, summary = classify_adjudicate.classify_row(
            self._jury("funerary", "funerary", "api_error")
        )
        assert disposition == "queue"
        assert summary["n_api_error"] == 1

    def test_all_api_error_routes_to_queue(self):
        disposition, summary = classify_adjudicate.classify_row(
            self._jury("api_error", "api_error", "api_error")
        )
        assert disposition == "queue"
        assert summary["n_raters"] == 0

    def test_api_error_is_not_an_unsure_vote(self):
        # unsure + unsure + api_error is NOT "all raters unsure".
        disposition, _ = classify_adjudicate.classify_row(
            self._jury("unsure", "unsure", "api_error")
        )
        assert disposition == "all_unsure"  # the two real raters were unsure


class TestSplitGeneratorRefusesEmptyText:
    def test_missing_corpus_hard_fails(self, tmp_path):
        silver = tmp_path / "silver.csv"
        silver.write_text(
            "id,label,confidence,signal_source\n"
            "A1,funerary,high,keyword\n"
            "A2,ownership,medium,keyword\n"
        )
        rc = classify_split.main(
            [
                "--corpus",
                str(tmp_path / "does_not_exist.csv"),
                "--silver",
                str(silver),
                "--out-train",
                str(tmp_path / "train.jsonl"),
                "--out-test",
                str(tmp_path / "test.jsonl"),
                "--n-test",
                "1",
            ]
        )
        assert rc == 1
        assert not (tmp_path / "test.jsonl").exists()

    def test_allow_empty_text_flag_permits_smoke_runs(self, tmp_path):
        silver = tmp_path / "silver.csv"
        silver.write_text("id,label,confidence,signal_source\nA1,funerary,high,keyword\n")
        rc = classify_split.main(
            [
                "--corpus",
                str(tmp_path / "does_not_exist.csv"),
                "--silver",
                str(silver),
                "--out-train",
                str(tmp_path / "train.jsonl"),
                "--out-test",
                str(tmp_path / "test.jsonl"),
                "--n-test",
                "1",
                "--allow-empty-text",
            ]
        )
        assert rc == 0

    def test_text_bearing_corpus_passes_and_is_deterministic(self, tmp_path):
        silver = tmp_path / "silver.csv"
        silver.write_text(
            "id,label,confidence,signal_source\n"
            + "".join(f"A{i},funerary,high,keyword\n" for i in range(10))
        )
        corpus = tmp_path / "corpus.csv"
        corpus.write_text(
            "id,raw_text,canonical_transliterated,translation\n"
            + "".join(f"A{i},mi avil {i},mi avil {i},\n" for i in range(10))
        )
        outs = []
        for run in ("a", "b"):
            args = [
                "--corpus",
                str(corpus),
                "--silver",
                str(silver),
                "--out-train",
                str(tmp_path / f"train_{run}.jsonl"),
                "--out-test",
                str(tmp_path / f"test_{run}.jsonl"),
                "--n-test",
                "4",
                "--seed",
                "42",
            ]
            assert classify_split.main(args) == 0
            outs.append((tmp_path / f"test_{run}.jsonl").read_text())
        assert outs[0] == outs[1], "same seed must produce byte-identical splits"
        rows = [json.loads(line) for line in outs[0].splitlines()]
        assert all(r["raw_text"].strip() for r in rows)


class TestSplitIsTextDisjoint:
    """An id-disjoint split still leaks when one text carries several ids.

    The frozen v2 split was generated before this guard existed and leaks
    25/400 test rows; see PRE_REGISTRATION.md Deviation D.
    """

    @staticmethod
    def _run(tmp_path, corpus_rows, n_test="4"):
        silver = tmp_path / "silver.csv"
        silver.write_text(
            "id,label,confidence,signal_source\n"
            + "".join(f"{i},funerary,high,keyword\n" for i, _ in corpus_rows)
        )
        corpus = tmp_path / "corpus.csv"
        corpus.write_text(
            "id,raw_text,canonical_transliterated,translation\n"
            + "".join(f"{i},{t},{t},\n" for i, t in corpus_rows)
        )
        rc = classify_split.main(
            [
                "--corpus", str(corpus),
                "--silver", str(silver),
                "--out-train", str(tmp_path / "train.jsonl"),
                "--out-test", str(tmp_path / "test.jsonl"),
                "--n-test", n_test,
                "--seed", "42",
            ]
        )  # fmt: skip

        def _read(name):
            path = tmp_path / name
            if not path.exists():
                return []
            return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

        return rc, _read("train.jsonl"), _read("test.jsonl")

    def test_repeated_text_under_distinct_ids_never_straddles_the_split(self, tmp_path):
        # `mi` recurs across eight genuinely distinct artifacts in the real
        # corpus. Whichever side it lands on, all eight go together.
        rows = [(f"A{i}", "mi") for i in range(8)] + [(f"B{i}", f"avil {i}") for i in range(8)]
        rc, train, test = self._run(tmp_path, rows)
        assert rc == 0
        sides = {"train": {r["id"] for r in train}, "test": {r["id"] for r in test}}
        mi_ids = {f"A{i}" for i in range(8)}
        assert mi_ids <= sides["train"] or mi_ids <= sides["test"], (
            "the `mi` group was split across train and test"
        )

    def test_leiden_variants_of_one_word_are_one_group(self, tmp_path):
        # These four are the same word bracketed four ways; the manifest lists
        # them among the 635 rows the live DB deduplicates away.
        variants = ["la(u)tni", "lautn(i)", "laut(n)i", "lautni"]
        rows = [(f"L{i}", v) for i, v in enumerate(variants)]
        rows += [(f"C{i}", f"cae {i}") for i in range(8)]
        rc, train, test = self._run(tmp_path, rows)
        assert rc == 0
        lautni = {f"L{i}" for i in range(4)}
        train_ids, test_ids = {r["id"] for r in train}, {r["id"] for r in test}
        assert lautni <= train_ids or lautni <= test_ids

    def test_no_normalized_text_spans_both_pools(self, tmp_path):
        rows = [(f"A{i}", "mi") for i in range(4)]
        rows += [(f"B{i}", "su(θ)ina") for i in range(4)]
        rows += [(f"C{i}", "suθina") for i in range(4)]
        rows += [(f"D{i}", f"unique {i}") for i in range(8)]
        rc, train, test = self._run(tmp_path, rows, n_test="8")
        assert rc == 0
        train_keys = {classify_split.text_key(r["canonical_transliterated"]) for r in train}
        test_keys = {classify_split.text_key(r["canonical_transliterated"]) for r in test}
        assert not (train_keys & test_keys) - {""}

    def test_rows_that_are_pure_markup_are_not_fused_into_one_group(self, tmp_path):
        # `[---]` and `[?]` both normalize to the empty string. Grouping on
        # that would sweep every unreadable row into a single blob.
        rows = [("M0", "[---]"), ("M1", "[?]"), ("M2", "{}")]
        rows += [(f"D{i}", f"avil {i}") for i in range(9)]
        rc, _, test = self._run(tmp_path, rows)
        assert rc == 0
        assert len(test) < len(rows), "empty-key rows were fused into one group"


class TestTextKey:
    def test_strips_leiden_markup_and_casefolds(self):
        assert classify_split.text_key("La(u)tni") == "lautni"
        assert classify_split.text_key("menar{e}va") == "menareva"
        assert classify_split.text_key("<antar>") == "antar"

    def test_does_not_collapse_genuinely_distinct_words(self):
        assert classify_split.text_key("mi") != classify_split.text_key("mini")

    def test_pure_markup_normalizes_to_empty(self):
        assert classify_split.text_key("[---]") == ""

    def test_nfc_composition_cannot_evade_the_guard(self):
        # U+0073 U+0301 (s + combining acute) must group with U+015B
        # (precomposed s-acute): a decomposed spelling of the same text is
        # the same text for leakage purposes.
        assert classify_split.text_key("s\u0301uthina") == classify_split.text_key("\u015buthina")


class TestNeuralPredictionsWriter:
    """train_neural.py once destructured eval tuples as (gold, _, id) and
    wrote the inscription TEXT into the predictions' gold_label field
    (PRE_REGISTRATION.md Deviation §D, harness-bug disclosure). Pin the
    writer: gold_label must be a codebook label, never the text."""

    def test_gold_label_field_carries_labels_not_text(self, tmp_path):
        import pytest

        pytest.importorskip("torch")
        from research.v2.pipelines import train_neural

        labels = ["funerary", "ownership"]
        train = tmp_path / "train.jsonl"
        train.write_text(
            "".join(
                json.dumps(
                    {
                        "id": f"T{i}",
                        "canonical_transliterated": f"larth avil {i}",
                        "silver_label": labels[i % 2],
                    }
                )
                + "\n"
                for i in range(12)
            )
        )
        gold = tmp_path / "gold.jsonl"
        gold.write_text(
            "".join(
                json.dumps(
                    {
                        "id": f"E{i}",
                        "canonical_transliterated": f"velthur cae {i}",
                        "gold_label": labels[i % 2],
                    }
                )
                + "\n"
                for i in range(6)
            )
        )
        out_m, out_p = tmp_path / "m.json", tmp_path / "p.jsonl"
        rc = train_neural.main(
            [
                "--arch", "charcnn",
                "--train-pool", str(train),
                "--eval-gold", str(gold),
                "--out-metrics", str(out_m),
                "--out-predictions", str(out_p),
                "--epochs", "1",
                "--n-resamples", "10",
            ]
        )  # fmt: skip
        assert rc == 0
        rows = [json.loads(line) for line in out_p.read_text().splitlines()]
        assert len(rows) == 6
        for row in rows:
            assert row["gold_label"] in labels, (
                f"gold_label carries {row['gold_label']!r}; the (gold, _, id) "
                "destructuring bug is back"
            )


class TestHandoffBundle:
    """classify_handoff.py — the philologist bundle must be a deterministic
    function of in-repo adjudication artifacts (the v2.0 bundle wasn't, and
    became unregenerable when its GCS inputs died with the retired project)."""

    @staticmethod
    def _record(insc_id, silver, labels):
        return {
            "id": insc_id,
            "raw_text": f"text {insc_id}",
            "canonical_transliterated": f"text {insc_id}",
            "translation": "",
            "silver_label": silver,
            "silver_confidence": "medium",
            "jury_summary": {
                "consensus_label": next(iter(labels.values())),
                "per_model": [
                    {"model": m, "label": lab, "confidence": "high", "rationale": "r"}
                    for m, lab in labels.items()
                ],
            },
        }

    def _write(self, tmp_path):
        from research.v2.pipelines import classify_handoff

        tmp_path.mkdir(parents=True, exist_ok=True)
        raters = {"claude-opus-4-8": "funerary", "gemini-3.1-pro": "ownership"}
        queue = [self._record(f"Q{i}", "funerary", raters) for i in range(5)]
        gold = [
            self._record(f"G{i}", "ownership", dict.fromkeys(raters, "ownership"))
            for i in range(40)
        ]
        qp, gp = tmp_path / "q.jsonl", tmp_path / "g.jsonl"
        qp.write_text("".join(json.dumps(r) + "\n" for r in queue))
        gp.write_text("".join(json.dumps(r) + "\n" for r in gold))
        out = tmp_path / "bundle"
        rc = classify_handoff.main(
            ["--queue", str(qp), "--gold", str(gp), "--out-dir", str(out), "--seed", "42"]
        )
        assert rc == 0
        return out

    def test_bundle_has_queue_and_matching_blind_spot_checks(self, tmp_path):
        import csv

        out = self._write(tmp_path)
        queue = list(csv.DictReader((out / "adjudication_queue.csv").open()))
        assert len(queue) == 5
        assert "claude-opus-4-8_label" in queue[0]
        assert queue[0]["adjudicator_decision"] == ""
        a = (out / "spot_check_30_adjudicator_A.csv").read_text()
        b = (out / "spot_check_30_adjudicator_B.csv").read_text()
        assert a == b, "both adjudicators must receive identical blind samples"
        assert len(list(csv.DictReader((out / "spot_check_30_adjudicator_A.csv").open()))) == 30

    def test_bundle_is_deterministic(self, tmp_path):
        a = (self._write(tmp_path / "x") / "adjudication_queue.csv").read_text()
        b = (self._write(tmp_path / "y") / "adjudication_queue.csv").read_text()
        assert a == b


class TestKFoldAssignment:
    """classify_kfold.py — the v2.1 split shape: group-atomic stratified CV."""

    @staticmethod
    def _fixtures():
        silver = {
            f"A{i}": {"label": "funerary", "confidence": "high", "signal_source": "k"}
            for i in range(20)
        }
        # Two Leiden variants of one word, labelled — must land in ONE fold.
        silver["V0"] = {"label": "votive", "confidence": "high", "signal_source": "k"}
        silver["V1"] = {"label": "votive", "confidence": "high", "signal_source": "k"}
        corpus = {f"A{i}": {"canonical_transliterated": f"avil {i}"} for i in range(20)}
        corpus["V0"] = {"canonical_transliterated": "alpan(a)"}
        corpus["V1"] = {"canonical_transliterated": "alpana"}
        return silver, corpus

    def test_text_groups_never_span_folds(self):
        silver, corpus = self._fixtures()
        fold_of = classify_kfold.assign_folds(silver, corpus, n_folds=5, seed=42)
        assert fold_of["V0"] == fold_of["V1"]
        assert set(fold_of) == set(silver)

    def test_same_seed_same_assignment(self):
        silver, corpus = self._fixtures()
        a = classify_kfold.assign_folds(silver, corpus, n_folds=5, seed=42)
        b = classify_kfold.assign_folds(silver, corpus, n_folds=5, seed=42)
        assert a == b

    def test_majority_class_spreads_over_all_folds(self):
        silver, corpus = self._fixtures()
        fold_of = classify_kfold.assign_folds(silver, corpus, n_folds=5, seed=42)
        funerary_folds = {fold_of[f"A{i}"] for i in range(20)}
        assert funerary_folds == {0, 1, 2, 3, 4}


class TestDupGroupIdScript:
    """scripts/data_pipeline/add_dup_group_id.py — the column that lets any
    downstream consumer split on text groups instead of rows."""

    @staticmethod
    def _run(tmp_path, rows):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "add_dup_group_id",
            REPO_ROOT / "scripts/data_pipeline/add_dup_group_id.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        src = tmp_path / "in.csv"
        src.write_text("id,canonical_transliterated\n" + "".join(f"{i},{t}\n" for i, t in rows))
        out = tmp_path / "out.csv"
        assert mod.main(["--input", str(src), "--output", str(out)]) == 0
        import csv

        return list(csv.DictReader(out.open()))

    def test_variants_share_a_group_and_size_counts_them(self, tmp_path):
        got = self._run(
            tmp_path,
            [("A", "la(u)tni"), ("B", "lautn(i)"), ("C", "lautni"), ("D", "mi")],
        )
        lautni = [r for r in got if r["id"] in "ABC"]
        assert len({r["dup_group_id"] for r in lautni}) == 1
        assert all(r["dup_group_size"] == "3" for r in lautni)
        (mi,) = [r for r in got if r["id"] == "D"]
        assert mi["dup_group_size"] == "1"
        assert mi["dup_group_id"] != lautni[0]["dup_group_id"]

    def test_pure_markup_rows_stay_singletons(self, tmp_path):
        got = self._run(tmp_path, [("A", "[---]"), ("B", "[?]"), ("C", "{}")])
        assert len({r["dup_group_id"] for r in got}) == 3
        assert all(r["dup_group_size"] == "1" for r in got)

    def test_group_id_is_content_addressed_not_order_dependent(self, tmp_path):
        a = self._run(tmp_path, [("A", "suθina"), ("B", "mi")])
        b = self._run(tmp_path, [("X", "mi"), ("Y", "suθina")])
        key = lambda rows, text: next(  # noqa: E731
            r["dup_group_id"] for r in rows if r["canonical_transliterated"] == text
        )
        assert key(a, "mi") == key(b, "mi")
        assert key(a, "suθina") == key(b, "suθina")


class TestBootstrapStability:
    @staticmethod
    def _mean(rows):
        return sum(rows) / len(rows) if rows else 0.0

    def test_same_seed_same_ci(self):
        values = [1.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 0.0, 1.0, 1.0]
        a = bootstrap.bootstrap_ci(values, self._mean, n_resamples=2000, seed=42)
        b = bootstrap.bootstrap_ci(values, self._mean, n_resamples=2000, seed=42)
        assert (a.point, a.ci_low, a.ci_high) == (b.point, b.ci_low, b.ci_high)

    def test_paired_bootstrap_identical_metrics_is_null(self):
        values = [1.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.0]
        res = bootstrap.paired_bootstrap(values, self._mean, self._mean, n_resamples=2000, seed=42)
        assert res.delta_point == 0.0
        assert res.p_value > 0.05

    def test_paired_bootstrap_detects_dominance(self):
        # rows are (a_score, b_score) pairs; metric_a/metric_b project them.
        rows = [(1.0, 0.0)] * 30
        res = bootstrap.paired_bootstrap(
            rows,
            lambda rs: self._mean([r[0] for r in rs]),
            lambda rs: self._mean([r[1] for r in rs]),
            n_resamples=2000,
            seed=42,
        )
        assert res.delta_point == 1.0
        assert res.p_value < 0.05


class TestKrippendorffAlpha:
    def test_perfect_agreement_is_one(self):
        ratings = [["a", "a", "a"], ["b", "b", "b"], ["a", "a", "a"]]
        assert bootstrap.krippendorff_alpha_nominal(ratings) == pytest.approx(1.0)

    def test_handoff_implementation_agrees_with_eval_implementation(self):
        # compute_alpha.py is the dependency-free copy shipped to the
        # philologists; it must return the same α as the eval module.
        import importlib.util

        path = REPO_ROOT / "research/v2/handoff/v2.0-etr/compute_alpha.py"
        spec = importlib.util.spec_from_file_location("compute_alpha", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        ratings = [
            ["funerary", "funerary", "ownership"],
            ["votive", "votive", "votive"],
            ["funerary", "ownership", None],
            ["boundary", "boundary", "boundary"],
            ["ownership", "ownership", "ownership"],
        ]
        assert mod.krippendorff_alpha_nominal(ratings) == pytest.approx(
            bootstrap.krippendorff_alpha_nominal(ratings)
        )


class TestCommittedEvidencePins:
    """The tracked evidence under research/v2/ must keep matching the
    published tables. If these fail, either the evidence or the docs drifted."""

    RESULTS = REPO_ROOT / "research/v2/results/lacuna"
    DATA = REPO_ROOT / "research/v2/data"

    def test_v2_0_3_raw_jury_shape(self):
        rows = [
            json.loads(line)
            for line in (self.RESULTS / "lacuna_jury_raw_v2_0_3_rerun.jsonl").open()
        ]
        assert len(rows) == 210  # 3 raters x 70 unique tasks
        keys = {(r["model"], r["key"]) for r in rows}
        assert len(keys) == 210, "duplicate (model, task) pairs in the evidence file"
        assert {r["model"] for r in rows} == {
            "claude-opus-4-8",
            "gemini-3.1-pro-preview",
            "gemini-3.5-flash",
        }

    def test_v2_0_3_metrics_match_published_tables(self):
        d = json.loads((self.RESULTS / "lacuna_v2_0_3.json").read_text())
        pm = d["per_model"]
        assert pm["claude-opus-4-8"]["span_exact_match"]["point"] == pytest.approx(0.288, abs=5e-4)
        assert pm["gemini-3.1-pro-preview"]["span_exact_match"]["point"] == pytest.approx(
            0.258, abs=5e-4
        )
        assert pm["gemini-3.5-flash"]["hallucination_rate"]["point"] == pytest.approx(
            0.545, abs=5e-4
        )
        assert pm["gemini-3.1-pro-preview"]["hallucination_rate"]["point"] == pytest.approx(
            0.161, abs=5e-4
        )
        assert d["seed"] == 42
        assert d["n_resamples"] == 10_000

    def test_frozen_split_carries_text_and_preregistered_n(self):
        rows = [json.loads(line) for line in (self.DATA / "classify_test_v2.jsonl").open()]
        # 427 = the pre-registered 400 (seed=42) plus the 27 train-pool rows
        # whose normalized text matched a test row, pulled across when the
        # split was made text-disjoint (PRE_REGISTRATION.md Deviation §D).
        assert len(rows) == 427, "text-disjoint superset of the pre-registered 400"
        assert all(
            (r["raw_text"] or "").strip() or (r["canonical_transliterated"] or "").strip()
            for r in rows
        ), "frozen split must carry the text the jury reads"
        assert all(r["split_seed"] == 42 for r in rows)

    def test_frozen_split_contains_the_jury_handoff_ids(self):
        import csv

        split_ids = {
            str(json.loads(line)["id"]) for line in (self.DATA / "classify_test_v2.jsonl").open()
        }
        handoff = REPO_ROOT / "research/v2/handoff/v2.0-etr/adjudication_queue.csv"
        queue_ids = {row["id"] for row in csv.DictReader(handoff.open())}
        assert queue_ids <= split_ids, "the jury's adjudication queue must be a subset"

    def test_no_train_test_contamination(self):
        test_rows = [json.loads(line) for line in (self.DATA / "classify_test_v2.jsonl").open()]
        train_rows = [json.loads(line) for line in (self.DATA / "classify_train_pool.jsonl").open()]
        assert not {str(r["id"]) for r in test_rows} & {str(r["id"]) for r in train_rows}
        # Id-disjointness alone allowed the leak Deviation §D documents; the
        # committed split must also be text-disjoint, permanently.
        test_keys = {classify_split.text_key(r["canonical_transliterated"]) for r in test_rows}
        train_keys = {classify_split.text_key(r["canonical_transliterated"]) for r in train_rows}
        assert not (test_keys & train_keys) - {""}
