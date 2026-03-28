"""
Corpus module — structured epigraphic dataset with query API.

Dual-backend architecture:
  - SQLite (default): zero-infrastructure, bundled with the package.
  - PostgreSQL (optional): Cloud SQL for public access with abuse protection.

Usage:
    # Local SQLite (default)
    corpus = Corpus.load()

    # Cloud PostgreSQL
    corpus = Corpus.connect("postgresql://user:pass@host/db")
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from openetruscan.normalizer import normalize

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
    # Provenance fields
    provenance_status: str = "verified"
    provenance_flags: str = ""  # JSON-encoded list of detected issues

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
        }


@dataclass
class GeneticSample:
    """A single archaeogenetic sample record."""

    id: str
    findspot: str = ""
    findspot_lat: float | None = None
    findspot_lon: float | None = None
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

_SQLITE_SCHEMA_TABLE = """
CREATE TABLE IF NOT EXISTS inscriptions (
    id TEXT PRIMARY KEY,
    raw_text TEXT NOT NULL,
    canonical TEXT NOT NULL DEFAULT '',
    phonetic TEXT NOT NULL DEFAULT '',
    old_italic TEXT NOT NULL DEFAULT '',
    findspot TEXT NOT NULL DEFAULT '',
    findspot_lat REAL,
    findspot_lon REAL,
    date_approx INTEGER,
    date_uncertainty INTEGER,
    medium TEXT NOT NULL DEFAULT '',
    object_type TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    bibliography TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'etruscan',
    classification TEXT NOT NULL DEFAULT 'unknown',
    script_system TEXT NOT NULL DEFAULT 'old_italic',
    completeness TEXT NOT NULL DEFAULT 'complete',
    provenance_status TEXT NOT NULL DEFAULT 'verified',
    provenance_flags TEXT NOT NULL DEFAULT ''
);
"""

_SQLITE_SCHEMA_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_canonical ON inscriptions(canonical);
CREATE INDEX IF NOT EXISTS idx_findspot ON inscriptions(findspot);
CREATE INDEX IF NOT EXISTS idx_date ON inscriptions(date_approx);
CREATE INDEX IF NOT EXISTS idx_language ON inscriptions(language);
CREATE INDEX IF NOT EXISTS idx_classification ON inscriptions(classification);
CREATE INDEX IF NOT EXISTS idx_provenance ON inscriptions(provenance_status);
"""

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
    geom geometry(Point, 4326),
    emb_text vector(768),
    emb_context vector(768),
    emb_combined vector(768),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_canonical ON inscriptions(canonical);
CREATE INDEX IF NOT EXISTS idx_findspot ON inscriptions(findspot);
CREATE INDEX IF NOT EXISTS idx_date ON inscriptions(date_approx);
CREATE INDEX IF NOT EXISTS idx_language ON inscriptions(language);
CREATE INDEX IF NOT EXISTS idx_classification ON inscriptions(classification);
CREATE INDEX IF NOT EXISTS idx_provenance ON inscriptions(provenance_status);

