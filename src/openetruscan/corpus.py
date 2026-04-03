"""
Corpus module — structured epigraphic dataset with PostgreSQL native query API.
"""

from __future__ import annotations

import csv
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "corpus.db"

# ---------------------------------------------------------------------------
# Classification constants
# ---------------------------------------------------------------------------

CLASSIFICATIONS = (
    "funerary",
    "votive",
    "legal",
    "commercial",
    "boundary",
    "ownership",
    "dedicatory",
    "unknown",
)

SCRIPT_SYSTEMS = ("old_italic", "latin", "greek", "other")
COMPLETENESS_VALUES = ("complete", "fragmentary", "illegible")
PROVENANCE_STATUSES = ("verified", "quarantined", "rejected")

# Geographic bounds for Etruscan cultural area (used by provenance checks)
_ETRUSCAN_LAT_RANGE = (35.0, 48.0)
_ETRUSCAN_LON_RANGE = (5.0, 18.0)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Inscription:
    """A single inscription record."""

    id: str
    raw_text: str
    canonical: str = ""
    phonetic: str = ""
    old_italic: str = ""
    findspot: str = ""
    findspot_lat: float | None = None
    findspot_lon: float | None = None
    findspot_uncertainty_m: int | None = None
    date_approx: int | None = None  # negative = BCE
    date_uncertainty: int | None = None  # +/- years
    medium: str = ""
    object_type: str = ""
    source: str = ""
    bibliography: str = ""
    notes: str = ""
    # Classification fields
    language: str = "etruscan"
    classification: str = "unknown"
    script_system: str = "old_italic"
    completeness: str = "complete"
    provenance_status: str | None = "verified"
    provenance_flags: list[str] = field(default_factory=list)
    trismegistos_id: str | None = None
    eagle_id: str | None = None
    pleiades_id: str | None = None
    geonames_id: str | None = None
    is_codex: bool = False

    def date_display(self) -> str:
        """Human-readable date string."""
        if self.date_approx is None:
            return "undated"
        era = "BCE" if self.date_approx < 0 else "CE"
        year = abs(self.date_approx)
        if self.date_uncertainty:
            return f"{year} ± {self.date_uncertainty} {era}"
        return f"{year} {era}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "raw_text": self.raw_text,
            "canonical": self.canonical,
            "phonetic": self.phonetic,
            "old_italic": self.old_italic,
            "findspot": self.findspot,
            "findspot_lat": self.findspot_lat,
            "findspot_lon": self.findspot_lon,
            "findspot_uncertainty_m": self.findspot_uncertainty_m,
            "date_approx": self.date_approx,
            "date_uncertainty": self.date_uncertainty,
            "medium": self.medium,
            "object_type": self.object_type,
            "source": self.source,
            "bibliography": self.bibliography,
            "notes": self.notes,
            "language": self.language,
            "classification": self.classification,
            "script_system": self.script_system,
            "completeness": self.completeness,
            "provenance_status": self.provenance_status,
            "provenance_flags": self.provenance_flags,
            "trismegistos_id": self.trismegistos_id,
            "eagle_id": self.eagle_id,
            "pleiades_id": self.pleiades_id,
            "geonames_id": self.geonames_id,
            "is_codex": self.is_codex,
        }


@dataclass
class GeneticSample:
    """A single archaeogenetic sample record."""

    id: str
    findspot: str = ""
    findspot_lat: float | None = None
    findspot_lon: float | None = None
    findspot_uncertainty_m: int | None = None
    date_approx: int | None = None
    date_uncertainty: int | None = None
    y_haplogroup: str | None = None
    mt_haplogroup: str | None = None
    source: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "findspot": self.findspot,
            "findspot_lat": self.findspot_lat,
            "findspot_lon": self.findspot_lon,
            "findspot_uncertainty_m": self.findspot_uncertainty_m,
            "date_approx": self.date_approx,
            "date_uncertainty": self.date_uncertainty,
            "y_haplogroup": self.y_haplogroup,
            "mt_haplogroup": self.mt_haplogroup,
            "source": self.source,
            "notes": self.notes,
        }


