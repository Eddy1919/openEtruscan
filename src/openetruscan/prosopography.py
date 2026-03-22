"""
Prosopography module — name intelligence engine for ancient onomastics.

Parses naming formulas, builds kinship networks, enables prosopographical queries.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field

from openetruscan.adapter import LanguageAdapter, load_adapter
from openetruscan.normalizer import normalize


@dataclass
class NameComponent:
    """A parsed component of a naming formula."""

    form: str           # The surface form as it appears
    type: str           # praenomen, patronymic, gentilicium, metronymic, unknown
    gender: str = ""    # male, female, unknown
    base_form: str = "" # Stripped of case endings


@dataclass
class NameFormula:
    """A fully parsed naming formula."""

    raw: str
    canonical: str
    components: list[NameComponent] = field(default_factory=list)
    gender: str = "unknown"

    def praenomen(self) -> str | None:
        for c in self.components:
            if c.type == "praenomen":
                return c.form
        return None

    def gentilicium(self) -> str | None:
        for c in self.components:
            if c.type == "gentilicium":
                return c.form
        return None

    def patronymic(self) -> str | None:
        for c in self.components:
            if c.type == "patronymic":
                return c.form
        return None

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "canonical": self.canonical,
            "gender": self.gender,
            "components": [
                {"form": c.form, "type": c.type, "gender": c.gender, "base_form": c.base_form}
                for c in self.components
            ],
        }


def parse_name(text: str, language: str = "etruscan") -> NameFormula:
    """
    Parse a name string into a structured NameFormula.

    Uses the language adapter's onomastic rules to identify
    praenomina, gentilicia, patronymics, and metronymics.
    """
    adapter = load_adapter(language)
    result = normalize(text, language=language)
    tokens = result.tokens

    if not tokens:
        return NameFormula(raw=text, canonical=result.canonical)

    components: list[NameComponent] = []
    onomastics = adapter.onomastics
    gender = "unknown"

    for i, token in enumerate(tokens):
        component = _classify_token(token, i, onomastics, adapter)
        components.append(component)

        # Infer gender from praenomen if possible
        if component.type == "praenomen" and component.gender != "unknown":
            gender = component.gender

    # If gender still unknown, try from gentilicium endings
    if gender == "unknown":
        for c in components:
            if c.type == "gentilicium":
                gender = _infer_gender_from_ending(c.form, onomastics)
                break

    return NameFormula(
        raw=text,
        canonical=result.canonical,
        components=components,
        gender=gender,
    )


def _classify_token(
    token: str,
    position: int,
    onomastics,
    adapter: LanguageAdapter,
) -> NameComponent:
    """Classify a single name token."""

    # Check if it's a known praenomen
    male_praenomina = onomastics.known_praenomina.get("male", [])
    female_praenomina = onomastics.known_praenomina.get("female", [])

    if token in male_praenomina:
        return NameComponent(form=token, type="praenomen", gender="male", base_form=token)
    if token in female_praenomina:
        return NameComponent(form=token, type="praenomen", gender="female", base_form=token)

    # Check if it's a known gentilicium (or has genitive ending)
    gentilicia = onomastics.known_gentilicia
    gen_markers = []
    for markers in onomastics.genitive_markers.values():
        gen_markers.extend(markers)

    # Check if token base matches a known gentilicium
    for gens in gentilicia:
        if token == gens or token.startswith(gens):
            return NameComponent(form=token, type="gentilicium", gender="unknown", base_form=gens)

    # Check for genitive markers → patronymic/metronymic
    for marker in sorted(gen_markers, key=len, reverse=True):
        clean_marker = marker.lstrip("-")
        if token.endswith(clean_marker) and len(token) > len(clean_marker):
            base = token[: -len(clean_marker)]
            # Check if the base is a known praenomen → patronymic
            if base in male_praenomina:
                return NameComponent(form=token, type="patronymic", gender="male", base_form=base)
            if base in female_praenomina:
                return NameComponent(form=token, type="metronymic", gender="female", base_form=base)
            # If at typical patronymic position (2nd), assume patronymic
            if position == 1:
                return NameComponent(
                    form=token, type="patronymic",
                    gender="unknown", base_form=base,
                )

    # Position-based heuristic
    if position == 0:
        gender = _infer_gender_from_ending(token, onomastics)
        return NameComponent(form=token, type="praenomen", gender=gender, base_form=token)

    # Default: likely gentilicium if after praenomen/patronymic
    return NameComponent(form=token, type="gentilicium", gender="unknown", base_form=token)


def _infer_gender_from_ending(token: str, onomastics) -> str:
    """Infer gender from name endings."""
    female_endings = onomastics.gender_markers.get("female_endings", [])
    female_gent = onomastics.gender_markers.get("female_gentilicium_suffix", [])

    for ending in female_endings + female_gent:
        clean = ending.lstrip("-")
        if token.endswith(clean) and len(token) > len(clean):
            return "female"
    return "unknown"


# =============================================================================
# FAMILY GRAPH
# =============================================================================

@dataclass
class Person:
    """A person in the prosopographical database."""

    id: str
    name_formula: NameFormula
    inscription_ids: list[str] = field(default_factory=list)
    findspots: list[str] = field(default_factory=list)

    @property
    def praenomen(self) -> str | None:
        return self.name_formula.praenomen()

    @property
    def gentilicium(self) -> str | None:
        return self.name_formula.gentilicium()

    @property
    def gender(self) -> str:
        return self.name_formula.gender


@dataclass
class ClanInfo:
    """Information about a clan/gens."""

    name: str
    members: list[Person] = field(default_factory=list)
    findspots: set[str] = field(default_factory=set)

    def member_count(self) -> int:
        return len(self.members)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "member_count": self.member_count(),
            "findspots": sorted(self.findspots),
            "members": [
                {
                    "id": p.id,
                    "name": p.name_formula.canonical,
                    "gender": p.gender,
                    "findspots": p.findspots,
                }
                for p in self.members
            ],
        }


class FamilyGraph:
    """
    Prosopographical graph of named individuals and their relationships.

    Can be built from a Corpus or from raw data.
    """

    def __init__(self) -> None:
        self._persons: dict[str, Person] = {}
        self._clans: dict[str, ClanInfo] = {}

    @classmethod
    def from_corpus(cls, corpus, language: str = "etruscan") -> FamilyGraph:
        """Build a family graph from a Corpus instance."""
        graph = cls()
        results = corpus.search(limit=999999)
        person_id = 0

        for inscription in results:
            if not inscription.canonical.strip():
                continue

            formula = parse_name(inscription.canonical, language=language)
            person = Person(
                id=f"P{person_id:05d}",
                name_formula=formula,
                inscription_ids=[inscription.id],
                findspots=[inscription.findspot] if inscription.findspot else [],
            )
            graph.add_person(person)
            person_id += 1

        return graph

    def add_person(self, person: Person) -> None:
        """Add a person to the graph."""
        self._persons[person.id] = person

        # Index by clan
        gens = person.gentilicium
        if gens:
            if gens not in self._clans:
                self._clans[gens] = ClanInfo(name=gens)
            self._clans[gens].members.append(person)
            self._clans[gens].findspots.update(person.findspots)

    def clan(self, name: str) -> ClanInfo | None:
        """Get clan information by gentilicium name."""
        return self._clans.get(name)

    def clans(self) -> list[ClanInfo]:
        """All clans sorted by member count."""
        return sorted(self._clans.values(), key=lambda c: c.member_count(), reverse=True)

    def persons(self) -> list[Person]:
        """All persons."""
        return list(self._persons.values())

    def search_persons(
        self,
        gens: str | None = None,
        praenomen: str | None = None,
        gender: str | None = None,
    ) -> list[Person]:
        """Search for persons matching criteria."""
        results = list(self._persons.values())
        if gens:
            results = [p for p in results if p.gentilicium and gens in p.gentilicium]
        if praenomen:
            results = [p for p in results if p.praenomen and praenomen in p.praenomen]
        if gender:
            results = [p for p in results if p.gender == gender]
        return results

    def related_clans(self, clan_name: str) -> dict[str, int]:
        """
        Find clans related to the given clan through shared inscriptions/findspots.

        Returns dict of clan_name → co-occurrence count.
        """
        target_clan = self._clans.get(clan_name)
        if not target_clan:
            return {}

        target_findspots = target_clan.findspots
        related: dict[str, int] = {}

        for name, clan in self._clans.items():
            if name == clan_name:
                continue
            overlap = len(target_findspots & clan.findspots)
            if overlap > 0:
                related[name] = overlap

        return dict(sorted(related.items(), key=lambda x: x[1], reverse=True))

    def export(self, fmt: str = "json") -> str:
        """Export the graph in various formats."""
        if fmt == "json":
            return self._to_json()
        elif fmt == "graphml":
            return self._to_graphml()
        elif fmt == "csv":
            return self._to_csv()
        else:
            raise ValueError(f"Unknown format: {fmt}. Use: json, graphml, csv")

    def _to_json(self) -> str:
        data = {
            "persons": [
                {
                    "id": p.id,
                    "name": p.name_formula.canonical,
                    "gender": p.gender,
                    "praenomen": p.praenomen,
                    "gentilicium": p.gentilicium,
                    "inscription_ids": p.inscription_ids,
                    "findspots": p.findspots,
                    "components": [
                        {"form": c.form, "type": c.type, "gender": c.gender}
                        for c in p.name_formula.components
                    ],
                }
                for p in self._persons.values()
            ],
            "clans": [c.to_dict() for c in self.clans()],
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    def _to_graphml(self) -> str:
        """Export as GraphML for Gephi/yEd."""
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<graphml xmlns="http://graphml.graphstruct.org/graphml">',
            '  <key id="label" for="node" attr.name="label" attr.type="string"/>',
            '  <key id="gender" for="node" attr.name="gender" attr.type="string"/>',
            '  <key id="type" for="node" attr.name="type" attr.type="string"/>',
            '  <key id="weight" for="edge" attr.name="weight" attr.type="int"/>',
            '  <graph id="G" edgedefault="undirected">',
        ]

        # Add clan nodes
        for clan in self._clans.values():
            lines.append(f'    <node id="clan_{clan.name}">')
            lines.append(f'      <data key="label">{clan.name}</data>')
            lines.append('      <data key="type">clan</data>')
            lines.append('    </node>')

        # Add person nodes
        for person in self._persons.values():
            lines.append(f'    <node id="{person.id}">')
            lines.append(f'      <data key="label">{person.name_formula.canonical}</data>')
            lines.append(f'      <data key="gender">{person.gender}</data>')
            lines.append('      <data key="type">person</data>')
            lines.append('    </node>')

            # Edge: person → clan
            if person.gentilicium:
                lines.append(f'    <edge source="{person.id}" target="clan_{person.gentilicium}">')
                lines.append('      <data key="weight">1</data>')
                lines.append('    </edge>')

        lines.extend(['  </graph>', '</graphml>'])
        return "\n".join(lines)

    def _to_csv(self) -> str:
        """Export persons as CSV."""
        import io
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "name", "gender", "praenomen", "gentilicium", "findspots"])
        for p in self._persons.values():
            writer.writerow([
                p.id, p.name_formula.canonical, p.gender,
                p.praenomen or "", p.gentilicium or "",
                "; ".join(p.findspots),
            ])
        return buf.getvalue()
