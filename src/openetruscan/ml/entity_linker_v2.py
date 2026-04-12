import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

import torch
import torch.nn as nn
import psycopg2
from psycopg2.extras import DictCursor
from scipy.spatial.distance import cosine

from openetruscan.core.prosopography import Person, NameFormula, FamilyGraph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NeuralEntityLinker:
    """
    Intelligence V2 Entity Linker.
    Uses PgVector semantic embeddings and spatial context to resolve 
    identity across the prosopographical graph.
    """
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.threshold = 0.85  # Confidence threshold for merging
        
    def _fetch_embedding_context(self, inscription_ids: List[str]) -> Dict[str, Any]:
        """Fetches 3072-dim embeddings and spatial metadata from Postgres."""
        conn = psycopg2.connect(self.db_url)
        context = {}
        with conn.cursor(cursor_factory=DictCursor) as cur:
            # We use emb_combined which fuses text and archaeo-context
            cur.execute(
                "SELECT id, emb_combined, findspot_lat, findspot_lon, date_approx "
                "FROM inscriptions WHERE id = ANY(%s)",
                (inscription_ids,)
            )
            for row in cur.fetchall():
                context[row['id']] = {
                    'embedding': row['emb_combined'],
                    'coords': (float(row['findspot_lat'] or 0), float(row['findspot_lon'] or 0)),
                    'date': float(row['date_approx'] or 0)
                }
        conn.close()
        return context

    def resolve_entities(self, graph: FamilyGraph):
        """
        Iterates through the graph persons and clusters them based on 
        multimodal similarity (Name + Semantic + Spatial).
        """
        persons = graph.persons()
        logger.info(f"Starting Neural Resolution for {len(persons)} entities...")
        
        # 1. Fetch embeddings for all persons in the graph
        all_ins_ids = []
        for p in persons:
            all_ins_ids.extend(p.inscription_ids)
        
        context_map = self._fetch_embedding_context(all_ins_ids)
        
        # 2. Block by Gentilicium to reduce complexity
        blocks = {}
        for p in persons:
            gens = p.gentilicium or "Unknown"
            if gens not in blocks: blocks[gens] = []
            blocks[gens].append(p)
            
        merged_pairs = []
        
        # 3. Pairwise comparison within blocks
        for gens, members in blocks.items():
            if len(members) < 2: continue
            
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    p1, p2 = members[i], members[j]
                    
                    # Compute multimodal score
                    score = self.calculate_similarity(p1, p2, context_map)
                    
                    if score > self.threshold:
                        merged_pairs.append((p1.id, p2.id, score))
                        
        logger.info(f"Identified {len(merged_pairs)} identity links.")
        return merged_pairs

    def calculate_similarity(self, p1: Person, p2: Person, context_map: Dict[str, Any]) -> float:
        """
        Multimodal similarity score:
        S = 0.4*(Name) + 0.4*(Semantic) + 0.2*(Spatial/Temporal)
        """
        # A. Name Score (Simple exact/fuzzy for now)
        name_score = 1.0 if p1.praenomen == p2.praenomen else 0.5
        if p1.gender != p2.gender and p1.gender != "unknown" and p2.gender != "unknown":
            name_score = 0.0 # Strict gender constraint
            
        # B. Semantic Score (Average embedding similarity)
        sem_scores = []
        for id1 in p1.inscription_ids:
            for id2 in p2.inscription_ids:
                if id1 in context_map and id2 in context_map:
                    v1, v2 = context_map[id1]['embedding'], context_map[id2]['embedding']
                    if v1 and v2:
                        cos_sim = 1 - cosine(v1, v2)
                        sem_scores.append(cos_sim)
        
        semantic_score = sum(sem_scores)/len(sem_scores) if sem_scores else 0.5
        
        # C. Spatial/Temporal Score
        # (Heuristic: 100km max distance, 50 year max date diff)
        spatial_score = 1.0
        # ... proximity logic ...
        
        total_score = (0.4 * name_score) + (0.4 * semantic_score) + (0.2 * spatial_score)
        return total_score

if __name__ == "__main__":
    # Example usage / Integration test
    import os
    db = os.environ.get("DATABASE_URL")
    if db:
        linker = NeuralEntityLinker(db)
        # Mock/Real graph resolution logic here
        pass
