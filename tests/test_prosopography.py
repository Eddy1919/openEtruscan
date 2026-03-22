"""Tests for the prosopography module."""

import tempfile
from pathlib import Path

from openetruscan.corpus import Corpus, Inscription
from openetruscan.prosopography import FamilyGraph, parse_name


class TestParseName:
    """Test name formula parsing."""

    def test_known_male_praenomen(self):
        result = parse_name("larθ")
        assert result.components[0].type == "praenomen"
        assert result.components[0].gender == "male"

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


class TestFamilyGraph:
    """Test family graph construction and queries."""

    def _build_test_corpus(self):
        db_path = tempfile.mktemp(suffix=".db")
        corpus = Corpus.load(db_path)
        corpus.add(Inscription(id="T1", raw_text="larθ spurinas", findspot="Cerveteri"))
        corpus.add(Inscription(id="T2", raw_text="arnθ spurinas", findspot="Cerveteri"))
        corpus.add(Inscription(id="T3", raw_text="vel lecnes", findspot="Tarquinia"))
        corpus.add(Inscription(id="T4", raw_text="larθ lecnes", findspot="Cerveteri"))
        return corpus, db_path

    def test_build_from_corpus(self):
        corpus, db_path = self._build_test_corpus()
        graph = FamilyGraph.from_corpus(corpus)
        assert len(graph.persons()) == 4
        corpus.close()
        Path(db_path).unlink()

    def test_clan_lookup(self):
        corpus, db_path = self._build_test_corpus()
        graph = FamilyGraph.from_corpus(corpus)
        clan = graph.clan("spurinas")
        assert clan is not None
        assert clan.member_count() == 2
        corpus.close()
        Path(db_path).unlink()

    def test_search_by_gender(self):
        corpus, db_path = self._build_test_corpus()
        graph = FamilyGraph.from_corpus(corpus)
        males = graph.search_persons(gender="male")
        assert len(males) >= 2  # larθ and arnθ are male praenomina
        corpus.close()
        Path(db_path).unlink()

    def test_related_clans(self):
        corpus, db_path = self._build_test_corpus()
        graph = FamilyGraph.from_corpus(corpus)
        related = graph.related_clans("spurinas")
        # "lecnes" clan also appears in Cerveteri → related
        assert "lecnes" in related
        corpus.close()
        Path(db_path).unlink()

    def test_export_json(self):
        corpus, db_path = self._build_test_corpus()
        graph = FamilyGraph.from_corpus(corpus)
        json_out = graph.export("json")
        assert '"persons"' in json_out
        assert '"clans"' in json_out
        corpus.close()
        Path(db_path).unlink()

    def test_export_graphml(self):
        corpus, db_path = self._build_test_corpus()
        graph = FamilyGraph.from_corpus(corpus)
        graphml = graph.export("graphml")
        assert "<graphml" in graphml
        assert "<node" in graphml
        corpus.close()
        Path(db_path).unlink()

    def test_clans_sorted_by_size(self):
        corpus, db_path = self._build_test_corpus()
        graph = FamilyGraph.from_corpus(corpus)
        clans = graph.clans()
        assert len(clans) >= 2
        # Both spurinas and lecnes have 2 members each
        assert clans[0].member_count() >= clans[-1].member_count()
        corpus.close()
        Path(db_path).unlink()