@dataclass
class SearchResults:
    """Container for corpus search results."""

    inscriptions: list[Inscription] = field(default_factory=list)
    total: int = 0

    def __len__(self) -> int:
        return len(self.inscriptions)

    def __iter__(self) -> Iterator[Inscription]:
        return iter(self.inscriptions)

    def export(self, fmt: str = "csv") -> str:
        """Export results to string in specified format."""
        if fmt == "csv":
            return self._to_csv()
        elif fmt == "json":
            data = [i.to_dict() for i in self.inscriptions]
            return json.dumps(data, ensure_ascii=False, indent=2)
        elif fmt == "jsonl":
            lines = [json.dumps(i.to_dict(), ensure_ascii=False) for i in self.inscriptions]
            return "\n".join(lines)
        elif fmt == "geojson":
            return self._to_geojson()
        else:
            raise ValueError(f"Unknown format: {fmt}. Use: csv, json, jsonl, geojson")

    def _to_csv(self) -> str:
        import io

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "id",
                "canonical",
                "findspot",
                "date",
                "medium",
                "source",
                "language",
                "classification",
            ]
        )
        for i in self.inscriptions:
            writer.writerow(
                [
                    i.id,
                    i.canonical,
                    i.findspot,
                    i.date_display(),
                    i.medium,
                    i.source,
                    i.language,
                    i.classification,
                ]
            )
        return buf.getvalue()

    def _to_geojson(self) -> str:
        features = []
        for i in self.inscriptions:
            if i.findspot_lat is not None and i.findspot_lon is not None:
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [i.findspot_lon, i.findspot_lat],
                        },
                        "properties": {
                            "id": i.id,
                            "text": i.canonical,
                            "findspot": i.findspot,
                            "date": i.date_display(),
                            "language": i.language,
                            "classification": i.classification,
                        },
                    }
                )
        collection = {
            "type": "FeatureCollection",
            "features": features,
        }
        return json.dumps(collection, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Schema SQL
# ---------------------------------------------------------------------------


_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS inscriptions (
    id TEXT PRIMARY KEY,
    canonical TEXT NOT NULL,
    phonetic TEXT NOT NULL,
    old_italic TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    findspot TEXT DEFAULT '',
    findspot_lat DOUBLE PRECISION,
    findspot_lon DOUBLE PRECISION,
    findspot_uncertainty_m DOUBLE PRECISION,
    date_approx INTEGER,
    date_uncertainty INTEGER,
    medium TEXT DEFAULT '',
    object_type TEXT DEFAULT '',
    source TEXT DEFAULT '',
    bibliography TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    language TEXT NOT NULL DEFAULT 'etruscan',
    classification TEXT NOT NULL DEFAULT 'unknown',
    script_system TEXT NOT NULL DEFAULT 'old_italic',
    completeness TEXT NOT NULL DEFAULT 'complete',
    provenance_status TEXT NOT NULL DEFAULT 'verified',
    provenance_flags TEXT NOT NULL DEFAULT '',
    trismegistos_id TEXT,
    eagle_id TEXT,
    pleiades_id TEXT,
    geonames_id TEXT,
    is_codex BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    fts_canonical tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(canonical, ''))
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_canonical ON inscriptions(canonical);
CREATE INDEX IF NOT EXISTS idx_findspot ON inscriptions(findspot);
CREATE INDEX IF NOT EXISTS idx_date ON inscriptions(date_approx);
CREATE INDEX IF NOT EXISTS idx_language ON inscriptions(language);
CREATE INDEX IF NOT EXISTS idx_classification ON inscriptions(classification);
CREATE INDEX IF NOT EXISTS idx_provenance ON inscriptions(provenance_status);
CREATE INDEX IF NOT EXISTS idx_fts_canonical ON inscriptions USING GIN (fts_canonical);

CREATE TABLE IF NOT EXISTS genetic_samples (
    id TEXT PRIMARY KEY,
    findspot TEXT DEFAULT '',
    findspot_lat DOUBLE PRECISION,
    findspot_lon DOUBLE PRECISION,
    findspot_uncertainty_m DOUBLE PRECISION,
    date_approx INTEGER,
    date_uncertainty INTEGER,
    y_haplogroup TEXT,
    mt_haplogroup TEXT,
    source TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_genetic_date ON genetic_samples(date_approx);
"""

_PG_VECTOR_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_emb_text_hnsw
    ON inscriptions USING hnsw (emb_text vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_emb_context_hnsw
    ON inscriptions USING hnsw (emb_context vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_emb_combined_hnsw
    ON inscriptions USING hnsw (emb_combined vector_cosine_ops);
"""

# Columns used for INSERT/SELECT (shared between backends)
_COLUMNS = [
    "id",
    "raw_text",
    "canonical",
    "phonetic",
    "old_italic",
    "findspot",
    "findspot_lat",
    "findspot_lon",
    "findspot_uncertainty_m",
    "date_approx",
    "date_uncertainty",
    "medium",
    "object_type",
    "source",
    "bibliography",
    "notes",
    "language",
    "classification",
    "script_system",
    "completeness",
    "provenance_status",
    "provenance_flags",
    "trismegistos_id",
    "eagle_id",
    "pleiades_id",
    "geonames_id",
    "is_codex",
]


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


_KNOWN_NAMES = {
    "larθ",
    "laris",
    "aule",
    "vel",
    "arnθ",
    "θana",
    "larthi",
    "velia",
    "sethre",
    "marce",
    "avile",
    "lavtni",
    "ramtha",
    "fasti",
    "hasti",
    "tite",
    "caile",
    "larθi",
    "arnth",
    "thana",
    "lart",
    "lars",
    "arnt",
    "arn",
    "arath",
    "araθ",
    "veilia",
    "matunas",
    "velthur",
    "velθur",
    "cainei",
    "cai",
    "clan",
    "puia",
    "sec",
    "ati",
    "papa",
}


def _extract_names(canonical: str) -> list[str]:
    import re as _re

    tokens = _re.split(r"[\s·.,:;]+", canonical.lower())
    found = []
    seen = set()
    for t in tokens:
        if len(t) >= 2 and t in _KNOWN_NAMES and t not in seen:
            found.append(t)
            seen.add(t)
    return found


class Corpus:
    """Queryable corpus natively backed by PostgreSQL."""

    """
    Queryable corpus backed by PostgreSQL (Cloud SQL).

    Abuse protection:
      - Read-only public user (corpus_reader) for queries
      - Write user (corpus_admin) for imports only
    """

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg2  # noqa: F811
        except ImportError as exc:
            raise ImportError(
                "PostgreSQL support requires psycopg2. "
                "Install with: pip install openetruscan[postgres]"
            ) from exc
        self._dsn = dsn
        self._conn = psycopg2.connect(dsn)
        self._conn.autocommit = False

    @classmethod
    def connect(cls, url: str) -> Corpus:
        """Connect to PostgreSQL and ensure schema exists."""
        corpus = cls(url)
        corpus._ensure_db()
        return corpus

    def _prepare_inscription(self, inscription: Inscription, language: str) -> Inscription:
        # DH Normalizer bypass: return as is if normalizer not strictly required here
        return inscription

    def _inscription_values(self, inscription: Inscription):
        return (
            tuple(getattr(inscription, col) for col in _COLUMNS if col != "id") + (inscription.id,)
            if "id" not in _COLUMNS
            else tuple(getattr(inscription, col) for col in _COLUMNS)
        )

    @classmethod
    def load(cls, db_path=None) -> Corpus:
        env_url = os.environ.get("DATABASE_URL", "")
        if not env_url:
            env_path = Path(".env")
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("DATABASE_URL="):
                        env_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        if not env_url:
            raise ValueError("DATABASE_URL environment variable is missing.")
        return cls.connect(env_url)

    def _ensure_db(self) -> None:
        """Create tables if they don't exist (ignored for read-only users)."""
        import psycopg2

        from openetruscan.artifacts import IMAGES_PG_SCHEMA

        import contextlib

        with self._conn.cursor() as cur:
            # 1. Base Schema (always required)
            try:
                cur.execute(_PG_SCHEMA)
                cur.execute(IMAGES_PG_SCHEMA)
                self._conn.commit()
            except psycopg2.Error:
                self._conn.rollback()
                raise  # If base schema fails, the database is broken

            # 2. Spatial types mapping (optional)
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
                cur.execute("ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326);")
                cur.execute("ALTER TABLE genetic_samples ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_inscriptions_geom ON inscriptions USING GIST (geom);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_genetic_geom ON genetic_samples USING GIST (geom);")
                self._conn.commit()
            except psycopg2.Error:
                self._conn.rollback()

            # 3. Vector Embeddings schemas mapping (optional)
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute("ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS emb_text vector(768);")
                cur.execute("ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS emb_context vector(768);")
                cur.execute("ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS emb_combined vector(768);")
                cur.execute(_PG_VECTOR_INDEXES)
                self._conn.commit()
            except psycopg2.Error:
                self._conn.rollback()

            # 4. General Table Migrations schema options
            # Schema migrations for existing tables
            with contextlib.suppress(psycopg2.Error):
                cur.execute(
                    "ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS findspot_uncertainty_m DOUBLE PRECISION;"
                )
                cur.execute(
                    "ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS trismegistos_id TEXT;"
                )
                cur.execute("ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS eagle_id TEXT;")
                cur.execute(
                    "ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS pleiades_id TEXT;"
                )
                cur.execute(
                    "ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS geonames_id TEXT;"
                )
                cur.execute(
                    "ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS is_codex BOOLEAN NOT NULL DEFAULT FALSE;"
                )
                cur.execute(
                    "ALTER TABLE inscriptions ADD COLUMN IF NOT EXISTS fts_canonical "
                    "tsvector GENERATED ALWAYS AS "
                    "(to_tsvector('simple', coalesce(canonical, ''))) STORED;"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_fts_canonical "
                    "ON inscriptions USING GIN (fts_canonical);"
                )
            self._conn.commit()

    def add(
        self,
        inscription: Inscription,
        language: str = "etruscan",
    ) -> None:
        """Add an inscription."""
        inscription = self._prepare_inscription(inscription, language)
        cols = ", ".join(_COLUMNS)
        placeholders = ", ".join(["%s"] * len(_COLUMNS))
        conflict_updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLUMNS if c != "id")

        vals = list(self._inscription_values(inscription))

        if inscription.findspot_lon is not None and inscription.findspot_lat is not None:
            geom_insert = "ST_SetSRID(ST_MakePoint(%s, %s), 4326)"
            vals.extend([inscription.findspot_lon, inscription.findspot_lat])
            insert_cols = f"({cols}, geom)"
            insert_placeholders = f"({placeholders}, {geom_insert})"
        else:
            geom_insert = "NULL"
            insert_cols = f"({cols}, geom)"
            insert_placeholders = f"({placeholders}, {geom_insert})"

        # Dynamic construction is safe (strictly hardcoded internal lists)
        query_parts = [
            "INSERT INTO inscriptions",
            insert_cols,
            "VALUES",
            insert_placeholders,
            "ON CONFLICT (id) DO UPDATE SET",
            conflict_updates + ",",
            "geom = EXCLUDED.geom,",
            "updated_at = NOW()",
        ]
        query = "\n".join(query_parts)

        with self._conn.cursor() as cur:
            cur.execute(query, tuple(vals))
        self._conn.commit()

    def _build_search_query(
        self,
        text=None,
        findspot=None,
        date_range=None,
        medium=None,
        language=None,
        classification=None,
        limit=100,
        provenance_status=None,
        param_style="format",
        offset=0,
        sort_by="id",
        geo_only=False,
    ):
        conditions = []
        params = []

        ph = "%s" if param_style == "format" else "?"

        if text:
            # PostgreSQL FTS Search
            conditions.append(f"fts_canonical @@ plainto_tsquery('simple', {ph})")
            params.append(text)

        if findspot:
            conditions.append(f"findspot ILIKE {ph}")
            params.append(f"%{findspot}%")

        if date_range:
            conditions.append(f"date_approx >= {ph} AND date_approx <= {ph}")
            params.extend(date_range)

        if medium:
            conditions.append(f"medium ILIKE {ph}")
            params.append(f"%{medium}%")

        if language:
            conditions.append(f"language = {ph}")
            params.append(language)

        if classification:
            conditions.append(f"classification = {ph}")
            params.append(classification)

        if provenance_status:
            conditions.append(f"provenance_status = {ph}")
            params.append(provenance_status)

        if geo_only:
            conditions.append("findspot_lat IS NOT NULL AND findspot_lon IS NOT NULL")

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        count_query = f"SELECT COUNT(*) FROM inscriptions WHERE {where_clause}"

        # Valid sort columns mapping
        valid_sorts = {
            "id": "id ASC",
            "-id": "id DESC",
            "date": "date_approx ASC",
            "-date": "date_approx DESC",
        }
        order_by = valid_sorts.get(sort_by, "id ASC")

        query = f"SELECT * FROM inscriptions WHERE {where_clause} ORDER BY {order_by} LIMIT {ph} OFFSET {ph}"
        filter_params = list(params)
        query_params = list(params) + [limit, offset]
        return query, count_query, query_params, filter_params

    def search(
        self,
        text: str | None = None,
        findspot: str | None = None,
        date_range: tuple[int, int] | None = None,
        medium: str | None = None,
        language: str | None = None,
        classification: str | None = None,
        provenance_status: str | None = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "id",
        geo_only: bool = False,
    ) -> SearchResults:
        """Search the corpus."""
        import psycopg2.extras

        query, count_query, query_params, filter_params = self._build_search_query(
            text,
            findspot,
            date_range,
            medium,
            language,
            classification,
            limit,
            provenance_status=provenance_status,
            param_style="format",
            offset=offset,
            sort_by=sort_by,
            geo_only=geo_only,
        )
        with self._conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor,
        ) as cur:
            cur.execute(query, query_params)
            rows = cur.fetchall()
            inscriptions = [_dict_to_inscription(row) for row in rows]
            cur.execute(count_query, filter_params)
            total = cur.fetchone()["count"]
        return SearchResults(inscriptions=inscriptions, total=total)

    def review_quarantine(
        self,
        inscription_id: str,
        action: str = "verify",
    ) -> bool:
        """Review a quarantined inscription. Actions: 'verify', 'reject', 'quarantine'."""
        valid_actions = {"verify": "verified", "reject": "rejected", "quarantine": "quarantined"}
        new_status = valid_actions.get(action, "quarantined")
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE inscriptions SET provenance_status = %s WHERE id = %s",
                (new_status, inscription_id),
            )
            updated = cur.rowcount > 0
        self._conn.commit()
        return updated

    def search_radius(
        self,
        lat: float,
        lon: float,
        radius_km: float = 50.0,
        limit: int = 100,
    ) -> SearchResults:
        """Native PostGIS ST_DWithin search."""
        import psycopg2.extras

        radius_m = radius_km * 1000.0
        query = """
            SELECT *,
                   ST_Distance(
                       ST_Buffer(geom::geography, COALESCE(findspot_uncertainty_m, 0)),
                       ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                   ) as dist
            FROM inscriptions
            WHERE geom IS NOT NULL
            AND ST_DWithin(
                geom::geography,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                %s + COALESCE(findspot_uncertainty_m, 0)
            )
            ORDER BY dist ASC
            LIMIT %s
        """
        count_query = """
            SELECT COUNT(*)
            FROM inscriptions
            WHERE geom IS NOT NULL
            AND ST_DWithin(
                geom::geography,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                %s + COALESCE(findspot_uncertainty_m, 0)
            )
        """
        with self._conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor,
        ) as cur:
            cur.execute(query, (lon, lat, lon, lat, radius_m, limit))
            rows = cur.fetchall()
            inscriptions = [_dict_to_inscription(row) for row in rows]
            cur.execute(count_query, (lon, lat, radius_m))
            total = cur.fetchone()["count"]

        return SearchResults(inscriptions=inscriptions, total=total)

    def mvt_tiles(self, z: int, x: int, y: int) -> bytes:
        """Native PostGIS ST_AsMVT for serving Mapbox Vector Tiles."""
        import psycopg2.extras

        query = """
            WITH bounds AS (
                SELECT ST_TileEnvelope(%s, %s, %s) AS geom
            ),
            mvtgeom AS (
                SELECT ST_AsMVTGeom(ST_Transform(i.geom::geometry, 3857), bounds.geom) AS geom,
                       i.id,
                       i.classification,
                       i.findspot,
                       i.canonical
                FROM inscriptions i, bounds
                WHERE i.geom IS NOT NULL AND ST_Intersects(ST_Transform(i.geom::geometry, 3857), bounds.geom)
            )
            SELECT ST_AsMVT(mvtgeom.*, 'inscriptions') AS tile
            FROM mvtgeom;
        """
        with self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(query, (z, x, y))
            result = cur.fetchone()
            if result and result["tile"]:
                return bytes(result["tile"])
            return b""

    def semantic_search(
        self,
        query_embedding: list[float] | None,
        text_query: str | None = None,
        field: str = "emb_combined",
        limit: int = 20,
    ) -> SearchResults:
        """Find inscriptions using hybrid pgvector dense similarity and DB BM25 sparse logic."""
        import psycopg2.extras
        from psycopg2 import sql

        if field not in ("emb_text", "emb_context", "emb_combined"):
            raise ValueError(f"Invalid embedding field: {field}")

        query_parts = ["SELECT *"]
        from_parts = ["FROM inscriptions"]
        where_parts = []
        order_parts = []
        params = []

        if query_embedding:
            # Semantic search component
            vec_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
            query_parts.append(f", 1 - ({field} <=> %s::vector) AS semantic_sim")
            where_parts.append(f"{field} IS NOT NULL")
            params.append(vec_str)

        if text_query:
            # Sparse keyword component (BM25 logic)
            query_parts.append(
                ", ts_rank_cd(fts_canonical, websearch_to_tsquery('simple', %s)) AS sparse_rank"
            )
            where_parts.append("fts_canonical @@ websearch_to_tsquery('simple', %s)")
            params.extend([text_query, text_query])

        if not where_parts:
            return SearchResults(inscriptions=[], total=0)

        # Reciprocal Rank Fusion or weighted sorting
        if query_embedding and text_query:
            query_parts.append(
                ", (1 - ({field} <=> %s::vector)) * "
                "ts_rank_cd(fts_canonical, websearch_to_tsquery('simple', %s)) AS hybrid_score"
            )
            params.extend([vec_str, text_query])
            order_parts.append("hybrid_score DESC")
        elif query_embedding:
            order_parts.append("semantic_sim DESC")
        else:
            order_parts.append("sparse_rank DESC")

        sql_stmt = (
            sql.SQL(" ")
            .join(
                [
                    sql.SQL(", ".join(query_parts).replace("SELECT *, ,", "SELECT *,")),
                    sql.SQL(" ".join(from_parts)),
                    sql.SQL("WHERE " + " AND ".join(where_parts)),
                    sql.SQL("ORDER BY " + ", ".join(order_parts)),
                    sql.SQL("LIMIT %s"),
                ]
            )
            .format(field=sql.Identifier(field))
        )

        params.append(limit)

        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # nosemgrep
            cur.execute(sql_stmt, params)
            rows = cur.fetchall()
            inscriptions = [_dict_to_inscription(row) for row in rows]

        return SearchResults(inscriptions=inscriptions, total=len(inscriptions))

    def concordance(
        self,
        query: str,
        limit: int = 2000,
        context: int = 40,
    ) -> list[dict]:
        """Perform a highly optimized PostgreSQL FTS KWIC search on the corpus."""
        import psycopg2.extras

        try:
            with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, canonical FROM inscriptions "
                    "WHERE fts_canonical @@ websearch_to_tsquery('simple', %s) LIMIT %s",
                    (query, limit),
                )
                matching_rows = cur.fetchall()
                self._conn.commit()
        except Exception as e:
            self._conn.rollback()
            raise e

        # 2. Extract precise KWIC snippets from the small matching subset
        rows = []
        q_lower = query.lower().strip()
        for row in matching_rows:
            original = row["canonical"]
            text = original.lower()
            start_pos = 0
            while True:
                idx = text.find(q_lower, start_pos)
                if idx == -1:
                    break
                match_end = idx + len(q_lower)

                left_full = original[:idx]
                left = left_full[-context:] if len(left_full) > context else left_full

                right_full = original[match_end:]
                right = right_full[:context] if len(right_full) > context else right_full

                rows.append(
                    {
                        "inscId": row["id"],
                        "left": left,
                        "keyword": original[idx:match_end],
                        "right": right,
                    }
                )
                start_pos = idx + 1
        return rows

    def add_genetic_sample(
        self,
        sample: GeneticSample,
    ) -> None:
        """Add a genetic sample to the Postgres DB with PostGIS."""
        sql = """
            INSERT INTO genetic_samples (
                id, findspot, findspot_lat, findspot_lon,
                date_approx, date_uncertainty, y_haplogroup, mt_haplogroup,
                source, notes, geom
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)
            )
            ON CONFLICT (id) DO UPDATE SET
                findspot = EXCLUDED.findspot,
                findspot_lat = EXCLUDED.findspot_lat,
                findspot_lon = EXCLUDED.findspot_lon,
                date_approx = EXCLUDED.date_approx,
                date_uncertainty = EXCLUDED.date_uncertainty,
                y_haplogroup = EXCLUDED.y_haplogroup,
                mt_haplogroup = EXCLUDED.mt_haplogroup,
                source = EXCLUDED.source,
                notes = EXCLUDED.notes,
                geom = EXCLUDED.geom,
                updated_at = NOW()
        """
        vals = (
            sample.id,
            sample.findspot,
            sample.findspot_lat,
            sample.findspot_lon,
            sample.date_approx,
            sample.date_uncertainty,
            sample.y_haplogroup,
            sample.mt_haplogroup,
            sample.source,
            sample.notes,
            # for MakePoint: lon, lat
            sample.findspot_lon if sample.findspot_lon is not None else 0.0,
            sample.findspot_lat if sample.findspot_lat is not None else 0.0,
        )
        if sample.findspot_lon is None or sample.findspot_lat is None:
            sql = sql.replace("ST_SetSRID(ST_MakePoint(%s, %s), 4326)", "NULL")
            vals = vals[:-2]

        with self._conn.cursor() as cur:
            cur.execute(sql, vals)
        self._conn.commit()

    def find_genetic_matches(
        self,
        inscription_id: str,
        limit: int = 5,
    ) -> list[dict]:
        """Find best genetic matches using spatio-temporal weighting in PostGIS."""
        import psycopg2.extras

        query = """
            WITH insc AS (
                SELECT geom, date_approx
                FROM inscriptions
                WHERE id = %s AND geom IS NOT NULL
            )
            SELECT
                g.*,
                ST_Distance(g.geom::geography, insc.geom::geography) / 1000.0 AS distance_km,
                ABS(COALESCE(g.date_approx, 0) - COALESCE(insc.date_approx, 0)) AS date_diff_years,
                (ST_Distance(g.geom::geography, insc.geom::geography) / 1000.0) +
                (ABS(COALESCE(g.date_approx, 0) - COALESCE(insc.date_approx, 0)) * 0.5)
                AS match_score
            FROM genetic_samples g, insc
            WHERE g.geom IS NOT NULL
            ORDER BY match_score ASC
            LIMIT %s
        """
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, (inscription_id, limit))
            rows = cur.fetchall()

            # PostGIS geometry objects are not JSON serializable, so remove them
            results = []
            for row in rows:
                r = dict(row)
                r.pop("geom", None)
                # Convert datetime types from postgres automatically generated timestamps
                if "created_at" in r and r["created_at"]:
                    r["created_at"] = r["created_at"].isoformat()
                if "updated_at" in r and r["updated_at"]:
                    r["updated_at"] = r["updated_at"].isoformat()
                results.append(r)
            return results

    def count(self) -> int:
        with self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM inscriptions")
            return cur.fetchone()[0]

    def import_csv(
        self,
        csv_path: str | Path,
        language: str = "etruscan",
    ) -> int:
        """Bulk import from CSV."""
        path = Path(csv_path)
        imported = 0
        with path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                text = row.get(
                    "text",
                    row.get("raw_text", ""),
                ).strip()
                if not text:
                    continue
                inscription = Inscription(
                    id=row.get("id", f"import_{imported}"),
                    raw_text=text,
                    findspot=row.get("findspot", ""),
                    findspot_lat=_safe_float(row.get("findspot_lat")),
                    findspot_lon=_safe_float(row.get("findspot_lon")),
                    date_approx=_safe_int(row.get("date_approx")),
                    findspot_uncertainty_m=_safe_int(row.get("findspot_uncertainty_m")),
                    date_uncertainty=_safe_int(row.get("date_uncertainty")),
                    medium=row.get("medium", ""),
                    object_type=row.get("object_type", ""),
                    source=row.get("source", ""),
                    bibliography=row.get("bibliography", ""),
                    notes=row.get("notes", ""),
                    language=row.get("language", language),
                    classification=row.get("classification", "unknown"),
                )
                self.add(inscription, language=language)
                imported += 1
        return imported

    def create_readonly_user(self, password: str) -> None:
        """
        Create a read-only PostgreSQL user for public access.
        Prevents abuse: public users can only SELECT.
        """
        with self._conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'corpus_reader'")
            if not cur.fetchone():
                cur.execute(
                    "CREATE ROLE corpus_reader WITH LOGIN PASSWORD %s",
                    (password,),
                )
            cur.execute("GRANT CONNECT ON DATABASE corpus TO corpus_reader")
            cur.execute("GRANT USAGE ON SCHEMA public TO corpus_reader")
            cur.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO corpus_reader")
            cur.execute(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO corpus_reader"
            )
        self._conn.commit()

    def get_by_ids(self, ids: list[str]) -> SearchResults:
        """Fetch inscriptions by a list of IDs (PostgreSQL)."""
        import psycopg2.extras

        if not ids:
            return SearchResults(inscriptions=[], total=0)
        with self._conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor,
        ) as cur:
            # Use ANY(%s) with a list parameter for safe IN queries
            cur.execute(
                "SELECT * FROM inscriptions WHERE id = ANY(%s)",
                (ids,),
            )
            rows = cur.fetchall()
        inscriptions = [_dict_to_inscription(row) for row in rows]
        return SearchResults(inscriptions=inscriptions, total=len(inscriptions))

    def get_all_ids(self) -> list[str]:
        """Return a list of all inscription IDs."""
        with self._conn.cursor() as cur:
            cur.execute("SELECT id FROM inscriptions ORDER BY id ASC")
            return [row[0] for row in cur.fetchall()]

    def get_names_network(self) -> tuple[dict[str, list[str]], dict[str, dict[str, int]]]:
        from collections import defaultdict

        # We process canonical strings and run _extract_names logic directly here
        with self._conn.cursor() as cur:
            cur.execute("SELECT id, canonical FROM inscriptions WHERE canonical IS NOT NULL")
            rows = cur.fetchall()

        name_inscriptions = defaultdict(list)
        co_occurrences = defaultdict(int)

        for row in rows:
            insc_id = row[0]
            canonical = row[1]
            found_names = _extract_names(canonical)

            for name in found_names:
                name_inscriptions[name].append(insc_id)
                for other in found_names:
                    if name != other:
                        pair = f"{min(name, other)}|{max(name, other)}"
                        co_occurrences[pair] += 1

        return dict(name_inscriptions), dict(co_occurrences)

    def get_stats_summary(self) -> dict:
        import psycopg2.extras

        try:
            with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(findspot_lat) as with_coords,
                        COUNT(pleiades_id) as pleiades_linked,
                        SUM(CASE WHEN classification != 'unknown' THEN 1 ELSE 0 END) as classified
                    FROM inscriptions;
                """)
                summary = dict(cur.fetchone() or {})

                cur.execute("""
                    SELECT findspot, COUNT(*) as c
                    FROM inscriptions
                    WHERE findspot != '' AND findspot IS NOT NULL
                    GROUP BY findspot
                    ORDER BY c DESC LIMIT 20
                """)
                summary["top_sites"] = [(r["findspot"], r["c"]) for r in cur.fetchall()]

                cur.execute("""
                    SELECT classification, COUNT(*) as c
                    FROM inscriptions
                    GROUP BY classification
                    ORDER BY c DESC
                """)
                summary["classification_counts"] = [
                    (r["classification"], r["c"]) for r in cur.fetchall()
                ]

                summary["text_length_buckets"] = []
                summary["distinct_sites"] = []
                summary["distinct_classifications"] = [
                    x[0] for x in summary.get("classification_counts", [])
                ]

                self._conn.commit()
                return summary
        except Exception as e:
            self._conn.rollback()
            raise e

    def get_stats_timeline(self) -> dict:
        import psycopg2.extras

        try:
            with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, findspot, findspot_lat, findspot_lon, date_approx, classification
                    FROM inscriptions
                    WHERE date_approx IS NOT NULL AND findspot_lat IS NOT NULL;
                """)
                items = [dict(r) for r in cur.fetchall()]
                self._conn.commit()
                return {"total": len(items), "items": items}
        except Exception as e:
            self._conn.rollback()
            raise e

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_inscription(row: sqlite3.Row) -> Inscription:
    """Convert a SQLite Row to Inscription."""
    keys = row.keys()
    return Inscription(
        id=row["id"],
        raw_text=row["raw_text"],
        canonical=row["canonical"],
        phonetic=row["phonetic"],
        old_italic=row["old_italic"],
        findspot=row["findspot"],
        findspot_lat=row["findspot_lat"],
        findspot_lon=row["findspot_lon"],
        date_approx=row["date_approx"],
        date_uncertainty=row["date_uncertainty"],
        medium=row["medium"],
        object_type=row["object_type"],
        source=row["source"],
        bibliography=row["bibliography"],
        notes=row["notes"],
        language=row["language"] if "language" in keys else "etruscan",
        classification=(row["classification"] if "classification" in keys else "unknown"),
        script_system=(row["script_system"] if "script_system" in keys else None),
        completeness=(row["completeness"] if "completeness" in keys else None),
        provenance_status=(row["provenance_status"] if "provenance_status" in keys else "verified"),
        provenance_flags=(
            []
            if not ("provenance_flags" in keys and row["provenance_flags"])
            else row["provenance_flags"].split(",")
        ),
        trismegistos_id=(row["trismegistos_id"] if "trismegistos_id" in keys else None),
        eagle_id=(row["eagle_id"] if "eagle_id" in keys else None),
        pleiades_id=(row["pleiades_id"] if "pleiades_id" in keys else None),
        geonames_id=(row["geonames_id"] if "geonames_id" in keys else None),
        is_codex=(row["is_codex"] if "is_codex" in keys else False),
    )


