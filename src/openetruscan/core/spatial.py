"""
Spatial Correlation Engine — Links archaeogenetic samples with epigraphic records.
"""

import logging
from dataclasses import dataclass
from typing import Any

from openetruscan.core.corpus import Corpus

logger = logging.getLogger("spatial_correlation")

@dataclass
class CorrelationResult:
    inscription_id: str
    sample_id: str
    distance_km: float
    temporal_diff_years: int
    combined_score: float

class SpatialCorrelationEngine:
    """
    Engine to correlate genetic and epigraphic data based on spatio-temporal proximity.
    """

    def __init__(self, corpus: Corpus):
        self.corpus = corpus

    def find_inscriptions_near_sample(
        self, 
        sample_id: str, 
        radius_km: float = 10.0, 
        temporal_window_years: int = 200
    ) -> list[dict[str, Any]]:
        """
        Find inscriptions within a radius and temporal window of a genetic sample.
        """
        # 1. Get sample details
        # Note: Corpus doesn't have get_genetic_sample_by_id yet, need to add or query manually
        with self.corpus._conn.cursor(cursor_factory=None) as cur:
            cur.execute(
                "SELECT findspot_lat, findspot_lon, date_approx FROM genetic_samples WHERE id = %s",
                (sample_id,)
            )
            row = cur.fetchone()
            if not row or row[0] is None or row[1] is None:
                return []
            
            lat, lon, date = row
            
        # 2. Use existing search_radius but filter by date
        # Radius search in Corpus returns SearchResults
        results = self.corpus.search_radius(lat, lon, radius_km=radius_km)
        
        correlated = []
        for insc in results.inscriptions:
            date_diff = abs((insc.date_approx or 0) - (date or 0))
            if date_diff <= temporal_window_years:
                # Actually search_radius already does ST_Distance, but we don't have it here easily

                
                correlated.append({
                    "inscription_id": insc.id,
                    "distance_km": None, # search_radius doesn't return distance in inscriptions list currently
                    "date_diff": date_diff,
                    "inscription": insc.to_dict()
                })
                
        return correlated

    def correlate_corpus(self, radius_km: float = 5.0) -> list[CorrelationResult]:
        """
        Perform a global correlation between the genetic and epigraphic datasets.
        Returns a list of high-confidence links.
        """
        # This would be a heavy operation in Python, better done in SQL with a Join
        query = """
            SELECT 
                i.id as inscription_id,
                g.id as sample_id,
                ST_Distance(i.geom::geography, g.geom::geography) / 1000.0 AS distance_km,
                ABS(COALESCE(i.date_approx, 0) - COALESCE(g.date_approx, 0)) AS temporal_diff_years
            FROM inscriptions i
            JOIN genetic_samples g ON ST_DWithin(i.geom::geography, g.geom::geography, %s * 1000)
            WHERE i.geom IS NOT NULL AND g.geom IS NOT NULL
            ORDER BY distance_km ASC
        """
        
        correlations = []
        with self.corpus._conn.cursor() as cur:
            cur.execute(query, (radius_km,))
            for row in cur.fetchall():
                # Score = km + (years / 50)
                score = row[2] + (row[3] / 50.0)
                correlations.append(CorrelationResult(
                    inscription_id=row[0],
                    sample_id=row[1],
                    distance_km=row[2],
                    temporal_diff_years=row[3],
                    combined_score=score
                ))
                
    def find_samples_near_inscription(
        self, 
        inscription_id: str, 
        radius_m: float = 500.0
    ) -> list[dict[str, Any]]:
        """
        Geographic Proximity Resolver: find genetic samples within X meters of an inscription.
        """
        query = """
            WITH insc AS (
                SELECT geom FROM inscriptions WHERE id = %s AND geom IS NOT NULL
            )
            SELECT 
                g.id, g.findspot, g.y_haplogroup, g.mt_haplogroup, g.tomb_id,
                ST_Distance(g.geom::geography, insc.geom::geography) AS distance_m
            FROM genetic_samples g, insc
            WHERE g.geom IS NOT NULL
            AND ST_DWithin(g.geom::geography, insc.geom::geography, %s)
            ORDER BY distance_m ASC
        """
        samples = []
        with self.corpus._conn.cursor(cursor_factory=None) as cur:
            cur.execute(query, (inscription_id, radius_m))
            for row in cur.fetchall():
                samples.append({
                    "id": row[0],
                    "findspot": row[1],
                    "y_haplo": row[2],
                    "mt_haplo": row[3],
                    "tomb_id": row[4],
                    "distance_m": row[5]
                })
        return samples

    def get_context_cluster(self, tomb_id: str) -> list[dict[str, Any]]:
        """
        Cluster Analysis: Group samples by specific archaeological context (e.g., a chamber tomb).
        """
        query = """
            SELECT id, findspot, y_haplogroup, mt_haplogroup, biological_sex, ancestry_components
            FROM genetic_samples
            WHERE tomb_id = %s OR context_detail ILIKE %s
            ORDER BY id ASC
        """
        cluster = []
        with self.corpus._conn.cursor() as cur:
            cur.execute(query, (tomb_id, f"%{tomb_id}%"))
            for row in cur.fetchall():
                cluster.append({
                    "id": row[0],
                    "findspot": row[1],
                    "y_haplo": row[2],
                    "mt_haplo": row[3],
                    "sex": row[4],
                    "ancestry": row[5]
                })
        return cluster

    def get_site_biological_profile(self, site_name: str) -> dict[str, Any]:
        """
        Biological Site Profiles: Generate predominant haplogroup statistics per site.
        """
        query_y = """
            SELECT y_haplogroup, COUNT(*) as c
            FROM genetic_samples
            WHERE findspot ILIKE %s AND y_haplogroup IS NOT NULL AND y_haplogroup <> ''
            GROUP BY y_haplogroup ORDER BY c DESC
        """
        query_mt = """
            SELECT mt_haplogroup, COUNT(*) as c
            FROM genetic_samples
            WHERE findspot ILIKE %s AND mt_haplogroup IS NOT NULL AND mt_haplogroup <> ''
            GROUP BY mt_haplogroup ORDER BY c DESC
        """
        
        profile = {"site": site_name, "y_haplogroups": {}, "mt_haplogroups": {}}
        with self.corpus._conn.cursor() as cur:
            # Y-Haplogroups
            cur.execute(query_y, (f"%{site_name}%",))
            profile["y_haplogroups"] = {row[0]: row[1] for row in cur.fetchall()}
            
            # mt-Haplogroups
            cur.execute(query_mt, (f"%{site_name}%",))
            profile["mt_haplogroups"] = {row[0]: row[1] for row in cur.fetchall()}
            
        return profile
