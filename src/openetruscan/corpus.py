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
    "funerary", "votive", "legal", "commercial",
    "boundary", "ownership", "dedicatory", "unknown",
)

SCRIPT_SYSTEMS = ("old_italic", "latin", "greek", "other")
COMPLETENESS_VALUES = ("complete", "fragmentary", "illegible")


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
    date_approx: int | None = None       # negative = BCE
    date_uncertainty: int | None = None   # +/- years
    medium: str = ""
    object_type: str = ""
    source: str = ""
    bibliography: str = ""
    notes: str = ""
    # New classification fields
    language: str = "etruscan"
    classification: str = "unknown"
    script_system: str = "old_italic"
    completeness: str = "complete"

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
            lines = [
                json.dumps(i.to_dict(), ensure_ascii=False)
                for i in self.inscriptions
            ]
            return "\n".join(lines)
        elif fmt == "geojson":
            return self._to_geojson()
        else:
            raise ValueError(
                f"Unknown format: {fmt}. Use: csv, json, jsonl, geojson"
            )

    def _to_csv(self) -> str:
        import io
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "id", "canonical", "findspot", "date", "medium",
            "source", "language", "classification",
        ])
        for i in self.inscriptions:
            writer.writerow([
                i.id, i.canonical, i.findspot, i.date_display(),
                i.medium, i.source, i.language, i.classification,
            ])
        return buf.getvalue()

    def _to_geojson(self) -> str:
        features = []
        for i in self.inscriptions:
            if i.findspot_lat is not None and i.findspot_lon is not None:
                features.append({
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
                })
        collection = {
            "type": "FeatureCollection",
            "features": features,
        }
        return json.dumps(collection, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Schema SQL
# ---------------------------------------------------------------------------

_SQLITE_SCHEMA = """
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
    completeness TEXT NOT NULL DEFAULT 'complete'
);

CREATE INDEX IF NOT EXISTS idx_canonical ON inscriptions(canonical);
CREATE INDEX IF NOT EXISTS idx_findspot ON inscriptions(findspot);
CREATE INDEX IF NOT EXISTS idx_date ON inscriptions(date_approx);
CREATE INDEX IF NOT EXISTS idx_language ON inscriptions(language);
CREATE INDEX IF NOT EXISTS idx_classification ON inscriptions(classification);
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
    geom geometry(Point, 4326),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_canonical ON inscriptions(canonical);
CREATE INDEX IF NOT EXISTS idx_findspot ON inscriptions(findspot);
CREATE INDEX IF NOT EXISTS idx_date ON inscriptions(date_approx);
CREATE INDEX IF NOT EXISTS idx_language ON inscriptions(language);
CREATE INDEX IF NOT EXISTS idx_classification ON inscriptions(classification);
"""

# Columns used for INSERT/SELECT (shared between backends)
_COLUMNS = [
    "id", "raw_text", "canonical", "phonetic", "old_italic",
    "findspot", "findspot_lat", "findspot_lon",
    "date_approx", "date_uncertainty",
    "medium", "object_type", "source", "bibliography", "notes",
    "language", "classification", "script_system", "completeness",
]


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseCorpus(ABC):
    """Abstract corpus backend."""

    @abstractmethod
    def add(
        self, inscription: Inscription, language: str = "etruscan",
    ) -> None:
        ...

    @abstractmethod
    def search(
        self,
        text: str | None = None,
        findspot: str | None = None,
        date_range: tuple[int, int] | None = None,
        medium: str | None = None,
        language: str | None = None,
        classification: str | None = None,
        limit: int = 100,
    ) -> SearchResults:
        ...

    @abstractmethod
    def count(self) -> int:
        ...

    @abstractmethod
    def import_csv(
        self, csv_path: str | Path, language: str = "etruscan",
    ) -> int:
        ...

    def export_all(self, fmt: str = "csv") -> str:
        """Export the entire corpus."""
        results = self.search(limit=999999)
        return results.export(fmt)

    @abstractmethod
    def close(self) -> None:
        ...

    def _prepare_inscription(
        self, inscription: Inscription, language: str,
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
            )
        return inscription

    def _inscription_values(self, insc: Inscription) -> tuple:
        """Extract ordered values for INSERT."""
        return (
            insc.id, insc.raw_text, insc.canonical, insc.phonetic,
            insc.old_italic, insc.findspot,
            insc.findspot_lat, insc.findspot_lon,
            insc.date_approx, insc.date_uncertainty,
            insc.medium, insc.object_type,
            insc.source, insc.bibliography,
            insc.notes, insc.language, insc.classification,
            insc.script_system, insc.completeness,
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
            conditions.append(
                f"date_approx >= {ph} AND date_approx <= {ph}"
            )
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

        where = " AND ".join(conditions) if conditions else "1=1"
        query = " ".join([
            "SELECT * FROM inscriptions WHERE", where,
            "ORDER BY id LIMIT", ph
        ])
        count_query = " ".join([
            "SELECT COUNT(*) FROM inscriptions WHERE", where
        ])
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
        # Auto-detect from environment
        env_url = os.environ.get("DATABASE_URL", "")
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
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_db(self) -> None:
        """Create tables if they don't exist and migrate schema."""
        from openetruscan.artifacts import IMAGES_SQLITE_SCHEMA

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn.executescript(_SQLITE_SCHEMA)
        self.conn.executescript(IMAGES_SQLITE_SCHEMA)
        self._migrate_columns()

    def _migrate_columns(self) -> None:
        """Add new columns to existing databases."""
        cursor = self.conn.execute("PRAGMA table_info(inscriptions)")
        existing = {row[1] for row in cursor.fetchall()}
        migrations = [
            ("language", "TEXT NOT NULL DEFAULT 'etruscan'"),
            ("classification", "TEXT NOT NULL DEFAULT 'unknown'"),
            ("script_system", "TEXT NOT NULL DEFAULT 'old_italic'"),
            ("completeness", "TEXT NOT NULL DEFAULT 'complete'"),
        ]
        for col_name, col_def in migrations:
            if col_name not in existing:
                self.conn.execute(
                    f"ALTER TABLE inscriptions "
                    f"ADD COLUMN {col_name} {col_def}"
                )
        self.conn.commit()

    def add(
        self, inscription: Inscription, language: str = "etruscan",
    ) -> None:
        """Add an inscription, auto-normalizing the text."""
        inscription = self._prepare_inscription(inscription, language)
        cols = ", ".join(_COLUMNS)
        placeholders = ", ".join(["?"] * len(_COLUMNS))
        self.conn.execute(
            f"INSERT OR REPLACE INTO inscriptions "
            f"({cols}) VALUES ({placeholders})",
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
        limit: int = 100,
    ) -> SearchResults:
        """Search the corpus with optional filters."""
        query, count_query, params = self._build_search_query(
            text, findspot, date_range, medium,
            language, classification, limit, param_style="qmark",
        )
        rows = self.conn.execute(query, params).fetchall()
        inscriptions = [_row_to_inscription(row) for row in rows]
        total = self.conn.execute(
            count_query, params[:-1],
        ).fetchone()[0]
        return SearchResults(inscriptions=inscriptions, total=total)

    def count(self) -> int:
        """Total number of inscriptions."""
        return self.conn.execute(
            "SELECT COUNT(*) FROM inscriptions",
        ).fetchone()[0]

    def import_csv(
        self, csv_path: str | Path, language: str = "etruscan",
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
                    "text", row.get("raw_text", ""),
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
                        "script_system", "old_italic",
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
            (image_id, inscription_id, filename,
             mime_type, description, file_hash),
        )
        self.conn.commit()

    def get_images(self, inscription_id: str) -> list[dict]:
        """Get all images for an inscription."""
        rows = self.conn.execute(
            "SELECT * FROM images WHERE inscription_id = ?",
            (inscription_id,),
        ).fetchall()
        return [
            {k: row[k] for k in row}
            for row in rows
        ]

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
        """Create tables if they don't exist."""
        from openetruscan.artifacts import IMAGES_PG_SCHEMA

        with self._conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
            cur.execute(_PG_SCHEMA)
            cur.execute(IMAGES_PG_SCHEMA)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_inscriptions_geom "
                "ON inscriptions USING GIST (geom);"
            )
        self._conn.commit()

    def add(
        self, inscription: Inscription, language: str = "etruscan",
    ) -> None:
        """Add an inscription."""
        inscription = self._prepare_inscription(inscription, language)
        cols = ", ".join(_COLUMNS)
        placeholders = ", ".join(["%s"] * len(_COLUMNS))
        conflict_updates = ", ".join(
            f"{c} = EXCLUDED.{c}" for c in _COLUMNS if c != "id"
        )

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
            "INSERT INTO inscriptions", insert_cols,
            "VALUES", insert_placeholders,
            "ON CONFLICT (id) DO UPDATE SET",
            conflict_updates + ",",
            "geom = EXCLUDED.geom,",
            "updated_at = NOW()"
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
        limit: int = 100,
    ) -> SearchResults:
        """Search the corpus."""
        import psycopg2.extras
        query, count_query, params = self._build_search_query(
            text, findspot, date_range, medium,
            language, classification, limit, param_style="format",
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

    def count(self) -> int:
        with self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM inscriptions")
            return cur.fetchone()[0]

    def import_csv(
        self, csv_path: str | Path, language: str = "etruscan",
    ) -> int:
        """Bulk import from CSV."""
        path = Path(csv_path)
        imported = 0
        with path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                text = row.get(
                    "text", row.get("raw_text", ""),
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
            cur.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = 'corpus_reader'"
            )
            if not cur.fetchone():
                cur.execute(
                    "CREATE ROLE corpus_reader "
                    "WITH LOGIN PASSWORD %s",
                    (password,),
                )
            cur.execute(
                "GRANT CONNECT ON DATABASE corpus TO corpus_reader"
            )
            cur.execute(
                "GRANT USAGE ON SCHEMA public TO corpus_reader"
            )
            cur.execute(
                "GRANT SELECT ON ALL TABLES IN SCHEMA public "
                "TO corpus_reader"
            )
            cur.execute(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                "GRANT SELECT ON TABLES TO corpus_reader"
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
        classification=(
            row["classification"] if "classification" in keys else "unknown"
        ),
        script_system=(
            row["script_system"] if "script_system" in keys else "old_italic"
        ),
        completeness=(
            row["completeness"] if "completeness" in keys else "complete"
        ),
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
