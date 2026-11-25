"""PostgreSQL schema and SQL builders for the inscriptions table."""

from __future__ import annotations

# Columns consumed by _dict_to_inscription. Excludes emb_text/emb_context/emb_combined
# (vector(768), ~3 KB each), fts_canonical (tsvector), and geom (PostGIS) — which
# _dict_to_inscription never reads. Pulling them turned full-table scans into 700-second
# queries on the production read path.
_INSCRIPTION_COLS = (
    "id, raw_text, canonical, phonetic, old_italic, "
    "findspot, findspot_lat, findspot_lon, findspot_uncertainty_m, "
    "date_approx, date_uncertainty, "
    "medium, object_type, source, bibliography, notes, "
    "language, classification, script_system, completeness, "
    "provenance_status, provenance_flags, "
    "trismegistos_id, eagle_id, pleiades_id, geonames_id, zotero_id, is_codex"
)

# Widened FTS expression — single source of truth for the bootstrap path here
# and the alembic migration `e7c8d9e0f1a2_widen_fts_canonical`. canonical is
# weight A (primary text), structured identifiers are B, bibliographic
# context is C. ts_rank_cd applies the standard {0.1, 0.2, 0.4, 1.0} weights
# from D→A unless overridden, so canonical-text relevance still dominates.
_FTS_DOC_EXPR = (
    "setweight(to_tsvector('simple', coalesce(canonical, '')), 'A') || "
    "setweight(to_tsvector('simple', "
    "coalesce(findspot, '') || ' ' || "
    "coalesce(pleiades_id, '') || ' ' || "
    "coalesce(geonames_id, '') || ' ' || "
    "coalesce(trismegistos_id, '') || ' ' || "
    "coalesce(eagle_id, '')"
    "), 'B') || "
    "setweight(to_tsvector('simple', "
    "coalesce(source, '') || ' ' || "
    "coalesce(source_detail, '') || ' ' || "
    "coalesce(bibliography, '') || ' ' || "
    "coalesce(notes, '') || ' ' || "
    "coalesce(raw_text, '')"
    "), 'C')"
)


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
    provenance_status TEXT NOT NULL DEFAULT 'unknown',
    provenance_flags TEXT NOT NULL DEFAULT '',
    trismegistos_id TEXT,
    eagle_id TEXT,
    pleiades_id TEXT,
    geonames_id TEXT,
    is_codex BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    fts_canonical tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(canonical, '')), 'A') ||
        setweight(to_tsvector('simple',
            coalesce(findspot, '') || ' ' ||
            coalesce(pleiades_id, '') || ' ' ||
            coalesce(geonames_id, '') || ' ' ||
            coalesce(trismegistos_id, '') || ' ' ||
            coalesce(eagle_id, '')
        ), 'B') ||
        setweight(to_tsvector('simple',
            coalesce(source, '') || ' ' ||
            coalesce(source_detail, '') || ' ' ||
            coalesce(bibliography, '') || ' ' ||
            coalesce(notes, '') || ' ' ||
            coalesce(raw_text, '')
        ), 'C')
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_canonical ON inscriptions(canonical);
CREATE INDEX IF NOT EXISTS idx_findspot ON inscriptions(findspot);
CREATE INDEX IF NOT EXISTS idx_date ON inscriptions(date_approx);
CREATE INDEX IF NOT EXISTS idx_language ON inscriptions(language);
CREATE INDEX IF NOT EXISTS idx_classification ON inscriptions(classification);
CREATE INDEX IF NOT EXISTS ix_inscriptions_provenance_status ON inscriptions(provenance_status);
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
    biological_sex TEXT,
    c14_date_range TEXT,
    tomb_id TEXT,
    context_detail TEXT,
    ancestry_components TEXT,
    source TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_genetic_date ON genetic_samples(date_approx);

