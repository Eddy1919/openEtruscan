"""Tests for the prosopography module."""

import pytest

from openetruscan.core.corpus import Corpus, Inscription
from openetruscan.core.prosopography import (
    FamilyGraph,
    fuzzy_match,
    levenshtein_distance,
    parse_name,
    phonological_distance,
)


class TestParseName:
    """Test name formula parsing."""

    def test_known_male_praenomen(self):
        result = parse_name("larθ")
        assert result.components[0].type == "praenomen"
        assert result.components[0].gender == "male"
        assert result.components[0].match_method == "exact"
        assert result.components[0].match_confidence == 1.0

    def test_known_female_praenomen(self):
        result = parse_name("ramθa")
        assert result.components[0].type == "praenomen"
        assert result.components[0].gender == "female"

    def test_praenomen_plus_gentilicium(self):
        result = parse_name("Larθ Spurinas")
        assert len(result.components) >= 2
        assert result.components[0].type == "praenomen"

    def test_patronymic_detection(self):
        result = parse_name("Larθal Lecnes")
        # "Larθal" = Larθ + -al (genitive) → patronymic
        # At minimum it should classify components
        assert len(result.components) == 2

    def test_gender_inference(self):
        male = parse_name("larθ spurinas")
        assert male.gender == "male"

        female = parse_name("ramθa matunai")
        assert female.gender == "female"

    def test_empty_input(self):
        result = parse_name("")
        assert result.canonical == ""
        assert result.components == []

    def test_to_dict(self):
        result = parse_name("Larθ Spurinas")
        d = result.to_dict()
        assert "components" in d
        assert "gender" in d
        # New fields in serialized output
        assert "match_confidence" in d["components"][0]
        assert "match_method" in d["components"][0]


class TestFuzzyMatching:
    """Test Levenshtein distance and fuzzy name matching."""

    def test_levenshtein_identical(self):
        assert levenshtein_distance("larθ", "larθ") == 0

    def test_levenshtein_one_deletion(self):
        # "lrθ" vs "larθ" — missing 'a'
        assert levenshtein_distance("lrθ", "larθ") == 1

    def test_levenshtein_one_substitution(self):
        assert levenshtein_distance("larθ", "lirθ") == 1

    def test_levenshtein_two_edits(self):
        assert levenshtein_distance("lθ", "larθ") == 2

    def test_fuzzy_match_finds_close_names(self):
        candidates = ["larθ", "arnθ", "vel", "ramθa"]
        matches = fuzzy_match("lrθ", candidates, max_distance=2)
        # Should find "larθ" at distance 1
        assert len(matches) > 0
        assert matches[0][0] == "larθ"
        assert matches[0][1] == 1

    def test_fuzzy_match_rejects_distant(self):
        candidates = ["larθ", "arnθ"]
        matches = fuzzy_match("xyz", candidates, max_distance=2)
        assert len(matches) == 0

    def test_fuzzy_praenomen_recognition(self):
        # "lrθ" should fuzzy-match to "larθ" (distance 1)
        result = parse_name("lrθ lecne")
        comp = result.components[0]
        assert comp.type == "praenomen"
        assert comp.base_form == "larθ"
        assert comp.match_method == "fuzzy"
        assert comp.match_confidence < 1.0
        assert comp.match_confidence > 0.5

    def test_fuzzy_gentilicium_recognition(self):
        # "spurna" should fuzzy-match to "spurina" (distance 1)
        result = parse_name("larθ spurna")
        # Second component should be fuzzy-matched gentilicium
        comp = result.components[1]
        assert comp.type == "gentilicium"
        assert comp.match_method == "fuzzy"

    def test_positional_fallback_labels(self):
        # Random token that doesn't match anything
        result = parse_name("xyzqw abcdef")
        assert result.components[0].match_method == "positional"
        assert result.components[0].match_confidence == 0.5


class TestPhonologicalDistance:
    """Test IPA-aware phonological edit distance."""

    def test_identical_strings(self):
        assert phonological_distance("larθ", "larθ") == 0.0

    def test_related_substitution_cheaper(self):
        # θ↔t are in related categories (aspirates↔stops) → cost 0.5
        # θ↔m are unrelated → cost 1.0
        cost_theta_t = phonological_distance("θ", "t")
        cost_theta_m = phonological_distance("θ", "m")
        assert cost_theta_t < cost_theta_m
        assert cost_theta_t == 0.5
        assert cost_theta_m == 1.0

    def test_same_category_cheapest(self):
        # s↔ś are in same sibilant category → cost 0.3
        cost_s_s_acute = phonological_distance("s", "ś")
        assert cost_s_s_acute == 0.3

    def test_vowel_swap_cheap(self):
        # a↔e are both vowels → cost 0.3
        cost_a_e = phonological_distance("a", "e")
        assert cost_a_e == 0.3

    def test_unrelated_swap_full_cost(self):
        # l↔θ are unrelated → cost 1.0
        cost_l_theta = phonological_distance("l", "θ")
        assert cost_l_theta == 1.0

    def test_phonological_vs_levenshtein(self):
        # "larθ" vs "lart" — phonological should be cheaper than Levenshtein
        phono = phonological_distance("larθ", "lart")
        lev = levenshtein_distance("larθ", "lart")
        assert phono < lev  # 0.5 < 1

    def test_fuzzy_match_prefers_phonological(self):
        # "lart" should match "larθ" better than "larm" because t↔θ is related
        candidates = ["larθ", "larm"]
        matches = fuzzy_match("lart", candidates)
        # "larθ" should be closer (distance 0.5) than "larm" (distance 1.0)
        assert len(matches) >= 1
        assert matches[0][0] == "larθ"
        assert matches[0][1] < 1.0


