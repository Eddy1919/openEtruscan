<div align="center">

# OpenEtruscan

**Open-source digital corpus platform for Etruscan epigraphy**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Data: CC0](https://img.shields.io/badge/data-CC0-green.svg)](https://creativecommons.org/publicdomain/zero/1.0/)
[![Models: Apache 2.0](https://img.shields.io/badge/models-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![PyPI](https://img.shields.io/pypi/v/openetruscan.svg)](https://pypi.org/project/openetruscan/)

**[open-etruscan.vercel.app](https://open-etruscan.vercel.app)**

</div>

---

## Overview

OpenEtruscan provides computationally accessible tools for the Etruscan epigraphic record. The platform normalises transcriptions across five notation systems, classifies inscriptions using neural models, and publishes the full corpus as Linked Open Data.

The corpus contains 4,728 inscriptions in Etruscan and related Italic scripts, georeferenced to 45 archaeological sites.

## Platform

The web interface is built with Next.js 15 (App Router) and deployed on Vercel. All tools run client-side; no data leaves the user's browser.

| Page | Description |
|---|---|
| [Search](https://open-etruscan.vercel.app/search) | Full-text search with faceted classification filtering and sorting |
| [Concordance](https://open-etruscan.vercel.app/concordance) | Keyword-in-Context (KWIC) display across the entire corpus |
| [Explorer](https://open-etruscan.vercel.app/explorer) | Interactive map of inscription findspots with Old Italic rendering |
| [Timeline](https://open-etruscan.vercel.app/timeline) | Temporal distribution with century range slider |
| [Names](https://open-etruscan.vercel.app/names) | Prosopography network graph of personal name co-occurrences |
| [Normalizer](https://open-etruscan.vercel.app/normalizer) | Convert between CIE, philological, Old Italic, IPA, and web-safe |
| [Classifier](https://open-etruscan.vercel.app/classifier) | Dual-model (CNN vs Transformer) epigraphic classification via ONNX |
| [Compare](https://open-etruscan.vercel.app/compare) | Side-by-side inscription diff with character-level highlighting |
| [Statistics](https://open-etruscan.vercel.app/stats) | Corpus-wide distributions and classification breakdowns |
| [Downloads](https://open-etruscan.vercel.app/downloads) | Corpus JSON/RDF, ONNX models, and language data |

## API

A REST endpoint is available for programmatic normalisation:

```bash
curl -X POST https://open-etruscan.vercel.app/api/normalize \
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
      data/          corpus.json, languages.json
      models/        cnn.onnx, transformer.onnx + metadata
  src/               Python package source
  data/              Corpus data, RDF exports, CIE fascicles
  web/               Legacy static site (deprecated)
  .github/           CI/CD workflows
```

## Linked Open Data

The corpus is published as RDF/Turtle using the LAWD, Dublin Core, and GeoSPARQL ontologies:

- 41 findspots aligned to Pleiades
- 17 findspots aligned to GeoNames
- SPARQL endpoint via Apache Jena Fuseki

## Neural Classification

Two character-level models classify inscriptions into 7 epigraphic types:

| Model | Parameters | Size | Architecture |
|---|---|---|---|
| CharCNN | ~28K | 111 KB | 1D convolution, max-pool, dense |
| Transformer | ~300K | 1.2 MB | 2-layer Transformer encoder, classifier head |

Both models are exported as ONNX and run client-side via WebAssembly. Available on [Hugging Face](https://huggingface.co/Eddy1919/openetruscan-classifier).

## Development

```bash
git clone https://github.com/Eddy1919/openEtruscan.git
cd openEtruscan/frontend
npm install
npm run dev
```

### Deployment

```bash
cd openEtruscan
npx vercel --prod
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
