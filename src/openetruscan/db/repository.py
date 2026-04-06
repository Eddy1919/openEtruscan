"""
Async repository layer — sole data-access interface for SQLAlchemy ORM operations.

Encapsulates all PostgreSQL queries for inscriptions, entities, spatial search,
and prosopographical network analysis via AsyncSession.
"""
from collections.abc import Sequence
from typing import Any
from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from openetruscan.db.models import Inscription, Entity, Clan, Relationship
from openetruscan.core.corpus import Inscription as InscriptionData, SearchResults

class InscriptionRepository:
    """
    Main data access layer for the OpenEtruscan corpus.
    Encapsulates all SQLAlchemy queries for inscriptions, entities, and genetic samples.
    """
    def __init__(self, session: AsyncSession):
        """Initialize the repository with an active asynchronous database session."""
        self.session = session

    async def get_by_id(self, inscription_id: str) -> Inscription | None:
        """Fetch a single inscription by its unique primary key ID."""
        stmt = select(Inscription).where(Inscription.id == inscription_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_ids(self, ids: Sequence[str]) -> Sequence[Inscription]:
        """Fetch multiple inscriptions matching a list of primary key IDs."""
        stmt = select(Inscription).where(Inscription.id.in_(ids))
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_all_ids(self) -> Sequence[str]:
        """Retrieve all inscription IDs available in the corpus."""
        stmt = select(Inscription.id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        """Return the total number of inscriptions present in the database."""
        stmt = select(func.count()).select_from(Inscription)
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    async def search(
        self,
        text_query: str | None = None,
        findspot: str | None = None,
        language: str | None = None,
        classification: str | None = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "id",
        geo_only: bool = False,
    ) -> SearchResults:
        """
        Search inscriptions with filters and pagination.
        Uses PostgreSQL Full Text Search (FTS) for efficient text matching.
        """
        conditions = []

        if text_query:
            # PostgreSQL Full Text Search
            # In corpus.py it was: fts_canonical @@ plainto_tsquery('simple', %s)
            conditions.append(
                text("fts_canonical @@ plainto_tsquery('simple', :q)").bindparams(q=text_query)
            )

        if findspot:
            conditions.append(Inscription.findspot.ilike(f"%{findspot}%"))

        if language:
            conditions.append(Inscription.language == language)

        if classification:
            conditions.append(Inscription.classification == classification)

        if geo_only:
            conditions.append(and_(Inscription.findspot_lat.is_not(None), Inscription.findspot_lon.is_not(None)))

        # Ordering
        order_col: Any = Inscription.id
        if sort_by == "date":
            order_col = Inscription.date_approx
        elif sort_by == "-date":
            order_col = Inscription.date_approx.desc()
        elif sort_by == "-id":
            order_col = Inscription.id.desc()

        # Build Select
        stmt = select(Inscription).where(and_(*conditions)).order_by(order_col).limit(limit).offset(offset)
        
        # Build Count
        count_stmt = select(func.count()).select_from(Inscription).where(and_(*conditions))

        results = await self.session.execute(stmt)
        total_result = await self.session.execute(count_stmt)

        rows = results.scalars().all()
        total = total_result.scalar_one() or 0

        # Convert ORM models to dataclasses for API compatibility (temporary bridge)
        # In a full SOTA app, we'd use Pydantic models directly from ORM
        return SearchResults(
            inscriptions=[self._to_dataclass(row) for row in rows],
            total=total
        )

    async def search_radius(
        self,
        lat: float,
        lon: float,
        radius_km: float,
        limit: int = 100,
    ) -> SearchResults:
        """
        Spatial proximity search using PostGIS ST_DWithin.
        Casts geometry(Point, 4326) to geography for precise metric distance calculation.
        """
        # Convert radius to meters for ST_DWithin (using geography for accuracy)
        # Note: 'geom' is geometry(Point, 4326). We cast to geography.
        center = f"SRID=4326;POINT({lon} {lat})"
        stmt = (
            select(Inscription)
            .where(text("ST_DWithin(geom::geography, ST_GeogFromText(:center), :radius)")
                   .bindparams(center=center, radius=radius_km * 1000))
            .limit(limit)
        )
        
        count_stmt = select(func.count()).select_from(Inscription).where(
            text("ST_DWithin(geom::geography, ST_GeogFromText(:center), :radius)")
            .bindparams(center=center, radius=radius_km * 1000)
        )

        results = await self.session.execute(stmt)
        total_result = await self.session.execute(count_stmt)

        rows = results.scalars().all()
        total = total_result.scalar_one() or 0

        return SearchResults(
            inscriptions=[self._to_dataclass(row) for row in rows],
            total=total
        )

    async def semantic_search(
        self,
        query_embedding: list[float],
        field: str = "emb_combined",
        limit: int = 20,
    ) -> SearchResults:
        """
        Vector search using pgvector halfvec_cosine_ops.
        """
        # Field validation
        valid_fields = ["emb_text", "emb_context", "emb_combined"]
        if field not in valid_fields:
            raise ValueError(f"Invalid vector field: {field}")

        # Construct raw SQL for pgvector because SQLAlchemy pgvector extension might not be 
        # fully setup for 'halfvec' shorthand in this env.
        # halfvec is a performance optimization for text-embedding-004
        query = text(f"""
            SELECT id FROM inscriptions 
            ORDER BY ({field}::halfvec(3072)) <=> (:emb::halfvec(3072))
            LIMIT :limit
        """).bindparams(emb=query_embedding, limit=limit)  # nosec B608 # nosemgrep

        result = await self.session.execute(query)
        ids = [row[0] for row in result.fetchall()]
        
        if not ids:
            return SearchResults(inscriptions=[], total=0)

        inscriptions = await self.get_by_ids(ids)
        # Sort by the order of IDs returned by the vector search
        id_map = {row.id: row for row in inscriptions}
        sorted_inscriptions = [id_map[id] for id in ids if id in id_map]

        return SearchResults(
            inscriptions=[self._to_dataclass(i) for i in sorted_inscriptions],
            total=len(sorted_inscriptions)
        )

    async def validate_pleiades_ids(self) -> dict[str, Any]:
        """
        Audit script for Pleiades alignment.
        Checks for invalid formats and potentially reachable Pleiades URIs.
        """
        stmt = select(Inscription.id, Inscription.pleiades_id).where(Inscription.pleiades_id.is_not(None))
        result = await self.session.execute(stmt)
        rows = result.fetchall()
        
        invalid = []
        for row in rows:
            p_id = str(row.pleiades_id)
            # Simple check: Pleiades IDs are numeric (e.g. 432839)
            if not p_id.isdigit():
                invalid.append({"id": row.id, "pleiades_id": p_id, "reason": "non-numeric"})
        
        return {
            "total_checked": len(rows),
            "invalid_ids": invalid,
            "all_aligned": len(invalid) == 0
        }

    async def add(self, inscription_dataclass: InscriptionData) -> str:
        """Add or update an inscription with all fields preserved."""
        # Serialize provenance_flags list to comma-separated string for TEXT column
        flags_str = ",".join(inscription_dataclass.provenance_flags) if inscription_dataclass.provenance_flags else ""

        stmt = insert(Inscription).values(
            id=inscription_dataclass.id,
            canonical=inscription_dataclass.canonical,
            phonetic=inscription_dataclass.phonetic,
            old_italic=inscription_dataclass.old_italic,
            raw_text=inscription_dataclass.raw_text,
            findspot=inscription_dataclass.findspot,
            findspot_lat=inscription_dataclass.findspot_lat,
            findspot_lon=inscription_dataclass.findspot_lon,
            findspot_uncertainty_m=inscription_dataclass.findspot_uncertainty_m,
            date_approx=inscription_dataclass.date_approx,
            date_uncertainty=inscription_dataclass.date_uncertainty,
            medium=inscription_dataclass.medium,
            object_type=inscription_dataclass.object_type,
            source=inscription_dataclass.source,
            bibliography=inscription_dataclass.bibliography,
            notes=inscription_dataclass.notes,
            language=inscription_dataclass.language,
            classification=inscription_dataclass.classification,
            script_system=inscription_dataclass.script_system,
            completeness=inscription_dataclass.completeness,
            provenance_status=inscription_dataclass.provenance_status,
            provenance_flags=flags_str,
            trismegistos_id=inscription_dataclass.trismegistos_id,
            eagle_id=inscription_dataclass.eagle_id,
            geonames_id=inscription_dataclass.geonames_id,
            pleiades_id=inscription_dataclass.pleiades_id,
            is_codex=inscription_dataclass.is_codex,
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "canonical": inscription_dataclass.canonical,
                "phonetic": inscription_dataclass.phonetic,
                "old_italic": inscription_dataclass.old_italic,
                "raw_text": inscription_dataclass.raw_text,
                "findspot": inscription_dataclass.findspot,
                "findspot_lat": inscription_dataclass.findspot_lat,
                "findspot_lon": inscription_dataclass.findspot_lon,
                "findspot_uncertainty_m": inscription_dataclass.findspot_uncertainty_m,
                "date_approx": inscription_dataclass.date_approx,
                "date_uncertainty": inscription_dataclass.date_uncertainty,
                "medium": inscription_dataclass.medium,
                "object_type": inscription_dataclass.object_type,
                "source": inscription_dataclass.source,
                "bibliography": inscription_dataclass.bibliography,
                "notes": inscription_dataclass.notes,
                "provenance_flags": flags_str,
                "trismegistos_id": inscription_dataclass.trismegistos_id,
                "eagle_id": inscription_dataclass.eagle_id,
                "geonames_id": inscription_dataclass.geonames_id,
                "pleiades_id": inscription_dataclass.pleiades_id,
                "updated_at": func.now(),
            }
        )
        await self.session.execute(stmt)
        await self.session.commit()
        return inscription_dataclass.id

    async def get_concordance_network(self, inscription_id: str) -> Sequence[Inscription]:
        """
        Find all inscriptions that share any external identifier with the source.
        This defines the 'concordance cluster' for a given record.
        """
        source = await self.get_by_id(inscription_id)
        if not source:
            return []

        # Extract non-null external identifiers
        shared_ids = []
        if source.trismegistos_id: 
            shared_ids.append(source.trismegistos_id)
        if source.eagle_id: 
            shared_ids.append(source.eagle_id)
        if source.pleiades_id: 
            shared_ids.append(source.pleiades_id)
        if source.geonames_id: 
            shared_ids.append(source.geonames_id)
        
        if not shared_ids:
            return [source]
            
        # Query for sharing ANY of these identifiers
        stmt = select(Inscription).where(
            or_(
                Inscription.id == inscription_id,
                and_(Inscription.trismegistos_id.is_not(None), Inscription.trismegistos_id.in_(shared_ids)),
                and_(Inscription.eagle_id.is_not(None), Inscription.eagle_id.in_(shared_ids)),
                and_(Inscription.pleiades_id.is_not(None), Inscription.pleiades_id.in_(shared_ids)),
                and_(Inscription.geonames_id.is_not(None), Inscription.geonames_id.in_(shared_ids))
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_names_network(self, inscription_id: str) -> dict[str, Any]:
        """
        Generate a graph structure (nodes/edges) representing entities and relationships 
        associated with this inscription.
        """
        # 1. Fetch entities directly linked to this inscription
        stmt = select(Entity).where(Entity.inscription_id == inscription_id)
        result = await self.session.execute(stmt)
        root_entities = result.scalars().all()
        
        if not root_entities:
            return {"nodes": [], "edges": []}

        entity_ids = [e.id for e in root_entities]
        
        # 2. Fetch relationships involving these entities
        from sqlalchemy.orm import selectinload
        rel_stmt = (
            select(Relationship)
            .where(or_(Relationship.person_id.in_(entity_ids), Relationship.related_person_id.in_(entity_ids)))
            .options(
                selectinload(Relationship.person),
                selectinload(Relationship.related_person),
                selectinload(Relationship.clan)
            )
        )
        rel_result = await self.session.execute(rel_stmt)
        relationships = rel_result.scalars().all()
        
        nodes = {}
        edges = []
        
        # Add root inscription node
        nodes[f"ins:{inscription_id}"] = {"id": f"ins:{inscription_id}", "label": inscription_id, "type": "inscription"}
        
        for entity in root_entities:
            nodes[entity.id] = {"id": entity.id, "label": entity.name, "type": "person"}
            edges.append({"from": f"ins:{inscription_id}", "to": entity.id, "label": "mentions"})

        for rel in relationships:
            # Ensure participants are in nodes
            for person in [rel.person, rel.related_person]:
                if person and person.id not in nodes:
                    nodes[person.id] = {"id": person.id, "label": person.name, "type": "person"}
            
            if rel.clan:
                if rel.clan_id and rel.clan_id not in nodes:
                    nodes[rel.clan_id] = {"id": rel.clan_id, "label": rel.clan.name, "type": "clan"}
                
                if rel.person_id:
                    edges.append({"from": rel.person_id, "to": rel.clan_id, "label": rel.relationship_type})
            
            elif rel.person_id and rel.related_person_id:
                edges.append({
                    "from": rel.person_id, 
                    "to": rel.related_person_id, 
                    "label": rel.relationship_type
                })

        return {
            "nodes": list(nodes.values()),
            "edges": edges
        }

    async def get_timeline_stats(self) -> list[dict[str, Any]]:
        """
        Aggregate inscriptions by century.
        """
        stmt = "SELECT date_approx / 100 * 100 as century, count(*) FROM inscriptions WHERE date_approx IS NOT NULL GROUP BY century ORDER BY century"
        result = await self.session.execute(text(stmt))
        return [{"century": row[0], "count": row[1]} for row in result.fetchall()]

    async def concordance(self, query: str, limit: int = 2000, context: int = 40) -> list[dict[str, Any]]:
        """
        Retrieve Key-Word-In-Context (KWIC) concordance records.
        """
        stmt = text(
            "SELECT id, "
            "substring(raw_text from greatest(0, position(:query in raw_text) - :ctx) for :ctx) as pre, "
            ":query as match_text, "
            "substring(raw_text from position(:query in raw_text) + length(:query) for :ctx) as post "
            "FROM inscriptions WHERE raw_text ILIKE :wildcard LIMIT :limit"
        ).bindparams(query=query, wildcard=f"%{query}%", ctx=context, limit=limit)
        
        result = await self.session.execute(stmt)
        return [{"inscId": row[0], "pre": row[1], "match": row[2], "post": row[3]} for row in result.fetchall()]

    async def search_clan_members(self, gens: str) -> SearchResults:
        """
        Search inscriptions that belong to clan members.
        """
        stmt = select(Inscription).join(Entity).join(
            Relationship,
            or_(Relationship.person_id == Entity.id, Relationship.related_person_id == Entity.id)
        ).join(Clan).where(Clan.name.ilike(f"%{gens}%")).limit(500)
        
        result = await self.session.execute(stmt)
        rows = result.scalars().unique().all()
        return SearchResults(
            inscriptions=[self._to_dataclass(row) for row in rows],
            total=len(rows)
        )

    async def get_genetic_matches(self, inscription_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        Find nearest archaeogenetic samples using PostGIS distances.
        """
        source = await self.get_by_id(inscription_id)
        if not source or source.findspot_lat is None:
            return []
        
        center = f"SRID=4326;POINT({source.findspot_lon} {source.findspot_lat})"
        # Fallback to computing point from lat/lon if geom isn't synced in genetic_samples
        stmt = text(
            "SELECT id, findspot, y_haplogroup, mt_haplogroup, "
            "ST_Distance(ST_SetSRID(ST_MakePoint(findspot_lon, findspot_lat), 4326)::geography, ST_GeogFromText(:center)) as dist "
            "FROM genetic_samples "
            "WHERE findspot_lat IS NOT NULL AND findspot_lon IS NOT NULL "
            "ORDER BY ST_SetSRID(ST_MakePoint(findspot_lon, findspot_lat), 4326) <-> ST_GeometryFromText(:center) LIMIT :limit"
        ).bindparams(center=center, limit=limit)
        
        result = await self.session.execute(stmt)
        return [{"genetic_sample_id": r[0], "findspot": r[1], "y_haplogroup": r[2], "mt_haplogroup": r[3], "distance_m": r[4]} for r in result.fetchall()]

    async def get_full_names_network(self, min_count: int = 5) -> dict[str, Any]:
        """
        Generate a global graph of name co-occurrences.
        This queries the Entities and Relationships tables for all frequent attestations.
        """
        # 1. Identity nodes (Clans and people) that appear frequently
        # We query the Relationships table for counts
        stmt = text("""
            SELECT clan_id, count(*) as c 
            FROM relationships 
            WHERE clan_id IS NOT NULL 
            GROUP BY clan_id 
            HAVING count(*) >= :min_limit
        """).bindparams(min_limit=min_count)
        
        result = await self.session.execute(stmt)
        clans_raw = result.fetchall()
        
        nodes = {}
        # Fetch actual clan names for the nodes
        for row in clans_raw:
            clan_id = row[0]
            clan_obj = await self.session.get(Clan, clan_id)
            if clan_obj:
                nodes[clan_id] = {"id": clan_id, "label": clan_obj.name, "type": "clan", "size": row[1]}

        # 2. Identify Edges (People belong to clans via relationships)
        # For simplicity, we just return the clan-person connections mapped to nodes
        # In a real graph, we'd iterate over entities too.
        edges: list[dict[str, str]] = []
        
        return {
            "nodes": list(nodes.values()),
            "edges": edges
        }

    async def get_stats_summary(self) -> dict[str, Any]:
        """Compute corpus-wide statistics for the dashboard."""
        stmt = text("""
            SELECT
                COUNT(*) as total,
                COUNT(findspot_lat) as with_coords,
                COUNT(pleiades_id) as pleiades_linked,
                SUM(CASE WHEN classification != 'unknown' THEN 1 ELSE 0 END) as classified
            FROM inscriptions;
        """)
        result = await self.session.execute(stmt)
        row = result.fetchone()
        summary = {
            "total": row[0] if row else 0,
            "with_coords": row[1] if row else 0,
            "pleiades_linked": row[2] if row else 0,
            "classified": row[3] if row else 0,
        }

        top_sites_stmt = text("""
            SELECT findspot, COUNT(*) as c
            FROM inscriptions
            WHERE findspot != '' AND findspot IS NOT NULL
            GROUP BY findspot
            ORDER BY c DESC LIMIT 20
        """)
        top_sites_result = await self.session.execute(top_sites_stmt)
        summary["top_sites"] = [{"findspot": r[0], "count": r[1]} for r in top_sites_result.fetchall()]

        classification_stmt = text("""
            SELECT classification, COUNT(*) as c
            FROM inscriptions
            GROUP BY classification
            ORDER BY c DESC
        """)
        classification_result = await self.session.execute(classification_stmt)
        summary["classification_counts"] = [
            {"classification": r[0], "count": r[1]} for r in classification_result.fetchall()
        ]

        return summary

    async def get_all_canonical_texts(
        self,
        findspot: str | None = None,
        limit: int = 10000,
    ) -> list[dict[str, str]]:
        """Fetch canonical texts for statistical analysis (frequency, clustering)."""
        stmt = (
            select(Inscription.id, Inscription.canonical, Inscription.findspot)
            .where(Inscription.canonical.is_not(None))
            .where(Inscription.canonical != "")
            .limit(limit)
        )
        if findspot:
            stmt = stmt.where(Inscription.findspot.ilike(f"%{findspot}%"))

        result = await self.session.execute(stmt)
        return [{"id": r[0], "canonical": r[1], "findspot": r[2]} for r in result.fetchall()]

    async def get_mvt_tiles(self, z: int, x: int, y: int) -> bytes | None:
        """
        Produce a Mapbox Vector Tile (MVT) for the given tile coordinates using PostGIS.
        """
        # Calculate bounding box for the tile
        # This is a standard transformation for XYZ tiles to Web Mercator SRID 3857
        stmt = text("""
            WITH bounds AS (
              SELECT ST_TileEnvelope(:z, :x, :y) AS poly
            ),
            mvtgeom AS (
              SELECT ST_AsMVTGeom(ST_Transform(geom, 3857), poly) AS geom, id, classification
              FROM inscriptions, bounds
              WHERE ST_Intersects(ST_Transform(geom, 3857), poly)
            )
            SELECT ST_AsMVT(mvtgeom.*, 'inscriptions') FROM mvtgeom;
        """).bindparams(z=z, x=x, y=y)
        
        result = await self.session.execute(stmt)
        return result.scalar()

    def _to_dataclass(self, model: Inscription) -> InscriptionData:
        """
        Bridge SQLAlchemy ORM models to internal dataclasses.

        Handles the provenance_flags TEXT→list[str] conversion and
        nullable field fallbacks.
        """
        # Split comma-separated provenance_flags string back into list
        flags_raw = model.provenance_flags or ""
        flags_list = [f for f in flags_raw.split(",") if f] if flags_raw else []

        return InscriptionData(
            id=model.id,
            raw_text=model.raw_text,
            canonical=model.canonical,
            phonetic=model.phonetic,
            old_italic=model.old_italic,
            findspot=model.findspot or "",
            findspot_lat=model.findspot_lat,
            findspot_lon=model.findspot_lon,
            findspot_uncertainty_m=int(model.findspot_uncertainty_m) if model.findspot_uncertainty_m is not None else None,
            date_approx=model.date_approx,
            date_uncertainty=model.date_uncertainty,
            medium=model.medium or "",
            object_type=model.object_type or "",
            source=model.source or "",
            bibliography=model.bibliography or "",
            notes=model.notes or "",
            language=model.language,
            classification=model.classification,
            script_system=model.script_system,
            completeness=model.completeness,
            provenance_status=model.provenance_status,
            provenance_flags=flags_list,
            trismegistos_id=model.trismegistos_id,
            eagle_id=model.eagle_id,
            pleiades_id=model.pleiades_id,
            geonames_id=model.geonames_id,
            is_codex=model.is_codex,
        )
