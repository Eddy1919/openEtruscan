<div align="center">

# 𐌏𐌐𐌄𐌍 𐌄𐌕𐌓𐌖𐌔𐌂𐌀𐌍

# OpenEtruscan

**Open-source tools for ancient epigraphy — built for Etruscan, designed to be copied.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/Eddy1919/openEtruscan/actions/workflows/ci.yml/badge.svg)](https://github.com/Eddy1919/openEtruscan/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/openetruscan.svg)](https://pypi.org/project/openetruscan/)
[![Data: CC0](https://img.shields.io/badge/data-CC0-green.svg)](https://creativecommons.org/publicdomain/zero/1.0/)

🌐 **Live at [openetruscan.com](https://openetruscan.com)**

*Normalize · Search · Map · Export · Contribute*

</div>

---

## What Is This?

OpenEtruscan is a Python toolkit that solves the **transcription chaos** in Etruscan studies. The same word appears as 5+ incompatible forms across publications — making cross-corpus search impossible.

We fix that. One `pip install`, zero servers, works offline forever.

```python
from openetruscan import normalize

# Input in ANY transcription system
result = normalize("LARTHAL")       # CIE standard
result = normalize("Larθal")        # Philological
result = normalize("𐌓𐌀𐌓𐌈𐌀𐌋")  # Unicode Old Italic

# Always get the same canonical output
print(result.canonical)   # → "larθal"
print(result.phonetic)    # → "/lar.tʰal/"
print(result.old_italic)  # → "𐌓𐌀𐌓𐌈𐌀𐌋"
```

## Quick Start

```bash
pip install openetruscan
```

### Normalize a text

```bash
openetruscan normalize "LARTHAL LECNES"
```

### Batch process a file

```bash
openetruscan batch corpus.txt --format csv --output clean.csv
```

### Validate encoding

```bash
openetruscan validate my_transcription.txt
```

### Run the API + Web UI locally

```bash
pip install openetruscan[all]
uvicorn openetruscan.server:app --reload
# Open http://localhost:8000/web/index.html
```

## Why?

| Problem | Today | With OpenEtruscan |
|---|---|---|
| "Where else does this word appear?" | Flip through 300 pages of print volumes | `corpus.search(text="*al lecn*")` |
| "Is this spelling a dialect variant?" | An entire journal article to pose the question | One query, 30 seconds |
| "I need to publish my thesis data" | Word doc, usable only by the author | `openetruscan batch thesis.txt --format epidoc` → PR → global corpus |
| "How widespread was this clan?" | Months of manual index-reading | `corpus.names.search(gens="lecne")` → interactive map |

## Architecture

The core engine is **language-agnostic**. Each language is a YAML config file:

```
openetruscan/
├── engine/          # Universal normalizer, parser, exporter
├── adapters/
│   ├── etruscan.yaml    # Etruscan alphabet, phonotactics, names
│   ├── oscan.yaml       # Same engine, different YAML
│   ├── faliscan.yaml    # ... add any ancient script
│   └── YOUR_LANG.yaml   # Fork this pattern
├── corpus/          # Structured dataset (Local SQLite / Cloud PostgreSQL)
├── prosopography/   # NLP name parser + kinship graph + Neo4j export
└── exporters/       # EpiDoc XML, CSV, JSON-LD, GeoJSON
```

**Want to support another language?** Write 50 lines of YAML. The engine does the rest.

## Web Interface

OpenEtruscan ships with three interconnected browser-based tools, live at [openetruscan.com](https://openetruscan.com):

| Page | Description |
|---|---|
| **Normalizer** ([`index.html`](web/index.html)) | Convert any Etruscan text between transcription systems in real time |
| **Search** ([`search.html`](web/search.html)) | Full-text search across the corpus with clickable Clan network badges |
| **Map** ([`map.html`](web/map.html)) | Interactive Leaflet map of inscription findspots across Etruria |

## Self-Hosting

OpenEtruscan is designed for easy self-hosting. Copy the `docker-compose.yml` and you're done:

```bash
git clone https://github.com/Eddy1919/openEtruscan.git
cd openEtruscan
cp .env.example .env    # Edit with your DATABASE_URL
docker compose up -d --build
```

See [`.env.example`](.env.example) for all configuration options. By default, OpenEtruscan runs in **zero-config mode** with a bundled SQLite database — no external database required.

## Packages

| Package | Description | Status |
|---|---|---|
| `openetruscan` (core) | Normalizer + CLI + adapters | ✅ Released |
| `openetruscan[corpus]` | Structured dataset + query API | ✅ Released |
| `openetruscan[prosopography]` | NLP name parser + kinship graph | ✅ Released |
| `openetruscan[server]` | FastAPI backend + Web UI | ✅ Released |
| `openetruscan[all]` | Everything | ✅ Released |

## Contributing

We welcome contributions from epigraphers, linguists, and developers alike. See [CONTRIBUTING.md](CONTRIBUTING.md) for full details.

**Quick paths:**

- 📝 **Add data** — submit new inscriptions via CSV or CLI
- 🔤 **Improve mappings** — fix transliteration rules in the YAML adapters
- 🌍 **Add a language** — copy a YAML adapter, fill in your script
- 🐛 **Report bugs** — open an issue with reproduction steps
- 💻 **Write code** — fork, hack, PR

```bash
git clone https://github.com/Eddy1919/openEtruscan.git
cd openEtruscan
pip install -e ".[dev]"
pytest
```

## Roadmap

### ✅ Done

- [x] **Normalizer engine** — auto-detect 5 transcription systems, fold to canonical, phonotactic validation
- [x] **CLI** — `normalize`, `batch`, `convert`, `validate`, `adapters` commands
- [x] **Multi-language adapters** — Etruscan, Oscan, Faliscan (23+ letters, 35+ names, equivalence classes)
- [x] **Corpus database** — SQLite + PostgreSQL, 4,700+ inscriptions from Larth dataset
- [x] **Prosopography engine** — NLP name parser, 633 clans, kinship graph, Neo4j Cypher + GraphML export
- [x] **Web UI** — Normalizer, full-text Search, interactive Map with clan network visualization
- [x] **Production deployment** — Docker + Nginx + HTTPS on [openetruscan.com](https://openetruscan.com)
- [x] **CI/CD** — GitHub Actions (test on Python 3.10–3.13, auto-deploy, PyPI publish)
- [x] **65 tests** passing across all modules

### 🔜 Next

- [ ] **EpiDoc XML exporter** — interoperability with the digital classics ecosystem
- [ ] **Corpus CLI** — `openetruscan search`, `openetruscan import`, `openetruscan export` commands
- [ ] **Rhaetic + Lemnian adapters** — expand to the Tyrsenian language family

### 🗓️ Planned

- [ ] **CLTK Etruscan module** — contribute to the [Classical Language Toolkit](https://cltk.org)
- [ ] **Linked Open Data** — publish to [Pelagios](https://pelagios.org)/[Pleiades](https://pleiades.stoa.org) gazetteers
- [ ] **Statistical tools** — letter frequency analysis, dialect clustering, dating heuristics

## License

- **Code:** [MIT](LICENSE) — do whatever you want
- **Data:** [CC0](https://creativecommons.org/publicdomain/zero/1.0/) — public domain, no restrictions

## Acknowledgments

OpenEtruscan builds on decades of work by epigraphers and Etruscologists. We are especially grateful to:

- The compilers of the [Corpus Inscriptionum Etruscarum](https://www.studietruschi.org)
- The [Etruscan Texts Project](https://etp.classics.umass.edu) (UMass Amherst)
- The [Larth Dataset](https://github.com/gianlucavico/Larth) (Vico & Spanakis, 2023)
- The [EpiDoc](https://epidoc.stoa.org) community
- The [Classical Language Toolkit](https://cltk.org)

---

<div align="center">

*Built for Etruscan. Designed to be copied.*

𐌀 𐌁 𐌂 𐌃 𐌄 𐌅 𐌆 𐌇 𐌈 𐌉 𐌊 𐌋 𐌌 𐌍 𐌎 𐌏 𐌐 𐌑 𐌓 𐌔 𐌕 𐌖 𐌗 𐌘 𐌙 𐌚

</div>
