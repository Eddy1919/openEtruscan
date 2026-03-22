"""
Corpus module — structured epigraphic dataset with query API.

Zero-infrastructure: data stored as SQLite, bundled with the package.
Git-native: designed for version-controlled CSV/JSON seed data.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from openetruscan.normalizer import normalize

DB_PATH = Path(__file__).parent / "data" / "corpus.db"


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
    date_uncertainty: int | None = None   # ± years
    medium: str = ""
    object_type: str = ""
    source: str = ""
    bibliography: str = ""
    notes: str = ""

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
            raise ValueError(f"Unknown format: {fmt}. Use: csv, json, jsonl, geojson")

    def _to_csv(self) -> str:
        import io
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "canonical", "findspot", "date", "medium", "source"])
        for i in self.inscriptions:
            writer.writerow([i.id, i.canonical, i.findspot, i.date_display(), i.medium, i.source])
        return buf.getvalue()

    def _to_geojson(self) -> str:
        features = []
        for i in self.inscriptions:
            if i.findspot_lat is not None and i.findspot_lon is not None:
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [i.findspot_lon, i.findspot_lat]},
                    "properties": {
                        "id": i.id, "text": i.canonical,
                        "findspot": i.findspot, "date": i.date_display(),
                    }
                })
        collection = {
            "type": "FeatureCollection",
            "features": features,
        }
        return json.dumps(collection, ensure_ascii=False, indent=2)


class Corpus:
    """
    Queryable corpus of inscriptions backed by SQLite.

    Usage:
        corpus = Corpus.load()
        results = corpus.search(text="larθ", findspot="Cerveteri")
        print(results.export("csv"))
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._conn: sqlite3.Connection | None = None

    @classmethod
    def load(cls, db_path: str | Path | None = None) -> Corpus:
        """Load or create the corpus database."""
        corpus = cls(db_path)
        corpus._ensure_db()
        return corpus

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_db(self) -> None:
        """Create tables if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn.executescript("""
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
                notes TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_canonical ON inscriptions(canonical);
            CREATE INDEX IF NOT EXISTS idx_findspot ON inscriptions(findspot);
            CREATE INDEX IF NOT EXISTS idx_date ON inscriptions(date_approx);
        """)

    def add(self, inscription: Inscription, language: str = "etruscan") -> None:
        """Add an inscription, auto-normalizing the text."""
        if not inscription.canonical:
            result = normalize(inscription.raw_text, language=language)
            inscription = Inscription(
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
            )

        self.conn.execute("""
            INSERT OR REPLACE INTO inscriptions
            (id, raw_text, canonical, phonetic, old_italic, findspot,
             findspot_lat, findspot_lon, date_approx, date_uncertainty,
             medium, object_type, source, bibliography, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            inscription.id, inscription.raw_text, inscription.canonical,
            inscription.phonetic, inscription.old_italic, inscription.findspot,
            inscription.findspot_lat, inscription.findspot_lon,
            inscription.date_approx, inscription.date_uncertainty,
            inscription.medium, inscription.object_type, inscription.source,
            inscription.bibliography, inscription.notes,
        ))
        self.conn.commit()

    def search(
        self,
        text: str | None = None,
        findspot: str | None = None,
        date_range: tuple[int, int] | None = None,
        medium: str | None = None,
        limit: int = 100,
    ) -> SearchResults:
        """
        Search the corpus with optional filters.

        Args:
            text: Wildcard search on canonical text (use * for wildcards).
            findspot: Exact or partial match on findspot.
            date_range: Tuple of (start, end) years (negative = BCE).
            medium: Filter by medium (e.g., "tufa", "bronze").
            limit: Maximum results to return.
        """
        conditions: list[str] = []
        params: list = []

        if text:
            # Convert user wildcards to SQL LIKE
            sql_pattern = text.replace("*", "%").replace("?", "_")
            conditions.append("canonical LIKE ?")
            params.append(sql_pattern)

        if findspot:
            conditions.append("findspot LIKE ?")
            params.append(f"%{findspot}%")

        if date_range:
            conditions.append("date_approx >= ? AND date_approx <= ?")
            params.extend(date_range)

        if medium:
            conditions.append("medium LIKE ?")
            params.append(f"%{medium}%")

        where = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT * FROM inscriptions WHERE {where} ORDER BY id LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        inscriptions = [self._row_to_inscription(row) for row in rows]

        # Get total count
        count_query = f"SELECT COUNT(*) FROM inscriptions WHERE {where}"
        total = self.conn.execute(count_query, params[:-1]).fetchone()[0]

        return SearchResults(inscriptions=inscriptions, total=total)

    def count(self) -> int:
        """Total number of inscriptions."""
        return self.conn.execute("SELECT COUNT(*) FROM inscriptions").fetchone()[0]

    def import_csv(self, csv_path: str | Path, language: str = "etruscan") -> int:
        """
        Import inscriptions from a CSV file.

        Expected columns: id, text, findspot, date_approx, date_uncertainty,
                         medium, object_type, source, bibliography, notes

        Returns number of imported inscriptions.
        """
        path = Path(csv_path)
        count = 0
        with path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                text = row.get("text", row.get("raw_text", "")).strip()
                if not text:
                    continue

                inscription = Inscription(
                    id=row.get("id", f"import_{count}"),
                    raw_text=text,
                    findspot=row.get("findspot", ""),
                    findspot_lat=_safe_float(row.get("findspot_lat")),
                    findspot_lon=_safe_float(row.get("findspot_lon")),
                    date_approx=_safe_int(row.get("date_approx")),
                    date_uncertainty=_safe_int(row.get("date_uncertainty")),
                    medium=row.get("medium", ""),
                    object_type=row.get("object_type", ""),
                    source=row.get("source", ""),
                    bibliography=row.get("bibliography", ""),
                    notes=row.get("notes", ""),
                )
                self.add(inscription, language=language)
                count += 1

        return count

    def export_all(self, fmt: str = "csv") -> str:
        """Export the entire corpus."""
        results = self.search(limit=999999)
        return results.export(fmt)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _row_to_inscription(row: sqlite3.Row) -> Inscription:
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
