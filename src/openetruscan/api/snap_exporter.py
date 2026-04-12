"""
SNAP Exporter — Standards for Networking Ancient Prosopographies.

Exports the OpenEtruscan prosopography graph as SNAP-compatible Linked Data.
Maps Etruscan relationships (puia, sec, clan) to canonical SNAP ontologies.
"""

import json
from datetime import datetime

OPENETRUSCAN_BASE = "https://openetruscan.com"
SNAP_ONTO = "http://data.snapdrgn.net/ontology/snap#"
BOND_ONTO = "http://openetruscan.com/ontology/bonds#"

# Mapping Etruscan relationships to SNAP/BOND ontologies
REL_MAPPING = {
    "puia": f"{BOND_ONTO}wifeOf",
    "sec": f"{SNAP_ONTO}childOf",
    "clan": f"{SNAP_ONTO}childOf",
    "ati": f"{SNAP_ONTO}childOf",
    "apa": f"{SNAP_ONTO}childOf",
}

def person_to_snap_jsonld(person) -> dict:
    """
    Convert a Person entity to a SNAP-compatible JSON-LD structure.
    """
    snap_id = f"{OPENETRUSCAN_BASE}/entities/{person.id}"
    
    data = {
        "@context": [
            "http://www.w3.org/ns/anno.jsonld",
            {
                "snap": SNAP_ONTO,
                "bond": BOND_ONTO,
                "dcterms": "http://purl.org/dc/terms/",
            }
        ],
        "@id": snap_id,
        "@type": "snap:Person",
        "snap:praenomen": person.praenomen,
        "snap:gentilicium": person.gentilicium,
        "snap:gender": person.gender,
        "dcterms:source": [
            f"{OPENETRUSCAN_BASE}/inscriptions/{ins_id}" 
            for ins_id in person.inscription_ids
        ],
        "snap:hasBond": []
    }
    
    # Map relationships (if person object has relations)
    if hasattr(person, 'relationships'):
        for rel in person.relationships:
            predicate = REL_MAPPING.get(rel.type, f"{SNAP_ONTO}associatedWith")
            data["snap:hasBond"].append({
                "@type": "snap:Bond",
                "snap:hasPredicate": predicate,
                "snap:hasTarget": f"{OPENETRUSCAN_BASE}/entities/{rel.target_id}"
            })
            
    return data

def export_full_snap_collection(persons) -> str:
    """
    Export the entire prosopography graph as a SNAP collection.
    """
    items = [person_to_snap_jsonld(p) for p in persons]
    
    collection = {
        "@context": "https://purl.org/snap/context.jsonld",
        "id": f"{OPENETRUSCAN_BASE}/snap.jsonld",
        "type": "Collection",
        "label": "OpenEtruscan SNAP Prosopography",
        "dcterms:issued": datetime.now().isoformat(),
        "items": items
    }
    
    return json.dumps(collection, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    # Example logic for standalone execution
    print("✅ SNAP Exporter initialized for Gold Standard LOD.")
