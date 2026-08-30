<div align="center">

# OpenEtruscan

**Open-source digital corpus platform and NLP suite for Etruscan epigraphy**

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21854263.svg)](https://doi.org/10.5281/zenodo.21854263)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Data: CC BY 4.0](https://img.shields.io/badge/data-CC%20BY%204.0-green.svg)](https://creativecommons.org/licenses/by/4.0/)
[![Models: Apache 2.0](https://img.shields.io/badge/models-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![PyPI](https://img.shields.io/pypi/v/openetruscan.svg)](https://pypi.org/project/openetruscan/)

**[www.openetruscan.com](https://www.openetruscan.com)**

</div>

---

## Overview

**OpenEtruscan** is an open-source platform for digital epigraphy and computational linguistics applied to the Etruscan epigraphic record. It provides end-to-end tooling to normalise transcriptions across historical notation systems, parse editorial apparatus using standard Leiden conventions, classify inscriptions into epigraphic categories, and publish the corpus as Linked Open Data (LOD).

### Key Features

- **Transcription Normalization & Leiden Parsing**: Converts across historical transliterations (CIE, philological, web-safe) and native Old Italic Unicode script (`𐌄𐌕𐌓𐌖𐌔𐌂𐌀𐌍`), parsing editorial brackets (`[..]`, `(..)`, `⟨..⟩`, `?`) into structured machine-readable metadata.
- **Unified Epigraphic Corpus**: Aggregates records from the *Corpus Inscriptionum Etruscarum* (CIE) and the *Larth Dataset* (Vico & Spanakis, 2023), cross-referenced with Trismegistos, EAGLE, and Pleiades gazetteers.
- **Epigraphic Machine Learning**: Shipped classification models (CharCNN, TF-IDF + Naive Bayes) for epigraphic typology identification (funerary, ownership, dedicatory, boundary, legal, votive, commercial) and neural lacuna restoration.
- **Linked Open Data (LOD)**: Compatible with the Pelagios Network format (Web Annotation JSON-LD), PeriodO temporal authorities, and Pleiades geospatial alignments.
- **Python CLI & API**: Command-line tool and Python library for script conversion, batch normalization, dataset export, and EpiDoc/TEI XML generation.
- **Modern Web Application**: Interactive exploration via [openetruscan.com](https://www.openetruscan.com) with faceted search, KWIC concordance, geospatial explorer, prosopography network graph, and timeline analysis.

---

## The Corpus

OpenEtruscan tracks three precisely defined corpus numbers:

- **6,633 unified inscriptions** (Archival corpus): The complete unified dataset combining the *Larth Dataset* (~71%) and *CIE Vol. I* extractions (~29%).
- **6,567 published inscriptions** (Zenodo deposit): The cleaned dataset released on Zenodo (DOI: [10.5281/zenodo.21854263](https://doi.org/10.5281/zenodo.21854263)), after dropping 66 malformed or empty rows.
- **5,932 deployed inscriptions** (Live production database): The deduplicated production corpus served at [openetruscan.com](https://www.openetruscan.com) and through the Pelagios JSON-LD feed.

Every count is maintained and verified via [`release-manifest.json`](release-manifest.json).

### Archaeological Provenance

To maintain scientific integrity, OpenEtruscan explicitly distinguishes **editorial attestation** (a verified reading in philological literature) from **archaeological findspot context** (documented excavation location):

| Tier | Archival Count (6,633) | Share | Definition |
|---|---:|---:|---|
| `acquired_documented` | 2,317 | 34.9% | A findspot or region is recorded in source bibliography (suitable for spatial analysis). |
| `acquired_undocumented` | 4,316 | 65.1% | Attested in epigraphic literature, but without verified discovery coordinates. |
| `excavated` | 0 | 0.0% | Stratigraphically excavated with full modern context (reserved for manual curatorial curation). |
| `unknown` | 0 | 0.0% | Unassessed records. |

*Note: In the live database (5,932 records), 2,203 are documented and 3,729 undocumented. The `/search` interface defaults to documented findspots via `?has_provenance=true`.*

---

## Python Package & CLI

Install the core Python library and CLI:

```bash
pip install openetruscan          # Core library + CLI
pip install 'openetruscan[neural]' # Neural classifiers (PyTorch + ONNX)
pip install 'openetruscan[server]' # Local development FastAPI server
pip install 'openetruscan[all]'    # Full stack including transformers
```

### Python Library Usage

```python
from openetruscan import normalize, convert

# Normalise historical transliterations and parse Leiden apparatus
result = normalize("LARTHAL [VEL]CHAS")

print(result.canonical)   # "larθal velchas"
print(result.phonetic)    # "/lar.tʰal vel.kʰas/"
print(result.old_italic)  # "𐌋𐌀𐌓𐌈𐌀𐌋 𐌅𐌄𐌋𐌙𐌀𐌔"
print(result.apparatus)   # Structured list of editorial annotations
```

### Command-Line Interface (CLI)

The `openetruscan` command provides a suite of epigraphic utilities:

| Command | Description |
|---|---|
| `openetruscan normalize "TEXT"` | Canonicalise transcription and output phonetic/script representations (`--json-output`). |
| `openetruscan convert "TEXT"` | Transliterate between Latin alphabet and Old Italic script (`--to old_italic`). |
| `openetruscan validate FILE.csv` | Lint inscription files for orthography and schema compliance. |
| `openetruscan batch INPUT.csv` | Bulk-normalise files and export to CSV, JSON, or JSONL. |
| `openetruscan search QUERY` | Search local database records with fuzzy and boolean filters. |
| `openetruscan epidoc "TEXT"` | Convert Leiden-annotated text into EpiDoc/TEI XML elements. |
| `openetruscan export-corpus` | Export corpus to CSV, JSONL, EpiDoc TEI XML, or RDF. |
| `openetruscan classify "TEXT"` | Classify inscription into epigraphic typology (funerary, ownership, etc.). |
| `openetruscan train-neural` | Train CharCNN / Transformer classification heads on local splits. |
| `openetruscan list-adapters` | List installed language adapters (Etruscan, Oscan, Faliscan, etc.). |

---

## Web Platform & Public API

The web application is hosted at **[www.openetruscan.com](https://www.openetruscan.com)**.

### Web Modules

- **[Search](https://www.openetruscan.com/search)**: Full-text and faceted search with orthographic expansion.
- **[Concordance (KWIC)](https://www.openetruscan.com/concordance)**: Keyword-in-Context browser across the entire corpus.
- **[Map Explorer](https://www.openetruscan.com/explorer)**: Interactive findspot mapping with Pleiades links and temporal filters.
- **[Prosopography (Names)](https://www.openetruscan.com/names)**: Network graph of co-occurring gens and praenomina.
- **[Normalizer](https://www.openetruscan.com/normalizer)**: Web-based 5-system transliteration and script converter.
- **[Classifier](https://www.openetruscan.com/classifier)**: Real-time dual-model epigraphic classification (ONNX Web).
- **[Diff & Compare](https://www.openetruscan.com/compare)**: Side-by-side inscription diff with character-level alignment.
- **[Downloads](https://www.openetruscan.com/downloads)**: Corpus dumps (JSON, CSV, RDF, ONNX models).

### REST API Example

Normalise text programmatically:

```bash
curl -X POST https://www.openetruscan.com/api/normalize \
  -H "Content-Type: application/json" \
  -d '{"text": "MI AVILES"}'
```

```json
{
  "canonical": "mi aviles",
  "phonetic": "/mi.aviles/",
  "old_italic": "𐌌𐌉 𐌀𐌅𐌉𐌋𐌄𐌔",
  "source_system": "cie",
  "tokens": ["mi", "aviles"]
}
```

Core endpoints:
- `GET /api/inscription/{id}`: Detailed inscription metadata, apparatus, findspot, and Pleiades alignments.
- `GET /api/stats/timeline`: Aggregated temporal distributions across centuries.
- `GET /api/clan/{gens}`: Onomastic network data for a family name.
- `GET /api/pelagios.jsonld`: Pelagios-compatible Web Annotation collection (5,932 inscriptions).

---

## Machine Learning & Evaluation

OpenEtruscan provides pre-trained models and a pre-registered benchmarking harness for epigraphic NLP tasks. Full replication workflows, frozen stratified splits, and raw outputs are documented in [`research/v2/`](research/v2/) and [`docs/INTELLIGENCE_V2.md`](docs/INTELLIGENCE_V2.md).

### 1. Inscription Typology Classification (7-Class Task)

Evaluated on the v2.0.4 text-disjoint candidate-gold benchmark (n=167, 3-rater consensus, 10,000-resample bootstrap):

| Architecture | Parameters | Macro F1 (95% CI) | Accuracy | Notes |
|---|---|---|---|---|
| **CharCNN** | 28K | **0.399** (0.353 – 0.435) | 0.665 | Character convolutions capture morphological affixes (`-al`, `-as`, `-ce`). |
| **TF-IDF + Naive Bayes** | ~3K | **0.293** (0.255 – 0.329) | 0.755 | Fast baseline model shipped in library core (`ml/classifier.py`). |
| **MicroTransformer** | 274K | **0.252** (0.140 – 0.338) | 0.317 | Character-level transformer encoder. |
| **EmbeddingMLP** | 58K + encoder | **0.210** (0.181 – 0.242) | 0.641 | Multilingual MiniLM embeddings + MLP head. |

### 2. Lacuna Restoration

Evaluated on 66 clean-gold single/multi-character gap restoration tasks (Leiden `[abc]` spans):

| Model | Span Exact-Match (95% CI) | Char Accuracy Top-1 (95% CI) | Hallucination Rate |
|---|---|---|---|
| **Claude Opus 4.8** | **0.288** (0.182 – 0.394) | **0.341** (0.235 – 0.449) | 0.0% (mechanical span isolation) |
| **Gemini 3.1 Pro** | 0.258 (0.161 – 0.371) | 0.315 (0.210 – 0.426) | 16.1% (0.081 – 0.258) |
| **Gemini 3.5 Flash** | 0.258 (0.152 – 0.364) | 0.278 (0.178 – 0.389) | 54.5% (0.424 – 0.667) |

---

## Linked Open Data & Standards Compliance

- **Pelagios Network**: Published as a Web Annotation collection at `/pelagios.jsonld` and described by the VoID dataset descriptor at `/void.ttl`.
- **Pleiades Gazetteer**: Geospatial coordinates linked to stable Pleiades URIs for all documented findspots.
- **PeriodO**: Chronological ranges mapped to PeriodO authority URIs (e.g., MAPPA Lab Tuscany model).
- **EpiDoc / TEI XML**: Export format for digital humanities interoperability.

---

## Repository Architecture

```
openEtruscan/
├── src/openetruscan/    # Python package source: normalizer, Leiden parser, EpiDoc, ML, DB
│   ├── core/           # Transliteration adapters, Leiden apparatus parser, gazetteer, PeriodO
│   ├── ml/             # TF-IDF, CharCNN, and transformer classification modules
│   ├── db/             # SQLAlchemy ORM models & Alembic migration scripts
│   └── api/            # Local FastAPI server (parity reference)
├── research/           # Research codebooks, frozen splits, evaluation benchmarks (v2)
├── eval/               # Evaluation harnesses and benchmark definitions
├── scripts/            # Data pipeline, database ingestion, and maintenance utilities
├── services/           # Cloud Run inference services (ByT5 restorer, reranker)
├── tests/              # Comprehensive pytest test suite
└── docs/               # Architecture, reproduction, and technical guides
```

The web application and production TypeScript API live in the companion repository: [`openEtruscan-frontend`](https://github.com/Eddy1919/openEtruscan-frontend).

---

## Development

```bash
# Clone repository
git clone https://github.com/Eddy1919/openEtruscan.git
cd openEtruscan

# Install in development mode with uv (or pip install -e ".[dev]")
uv sync --extra dev

# Run test suite
pytest

# Verify manifest and documentation consistency
uv run python scripts/ops/check_release_truth.py
```

To set up a local Postgres + pgvector development database:

```bash
docker compose -f docker-compose.dev.yml up -d db
DATABASE_URL=postgresql://openetruscan:openetruscan@localhost:5432/openetruscan pytest
```

---

## Citation

If you use OpenEtruscan in your research, please cite both the software and the dataset:

```bibtex
@software{openetruscan_2026,
  author    = {Panichi, Edoardo},
  title     = {{OpenEtruscan: Open-source digital corpus platform and NLP suite for Etruscan epigraphy}},
  year      = {2026},
  version   = {1.3.1},
  doi       = {10.5281/zenodo.21854263},
  url       = {https://doi.org/10.5281/zenodo.21854263},
  publisher = {Zenodo}
}
```

- **Concept DOI (latest version)**: [10.5281/zenodo.20075835](https://doi.org/10.5281/zenodo.20075835)
- **Version DOI (v1.1.0 deposit)**: [10.5281/zenodo.21854263](https://doi.org/10.5281/zenodo.21854263)

---

## License

- **Software**: [MIT License](LICENSE)
- **Corpus Data**: [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)
- **Machine Learning Models**: [Apache 2.0 License](https://www.apache.org/licenses/LICENSE-2.0)

---

## Acknowledgements

- Compilers of the *Corpus Inscriptionum Etruscarum* (CIE)
- *Etruscan Texts Project* (ETP, University of Massachusetts Amherst)
- *Larth Dataset* (Vico & Spanakis, 2023)
- The EpiDoc and Pelagios Network communities
- Classical Language Toolkit (CLTK)