CREATE TABLE IF NOT EXISTS genetic_samples (
    id TEXT PRIMARY KEY,
    findspot TEXT DEFAULT '',
    findspot_lat DOUBLE PRECISION,
    findspot_lon DOUBLE PRECISION,
    date_approx INTEGER,
    date_uncertainty INTEGER,
    y_haplogroup TEXT,
    mt_haplogroup TEXT,
    source TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    geom geometry(Point, 4326),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_genetic_geom ON genetic_samples USING GIST (geom);
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
]


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class BaseCorpus(ABC):
    """Abstract corpus backend."""

    @abstractmethod
    def add(
        self,
        inscription: Inscription,
        language: str = "etruscan",
    ) -> None: ...

    @abstractmethod
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
    ) -> SearchResults: ...

    @abstractmethod
    def search_radius(
        self,
        lat: float,
        lon: float,
        radius_km: float = 50.0,
        limit: int = 100,
    ) -> SearchResults: ...

    @abstractmethod
    def semantic_search(
        self,
        query_embedding: list[float],
        field: str = "emb_combined",
        limit: int = 20,
    ) -> SearchResults: ...

    @abstractmethod
    def count(self) -> int: ...

    @abstractmethod
    def import_csv(
        self,
        csv_path: str | Path,
        language: str = "etruscan",
    ) -> int: ...

    @abstractmethod
    def add_genetic_sample(
        self,
        sample: GeneticSample,
    ) -> None: ...

    @abstractmethod
    def find_genetic_matches(
        self,
        inscription_id: str,
        limit: int = 5,
    ) -> list[dict]: ...

    def export_all(self, fmt: str = "csv") -> str:
        """Export the entire corpus."""
        results = self.search(limit=999999)
        return results.export(fmt)

    @abstractmethod
    def close(self) -> None: ...

    def _prepare_inscription(
        self,
        inscription: Inscription,
        language: str,
    ) -> Inscription:
        """Auto-normalize text if canonical is empty."""
        if not inscription.canonical:
            result = normalize(inscription.raw_text, language=language)
            return Inscription(
                id=inscription.id,
                raw_text=inscription.raw_text,
                canonical=result.canonical,
                phonetic=result.phonetic,
                old_italic=result.old_italic,
                findspot=inscription.findspot,
                findspot_lat=inscription.findspot_lat,
                findspot_lon=inscription.findspot_lon,
                date_approx=inscription.date_approx,
                date_uncertainty=inscription.date_uncertainty,
                medium=inscription.medium,
                object_type=inscription.object_type,
                source=inscription.source,
                bibliography=inscription.bibliography,
                notes=inscription.notes,
                language=inscription.language or language,
                classification=inscription.classification,
                script_system=inscription.script_system,
                completeness=inscription.completeness,
                provenance_status=inscription.provenance_status,
                provenance_flags=inscription.provenance_flags,
            )
        return inscription

    def _inscription_values(self, insc: Inscription) -> tuple:
        """Extract ordered values for INSERT."""
        return (
            insc.id,
            insc.raw_text,
            insc.canonical,
            insc.phonetic,
            insc.old_italic,
            insc.findspot,
            insc.findspot_lat,
            insc.findspot_lon,
            insc.date_approx,
            insc.date_uncertainty,
            insc.medium,
            insc.object_type,
            insc.source,
            insc.bibliography,
            insc.notes,
            insc.language,
            insc.classification,
            insc.script_system,
            insc.completeness,
            insc.provenance_status,
            insc.provenance_flags,
        )

    def _build_search_query(
        self,
        text: str | None,
        findspot: str | None,
        date_range: tuple[int, int] | None,
        medium: str | None,
        language: str | None,
        classification: str | None,
        limit: int,
        provenance_status: str | None = None,
        param_style: str = "qmark",
    ) -> tuple[str, str, list]:
        """Build WHERE clause. Returns (query, count_query, params)."""
        conditions: list[str] = []
        params: list = []
        ph = "?" if param_style == "qmark" else "%s"

        if text:
            sql_pattern = text.replace("*", "%").replace("?", "_")
            conditions.append(f"canonical LIKE {ph}")
            params.append(sql_pattern)

        if findspot:
            conditions.append(f"findspot LIKE {ph}")
            params.append(f"%{findspot}%")

        if date_range:
            conditions.append(f"date_approx >= {ph} AND date_approx <= {ph}")
            params.extend(date_range)

        if medium:
            conditions.append(f"medium LIKE {ph}")
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

        where = " AND ".join(conditions) if conditions else "1=1"
        query = " ".join(["SELECT * FROM inscriptions WHERE", where, "ORDER BY id LIMIT", ph])
        count_query = " ".join(["SELECT COUNT(*) FROM inscriptions WHERE", where])
        params_with_limit = params + [limit]

        return query, count_query, params_with_limit


# ---------------------------------------------------------------------------
# SQLite backend
# ---------------------------------------------------------------------------


