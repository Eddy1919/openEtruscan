<div align="center">

# 𐌏𐌐𐌄𐌍 𐌄𐌕𐌓𐌖𐌔𐌂𐌀𐌍

# OpenEtruscan

**Open-source tools for ancient epigraphy — built for Etruscan, designed to be copied.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Data: CC0](https://img.shields.io/badge/data-CC0-green.svg)](https://creativecommons.org/publicdomain/zero/1.0/)

*Normalize · Search · Export · Contribute*

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

## Why?

| Problem | Today | With OpenEtruscan |
|---|---|---|
| "Where else does this word appear?" | Flip through 300 pages of print volumes | `corpus.search(text="*al lecn*")` |
| "Is this spelling a dialect variant?" | An entire journal article to pose the question | One query, 30 seconds |
| "I need to publish my thesis data" | Word doc, usable only by the author | `openetruscan batch thesis.txt --format epidoc` → PR → global corpus |
| "How widespread was this clan?" | Months of manual index-reading | `corpus.names.search(gens="lecne")` → map |

## Architecture

The core engine is **language-agnostic**. Each language is a YAML config file:

```
openetruscan/
├── engine/          # Universal normalizer, parser, exporter
├── adapters/
│   ├── etruscan.yaml    # Etruscan alphabet, phonotactics, names
│   ├── oscan.yaml       # Same engine, different YAML
│   ├── rhaetic.yaml     # ... add any ancient script
│   └── YOUR_LANG.yaml   # Fork this pattern
├── corpus/          # Structured dataset (Local SQLite / Cloud PostgreSQL)
├── prosopography/   # Name parser + kinship graph
└── exporters/       # EpiDoc XML, CSV, JSON-LD, GeoJSON
```

**Want to support another language?** Write 50 lines of YAML. The engine does the rest.

## Infrastructure & Configuration

OpenEtruscan supports two deployment modes via the `.env` file (see `.env.example`):

1. **Zero-Config Local (SQLite)**: By default, OpenEtruscan bundles its entire corpus as a local SQLite database (`data/corpus.db`). It works offline, has zero infrastructure costs, and requires no setup.
2. **Cloud Public (PostgreSQL)**: To connect to our live public Cloud SQL instance, set `DATABASE_URL` in your `.env`. The cloud instance features abuse protection (a read-only `corpus_reader` role) so anyone can query the most up-to-date data directly.

```bash
# Example .env connection (replace <PASSWORD> with actual password)
DATABASE_URL=postgresql://corpus_reader:<PASSWORD>@34.76.146.115/corpus
```

## Contributing

### Add Data

Found a new inscription? Have a dissertation corpus?

1. Fork this repo
2. Add entries to `data/contributions/your_name.csv`
3. Run `openetruscan validate data/contributions/your_name.csv`
4. Open a Pull Request
5. CI validates encoding + duplicates
6. We merge → your data is in the next release

Your name stays in the Git history. Your discovery becomes searchable worldwide.

### Add a Language

1. Copy `src/openetruscan/adapters/etruscan.yaml`
2. Fill in your language's alphabet, variants, phonotactics
3. Run `pytest` to verify
4. Open a Pull Request

### Improve the Code

```bash
git clone https://github.com/open-etruscan/openetruscan.git
cd openetruscan
pip install -e ".[dev]"
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## Packages

| Package | Description | Status |
|---|---|---|
| `openetruscan` (core) | Normalizer + CLI + adapters | ✅ Released |
| `openetruscan[corpus]` | Structured dataset + query API | ✅ Released |
| `openetruscan[prosopography]` | Name parser + kinship graph | ✅ Released |
| `openetruscan[all]` | Everything | ✅ Released |

## Roadmap

### ✅ Done

- [x] **Normalizer engine** — auto-detect 5 transcription systems, fold to canonical, phonotactic validation
- [x] **CLI** — `normalize`, `batch`, `convert`, `validate`, `adapters` commands
- [x] **Etruscan adapter** — 23 letters, 35+ known names, equivalence classes
- [x] **Corpus database** — SQLite-backed, 4,700+ inscriptions from Larth dataset
- [x] **Prosopography** — name parser, 633 clans, kinship graph, GraphML/JSON export
- [x] **Web converter** — static HTML/CSS/JS, runs in any browser, zero backend
- [x] **GitHub Actions** — CI (Python 3.10-3.13 + Ruff), Pages deploy, PyPI publish
- [x] **64 tests** passing across all modules

### 🔜 Next (v0.2)

- [ ] **Faliscan + Oscan adapters** — prove the multi-language architecture (one YAML each)
- [ ] **Web language selector** — switch between languages in the web converter
- [x] **GeoJSON map viewer** — interactive Leaflet map of inscription findspots ([`web/map.html`](web/map.html))
- [ ] **EpiDoc XML exporter** — interoperability with the digital classics ecosystem
- [x] **PyPI release** — first public `pip install openetruscan`
- [ ] **Corpus CLI** — `openetruscan search`, `openetruscan import`, `openetruscan export` commands

### 🗓️ Planned (v0.3)

- [ ] **CLTK Etruscan module** — contribute to the [Classical Language Toolkit](https://cltk.org)
- [ ] **Linked Open Data** — publish to [Pelagios](https://pelagios.org)/[Pleiades](https://pleiades.stoa.org) gazetteers
- [ ] **Statistical tools** — letter frequency analysis, dialect clustering, dating heuristics
- [ ] **Web search interface** — search the corpus from the browser (static, no backend)
- [ ] **Rhaetic + Lemnian adapters** — expand to the Tyrsenian language family

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
