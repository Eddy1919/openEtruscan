<div align="center">

# OpenEtruscan

**Open-source digital corpus platform for Etruscan epigraphy**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Data: CC0](https://img.shields.io/badge/data-CC0-green.svg)](https://creativecommons.org/publicdomain/zero/1.0/)
[![Models: Apache 2.0](https://img.shields.io/badge/models-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![PyPI](https://img.shields.io/pypi/v/openetruscan.svg)](https://pypi.org/project/openetruscan/)

**[www.openetruscan.com](https://www.openetruscan.com)**

</div>

---

## Overview

OpenEtruscan provides computationally accessible tools for the Etruscan epigraphic record. The platform normalises transcriptions across notation systems, classifies inscriptions using neural models, and publishes the full corpus as Linked Open Data.

The corpus currently contains a unified, verified dataset of **8,091 inscriptions** georeferenced to 191 archaeological sites (including the recent CIE Rescue Integration), with high-fidelity semantic links to Trismegistos, EAGLE, and Pleiades.

The platform follows a decoupled, cloud-native architecture:
- **Data Layer:** PostgreSQL (PostGIS + pgvector) hosted on Google Cloud SQL, featuring 3,072-dimensional `text-embedding-004` semantic embeddings for high-precision epigraphic similarity search.
- **Backend Layer:** FastAPI service on GCE (App VM) serving structured data and neural inference proxies.
- **Frontend Layer:** Next.js 15 (App Router) deployed on Vercel, fetching dynamically from the live production API.

| Page | Description |
|---|---|
| [Search](https://www.openetruscan.com/search) | Full-text search with faceted classification filtering and sorting |
| [Concordance](https://www.openetruscan.com/concordance) | Keyword-in-Context (KWIC) display across the entire corpus |
| [Explorer](https://www.openetruscan.com/explorer) | Interactive map of inscription findspots with Old Italic rendering |
| [Timeline](https://www.openetruscan.com/timeline) | Temporal distribution with century range slider |
| [Names](https://www.openetruscan.com/names) | Prosopography network graph of personal name co-occurrences |
| [Normalizer](https://www.openetruscan.com/normalizer) | Convert between CIE, philological, Old Italic, IPA, and web-safe |
| [Classifier](https://www.openetruscan.com/classifier) | Dual-model (CNN vs Transformer) epigraphic classification via ONNX |
| [Compare](https://www.openetruscan.com/compare) | Side-by-side inscription diff with character-level highlighting |
| [Statistics](https://www.openetruscan.com/stats) | Corpus-wide distributions and classification breakdowns |
| [Downloads](https://www.openetruscan.com/downloads) | Corpus JSON/RDF, ONNX models, and language data |

## API

A REST endpoint is available for programmatic normalisation:

```bash
curl -X POST https://www.openetruscan.com/api/normalize \
  -H "Content-Type: application/json" \
  -d '{"text": "MI AVILES"}'
```

Response:

```json
{
  "canonical": "mi aviles",
  "phonetic": "/mi.aviles/",
  "old_italic": "\ud800\udf0c\ud800\udf09 \ud800\udf00\ud800\udf05\ud800\udf09\ud800\udf0b\ud800\udf04\ud800\udf14",
  "source_system": "cie",
  "tokens": ["mi", "aviles"]
}
```

Other core endpoints:
- `GET /stats/timeline` — Retrieve aggregated spatio-temporal distributions for 11,361 inscriptions
- `GET /clan/{gens}` — Perform prosopographical network search for a localized clan
- `GET /concordance` — Perform Keyword-in-Context (KWIC) search across transcriptions
- `GET /inscriptions/{id}/genetics` — Match inscriptions with archaeogenetic sequences within local spatial radius

## Python Package

```bash
pip install openetruscan
```

```python
from openetruscan import normalize

result = normalize("LARTHAL")
print(result.canonical)   # larθal
print(result.phonetic)    # /lar.tʰal/
print(result.old_italic)  # 𐌓𐌀𐌓𐌈𐌀𐌋
```

## Repository Structure

```
openEtruscan/
  frontend/          Next.js 15 web application (TypeScript, CSS Modules)
    app/             App Router pages and API routes
    components/      Shared UI components (Nav, Footer, CitationExport)
    lib/             Corpus loader, normalizer engine, ONNX classifier
    public/
      data/          languages.json
      models/        cnn.onnx, transformer.onnx + metadata
  src/               Python package source (FastAPI backend + Core library)
  data/              Corpus data, RDF exports, CIE fascicles
  web/               Legacy static site (deprecated)
  .github/           CI/CD workflows
```

## Linked Open Data & Pelagios Network

OpenEtruscan is an official member of the **[Pelagios Network](https://pelagios.org/)** (Contributing to the People, Place, and Registry Working Groups). Our robust Linked Open Data integrations guarantee interoperability with primary external ancient-world DH graphs:

- **11,361 total inscriptions** exported natively via our [Pelagios JSON-LD Endpoint](/pelagios.jsonld)
- 184 dynamic findspots aligned dynamically with [Pleiades](https://pleiades.stoa.org)
- Robust Web Annotations supporting spatial geometries even beneath uncertainty arrays
- 17 findspots aligned to GeoNames
- SPARQL endpoint: Apache Jena Fuseki 5.1 (34,477 triples, SPARQL 1.1)

## Neural Classification

Two character-level models classify inscriptions into 7 epigraphic types:

### 🧠 Intelligence Suite (V2)

The OpenEtruscan Intelligence Suite provides state-of-the-art neural restoration and classification.

- **Lacunae Restoration**: ByT5-based **Scholarly Span Corruption** (LoRA).
- **Inscription Classifier**: Neural MLP achieving **99% Macro F1**.
- **Prosopography**: Neural Entity Disambiguation (NED) using `pgvector`.

Available on [Hugging Face](https://huggingface.co/Eddy1919/openetruscan-classifier).

#### Performance Benchmarks
| Task | Model | Metric | Baseline (V1) | **Intelligence V2** |
| :--- | :--- | :--- | :--- | :--- |
| **Classification** | Embedding MLP | F1-Macro | 0.52 | **0.99** |
| **Restoration** | ByT5-Small | Phil. Safety | Low (Halluc.) | **High (Sentinels)** |

See [Intelligence V2 Methodology](docs/INTELLIGENCE_V2.md) for architectural details.

## Development

```bash
git clone https://github.com/Eddy1919/openEtruscan.git
cd openEtruscan/frontend
npm install
npm run dev
```

### Deployment

**Development & Preview**
Push local dev environment variables and deploy a Preview build:
```bash
# Pull Vercel preview/dev environment variables
npx vercel env pull .env.local

# Deploy to Vercel Preview Environment
npx vercel -y
```

**Production**
Push directly to the live production site and SPARQL endpoint:
```bash
npx vercel --prod -y
```

## Licence

- **Code:** MIT
- **Data:** CC0 1.0 (Public Domain)
- **Models:** Apache 2.0

## Acknowledgements

- Compilers of the *Corpus Inscriptionum Etruscarum*
- The *Etruscan Texts Project* (UMass Amherst)
- The *Larth Dataset* (Vico and Spanakis, 2023)
- The EpiDoc community
- The Classical Language Toolkit

---

<div align="center">

𐌀 𐌁 𐌂 𐌃 𐌄 𐌅 𐌆 𐌇 𐌈 𐌉 𐌊 𐌋 𐌌 𐌍 𐌎 𐌏 𐌐 𐌑 𐌓 𐌔 𐌕 𐌖 𐌗 𐌘 𐌙 𐌚

</div>
