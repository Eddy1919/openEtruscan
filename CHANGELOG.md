# Changelog

All notable changes to OpenEtruscan are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-05-24

First stable release. Closes the v1 audit gaps, ships the v2.0.2 evaluation
suite (3-rater LLM jury for classification and lacuna restoration), and
publishes a polished frontend + backend pair to production.

### Added — Research-grade evaluation infrastructure

- **v2.0.2 classifier jury** — 3-rater (Claude Sonnet 4.6 + Gemini 2.5 Pro +
  Llama 4 Maverick on Vertex AI) over a frozen 400-row stratified test
  split. **143 candidate-gold rows** at Krippendorff α = 0.7649; remaining
  99-row queue awaiting philologist α ≥ 0.80 spot-check.
- **v2.0.2 lacuna jury** — 3-rater on 118 editor-restored inscriptions.
  Headline numbers (10 000-resample bootstrap, seed=42):

  | Model              | Span exact (95 % CI)      | Char acc top-1            | Hallucination               |
  |--------------------|---------------------------|---------------------------|-----------------------------|
  | Gemini 2.5 Pro     | **0.220** (0.144 – 0.297) | **0.245** (0.172 – 0.321) | **0.271** (0.195 – 0.356)   |
  | Llama 4 Maverick   | 0.170 (0.102 – 0.237)     | 0.189 (0.123 – 0.259)     | 0.627 (0.542 – 0.712)       |
  | Claude Sonnet 4.6  | 0.051 (0.017 – 0.093)     | 0.055 (0.017 – 0.098)     | **0.949** (0.907 – 0.983)   |

- **Finding C** (new at v2.0.2) — Sonnet 4.6 hallucinates outside the
  marked lacuna span on **94.9 %** of inscriptions, significantly worse
  than Gemini (Δ +0.169 span-exact, two-sided **p < 0.001**) and Llama
  (Δ +0.123, **p ≈ 0.002**) on the n=65 paired subset. A frontier
  reasoning model loses to two general-purpose models on a structured-edit
  task.
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
