# OpenEtruscan Platform Architecture

OpenEtruscan is a decoupled, multi-tier digital humanities platform designed for high-performance epigraphic analysis.

## Core Stack Overview

```mermaid
graph TD
    subgraph Frontend [Next.js 15 Client]
        A[App Router] --> B[React Components]
        B --> C[Leaflet Maps]
        B --> D[Chart.js Stats]
        B --> E[ONNX Runtime Web]
    end

    subgraph Backend [FastAPI Python Server]
        F[FastAPI Router] --> G[Limiter/Middleware]
        F --> H[InscriptionRepository]
        H --> I[SQLAlchemy Async]
        F --> J[Normalizer Engine]
        F --> K[ML/Classifier Inference]
    end

    subgraph Data [PostgreSQL + PostGIS + pgvector]
        L[(Consolidated Database)]
        I --> L
        L --> M[PostGIS ST_AsMVT]
        L --> N[pgvector HNSW]
    end

    Frontend -- REST API --> Backend
    Backend -- Vector Tiles (PBF) --> Frontend
```

## Component Breakdown

### 1. The Normalizer Engine (`core/normalizer.py`)
The "heart" of the system. It handles the transformation of varied epigraphic transcription systems into a canonical phonological representation.

```mermaid
sequenceDiagram
    participant U as User Input
    participant D as Detector
    participant P as Preprocessor (LaTeX/Unicode)
    participant F as Folder (Variants -> Canonical)
    participant V as Validator (Phonotactics)
    participant O as Output (IPA/Unicode)

    U->>D: Raw String
    D->>P: Identification
    P->>F: Clean Transliteration
    F->>V: Canonical Mapping
    V->>O: Result Object
```

### 2. Database Layer (`db/repository.py`)
A strictly decoupled repository pattern using `SQLAlchemy 2.0` and `pgvector`.
- **Spatial**: Native PostGIS integration for proximity searches (`genetic_samples` x `inscriptions`).
- **Semantic**: Uses `halfvec(3072)` embeddings for cosine similarity across 11,361 records.
- **Tiles**: Direct `ST_AsMVT` generation for high-performance mapping of tens of thousands of points.

### 3. API Middleware (`api/server.py`)
- **Rate Limiting**: Per-endpoint windowed limiting using `slowapi`.
- **Content Negotiation**: Support for JSON, CSV, and GeoJSON exports.
- **Documentation**: Automatic OpenAPI 3.1 generation with Pydantic v2 schemas.

## Data Flow: Search Request

```mermaid
flowchart LR
    A[Client UI] --> B{Search Type?}
    B -- Full Text --> C[PG FTS tsvector]
    B -- Semantic --> D[Gemini Embedding + pgvector]
    B -- Spatial --> E[PostGIS ST_DWithin]
    C --> F[Repository Aggregation]
    D --> F
    E --> F
    F --> G[JSON Response]
```
