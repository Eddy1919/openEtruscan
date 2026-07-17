# Changelog

All notable changes to OpenEtruscan are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Version namespaces.** Two version streams appear below and they are not
> the same thing: plain `x.y.z` entries are **package/software releases**
> (PyPI `openetruscan`, `pyproject.toml`), while `v2.0.x` entries are
> **evaluation-protocol versions** of the `research/v2/` annotation and
> benchmark work. Earlier revisions of this file used bare `[2.0.3]` for a
> protocol version, which read as a package release — those headings now
> carry the `evaluation protocol` label.

## [Unreleased]

### Fixed — integrity repairs (S2)
- **CIE pipeline emits four-tier provenance values.** The regeneration
  chain hardcoded pre-migration `verified`/`rejected`, which the
  `provenance_status` CHECK constraint prohibits; the findspot-based
  mapping from migration `a1f2c3d4e5f6` now lives in one shared helper
  used by every pipeline script, upserts refresh the value, and
  `Corpus.review_quarantine` (no callers, prohibited values only) is
  deprecated and raises with guidance. `export_rejected.py` moved to the
  attic — its query matches nothing by construction post-migration.
- **`docs/openapi.json` regenerated (0.5.0 → 1.1.0)** and drift-gated in
  CI via the new `scripts/ops/generate_openapi.py`; the duplicate
  `export_openapi.py` is deleted.
- **byt5-restorer refuses to start without an explicit `MODEL_URI`** —
  it previously defaulted to plain `google/byt5-small` while advertising
  `byt5-lacunae-v1`. `/health` now reports the resolved model;
  `deploy-byt5.sh` requires and passes `MODEL_URI`; the env-contract
  tests run in CI.
- **Lacuna-restoration reproducer restored** against the surviving
  `CharMLM` API (its module died in the July history rewrite), with
  special tokens masked out of top-k and the experiment README stating
  exactly what is and is not reproducible today.
- **`/health` no longer probes the retired Fuseki host**, whose
  hostname only the deleted self-hosting compose ever defined.

### Removed — self-hosting compose surface
- Root `docker-compose.yml` retired (depended on absent `nginx.conf`
  and retired infrastructure); `docker-compose.dev.yml` is the only
  compose surface, and the docs no longer claim a self-hosted
  production stack or SPARQL endpoint.

### Fixed — corpus import without PostGIS
- **`openetruscan import` no longer fails on a PostGIS-less database.**
  `Corpus.add()`/`add_batch()` referenced the `geom` column unconditionally
  (even the no-coordinates branch wrote NULL into it), but `_ensure_db()`
  only creates that column where the PostGIS extension installs — on the
  `docker-compose.dev.yml` stack (pgvector image, no PostGIS) every insert
  died with `UndefinedColumn` and imports failed 100%. The corpus now probes
  once per connection whether `inscriptions.geom` exists and omits the
  column from its INSERTs when absent: rows import with plain
  `findspot_lat`/`findspot_lon` and no spatial geometry; statements on
  PostGIS-enabled databases are byte-for-byte unchanged (pinned by
  `tests/test_corpus_geom.py`). The dev-compose header now states the actual
  limitation instead of claiming everything but the spatial endpoints works.

### Fixed
- **CLI no longer lists duplicate commands.** `normalize` and `convert` were
  each registered twice (once as `normalize-cmd`/`convert-cmd` from the bare
  decorator, once under the documented name via `add_command`), so `--help`
  showed 16 commands instead of the documented 14. Each is now registered
  once; a test pins the exact 14-name command set.

### Removed — dead-code prune (S2 audit)
Every item was verified before removal (no importers/callers repo-wide,
or an import that no longer resolves).
- 11 dead files deleted: 6 scripts with broken imports or superseded
  behaviour (`classify_all`, `build_web_languages`, `populate_zotero`,
  `align_pleiades`, `migrate_db`, `add_docs`), the stale
  `scripts/docs/openapi.json` snapshot (API 0.4.0), `.vercelignore`
  (this repo does not deploy to Vercel), and 3 duplicate/empty texture
  images in `research/parked/cv_pipeline`.
- 3 declared-but-never-imported dependencies dropped: `lxml` (EpiDoc uses
  stdlib ElementTree + defusedxml) and `networkx` (prosopography is pure
  Python) from the extras — the `epidoc`/`prosopography` extras remain as
  no-ops so existing installs keep resolving — and `google-cloud-storage`
  from the byt5-restorer service.