CREATE TABLE IF NOT EXISTS clans (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    notes TEXT DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    inscription_id TEXT REFERENCES inscriptions(id) ON DELETE CASCADE,
    notes TEXT DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS relationships (
    id SERIAL PRIMARY KEY,
    person_id TEXT REFERENCES entities(id) ON DELETE CASCADE,
    related_person_id TEXT REFERENCES entities(id) ON DELETE CASCADE,
    clan_id TEXT REFERENCES clans(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    CHECK (
        (related_person_id IS NOT NULL AND clan_id IS NULL) OR
        (clan_id IS NOT NULL AND related_person_id IS NULL)
    ),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rel_person ON relationships(person_id);
CREATE INDEX IF NOT EXISTS idx_rel_related ON relationships(related_person_id);
CREATE INDEX IF NOT EXISTS idx_rel_clan ON relationships(clan_id);
CREATE INDEX IF NOT EXISTS idx_ent_inscription ON entities(inscription_id);
"""

_PG_VECTOR_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_emb_text_hnsw
    ON inscriptions USING hnsw ((emb_text::halfvec(3072)) halfvec_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_emb_context_hnsw
    ON inscriptions USING hnsw ((emb_context::halfvec(3072)) halfvec_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_emb_combined_hnsw
    ON inscriptions USING hnsw ((emb_combined::halfvec(3072)) halfvec_cosine_ops);
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
    "zotero_id",
    "is_codex",
]


def _single_insert_sql(has_geom: bool, has_coords: bool) -> str:
    """Build the INSERT statement used by :meth:`Corpus.add`.

    ``has_geom`` says whether the ``inscriptions.geom`` column exists on the
    connected database (it only does where PostGIS is installed; the dev
    stack in ``docker-compose.dev.yml`` ships pgvector without PostGIS).
    When it is absent the statement must not mention ``geom`` at all —
    writing NULL to a missing column is still ``UndefinedColumn``.
    ``has_coords`` only matters when ``has_geom`` is true: it switches the
    geom value between ``ST_MakePoint`` over two extra parameters and NULL.

    Dynamic construction is safe: every fragment derives from the hardcoded
    ``_COLUMNS`` list.
    """
    cols = ", ".join(_COLUMNS)
    placeholders = ", ".join(["%s"] * len(_COLUMNS))
    conflict_updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLUMNS if c != "id")

    if has_geom:
        geom_insert = "ST_SetSRID(ST_MakePoint(%s, %s), 4326)" if has_coords else "NULL"
        insert_cols = f"({cols}, geom)"
        insert_placeholders = f"({placeholders}, {geom_insert})"
        geom_update = ["geom = EXCLUDED.geom,"]
    else:
        insert_cols = f"({cols})"
        insert_placeholders = f"({placeholders})"
        geom_update = []

    query_parts = [
        "INSERT INTO inscriptions",
        insert_cols,
        "VALUES",
        insert_placeholders,
        "ON CONFLICT (id) DO UPDATE SET",
        conflict_updates + ",",
        *geom_update,
        "updated_at = NOW()",
    ]
    return "\n".join(query_parts)


def _batch_insert_sql(has_geom: bool) -> tuple[str, str]:
    """Build the ``(query, row template)`` pair used by :meth:`Corpus.add_batch`.

    Same ``has_geom`` contract as :func:`_single_insert_sql`. With the column
    present, each row carries lon/lat twice over (guard + value) for the
    CASE WHEN template; without it, a row is exactly the ``_COLUMNS`` tuple.
    """
    cols = ", ".join(_COLUMNS)
    conflict_updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLUMNS if c != "id")
    col_placeholders = ", ".join(["%s"] * len(_COLUMNS))

    if has_geom:
        template = (
            f"({col_placeholders}, "
            f"CASE WHEN %s IS NOT NULL AND %s IS NOT NULL "
            f"THEN ST_SetSRID(ST_MakePoint(%s, %s), 4326) "
            f"ELSE NULL END)"
        )
        query = (
            f"INSERT INTO inscriptions ({cols}, geom) VALUES %s "  # nosec B608 # nosemgrep
            f"ON CONFLICT (id) DO UPDATE SET {conflict_updates}, "
            f"geom = EXCLUDED.geom, updated_at = NOW()"
        )
    else:
        template = f"({col_placeholders})"
        query = (
            f"INSERT INTO inscriptions ({cols}) VALUES %s "  # nosec B608 # nosemgrep
            f"ON CONFLICT (id) DO UPDATE SET {conflict_updates}, "
            f"updated_at = NOW()"
        )
    return query, template