@pytest.mark.slow
class TestFamilyGraph:
    """Test family graph construction and queries (slow — parses all DB inscriptions)."""

    def _build_test_corpus(self):
        corpus = Corpus.load()
        # Clean up any leftover test IDs
        test_ids = ("T1", "T2", "T3", "T4", "T_PATRO")
        with corpus._conn.cursor() as cur:
            cur.execute("DELETE FROM inscriptions WHERE id = ANY(%s)", (list(test_ids),))
        corpus._conn.commit()
        corpus.add(Inscription(id="T1", raw_text="larθ spurinas", findspot="Cerveteri"))
        corpus.add(Inscription(id="T2", raw_text="arnθ spurinas", findspot="Cerveteri"))
        corpus.add(Inscription(id="T3", raw_text="vel lecnes", findspot="Tarquinia"))
        corpus.add(Inscription(id="T4", raw_text="larθ lecnes", findspot="Cerveteri"))
        return corpus

    def test_build_from_corpus(self):
        corpus = self._build_test_corpus()
        graph = FamilyGraph.from_corpus(corpus)
        assert len(graph.persons()) >= 4
        corpus.close()

    def test_clan_lookup(self):
        corpus = self._build_test_corpus()
        graph = FamilyGraph.from_corpus(corpus)
        clan = graph.clan("spurinas")
        assert clan is not None
        assert clan.member_count() == 2
        corpus.close()

    def test_search_by_gender(self):
        corpus = self._build_test_corpus()
        graph = FamilyGraph.from_corpus(corpus)
        males = graph.search_persons(gender="male")
        assert len(males) >= 2  # larθ and arnθ are male praenomina
        corpus.close()

    def test_related_clans(self):
        corpus = self._build_test_corpus()
        graph = FamilyGraph.from_corpus(corpus)
        related = graph.related_clans("spurinas")
        # "lecnes" clan also appears in Cerveteri → related
        assert "lecnes" in related
        corpus.close()

    def test_export_json(self):
        corpus = self._build_test_corpus()
        graph = FamilyGraph.from_corpus(corpus)
        json_out = graph.export("json")
        assert '"persons"' in json_out
        assert '"clans"' in json_out
        corpus.close()

    def test_export_graphml(self):
        corpus = self._build_test_corpus()
        graph = FamilyGraph.from_corpus(corpus)
        graphml = graph.export("graphml")
        assert "<graphml" in graphml
        assert "<node" in graphml
        corpus.close()

    def test_export_neo4j(self):
        """Test FamilyGraph Neo4j Cypher script generation."""
        corpus = self._build_test_corpus()

        # We need a complex formula to test Paternity reconstruction
        # Let's add Larθ Spurinas son of Arnθ
        corpus.add(
            Inscription(
                id="T_PATRO",
                raw_text="larθ spurinas arnθal clan",
                findspot="Vulci",
            )
        )

        graph = FamilyGraph.from_corpus(corpus)
        cypher = graph.export("neo4j")

        # Asserting constraints
        assert "CREATE CONSTRAINT clan_unique" in cypher
        assert "CREATE CONSTRAINT person_unique" in cypher

        # Asserting Clan node
        assert "MERGE (c:Clan {name: 'spurinas'})" in cypher

        # Asserting Person node
        assert "MERGE (p:Person {id: 'P00004'})" in cypher
        assert "p.praenomen = 'larθ'" in cypher
        assert "p.gentilicium = 'spurinas'" in cypher

        # Asserting BELONGS_TO relationship is in the query (multiple times probably)
        assert "-[:BELONGS_TO]->(c)" in cypher

        # Asserting Reconstructed Father node and CHILD_OF edge
        assert "MERGE (father:Person {id: 'father_P00004_arnθ'})" in cypher
        assert "father.type = 'Reconstructed_Patronymic'" in cypher
        assert "-[:CHILD_OF]->(father)" in cypher

        corpus.close()

    def test_clans_sorted_by_size(self):
        corpus = self._build_test_corpus()
        graph = FamilyGraph.from_corpus(corpus)
        clans = graph.clans()
        assert len(clans) >= 2
        # Both spurinas and lecnes have 2 members each
        assert clans[0].member_count() >= clans[-1].member_count()
        corpus.close()
