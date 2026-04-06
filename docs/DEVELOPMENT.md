# OpenEtruscan Development Guide

This guide details how to set up, maintain, and expand the OpenEtruscan ecosystem.

## Environment Setup

### 1. Backend (FastAPI)
The backend requires Python 3.10+ and a PostgreSQL 15+ database with `PostGIS` and `pgvector` extensions.

```bash
# Clone the repository
git clone https://github.com/Eddy1919/openEtruscan.git
cd openEtruscan

# Install dependencies (use [all] for ML support)
pip install -e "."
pip install -r requirements-dev.txt
```

### 2. Frontend (Next.js)
```bash
cd frontend
npm install
npm run dev
```

## Database Migrations

OpenEtruscan uses **Alembic** for SQLAlchemy schema versioning.

```mermaid
graph LR
    A[models.py] -- autogenerate --> B[Revision Script]
    B -- upgrade --> C[PostgreSQL Schema]
```

To create a new migration:
```bash
# Point alembic to the core database
export DATABASE_URL="postgresql://user:password@localhost:5432/openetruscan"
alembic revision --autogenerate -m "Add new column"
alembic upgrade head
```

## Classification Training

The CharCNN and Transformer models are trained on the `src/openetruscan/ml` modules.

```mermaid
flowchart TD
    A[Raw Corpus] --> B[Normalizer]
    B --> C[Canonical Text]
    C --> D[Synthetic Augmentation]
    D --> E[Neural Trainer]
    E --> F[ONNX Export]
    F --> G[Frontend public/models]
```

To re-export models for the frontend:
```bash
# Training a specific language model
python -m openetruscan.ml.trainer --language etruscan --export true
```

## Deployment

Deploying the stack to Vercel and Google Cloud:

```mermaid
graph TD
    A[Local Push] --> B{GHA CI}
    B -- Build --> C[Next.js App]
    B -- Test --> D[FastAPI Server]
    C --> E[Vercel]
    D --> F[Cloud Run]
```

- **Frontend**: Vercel (CLI)
- **Backend**: Google Cloud Run (Dockerized)
- **Database**: Cloud SQL with PostGIS