def _dict_to_inscription(row: dict) -> Inscription:
    """Convert a PostgreSQL dict row to Inscription."""
    return Inscription(
        id=row["id"],
        raw_text=row["raw_text"],
        canonical=row["canonical"],
        phonetic=row["phonetic"],
        old_italic=row["old_italic"],
        findspot=row["findspot"],
        findspot_lat=row.get("findspot_lat"),
        findspot_lon=row.get("findspot_lon"),
        date_approx=row.get("date_approx"),
        date_uncertainty=row.get("date_uncertainty"),
        medium=row.get("medium", ""),
        object_type=row.get("object_type", ""),
        source=row.get("source", ""),
        bibliography=row.get("bibliography", ""),
        notes=row.get("notes", ""),
        language=row.get("language", "etruscan"),
        classification=row.get("classification", "unknown"),
        script_system=row.get("script_system"),
        completeness=row.get("completeness"),
        provenance_status=row.get("provenance_status", "verified"),
        provenance_flags=(
            [] if not row.get("provenance_flags") else row["provenance_flags"].split(",")
        ),
        trismegistos_id=row.get("trismegistos_id"),
        eagle_id=row.get("eagle_id"),
        pleiades_id=row.get("pleiades_id"),
        geonames_id=row.get("geonames_id"),
        is_codex=row.get("is_codex", False),
    )