- 13 spent one-off scripts moved from `scripts/{ml,data_pipeline,ops}` to
  `scripts/attic/` (enrichment backfills, superseded trainers, the
  Cloud SQL→Tembo migration and its Secret Manager sidecar); indexed in
  `scripts/attic/README.md`.

### Deprecated
- `core/lineage`, `core/spatial`, `ml/lacuna`, `ml/entity_linker_v2`, and
  `ml/embedding_classifier` now emit a `DeprecationWarning` on import and
  will be removed in 2.0. Nothing inside the repo imports them, but they
  ship in the wheel, so external imports cannot be ruled out — hence a
  deprecation cycle instead of deletion.

### Fixed — rosetta-eval-v1 baseline integrity
- **Random baseline no longer fabricates its vocab size.** A failed
  `/neural/rosetta/vocab` fetch made `run_rosetta_eval.py --baseline random`
  silently compute the "analytic" column from a hard-coded V=100,000,
  indistinguishable from a real result in the JSON (a test asserted the
  fabricated value). It now aborts with an error; both baseline columns
  record the `vocab_size` they actually ran against.
- **Committed benchmark numbers independently verified.** The random column
  of `eval/rosetta-eval-v1-20260511T080032Z.json` replicates exactly from
  the closed-form math (V=50,000); the Levenshtein column is consistent
  with its own per-pair records; the FINDINGS.md table matches the JSON.
  Anchor count corrected to 61 pairs / 39-22 split (prose said 62 / 40-22);
  the benchmark definition is re-anchored in content hashes after the July
  history squash killed the pinned commit ids. Details in
  `research/notes/reproduce-rosetta-eval-v1.md`.

## [1.1.0] — 2026-07-17

Integrity and reproducibility release, closing the gaps found by the
2026-07-17 audit.

### Fixed — evidence chain
- **Frozen classification split repaired.** The committed
  `research/v2/data/classify_test_v2.jsonl` (99 rows) and train pool (613
  rows) had empty text on every row and contradicted the pre-registered
  n=400. Regenerated deterministically from the Zenodo corpus deposit
  (seed=42, n-test=400); verified that all 79 jury adjudication-queue IDs are
  contained in the regenerated pool with byte-identical text, and that the
  corrupt file's 99 IDs are a strict subset. `classify_split.py` now
  hard-fails on empty-text rows (`--allow-empty-text` for smoke runs). See
  `research/v2/data/README.md`, incl. one open delta (312 regenerated
  train-pool rows vs the historically reported 282).
- **Lacuna evidence promoted.** v2.0.2/v2.0.3 raw jury JSONL + metrics moved
  from untracked `research/private/` to `research/v2/results/lacuna/` with a
  SHA256 manifest; recomputation reproduces the published tables exactly.
- **Pre-registration re-anchored** (Deviation §C): the July 2026 history
  squash destroyed freeze commit `c281ed9`; integrity is now anchored in
  content hashes, not commit ids.
- **`initial_schema` migration was an empty stamp** — `alembic upgrade head`
  could not bootstrap an empty database (failed at the second migration).
  Reconstructed the 2026-04-04 base DDL; the full 17-migration chain now
  applies cleanly from empty and is exercised by `tests/test_migrations.py`.
- **Jury harness**: API failures are recorded as `label="api_error"` (missing
  data) instead of `"unsure"` (abstention), and any api_error blocks
  candidate-gold promotion — the same bug class as the retracted lacuna
  Finding C, closed in the classification stream before it produced one.
- **Label provenance rename**: `gold:claude_hand_label` →
  `silver:claude_hand_label` (184 rows) — those labels are LLM-derived, not
  philologist-validated. Split regenerated; membership unchanged.

### Added
- **Leiden-convention parsing** (`core/leiden.py`): `[abc]` restorations,
  `(abc)` expansions, `[..]`/`---` gaps, underdot-unclear, and half brackets
  are parsed into a structured `apparatus` on `normalize()` results instead
  of leaking literal brackets into canonical text, phonetics, Old Italic,
  tokens, and the FTS index. EpiDoc export now emits real
  `<supplied>/<ex>/<gap>/<unclear>` markup.
- **Science-harness invariant tests** (`tests/test_v2_harness.py`): no_parse
  ≠ hallucination, api_error dispositions, split-generator empty-text
  refusal, bootstrap seed stability, Krippendorff α implementation agreement,
  and pins on the committed evidence files.
