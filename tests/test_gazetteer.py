"""
Unit tests for findspot → Pleiades matching (openetruscan.core.gazetteer).

No network or DB: the gazetteer is a small hand-built fixture of real Etrurian
places, and every assertion is about the pure matching logic.
"""

import pytest

from openetruscan.core.gazetteer import (
    GazetteerPlace,
    normalize_place_name,
    propose_links,
    score_match,
    stem_place_name,
)

# A few real Etruria places (Pleiades IDs are the genuine ones) with the ancient
# Latin name variants a findspot string might surface as.
CLUSIUM = GazetteerPlace(
    pleiades_id="413047",
    title="Clusium",
    names=("Clusium", "Camars"),
    lat=43.017,
    lon=11.949,
)
PERUSIA = GazetteerPlace(pleiades_id="393839", title="Perusia", names=("Perusia",))
VOLATERRAE = GazetteerPlace(pleiades_id="413375", title="Volaterrae", names=("Volaterrae",))
TARQUINII = GazetteerPlace(
    pleiades_id="413332", title="Tarquinii", names=("Tarquinii", "Tarchna", "Tarquinia")
)

GAZETTEER = [CLUSIUM, PERUSIA, VOLATERRAE, TARQUINII]


class TestNormalize:
    def test_lowercases_and_folds_diacritics(self):
        assert (
            normalize_place_name("Località") == "localita"
            or normalize_place_name("Perùsia") == "perusia"
        )

    def test_strips_locative_scaffolding(self):
        assert normalize_place_name("Clusii in agro") == "clusii"
        assert normalize_place_name("prope Volaterras") == "volaterras"
        assert normalize_place_name("Ager Tarquiniensis") == "tarquiniensis"

    def test_punctuation_becomes_separators(self):
        assert normalize_place_name("Clusii (in-agro)") == "clusii"

    def test_empty(self):
        assert normalize_place_name("") == ""
        assert normalize_place_name("   ") == ""


class TestStem:
    def test_inflections_share_a_stem(self):
        # Nominative, locative/genitive, and a wrapped locative phrase converge.
        stems = {
            stem_place_name("Clusium"),
            stem_place_name("Clusii"),
            stem_place_name("Clusii in agro"),
        }
        assert len(stems) == 1, stems

    def test_keeps_minimum_stem_length(self):
        # Never strip so far that nothing meaningful remains.
        assert len(stem_place_name("Roma").replace(" ", "")) >= 3


class TestScore:
    def test_exact_normalized_match_is_one(self):
        assert score_match("Clusium", "Clusium") == 1.0

    def test_inflected_match_is_one_via_stem(self):
        assert score_match("Clusii in agro", "Clusium") == 1.0

    def test_unrelated_places_score_low(self):
        assert score_match("Clusium", "Volaterrae") < 0.5

    def test_empty_scores_zero(self):
        assert score_match("", "Clusium") == 0.0
        assert score_match("Clusium", "") == 0.0

    def test_score_is_bounded(self):
        for a in ("Perusiae", "Tarchna", "xyzzy"):
            for b in ("Perusia", "Tarquinii", "Clusium"):
                assert 0.0 <= score_match(a, b) <= 1.0


class TestProposeLinks:
    def test_matches_inflected_findspot_to_right_place(self):
        [proposal] = propose_links(["Clusii in agro"], GAZETTEER)
        assert proposal.best is not None
        assert proposal.best.pleiades_id == "413047"
        assert proposal.best.uri == "https://pleiades.stoa.org/places/413047"

    def test_matches_via_name_variant(self):
        # "Tarchna" is the Etruscan name variant of Tarquinii.
        [proposal] = propose_links(["Tarchna"], GAZETTEER)
        assert proposal.best is not None
        assert proposal.best.pleiades_id == "413332"
        assert proposal.best.matched_name == "Tarchna"

    def test_ablative_findspot(self):
        [proposal] = propose_links(["Volaterris"], GAZETTEER)
        assert proposal.best is not None
        assert proposal.best.pleiades_id == "413375"

    def test_no_match_returns_empty_candidates(self):
        [proposal] = propose_links(["Some Unknown Hamlet"], GAZETTEER, threshold=0.84)
        assert proposal.candidates == []
        assert proposal.best is None

    def test_threshold_is_respected(self):
        strict = propose_links(["Clusinum"], GAZETTEER, threshold=0.99)
        loose = propose_links(["Clusinum"], GAZETTEER, threshold=0.5)
        assert len(loose[0].candidates) >= len(strict[0].candidates)

    def test_top_k_caps_candidate_count(self):
        [proposal] = propose_links(["Clusii"], GAZETTEER, threshold=0.0, top_k=2)
        assert len(proposal.candidates) <= 2

    def test_candidates_sorted_by_score_desc(self):
        [proposal] = propose_links(["Clusii"], GAZETTEER, threshold=0.0, top_k=10)
        scores = [c.score for c in proposal.candidates]
        assert scores == sorted(scores, reverse=True)

    def test_one_candidate_per_place(self):
        # A place with multiple matching names must not appear twice.
        [proposal] = propose_links(["Tarquinia"], GAZETTEER, threshold=0.0, top_k=10)
        ids = [c.pleiades_id for c in proposal.candidates]
        assert len(ids) == len(set(ids))

    def test_batch_preserves_order_and_length(self):
        findspots = ["Clusii", "Perusiae", "nonsense-place"]
        proposals = propose_links(findspots, GAZETTEER)
        assert [p.findspot for p in proposals] == findspots


@pytest.mark.parametrize(
    ("findspot", "expected_id"),
    [
        ("Clusium", "413047"),
        ("Clusii", "413047"),
        ("Perusia", "393839"),
        ("Perusiae", "393839"),
        ("Volaterrae", "413375"),
        ("Tarquinii", "413332"),
        ("Tarquinia", "413332"),
    ],
)
def test_known_findspots_resolve(findspot, expected_id):
    [proposal] = propose_links([findspot], GAZETTEER)
    assert proposal.best is not None, f"{findspot} matched nothing"
    assert proposal.best.pleiades_id == expected_id