class Corpus(BaseCorpus):
    """
    Queryable corpus backed by SQLite.

    Usage:
        corpus = Corpus.load()
        results = corpus.search(text="larth", findspot="Cerveteri")
        print(results.export("csv"))
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._conn: sqlite3.Connection | None = None

    @classmethod
    def load(cls, db_path: str | Path | None = None) -> BaseCorpus:
        """
        Load or create the corpus database.

        If DATABASE_URL is set in the environment, connects to that
        backend automatically (PostgreSQL or SQLite URL). Otherwise
        uses the default local SQLite database.
        """
        # Auto-detect from environment or .env file
        env_url = os.environ.get("DATABASE_URL", "")
        if not env_url:
            env_path = Path(".env")
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("DATABASE_URL="):
                        env_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break

        if env_url and db_path is None:
            return cls.connect(env_url)
        corpus = cls(db_path)
        corpus._ensure_db()
        return corpus

    @classmethod
    def connect(cls, url: str) -> BaseCorpus:
        """
        Connect to a corpus backend by URL.

        - sqlite:///path or file path -> SQLite
        - postgresql://user:pass@host/db -> PostgreSQL
        """
        if url.startswith(("postgresql://", "postgres://")):
            return PostgresCorpus.from_url(url)
        path = url.replace("sqlite:///", "") if "sqlite:///" in url else url
        return cls.load(path)

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_db(self) -> None:
        """Create tables if they don't exist and migrate schema."""
        from openetruscan.artifacts import IMAGES_SQLITE_SCHEMA

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # 1. Create table (old DBs keep their columns, new DBs get all)
        self.conn.executescript(_SQLITE_SCHEMA_TABLE)
        # 2. Migrate: add any missing columns to old databases
        self._migrate_columns()
        # 3. Create indexes (now safe — all columns exist)
        self.conn.executescript(_SQLITE_SCHEMA_INDEXES)
        self.conn.executescript(IMAGES_SQLITE_SCHEMA)

    def _migrate_columns(self) -> None:
        """Add new columns to existing databases."""
        cursor = self.conn.execute("PRAGMA table_info(inscriptions)")
        existing = {row[1] for row in cursor.fetchall()}
        migrations = [
            ("language", "TEXT NOT NULL DEFAULT 'etruscan'"),
            ("classification", "TEXT NOT NULL DEFAULT 'unknown'"),
            ("script_system", "TEXT NOT NULL DEFAULT 'old_italic'"),
            ("completeness", "TEXT NOT NULL DEFAULT 'complete'"),
            ("provenance_status", "TEXT NOT NULL DEFAULT 'verified'"),
            ("provenance_flags", "TEXT NOT NULL DEFAULT ''"),
        ]
        for col_name, col_def in migrations:
            if col_name not in existing:
                self.conn.execute(f"ALTER TABLE inscriptions ADD COLUMN {col_name} {col_def}")
        self.conn.commit()

    def add(
        self,
        inscription: Inscription,
        language: str = "etruscan",
    ) -> None:
        """Add an inscription, auto-normalizing the text."""
        inscription = self._prepare_inscription(inscription, language)
        cols = ", ".join(_COLUMNS)
        placeholders = ", ".join(["?"] * len(_COLUMNS))
        self.conn.execute(
            f"INSERT OR REPLACE INTO inscriptions ({cols}) VALUES ({placeholders})",
            self._inscription_values(inscription),
        )
        self.conn.commit()

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
    ) -> SearchResults:
        """Search the corpus with optional filters."""
        query, count_query, params = self._build_search_query(
            text,
            findspot,
            date_range,
            medium,
            language,
            classification,
            limit,
            provenance_status=provenance_status,
            param_style="qmark",
        )
        rows = self.conn.execute(query, params).fetchall()
        inscriptions = [_row_to_inscription(row) for row in rows]
        total = self.conn.execute(
            count_query,
            params[:-1],
        ).fetchone()[0]
        return SearchResults(inscriptions=inscriptions, total=total)

    def search_radius(
        self,
        lat: float,
        lon: float,
        radius_km: float = 50.0,
        limit: int = 100,
    ) -> SearchResults:
        """Haversine fallback for SQLite."""
        from openetruscan.geo import haversine

        rows = self.conn.execute(
            "SELECT * FROM inscriptions WHERE findspot_lat IS NOT NULL AND findspot_lon IS NOT NULL"
        ).fetchall()

        inscriptions = []
        for row in rows:
            dist = haversine(
                lat,
                lon,
                row["findspot_lat"],
                row["findspot_lon"],
            )
            if dist <= radius_km:
                inscriptions.append((dist, _row_to_inscription(row)))

        inscriptions.sort(key=lambda x: x[0])
        results = [insc for _, insc in inscriptions[:limit]]
        return SearchResults(inscriptions=results, total=len(inscriptions))

    def semantic_search(
        self,
        query_embedding: list[float],
        field: str = "emb_combined",
        limit: int = 20,
    ) -> SearchResults:
        raise NotImplementedError(
            "semantic_search is only supported in PostgresCorpus with pgvector"
        )

    def count(self) -> int:
        """Total number of inscriptions."""
        return self.conn.execute(
            "SELECT COUNT(*) FROM inscriptions",
        ).fetchone()[0]

    def add_genetic_sample(
        self,
        sample: GeneticSample,
    ) -> None:
        """Add a genetic sample to the SQLite fallback DB."""
        sql = """
            INSERT OR REPLACE INTO genetic_samples (
                id, findspot, findspot_lat, findspot_lon,
                date_approx, date_uncertainty, y_haplogroup, mt_haplogroup,
                source, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        self.conn.execute(
            sql,
            (
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
            ),
        )
        self.conn.commit()

    def find_genetic_matches(
        self,
        inscription_id: str,
        limit: int = 5,
    ) -> list[dict]:
        """Haversine fallback for genetic matching in SQLite."""
        # Find the inscription's coordinates and date
        insc_row = self.conn.execute(
            "SELECT findspot_lat, findspot_lon, date_approx FROM inscriptions WHERE id = ?",
            (inscription_id,),
        ).fetchone()

        if not insc_row or not insc_row["findspot_lat"] or not insc_row["findspot_lon"]:
            return []

        lat = insc_row["findspot_lat"]
        lon = insc_row["findspot_lon"]
        date_approx = insc_row["date_approx"] or 0

        # Fetch all genetic samples
        genes = self.conn.execute(
            "SELECT * FROM genetic_samples "
            "WHERE findspot_lat IS NOT NULL AND findspot_lon IS NOT NULL"
        ).fetchall()

        from openetruscan.geo import haversine

        results = []
        for g in genes:
            dist = haversine(
                lat,
                lon,
                g["findspot_lat"],
                g["findspot_lon"],
            )
            g_date = g["date_approx"] or 0
            date_diff = abs(date_approx - g_date)

            # Score = Distance_Km + (Date_Diff_Yrs * 0.5)
            score = dist + (date_diff * 0.5)

            row_dict = dict(g)
            row_dict["distance_km"] = dist
            row_dict["date_diff_years"] = date_diff
            row_dict["match_score"] = score
            results.append((score, row_dict))

        results.sort(key=lambda x: x[0])
        return [r[1] for r in results[:limit]]

    def import_csv(
        self,
        csv_path: str | Path,
        language: str = "etruscan",
    ) -> int:
        """
        Import inscriptions from a CSV file.

        Returns number of imported inscriptions.
        """
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
                    date_uncertainty=_safe_int(
                        row.get("date_uncertainty"),
                    ),
                    medium=row.get("medium", ""),
                    object_type=row.get("object_type", ""),
                    source=row.get("source", ""),
                    bibliography=row.get("bibliography", ""),
                    notes=row.get("notes", ""),
                    language=row.get("language", language),
                    classification=row.get("classification", "unknown"),
                    script_system=row.get(
                        "script_system",
                        "old_italic",
                    ),
                    completeness=row.get("completeness", "complete"),
                )
                self.add(inscription, language=language)
                imported += 1
        return imported

    def add_image(
        self,
        image_id: str,
        inscription_id: str,
        filename: str,
        mime_type: str = "image/jpeg",
        description: str = "",
        file_hash: str = "",
    ) -> None:
        """Store image metadata."""
        self.conn.execute(
            "INSERT OR REPLACE INTO images "
            "(id, inscription_id, filename, mime_type, "
            "description, file_hash) VALUES (?, ?, ?, ?, ?, ?)",
            (image_id, inscription_id, filename, mime_type, description, file_hash),
        )
        self.conn.commit()

    def get_images(self, inscription_id: str) -> list[dict]:
        """Get all images for an inscription."""
        rows = self.conn.execute(
            "SELECT * FROM images WHERE inscription_id = ?",
            (inscription_id,),
        ).fetchall()
        return [{k: row[k] for k in row} for row in rows]

    def review_quarantine(
        self,
        inscription_id: str,
        action: str = "verify",
    ) -> bool:
        """
        Review a quarantined inscription.

        Args:
            inscription_id: The inscription ID to review.
            action: "verify" to mark as verified, "reject" to reject.

        Returns:
            True if the inscription was found and updated.
        """
        if action not in ("verify", "reject"):
            raise ValueError(f"Invalid action: {action}. Use 'verify' or 'reject'.")

        row = self.conn.execute(
            "SELECT id FROM inscriptions WHERE id = ?", (inscription_id,)
        ).fetchone()
        if not row:
            return False

        new_status = "verified" if action == "verify" else "rejected"
        self.conn.execute(
            "UPDATE inscriptions SET provenance_status = ? WHERE id = ?",
            (new_status, inscription_id),
        )
        self.conn.commit()
        return True

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


# ---------------------------------------------------------------------------
# PostgreSQL backend
# ---------------------------------------------------------------------------


class PostgresCorpus(BaseCorpus):
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
    def from_url(cls, url: str) -> PostgresCorpus:
        """Connect to PostgreSQL and ensure schema exists."""
        corpus = cls(url)
        corpus._ensure_db()
        return corpus

    def _ensure_db(self) -> None:
        """Create tables if they don't exist (ignored for read-only users)."""
        import psycopg2

        from openetruscan.artifacts import IMAGES_PG_SCHEMA

        try:
            with self._conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute(_PG_SCHEMA)
                cur.execute(IMAGES_PG_SCHEMA)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_inscriptions_geom "
                    "ON inscriptions USING GIST (geom);"
                )
                # Vector indexes — only create once data exists
                import contextlib
                with contextlib.suppress(psycopg2.Error):
                    cur.execute(_PG_VECTOR_INDEXES)
            self._conn.commit()
        except psycopg2.Error:
            self._conn.rollback()

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
    ) -> SearchResults:
        """Search the corpus."""
        import psycopg2.extras

        query, count_query, params = self._build_search_query(
            text,
            findspot,
            date_range,
            medium,
            language,
            classification,
            limit,
            provenance_status=provenance_status,
            param_style="format",
        )
        with self._conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor,
        ) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            inscriptions = [_dict_to_inscription(row) for row in rows]
            cur.execute(count_query, params[:-1])
            total = cur.fetchone()["count"]
        return SearchResults(inscriptions=inscriptions, total=total)

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
                       geom::geography,
                       ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                   ) as dist
            FROM inscriptions
            WHERE geom IS NOT NULL
            AND ST_DWithin(
                geom::geography,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                %s
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
                %s
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

    def semantic_search(
        self,
        query_embedding: list[float],
        field: str = "emb_combined",
        limit: int = 20,
    ) -> SearchResults:
        """Find similar inscriptions using pgvector cosine similarity."""
        import psycopg2.extras

        if field not in ("emb_text", "emb_context", "emb_combined"):
            raise ValueError(f"Invalid embedding field: {field}")

        from psycopg2 import sql

        query = sql.SQL("""
            SELECT *,
                   1 - ({field} <=> %s::vector) AS similarity
            FROM inscriptions
            WHERE {field} IS NOT NULL
            ORDER BY {field} <=> %s::vector
            LIMIT %s
        """).format(field=sql.Identifier(field))

        # Format the embedding for pgvector
        vec_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        with self._conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor,
        ) as cur:
            cur.execute(query, (vec_str, vec_str, limit))
            rows = cur.fetchall()
            inscriptions = [_dict_to_inscription(row) for row in rows]

        return SearchResults(inscriptions=inscriptions, total=len(inscriptions))

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
                r.pop('geom', None)
                # Convert datetime types from postgres automatically generated timestamps
                if 'created_at' in r and r['created_at']:
                    r['created_at'] = r['created_at'].isoformat()
                if 'updated_at' in r and r['updated_at']:
                    r['updated_at'] = r['updated_at'].isoformat()
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
                    date_uncertainty=_safe_int(
                        row.get("date_uncertainty"),
                    ),
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
        script_system=(row["script_system"] if "script_system" in keys else "old_italic"),
        completeness=(row["completeness"] if "completeness" in keys else "complete"),
        provenance_status=(row["provenance_status"] if "provenance_status" in keys else "verified"),
        provenance_flags=(row["provenance_flags"] if "provenance_flags" in keys else ""),
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
        script_system=row.get("script_system", "old_italic"),
        completeness=row.get("completeness", "complete"),
        provenance_status=row.get("provenance_status", "verified"),
        provenance_flags=row.get("provenance_flags", ""),
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
