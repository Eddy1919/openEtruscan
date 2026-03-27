# OpenEtruscan Frontend

Next.js 15 (App Router) web application for the OpenEtruscan digital corpus platform.

## Stack

- **Framework:** Next.js 15 with App Router (TypeScript)
- **Styling:** CSS Modules with custom design tokens
- **Maps:** react-leaflet with CartoDB dark tiles
- **Classification:** ONNX Runtime Web (client-side inference)
- **Charts:** Chart.js + react-chartjs-2
- **Fonts:** Inter, DM Serif Display, JetBrains Mono (via next/font)
- **Analytics:** Vercel Speed Insights
- **Deployment:** Vercel (CLI-based, from repo root)

## Pages

| Route | Type | Description |
|---|---|---|
| `/` | Static | Home page with corpus overview |
| `/search` | Client | Full-text search with faceted classification sidebar |
| `/concordance` | Client | KWIC (Keyword-in-Context) concordance viewer |
| `/explorer` | Client | Leaflet map with inscription sidebar |
| `/timeline` | Client | Temporal heatmap with century range slider |
| `/names` | Client | Prosopography force-directed graph |
| `/normalizer` | Client | 5-system script normalizer |
| `/classifier` | Client | CNN vs Transformer dual-model comparison |
| `/compare` | Client | Side-by-side inscription diff |
| `/stats` | Client | Corpus statistics with Chart.js |
| `/downloads` | Static | Download corpus data, models, and language files |
| `/docs` | Static | Technical documentation and resource links |
| `/manifesto` | Static | Project principles and scholarly context |
| `/inscription/[id]` | SSG | 4,728 individual inscription pages with citation export |
| `/api/normalize` | API | REST endpoint for programmatic normalisation |

## Development

```bash
npm install
npm run dev          # http://localhost:3000
```

## Deployment

Deploy from the repository root (not from `frontend/`):

```bash
cd /path/to/openEtruscan
npx vercel --prod
```

The Vercel project has `frontend` configured as the root directory in its dashboard settings.

## Data

- `public/data/corpus.json` -- 4,728 inscriptions
- `public/data/languages.json` -- Alphabet tables for 5 Italic scripts
- `public/models/cnn.onnx` -- CharCNN classifier (111 KB)
- `public/models/transformer.onnx` -- Transformer classifier (1.2 MB)
- `public/models/cnn.json`, `transformer.json` -- Model metadata
