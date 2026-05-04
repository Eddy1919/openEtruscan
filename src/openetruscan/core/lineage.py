"""
Lineage Engine — Bridges epigraphic clan data (Gentes) with archaeogenetic lineages.
"""

import logging
from typing import Any

from openetruscan.core.corpus import Corpus

logger = logging.getLogger("lineage_bridge")

class LineageBridge:
    """
    Engine to identify genetic signatures for Etruscan clans and analyze regional distributions.
    """

    def __init__(self, corpus: Corpus):
        self.corpus = corpus

    def get_clan_lineage_signature(self, clan_name: str, radius_km: float = 10.0) -> dict[str, Any]:
        """
        Identify "Lineage Signatures": Search for consistent Y-haplogroups associated 
        with epigraphic clan names by looking at genetic samples near relevant inscriptions.
        """
        query = """
            WITH clan_inscriptions AS (
                -- Find all inscriptions mentioning the clan
                SELECT i.id, i.geom, i.findspot 
                FROM inscriptions i
                JOIN entities e ON e.inscription_id = i.id
                JOIN relationships r ON r.person_id = e.id
                JOIN clans c ON r.clan_id = c.id
                WHERE c.name ILIKE %s AND i.geom IS NOT NULL
            )
            SELECT 
                g.y_haplogroup, COUNT(*) as c
            FROM genetic_samples g
            JOIN clan_inscriptions ci ON ST_DWithin(g.geom::geography, ci.geom::geography, %s * 1000)
            WHERE g.y_haplogroup IS NOT NULL AND g.y_haplogroup <> ''
            GROUP BY g.y_haplogroup
            ORDER BY c DESC
        """
        
        signature = {"clan": clan_name, "y_haplogroups": {}}
        with self.corpus._conn.cursor() as cur:
            cur.execute(query, (f"%{clan_name}%", radius_km))
            signature["y_haplogroups"] = {row[0]: row[1] for row in cur.fetchall()}
            
        return signature

    def get_regional_distribution(self, lat_threshold: float = 42.8) -> dict[str, Any]:
        """
        Calculate haplogroup frequencies by Etruscan region (Northern vs. Southern).
        """
        query = """
            SELECT 
                CASE WHEN findspot_lat >= %s THEN 'Northern' ELSE 'Southern' END as region,
                y_haplogroup, COUNT(*) as c
            FROM genetic_samples
            WHERE y_haplogroup IS NOT NULL AND y_haplogroup <> ''
            AND findspot_lat IS NOT NULL
            GROUP BY region, y_haplogroup
            ORDER BY region, c DESC
        """
        
        stats = {"Northern": {}, "Southern": {}}
        with self.corpus._conn.cursor() as cur:
            cur.execute(query, (lat_threshold,))
            for row in cur.fetchall():
                stats[row[0]][row[1]] = row[2]
                
        return stats

    def contrast_coastal_vs_inland(self, coastal_buffer_km: float = 20.0) -> dict[str, Any]:
        """
        Contrast genetic diversity in coastal vs. inland cities.
        Note: Requires a 'coastline' reference. For now, we use a simple distance from the Tyrrhenian coast
        or check specific coastal findspots.
        """
        # Heuristic list of major coastal cities
        coastal_sites = ("Tarquinia", "Cerveteri", "Vulci", "Populonia", "Vetulonia", "Gravisca", "Pyrgi")
        
        query = """
            SELECT 
                CASE 
                    WHEN findspot ILIKE ANY(%s) THEN 'Coastal'
                    ELSE 'Inland'
                END as location_type,
                mt_haplogroup, COUNT(*) as c
            FROM genetic_samples
            WHERE mt_haplogroup IS NOT NULL AND mt_haplogroup <> ''
            GROUP BY location_type, mt_haplogroup
            ORDER BY location_type, c DESC
        """
        
        stats = {"Coastal": {}, "Inland": {}}
        # Convert tuple to PostgreSQL array-like list for ILIKE ANY
        patterns = [f"%{s}%" for s in coastal_sites]
        
        with self.corpus._conn.cursor() as cur:
            cur.execute(query, (patterns,))
            for row in cur.fetchall():
                stats[row[0]][row[1]] = row[2]
                
        return stats