- **Reproducibility kit**: `scripts/ops/fetch_data.py` (Zenodo fetch +
  SHA256 verify), `docker-compose.dev.yml` (Postgres+pgvector dev stack),
  `uv.lock`, digest-pinned Docker base image, `docs/REPRODUCE.md`.
- **CI**: mypy gate, coverage floor (45%), pgvector-capable Postgres service
  with a hard extension assertion (previously the vector-search tests
  self-skipped silently and CI stayed green).

### Changed
- One-off corpus-surgery scripts moved to `scripts/attic/` with an
  audit-trail README; `scripts/` and `scripts/data_pipeline/` gained
  live-script indexes; machine-specific hardcoded paths removed.
- CV/YOLO pipeline, neurosymbolic WBS, and Oscan/Faliscan/Rhaetic protocol
  stubs parked under `research/parked/` until the Etruscan gold chain closes.
- Dead DVC remote configuration removed (data flows through the Zenodo DOI);
  `dashboard.json` (retired Cloud Run monitoring) and `.semgrepignore`
  (semgrep no longer runs anywhere) deleted.
- Concept vs version DOI corrected in the citation docs: concept is
  `10.5281/zenodo.20075835`, the v1.0.0 deposit is `…20075836` (previously
  stated backwards).

## [v2.0.3 — evaluation protocol] — 2026-07-04

### Retracted — v2.0.2 lacuna "Finding C" (harness artifact)

The v2.0.2 lacuna jury scored **empty API responses as hallucinations**. 114
of 125 Claude Sonnet 4.6 rows were empty completions (`max_tokens=1024`
exhausted while echoing `restored_full`), and `lacuna_jury.py` counted every
empty response as `hallucinated=True`. The reported **0.949** Sonnet
hallucination rate and the "frontier model loses at p<0.001" narrative
measured a Vertex integration failure, not model behaviour — on the 11 rows
Sonnet actually answered it led the field. The 118-row set was additionally
inflated by exact duplicates (125 rows → 70 unique tasks).

### Fixed — lacuna harness

- `research/v2/pipelines/lacuna_jury.py` — empty/unparseable responses now
  carry `no_parse=True` and are **never** scored as hallucinations.
- `research/v2/pipelines/classify_jury.py` — Anthropic-Vertex `max_tokens`
  1024 → 4096, non-empty retry that raises on persistent empty, and
  removed the hardcoded default pointing at a since-deleted GCP project.
- `research/v2/eval/{lacuna_metrics,compute_lacuna_v2}.py` — `no_parse` rows
  excluded from accuracy/hallucination denominators; coverage reported.

### Added — corrected lacuna re-run (v2.0.3)

3-rater jury — **Claude Opus 4.8** (direct agentic rater; Opus is not on the
available Vertex projects, only Haiku 4.5) + **Gemini 3.1 Pro** + **Gemini
3.5 Flash** — on the deduplicated **66 clean-gold tasks** (width-1-dominated),
10 000-resample bootstrap, seed=42:

| Model            | Span exact (95 % CI)      | Char acc top-1            | Hallucination             | Cover |
|------------------|---------------------------|---------------------------|---------------------------|-------|
| Claude Opus 4.8  | **0.288** (0.182 – 0.394) | **0.341** (0.235 – 0.449) | 0.000 (by construction)   | 66/66 |
| Gemini 3.1 Pro   | 0.258 (0.161 – 0.371)     | 0.315 (0.210 – 0.426)     | **0.161** (0.081 – 0.258) | 62/66 |
| Gemini 3.5 Flash | 0.258 (0.152 – 0.364)     | 0.278 (0.178 – 0.389)     | 0.545 (0.424 – 0.667)     | 66/66 |

- **No model wins on accuracy** — all span-exact deltas non-significant
  (paired bootstrap p = 0.24 / 0.37 / 0.66). The task is difficulty/data-bound,
  echoing the classifier's "data, not architecture" result.
- **Real differentiator is hallucination** — Gemini 3.5 Flash alters context
  outside the span on 54.5 % of rows vs Gemini 3.1 Pro's 16.1 %.
- **Independence caveat** — the two Gemini raters agree with each other (0.339)
  far more than with Opus (0.18–0.24); a Krippendorff α over this 2×Google
  panel is inflated by shared lineage. Opus's 0.000 hallucination is by
  construction (`restored_full` assembled mechanically) and not comparable.
- Data: `research/v2/results/lacuna/lacuna_jury_raw_v2_0_3_rerun.jsonl`
  (promoted from local-only staging to the tracked tree on 2026-07-17),
  `lacuna_v2_0_3.json`. The classifier stream (short outputs) is unaffected by
  the empty-completion bug; α = 0.7649 stands (GCS raw spot-check pending).