def _safe_float(val: str | None) -> float | None:
    if not val or val.strip() == "":
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _safe_int(val: str | None) -> int | None:
    if not val or val.strip() == "":
        return None
    try:
        return int(float(val))
    except ValueError:
        return None


def auto_flag_inscription(
    inscription: Inscription,
    language: str = "etruscan",
    corpus: BaseCorpus | None = None,
    similarity_threshold: float = 0.9,
) -> list[str]:
    """
    Auto-detect potential issues in an inscription for the provenance pipeline.

    Checks:
      - Non-alphabet characters (potential OCR errors)
      - Out-of-range coordinates (outside Etruscan cultural area)
      - Near-duplicate texts (TF-IDF cosine similarity > threshold)

    Args:
        inscription: The inscription to check.
        language: Language adapter to use.
        corpus: If provided, checks for near-duplicates against existing texts.
        similarity_threshold: Cosine similarity threshold for duplicate flagging (0-1).

    Returns:
        List of flag strings describing detected issues.
    """
    from openetruscan.adapter import load_adapter

    flags: list[str] = []

    # Check for non-alphabet characters
    if inscription.canonical:
        try:
            adapter = load_adapter(language)
            alphabet_set = set(adapter.alphabet.keys())
            unknown_chars = set()
            for ch in inscription.canonical:
                if ch not in alphabet_set and ch != " ":
                    unknown_chars.add(ch)
            if unknown_chars:
                flags.append(f"non_alphabet_chars: {', '.join(sorted(unknown_chars))}")
        except Exception:  # noqa: BLE001
            pass  # Adapter not found — skip check  # nosec B110

    # Check coordinate range
    if inscription.findspot_lat is not None and inscription.findspot_lon is not None:
        lat, lon = inscription.findspot_lat, inscription.findspot_lon
        if not (_ETRUSCAN_LAT_RANGE[0] <= lat <= _ETRUSCAN_LAT_RANGE[1]):
            flags.append(
                f"lat_out_of_range: {lat} "
                f"(expected {_ETRUSCAN_LAT_RANGE[0]}-"
                f"{_ETRUSCAN_LAT_RANGE[1]})"
            )
        if not (_ETRUSCAN_LON_RANGE[0] <= lon <= _ETRUSCAN_LON_RANGE[1]):
            flags.append(
                f"lon_out_of_range: {lon} "
                f"(expected {_ETRUSCAN_LON_RANGE[0]}-"
                f"{_ETRUSCAN_LON_RANGE[1]})"
            )

    # TF-IDF near-duplicate detection
    if corpus is not None and inscription.canonical:
        flags.extend(_check_near_duplicates(inscription, corpus, similarity_threshold))

    return flags


