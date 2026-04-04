-- OpenEtruscan: PostgreSQL extensions init
-- Auto-run on first DB boot via docker-entrypoint-initdb.d

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- trigram similarity for fuzzy text search