## [1.0.0] — 2026-05-24

First stable release. Closes the v1 audit gaps, ships the v2.0.2 evaluation
suite (3-rater LLM jury for classification and lacuna restoration), and
publishes a polished frontend + backend pair to production.

### Added — Research-grade evaluation infrastructure

- **v2.0.2 classifier jury** — 3-rater (Claude Sonnet 4.6 + Gemini 2.5 Pro +
  Llama 4 Maverick on Vertex AI) over a frozen 400-row stratified test
  split. **143 candidate-gold rows** at Krippendorff α = 0.7649; remaining
  99-row queue awaiting philologist α ≥ 0.80 spot-check.
- **v2.0.2 lacuna jury** — ⚠️ **RETRACTED at v2.0.3** (see the [2.0.3] entry
  above). The Sonnet lacuna row and "Finding C" were a harness artifact:
  empty Vertex completions scored as hallucinations. Superseded by the
  v2.0.3 re-run (Opus 4.8 + Gemini 3.1 Pro + Gemini 3.5 Flash).
- **Head-to-head classifier comparison** on the v2.0.2 split: TF-IDF + NB
  **0.313** (0.273 – 0.348), CharCNN 0.369, MicroTransformer 0.317,
  EmbeddingMLP (MiniLM, frozen) 0.124. Architecture-invariance among
  local-feature models confirmed; OOD dense embeddings fail.
- **Pre-registration protocol** — `research/v2/PRE_REGISTRATION.md` is the
  authoritative spec. Deviation §A documents the Sonnet-for-Opus
  substitution that closed at v2.0.2.

### Added — Frontend polish (web app)

- **WCAG 2.1 AA compliance** — Lighthouse a11y 92 → **100**. axe-core
  Serious violations reduced 88 % across all 16 public routes
  (color-contrast, list semantics, landmark dedup, canvas alt text,
  scrollable-region keyboard access).
- **Mobile performance refactor** — Lighthouse perf desktop **75 → 99**,
  mobile **75 → 92**. Mobile path now ships as Server Components
  (`MobileHome` + `MobileNav` + `MobileFooter`), with three
  `useSyncExternalStore`-gated dynamic-import islands for the rich
  NextUI/framer-motion/InteractiveStele experience on `lg+` viewports
  only. Mobile page weight 929 KB → 424 KB; mobile LCP 7.9 s → 3.2 s;
  CLS 0.

### Changed

- Backend `README.md`, `docs/INTELLIGENCE_V2.md`, `docs/HUGGINGFACE.md`,
  `research/v2/README.md`, and `models/etr-lora-v4/README.md` all updated
  to the v2.0.2 numbers and Finding C narrative.
- Frontend `lib/constants.ts` and `/classifier` disclaimer carry the
  v2.0.2 figures (macro F1 0.313 ± 0.038 on n=143).

### Security

- Bumped `torch` from `2.1.2` → `2.8.0` in `services/minilm-reranker/requirements.txt`,
  closing five Dependabot advisories (one critical RCE via `torch.load`,
  two high, one medium, one low).
- `.gitleaks.toml` allowlist now covers the public GCP project IDs and
  Zenodo DOI prefix that were generating false positives.

### Fixed

- `dt.UTC` → `dt.timezone.utc` in `scripts/research/llm_extract_anchors.py`
  and `review_anchors.py` for Python 3.10 compatibility (ci-matrix regression
  caught and resolved).
- Cloud Build `v2-lacuna-jury.yaml` timeout extended to 4 h with a Python
  partial-sync side-cart so OOM/timeout incidents preserve partial jury
  output to GCS instead of losing the run.

### Retracted

- The earlier "**99 % macro F1**" headline on the classifier — that number
  was an in-training-set fit on a self-labelled subset, not held-out
  performance. The current honest number is `0.313 ± 0.038`.
- The earlier "**Phil. Safety: High (Sentinels)**" qualitative label on
  lacuna restoration — replaced by the explicit hallucination-rate metric
  and Finding C above.

## [0.5.0] — 2026-05-10

Pre-1.0 development milestones (Larth dataset ingestion, CIE Vol. I
unification, FastAPI server, Vercel frontend, multilingual encoder, v1
rosetta-eval benchmark, byt5-restorer Cloud Run service). See git history
for commits prior to this changelog's introduction.