def _check_near_duplicates(
    inscription: Inscription,
    corpus: BaseCorpus,
    threshold: float = 0.9,
) -> list[str]:
    """
    Check for near-duplicate texts using TF-IDF cosine similarity.

    Uses character n-gram TF-IDF (2-4 grams) to detect texts that are
    suspiciously similar, which may indicate OCR duplicates or transcription
    errors from the same source.
    """
    flags: list[str] = []

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        return flags  # sklearn not installed — skip check

    # Fetch existing canonical texts
    results = corpus.search(limit=999999)
    existing = [
        (insc.id, insc.canonical)
        for insc in results
        if insc.canonical and insc.id != inscription.id
    ]

    if not existing:
        return flags

    existing_ids, existing_texts = zip(*existing, strict=True)

    # Build TF-IDF matrix with character n-grams
    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4),
        max_features=5000,
    )

    try:
        corpus_matrix = vectorizer.fit_transform(list(existing_texts))
        new_vector = vectorizer.transform([inscription.canonical])
        similarities = cosine_similarity(new_vector, corpus_matrix)[0]
    except ValueError:
        return flags  # Empty vocabulary or other vectorizer issue

    # Flag high-similarity matches
    for i, sim in enumerate(similarities):
        if sim >= threshold:
            flags.append(f"near_duplicate: {existing_ids[i]} (similarity={sim:.3f})")

    return flags
