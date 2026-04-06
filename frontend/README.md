# OpenEtruscan Frontend

Next.js 15 (App Router) web application for the OpenEtruscan digital corpus platform. 

The frontend architecture is decoupled from static datasets and now exclusively relies on the live FastAPI backend for dynamically querying the full 11,361-inscription corpus.

## Stack

- **Framework:** Next.js 15 with App Router (TypeScript)
- **Styling:** CSS Modules with custom design tokens (Folio Design System)
- **Maps:** react-leaflet with CartoDB dark tiles
- **Classification:** ONNX Runtime Web (client-side inference) and Server-side Semantic Search (pgvector)
- **Charts:** Chart.js + react-chartjs-2
- **Fonts:** Inter, DM Serif Display, JetBrains Mono (via next/font)
- **Analytics:** Vercel Speed Insights
- **Deployment:** Vercel (CLI-based, from repo root)

## Pages

| Route | Type | Description |
|---|---|---|
| `/` | SSR | Home page with corpus overview |
| `/search` | SSR/Client | Full-text and geospatial search fetching dynamically from the Python API |
| `/concordance` | SSR/Client | KWIC (Keyword-in-Context) concordance viewer (powered by PostgreSQL backend) |
| `/explorer` | Client | Leaflet map with inscription sidebar and PostGIS vector tiles |
| `/timeline` | SSR/Client | Temporal heatmap with century range slider |
| `/names` | Client | Prosopography force-directed graph (network fetched from DB) |
| `/normalizer` | Client | 5-system script normalizer |
| `/classifier` | Client | CNN vs Transformer dual-model comparison |
| `/compare` | Client | Side-by-side inscription diff |
| `/stats` | SSR/Client | Corpus statistics with Chart.js |
| `/downloads` | Static | Download corpus data, models, and language files |
| `/docs` | Static | Technical documentation and resource links |
| `/manifesto` | Static | Project principles and scholarly context |
| `/inscription/[id]` | SSR/SSG | Complete profile for 11,361 individual inscription pages |

## Development

```bash
npm install
npm run dev          # http://localhost:3000
```

*Note: The frontend expects the FastAPI backend to be running on localhost:8000 (configurable via environment variables).*

## Deployment

Deploy from the repository root (not from `frontend/`):

```bash
cd /path/to/openEtruscan
npx vercel --prod
```

The Vercel project has `frontend` configured as the root directory in its dashboard settings.

## Data Assets

- `public/data/languages.json` -- Alphabet tables for 5 Italic scripts
- `public/models/cnn.onnx` -- CharCNN classifier (111 KB)
- `public/models/transformer.onnx` -- Transformer classifier (1.2 MB)
- `public/models/cnn.json`, `transformer.json` -- Model metadata
