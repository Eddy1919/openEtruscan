<div align="center">

# OpenEtruscan

**Open-source digital corpus platform for Etruscan epigraphy**

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20075836.svg)](https://doi.org/10.5281/zenodo.20075836)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Data: CC0](https://img.shields.io/badge/data-CC0-green.svg)](https://creativecommons.org/publicdomain/zero/1.0/)
[![Models: Apache 2.0](https://img.shields.io/badge/models-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![PyPI](https://img.shields.io/pypi/v/openetruscan.svg)](https://pypi.org/project/openetruscan/)

**[www.openetruscan.com](https://www.openetruscan.com)**

</div>

---

## Overview

OpenEtruscan is an open-source platform for working with the Etruscan epigraphic record. It normalises transcriptions across notation systems (including structured Leiden-convention parsing of restorations, gaps, and unclear readings), classifies inscriptions into epigraphic types (macro F1 in the 0.31–0.37 band on a held-out set, with overlapping CIs across architectures from ~3K to 274K parameters — no model separates from the field; TF-IDF + Naïve Bayes is the production reference), and publishes the full corpus as Linked Open Data.

The corpus holds **6,633 unified inscriptions**, drawn mostly from the *Larth Dataset* (Vico & Spanakis, 2023; ~71%) and the *Corpus Inscriptionum Etruscarum* (Vol. I extractions; ~29%), with links to Trismegistos, EAGLE, and Pleiades. The cleaned, ML-ready dataset published on Zenodo is a 6,567-row subset (66 rows dropped during cleaning).

### Provenance disclosure

OpenEtruscan separates **editorial verification of a text** (we trust the published reading) from **archaeological provenance** (we know where the inscribed object actually surfaced). These are two different scholarly claims and each row carries a `provenance_status` in one of four tiers:

| Tier | Count | Share | Meaning |
|---|---:|---:|---|
| `acquired_documented` | 2,317 | 34.9% | A findspot is named in the source bibliography. Suitable for spatial citation. The deeper archaeological context (stratum, excavator, associated finds) is generally not recorded. |
| `acquired_undocumented` | 4,316 | 65.1% | The text is attested in the philological literature but no findspot is recorded. Treat as **unprovenanced**; cite with care. |
| `excavated` | 0 | 0.0% | Stratigraphically excavated with a published find context. Reserved for curatorial promotion of individual records — not assigned by automatic heuristic. |
| `unknown` | 0 | 0.0% | Not yet assessed. |

The `/search` endpoint accepts `?has_provenance=true` to restrict to the first two tiers, and the website's search UI defaults to that filter. The `/stats/provenance` endpoint returns the live breakdown.

The "184 archaeological sites" referenced in earlier copy is the count of distinct findspot strings across the **34.9% with documented provenance** — not across the whole corpus.

The platform follows a decoupled, cloud-native architecture (as of 2026-05-24):

- **Data Layer** — PostgreSQL (PostGIS + pgvector) on **Neon** serverless (was Cloud SQL, migrated). 3,072-dimensional `text-embedding-004` semantic embeddings for high-precision similarity search.
- **Public HTTP API** — **Vercel Functions** (TypeScript + Drizzle ORM + Neon serverless driver) co-located in the [`openetruscan-frontend`](https://github.com/Eddy1919/openEtruscan-frontend) repo under `app/api/*`. Single-origin, no cross-cloud hop. See `https://www.openetruscan.com/api/{search,inscription/[id],stats/summary,concordance,clan/[gens],radius,search/geo,names/network,anchors/…}`.
- **Web app** — Next.js 16 on Vercel, with the mobile path shipping as RSC + `useSyncExternalStore`-gated dynamic-import islands (Lighthouse a11y 100, perf 92 mobile / 99 desktop).
- **Python `openetruscan` package** (this repo) — **CLI + research-pipeline source of truth**. `pip install openetruscan` ships the 14-command CLI (`normalize`, `classify`, `train-neural`, `export-corpus`, `epidoc`, etc.) plus the `src/openetruscan/api/` FastAPI surface used for parity testing and local development. The live public HTTP API no longer runs from this codebase.
- **Research pipelines** — Cloud Build orchestrators (`cloudbuild/v2-classify-jury.yaml`, `v2-lacuna-jury.yaml`) drove the v2.0.x LLM-jury annotation work. The former Vertex AI billing project is now **deleted**; re-running these requires pointing them at a live project.

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
- `GET /stats/timeline` — Aggregated temporal distributions across the corpus.
- `GET /clan/{gens}` — Prosopographical network of co-occurring personal names for a single Etruscan family name.
- `GET /concordance` — Keyword-in-Context (KWIC) search across transcriptions.

## Python Package & CLI

```bash
pip install openetruscan          # core (CLI + library)
pip install 'openetruscan[server]' # FastAPI server runtime
pip install 'openetruscan[neural]' # neural classifiers (torch + onnxscript)
pip install 'openetruscan[all]'    # full stack incl. transformers + sotac
```

### Library

```python
from openetruscan import normalize

result = normalize("LARTHAL")
print(result.canonical)   # larθal
print(result.phonetic)    # /lar.tʰal/
print(result.old_italic)  # 𐌓𐌀𐌓𐌈𐌀𐌋
```

### CLI

The `openetruscan` console script wraps the library and the corpus
operations. Run `openetruscan --help` for the full menu; subcommands:

| Command                          | What it does                                                                       |
|----------------------------------|------------------------------------------------------------------------------------|
| `openetruscan normalize TEXT`    | Canonicalise an inscription string; `--json-output` for machine consumption.       |
| `openetruscan convert TEXT`      | Switch between Latin transliteration and Old Italic script (`--to old_italic`/etc).|
| `openetruscan validate FILE`     | Lint a transcription file or CSV column for orthography issues.                    |
| `openetruscan batch INPUT`       | Bulk-normalise CSV/JSONL; writes CSV/JSON/JSONL out.                               |
| `openetruscan list-adapters`     | Print the per-language adapters registered with the engine.                        |
| `openetruscan search QUERY`      | Query the local corpus DB (`OPENETRUSCAN_DB` or `--db`).                           |
| `openetruscan import-csv FILE`   | Ingest a CSV of inscriptions into the corpus DB.                                   |
| `openetruscan export-corpus`     | Dump the corpus to CSV / JSONL / TEI / RDF.                                        |
| `openetruscan epidoc TEXT`       | Render an inscription to EpiDoc/TEI XML.                                           |
| `openetruscan register …`        | Register a new inscription record.                                                 |
| `openetruscan upload-image …`    | Attach an image (file or URL) to an inscription.                                   |
| `openetruscan classify TEXT`     | Classify an inscription (TF-IDF + NB by default; `--arch charcnn` etc.).           |
| `openetruscan train-neural`      | Train CharCNN / MicroTransformer / EmbeddingMLP heads under the v2 protocol.       |
| `openetruscan predict-neural`    | Predict with a trained neural head; outputs JSON with probabilities.               |

All commands accept `--language` (default `etruscan`) and respect the
language adapter registry (`list-adapters`). The classification commands
report bootstrap-CI'd metrics; see [`research/v2/`](research/v2/) for the
evaluation protocol.

## Repository Structure

```
openEtruscan/
  src/openetruscan/  Python package: core library (normalizer, Leiden parser,
                     EpiDoc, corpus, prosopography), ml/, db/ (Alembic), api/
                     (local FastAPI parity reference)
  research/          Research narrative: v2 annotation protocol + frozen
                     benchmarks, findings, experiments, parked strands
  eval/              Frozen eval outputs + the rosetta/search harnesses
  scripts/           Data pipeline, ML, ops, training scripts (see scripts/README.md;
                     spent one-offs live in scripts/attic/)
  services/          Cloud Run inference services (ByT5 restorer, reranker)
  tests/             Pytest suite (incl. migration-chain and science-harness
                     invariant tests)
  data/              Local data artifacts (git-ignored; fetch via
                     scripts/ops/fetch_data.py — see data/README.md)
```

The web application (Next.js 16) and the production TypeScript API live in the
separate [`openEtruscan-frontend`](https://github.com/Eddy1919/openEtruscan-frontend) repository.

## Linked Open Data & Pelagios Network

OpenEtruscan exports Linked Open Data in formats interoperable with the wider ancient-world DH graph:

- **6,633 inscriptions** exported via the [Pelagios-compatible JSON-LD endpoint](/pelagios.jsonld) (Pelagios Network format spec; not a formal membership claim).
- Findspots aligned to [Pleiades](https://pleiades.stoa.org) for the subset with documented provenance (see §Provenance disclosure above).

## Classification & restoration models

This project ships two small models alongside an LLM-jury annotation pipeline. The numbers below are from `research/v2/` — frozen test splits, multi-rater consensus eval, bootstrap-CI'd metrics, full pre-registration in [`research/v2/PRE_REGISTRATION.md`](research/v2/PRE_REGISTRATION.md).

### Classifier (7-class inscription type) — v2.0.2 head-to-head

Four architectures spanning two orders of magnitude in parameter count were evaluated on the v2.0.2 candidate-gold (n=143, 3-rater LLM-jury unanimous: Sonnet 4.6 + Gemini 2.5 Pro + Llama 4 Maverick, Krippendorff α=0.7649). Train pool: 282 silver-labelled rows. **"Candidate-gold" is LLM-consensus silver, not gold**: the two-philologist ratification step (target human α ≥ 0.80, [`research/v2/handoff/`](research/v2/handoff/)) has not yet been performed, and these numbers measure agreement with a frontier-model consensus, not with expert epigraphic judgment. Cite them with that caveat.

| Architecture | Params | **Macro F1** (95% bootstrap CI) | Accuracy |
|---|---|---|---|
| TF-IDF + Multinomial NB | ~3K | **0.313** (0.273 – 0.348) | 0.776 |
| CharCNN | 28K | **0.369** (0.257 – 0.432) | 0.657 |
| MicroTransformer | 274K | **0.317** (0.202 – 0.404) | 0.483 |
| EmbeddingMLP (multilingual MiniLM, 384-d) | 58K + frozen encoder | **0.124** (0.099 – 0.149) | 0.469 |

Two findings:

1. **Architecture-invariance among local-feature models.** TF-IDF+NB, CharCNN, and MicroTransformer cluster at 0.31–0.37 macro F1 with overlapping bootstrap CIs despite 100× parameter-count range. Adding parameters does not move macro F1 — the bottleneck is data, not architecture.
2. **Out-of-distribution dense embeddings fail.** EmbeddingMLP using a multilingual MiniLM encoder lands at **0.124, with a CI that does not overlap with TF-IDF+NB's** — significant degradation. A frozen modern-multilingual encoder discards the surface-morphological features (`mi…al/-as` possessives, `tular spural` boundary formula, suffixal markers) that carry the typological signal. This contradicts the conventional NLP intuition that dense embeddings beat char-ngrams; for under-resourced ancient corpora with strong domain-specific morphology, the reverse holds.

The dominant `funerary` and `ownership` classes are well-modelled (per-class F1 0.84 and 0.79 on TF-IDF+NB); rare classes (`boundary`, `legal`, `votive`, `commercial`) remain data-starved. **The 0.31–0.37 macro band reflects this imbalance honestly** — earlier copy in this repository claimed "99% macro F1", which referred to in-training-set performance on a self-labeled subset and is retracted.

v2.0.1 (n=159, 2-rater jury without Sonnet) is preserved in GCS as a looser consensus-silver reference; v2.0.2 supersedes it per the closure of Deviation §A in [`research/v2/PRE_REGISTRATION.md`](research/v2/PRE_REGISTRATION.md).

### Lacuna restoration

> **⚠️ RETRACTED (v2.0.3, 2026-07-04): the v2.0.2 lacuna table and "Finding C" below were a harness artifact.** The v2.0.2 jury scored *empty API responses* as hallucinations: 114 of 125 Claude Sonnet 4.6 rows were empty completions (`max_tokens=1024` exhausted while echoing `restored_full`), and `lacuna_jury.py` counted every empty response as `hallucinated=True`. The 0.949 rate measured a Vertex integration failure, not model behaviour — on the 11 rows Sonnet actually answered it *led* the field. The set was also inflated by exact duplicates (125 rows → 70 unique tasks). Both bugs are fixed (`no_parse` handling; `max_tokens=4096` + non-empty retry). The corrected re-run is below.

Per-restoration evaluation on the deduplicated **66 clean-gold tasks** (Leiden `[abc]`-style, unknown-continuation markers excluded; **width-1-dominated, 43/66**). **v2.0.3 — 3-rater jury: Claude Opus 4.8 (direct agentic rater¹) + Gemini 3.1 Pro + Gemini 3.5 Flash, 10 000-resample bootstrap, seed=42:**

| Model | Span exact-match (95% CI) | Char acc top-1 (95% CI) | Hallucination rate (95% CI) | Coverage |
|---|---|---|---|---|
| Claude Opus 4.8 | **0.288** (0.182 – 0.394) | **0.341** (0.235 – 0.449) | 0.000² | 66/66 |
| Gemini 3.1 Pro | 0.258 (0.161 – 0.371) | 0.315 (0.210 – 0.426) | **0.161** (0.081 – 0.258) | 62/66 |
| Gemini 3.5 Flash | 0.258 (0.152 – 0.364) | 0.278 (0.178 – 0.389) | 0.545 (0.424 – 0.667) | 66/66 |

¹ Opus is not enabled on the Vertex projects available here (only Haiku 4.5), so it ran as a direct first-party rater, blind to gold, scored after — a documented deviation. ² Opus's `restored_full` was assembled mechanically, so its 0.000 hallucination is **by construction and not comparable** to the free-generating Gemini raters.

Hallucination = the model emits at least one character outside the marked lacuna span. Earlier copy claiming "Phil. Safety: High (Sentinels)" was a vibes-based label without a metric and remains retracted.

**Corrected findings (v2.0.3):**
- **No model wins on accuracy.** All span-exact differences are non-significant (paired bootstrap: Opus vs 3.1-Pro Δ+0.049 p=0.24; Opus vs 3.5-Flash Δ+0.031 p=0.37; 3.1-Pro vs 3.5-Flash p=0.66). The task is difficulty/data-bound — the same "data, not architecture" story as the classifier.
- **The real differentiator is hallucination:** Gemini 3.5 Flash alters context outside the span on 54.5% of rows vs 3.1-Pro's 16.1% — the small/fast model corrupts context.
- **Independence caveat:** the two Gemini raters agree with each other (0.339) far more than with Opus (0.18–0.24), so a Krippendorff α over this 2×Google panel is inflated by shared lineage.

### Methodology

Full annotation codebook, frozen stratified splits (SHA256-pinned, text-bearing — see [`research/v2/data/`](research/v2/data/)), LLM-jury runners, raw jury evidence + computed metrics ([`research/v2/results/lacuna/`](research/v2/results/lacuna/)), and the bootstrap-CI eval harness live in [`research/v2/`](research/v2/). The dataset cards and pre-registration are the citation-grade artifacts; this README is a summary. Reproduction steps: [`docs/REPRODUCE.md`](docs/REPRODUCE.md).

## Development

Python package (this repo):

```bash
git clone https://github.com/Eddy1919/openEtruscan.git
cd openEtruscan
pip install -e ".[dev]"      # or: uv sync --extra dev (uv.lock is committed)
pytest
```

Local corpus + API: see [`docs/REPRODUCE.md`](docs/REPRODUCE.md)
(`scripts/ops/fetch_data.py` fetches the corpus from the Zenodo DOI;
`docker-compose.dev.yml` stands up Postgres+pgvector and the API).

Web app: clone the separate
[`openEtruscan-frontend`](https://github.com/Eddy1919/openEtruscan-frontend)
repo, then `npm install && npm run dev`.

### Deployment

**Development & Preview** (from the frontend repo)
Push local dev environment variables and deploy a Preview build:
```bash
# Pull Vercel preview/dev environment variables
npx vercel env pull .env.local

# Deploy to Vercel Preview Environment
npx vercel -y
```

**Production**
Push directly to the live production site:
```bash
npx vercel --prod -y
```

## Citing this work

If you use OpenEtruscan or the OpenEtruscan corpus in your research, please cite both this software repository and the dataset deposit. Machine-readable citation metadata lives in:

- [`CITATION.cff`](CITATION.cff) — GitHub's *Cite this repository* button reads from here.
- [`codemeta.json`](codemeta.json) — schema.org-compatible (used by Zenodo, ORCID, OpenAlex).
- [`.zenodo.json`](.zenodo.json) — controls the auto-deposit on each tagged GitHub release.

A minimal BibTeX entry:

```bibtex
@software{openetruscan_2026,
  author    = {Panichi, Edoardo},
  title     = {{OpenEtruscan: open-source digital corpus platform for Etruscan epigraphy}},
  year      = {2026},
  version   = {1.0.0},
  doi       = {10.5281/zenodo.20075836},
  url       = {https://doi.org/10.5281/zenodo.20075836},
  publisher = {Zenodo}
}
```

Per the Zenodo record metadata, `10.5281/zenodo.20075835` is the **concept DOI** (resolves to the latest version) and `10.5281/zenodo.20075836` is the **version DOI** for the v1.0.0 deposit. Cite the concept DOI when referencing the project, the version DOI when referencing a specific snapshot. (An earlier revision of this section had the two swapped.)

The frozen reference benchmark is `rosetta-eval-v1`; full reproduction instructions live in [`research/notes/reproduce-rosetta-eval-v1.md`](research/notes/reproduce-rosetta-eval-v1.md). The research-grade roadmap is in [`research/SOTA_ROADMAP.md`](research/SOTA_ROADMAP.md).

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

## What's new

### v1.1.0 (2026-07-17) — integrity & reproducibility release

The frozen classification split was found corrupt (99 text-less rows vs the
pre-registered 400) and has been regenerated and verified against the jury's
own adjudication-queue IDs; the lacuna evidence (raw jury outputs + metrics)
moved from local-only staging into the tracked tree at
[`research/v2/results/lacuna/`](research/v2/results/lacuna/) with SHA256
manifests; the normalizer now parses Leiden editorial markup into a
structured apparatus (and EpiDoc export emits real
`<supplied>/<ex>/<gap>/<unclear>`); the Alembic chain bootstraps an empty
database (it previously could not); CI gained mypy, a coverage floor, and a
pgvector-backed test service. Full detail in
[`CHANGELOG.md`](CHANGELOG.md) §1.1.0 and
[`PRE_REGISTRATION.md` Deviation §C](research/v2/PRE_REGISTRATION.md).

### Architecture shift (2026-05-24) — research-first repo

The public HTTP API moved out of this repo. The live `www.openetruscan.com/api/*` surface is now **TypeScript route handlers in the [`openetruscan-frontend`](https://github.com/Eddy1919/openEtruscan-frontend) Vercel project**, talking to **Neon serverless Postgres** via Drizzle ORM + `@neondatabase/serverless`. Cloud SQL stopped, GCE VM terminated.

What stays here (and gets first billing in this README):
- **`research/v2/`** — the 3-rater LLM-jury annotation pipeline, pre-registration, codebooks, and frozen benchmarks. **Source of truth** for the v2.0.2 evaluation work below.
- **The `openetruscan` CLI** on PyPI — `pip install openetruscan` ships 14 commands for normalisation, classification, EpiDoc export, batch processing, neural training/inference.
- **`src/openetruscan/api/`** — the legacy FastAPI server stays in-tree as a parity reference + local-dev convenience (`uvicorn openetruscan.api.server:app`). It is **no longer the production HTTP surface**.
- **Cloud Build research pipelines** — `cloudbuild/v2-classify-jury.yaml`, `v2-lacuna-jury.yaml`, `v2-train-neural.yaml` were used for the v2 evaluation work. They are not currently running: the former Vertex billing project is deleted, so a re-run needs a live project.

### v2.0.2 annotation & evaluation pipeline (shipped 2026-05-24)

`research/v2/` is the gold-annotation and frozen-benchmark infrastructure that this project's earlier metric claims lacked. As of v2.0.2 both the classifier and lacuna streams are evaluated under a full 3-rater LLM jury (Claude Sonnet 4.6 + Gemini 2.5 Pro + Llama 4 Maverick on Vertex AI); the philologist α≥0.80 spot-check on the adjudication queue remains the final ratification step before Hugging Face publication.

- **Frozen, stratified test split** (seed=42, 400 rows, 7 classes with a class-2 floor) — see [`research/v2/pipelines/classify_split.py`](research/v2/pipelines/classify_split.py).
- **3-rater LLM jury** (Claude Sonnet 4.6 + Gemini 2.5 Pro + Llama 4 Maverick on Vertex AI; Sonnet substituted for Opus per [Deviation §A](research/v2/PRE_REGISTRATION.md)) produces independent labels; Krippendorff α and a unanimous-agreement filter promote rows to candidate-gold. Classifier α = 0.7649 on the full pool; n=143 candidate-gold rows.
- **Pre-registered eval** with bootstrap 95% CIs on every metric and paired-bootstrap p-values on every model-comparison claim — see [`research/v2/PRE_REGISTRATION.md`](research/v2/PRE_REGISTRATION.md) and [`research/v2/eval/bootstrap.py`](research/v2/eval/bootstrap.py).
- **Honest retraction** of the earlier "99% Macro F1" headline — the real number on a stricter eval is 0.313 ± 0.038 (TF-IDF + NB on n=143).
- **~~Finding C (v2.0.2)~~ — RETRACTED at v2.0.3.** The "Sonnet hallucinates 94.9%, frontier model loses" claim was a harness artifact: empty Vertex completions scored as hallucinations (see §Lacuna restoration above). The corrected v2.0.3 re-run (Opus 4.8 + Gemini 3.1 Pro + Gemini 3.5 Flash) finds **no significant model difference on accuracy** (span-exact 0.29 / 0.26 / 0.26, all p>0.2); the only real gap is hallucination (Gemini 3.5 Flash 0.545 vs Gemini 3.1 Pro 0.161). See [`docs/INTELLIGENCE_V2.md`](docs/INTELLIGENCE_V2.md).

### v0.5.0 infrastructure
- **Cloud Run neural restoration**: ByT5 lacunae restoration is served from a dedicated Cloud Run inference service (`services/byt5-restorer/`).
- **Search-eval harness with gate flags**: hybrid-search NDCG@10 computed by `eval/harness/run_search_eval.py --gate …` against real DB queries (`eval/harness/search_eval_queries.jsonl`). Run manually against a populated database — it is **not** wired into CI (an earlier version of this line claimed a "CI/CD eval gate"; no workflow invokes it, and CI has no populated corpus to run it against).
- **Admin curatorial UI**: provenance promotion workflow in the Inscription viewer (`ProvenancePromoteModal.tsx`).
