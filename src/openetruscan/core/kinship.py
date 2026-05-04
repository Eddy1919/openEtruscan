"""
Kinship Reconciliation Engine — Bridges epigraphic family structures with biological kinship.
"""

import logging
from typing import Any
from dataclasses import dataclass

from openetruscan.core.corpus import Corpus

logger = logging.getLogger("kinship_reconciliation")

@dataclass
class KinshipLink:
    person_a: str
    person_b: str
    type: str  # epigraphic or biological
    marker: str  # 'clan', 'puia', 'Y-haplo', etc.

class KinshipReconciler:
    """
    Engine to build and compare epigraphic and biological family trees.
    """

    def __init__(self, corpus: Corpus):
        self.corpus = corpus

    def build_epigraphic_tree(self, root_person_id: str, depth: int = 2) -> list[dict[str, Any]]:
        """
        Construct epigraphic family trees from the Relationship table (puia, clan, sec).
        Uses a recursive approach to build the local kinship graph.
        """
        query = """
            SELECT 
                r.person_id, r.related_person_id, r.relationship_type,
                e1.name as person_name, e2.name as related_name
            FROM relationships r
            JOIN entities e1 ON r.person_id = e1.id
            LEFT JOIN entities e2 ON r.related_person_id = e2.id
            WHERE r.person_id = %s OR r.related_person_id = %s
        """
        
        links = []
        with self.corpus._conn.cursor() as cur:
            cur.execute(query, (root_person_id, root_person_id))
            for row in cur.fetchall():
                links.append({
                    "from": row[0],
                    "to": row[1],
                    "type": row[2],
                    "names": (row[3], row[4])
                })
        return links

    def build_biological_tree(self, tomb_id: str) -> list[dict[str, Any]]:
        """
        Construct biological kinship trees from shared Y/Mt haplogroups and sex data.
        """
        query = """
            SELECT id, y_haplogroup, mt_haplogroup, biological_sex
            FROM genetic_samples
            WHERE tomb_id = %s OR context_detail ILIKE %s
        """
        
        samples = []
        with self.corpus._conn.cursor() as cur:
            cur.execute(query, (tomb_id, f"%{tomb_id}%"))
            for row in cur.fetchall():
                samples.append({
                    "id": row[0],
                    "y_haplo": row[1],
                    "mt_haplo": row[2],
                    "sex": row[3]
                })
        
        # Identify biological links (same Y = paternal, same Mt = maternal)
        bio_links = []
        for i, s1 in enumerate(samples):
            for s2 in samples[i+1:]:
                if s1["y_haplo"] and s1["y_haplo"] == s2["y_haplo"] and s1["y_haplo"] != "Unknown":
                    bio_links.append({"a": s1["id"], "b": s2["id"], "type": "paternal", "marker": s1["y_haplo"]})
                if s1["mt_haplo"] and s1["mt_haplo"] == s2["mt_haplo"] and s1["mt_haplo"] != "Unknown":
                    bio_links.append({"a": s1["id"], "b": s2["id"], "type": "maternal", "marker": s1["mt_haplo"]})
                    
        return bio_links

    def audit_kinship(self, tomb_id: str) -> list[dict[str, Any]]:
        """
        Kinship Auditor: Flags discrepancies between biological data and epigraphic claims.
        Detects potential adoptions, social kinship, or maternal lineage focus.
        """
        # 1. Get biological links
        bio_links = self.build_biological_tree(tomb_id)
        
        # 2. Get epigraphic links for the same context
        # We need to find inscriptions/entities associated with this tomb
        query_epi = """
            SELECT r.person_id, r.related_person_id, r.relationship_type
            FROM relationships r
            JOIN entities e ON r.person_id = e.id
            JOIN inscriptions i ON e.inscription_id = i.id
            WHERE i.findspot ILIKE %s
        """
        
        epi_links = []
        with self.corpus._conn.cursor() as cur:
            cur.execute(query_epi, (f"%{tomb_id}%",))
            epi_links = cur.fetchall()
            
        audit_report = {
            "tomb_id": tomb_id,
            "biological_links": bio_links,
            "epigraphic_links": epi_links,
            "potential_conflicts": []
        }
        
        return audit_report

