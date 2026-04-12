"""
VoID Generator — Vocabulary of Interlinked Datasets.

Generates the void.ttl file required for official Pelagios Network indexing.
Transforms the OpenEtruscan corpus into a formal Linked Data Set.
"""

from datetime import datetime
from pathlib import Path

OPENETRUSCAN_BASE = "https://openetruscan.com"
CC_BY_4_0 = "http://creativecommons.org/licenses/by/4.0/"

VOID_TEMPLATE = """@prefix : <{base}/#> .
@prefix void: <http://rdfs.org/ns/void#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<{base}/void.ttl> a void:DatasetDescription ;
    dcterms:title "OpenEtruscan VoID Description" ;
    dcterms:creator :OpenEtruscanTeam ;
    foaf:primaryTopic :OpenEtruscanInscriptions .

:OpenEtruscanInscriptions a void:Dataset ;
    dcterms:title "OpenEtruscan Epigraphic Corpus" ;
    dcterms:description "A curated dataset of ~11,000 Etruscan inscriptions with phonological and spatial metadata." ;
    dcterms:publisher :OpenEtruscanTeam ;
    dcterms:license <{license}> ;
    dcterms:issued "{date}"^^xsd:date ;
    void:feature <http://www.w3.org/ns/formats/JSON-LD> ;
    void:dataDump <{base}/pelagios.jsonld> ;
    void:sparqlEndpoint <{base}/sparql> ;
    void:entities {entities_count} ;
    void:triples {triples_estimate} ;
    
    # Vocabulary mappings
    void:vocabulary <http://www.w3.org/ns/anno.jsonld> ;
    void:vocabulary <http://purl.org/dc/terms/> ;

    # Linksets
    void:subset :PleiadesLinks ;
    void:subset :TrismegistosLinks ;
    void:subset :WikidataLinks .

:PleiadesLinks a void:Linkset ;
    void:target :OpenEtruscanInscriptions ;
    void:target <https://pleiades.stoa.org> ;
    void:linkPredicate <http://www.w3.org/ns/oa#hasTarget> ;
    void:objectsTarget <https://pleiades.stoa.org> .

:TrismegistosLinks a void:Linkset ;
    void:target :OpenEtruscanInscriptions ;
    void:target <https://www.trismegistos.org> ;
    void:linkPredicate <http://www.w3.org/ns/oa#hasTarget> ;
    void:objectsTarget <https://www.trismegistos.org> .

:WikidataLinks a void:Linkset ;
    void:target :OpenEtruscanInscriptions ;
    void:target <https://www.wikidata.org> ;
    void:linkPredicate <http://www.w3.org/ns/oa#hasTarget> ;
    void:objectsTarget <https://www.wikidata.org> .

:OpenEtruscanTeam a foaf:Organization ;
    foaf:name "OpenEtruscan Contributors" ;
    foaf:homepage <{base}> .
"""

def generate_void_ttl(
    output_path: str | Path,
    entities_count: int = 11361,
    triples_estimate: int = 34477,
) -> None:
    """
    Generate the void.ttl file for the corpus.
    
    Args:
        output_path: Path to save the .ttl file.
        entities_count: Number of inscriptions in the corpus.
        triples_estimate: Estimated number of RDF triples.
    """
    content = VOID_TEMPLATE.format(
        base=OPENETRUSCAN_BASE,
        license=CC_BY_4_0,
        date=datetime.now().strftime("%Y-%m-%d"),
        entities_count=entities_count,
        triples_estimate=triples_estimate
    )
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    # Standard build location: root of the project for web exposure
    project_root = Path(__file__).parent.parent.parent.parent
    output_file = project_root / "void.ttl"
    generate_void_ttl(output_file)
    print(f"✅ Gold Standard VoID generated at {output_file}")
