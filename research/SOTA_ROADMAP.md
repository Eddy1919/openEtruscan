# SOTA Roadmap — research-grade elevation

Operational plan for moving the repo from "well-engineered project"
to "research artifact that gets cited". One PR per task, same
discipline as [`EXECUTION_WBS.md`](EXECUTION_WBS.md).

> **How to use this doc.** Identical to `EXECUTION_WBS.md`: pick the
> lowest-numbered item whose dependencies are met, paste the block to
> a coding agent, open one PR titled `[<RG-ID>] <task title>`.

> **Companion docs.** [`EXECUTION_WBS.md`](EXECUTION_WBS.md) is the
> science-roadmap (defensible eval, v4 head-to-head, primary-source
> mining). This file is the *research-grade infrastructure* roadmap —
> what makes the science citable. The two run **in parallel**.

---

## Wave summary

| Wave | What it produces | Tasks | Est. effort |
|---|---|---|:---:|
| **W0** Finish in flight | pgbouncer fix (PR #22), CI on Cloud Build | merging-only | done after CI lands |
| **W1** Visible markers | Citation infra, coverage gate, eval-as-CI-gate, README framing | RG.1 – RG.5 | ~2 days |
| **W2** Actual rigor | Bootstrap CIs, replication kit, HF Hub, significance tests | RG.4, RG.6 – RG.8 | ~3 days |
| **W3** Research output | Paper draft, benchmark dashboard, GH issues mirror of WBS | RG.9 – RG.11 | ~1 week+ |

**Critical path** (sequential, low-risk): W0 → RG.1 → RG.2 → RG.3 → RG.6 → RG.7 → RG.9.
Everything else can be parallelised once W0 closes.

The substance-first principle: items that improve **what the work is**
(RG.4, RG.6, RG.8, RG.9) take precedence over items that improve **how
it looks** (RG.1, RG.5). When in doubt, prefer rigor over presentation.

---

## Wave 1 — visible research-grade markers

### RG.1 — Citation infrastructure (CITATION.cff + codemeta.json + .zenodo.json)

**Goal:** when someone clicks "Cite this repository" on GitHub, they
get a machine-readable BibTeX/APA/RIS that includes the Zenodo DOI of
the corpus.

**Files to create:**

- `CITATION.cff` — GitHub renders this automatically.
- `codemeta.json` — schema.org-compatible metadata; used by zenodo,
  ORCID, OpenAlex.
- `.zenodo.json` — the Zenodo GitHub integration reads this when a
  release is tagged; controls authors / license / keywords.

**Steps:**

1. Author list, ORCIDs (if any), affiliations, and the corpus Zenodo
   DOI go into all three files. They share fields; keep them in sync.
2. README gets a `## Citing this work` section pointing at the three
   files + showing a one-line BibTeX block.
3. **TODO marker** for the DOI: the user mints the Zenodo deposit and
   pastes the DOI in a single find-replace pass.

**Acceptance command:**

```bash
test -f CITATION.cff && test -f codemeta.json && test -f .zenodo.json
python3 -c "import yaml; yaml.safe_load(open('CITATION.cff'))" && \
python3 -c "import json; json.load(open('codemeta.json')); json.load(open('.zenodo.json'))" && \
echo OK
```

`OK` means all three files exist and parse.

**Effort:** 0.5 day.

**Dependencies:** none.

---

### RG.2 — Test coverage reporting + CI gate

**Goal:** `pytest --cov=src --cov-fail-under=75` runs in CI and fails
PRs that drop coverage below 75%.

**Files to touch:**

- [`pyproject.toml`](../pyproject.toml) — `[tool.pytest.ini_options]` add `addopts = "--cov=src --cov-report=term-missing --cov-report=xml"`; add `[tool.coverage.report]` with `fail_under = 75`.
- CI workflow / Cloud Build config — add coverage step + upload to codecov.io.
- README — `![Coverage](https://codecov.io/gh/Eddy1919/openEtruscan/badge.svg)` once codecov is wired.

**Acceptance command:**

```bash
pytest --cov=src --cov-fail-under=75
```

Either passes outright, or surfaces the actual coverage number so we
can negotiate the threshold.

**Effort:** 0.5 day.

**Dependencies:** W0 (CI on Cloud Build).

---

### RG.3 — Eval-as-CI-gate

**Goal:** a PR that regresses `model.field@10` below 0.10 fails the
build. We already have the gate primitive in
[`run_rosetta_eval.py:_evaluate_gates`](../evals/run_rosetta_eval.py) —
this task wires it into CI.

**Files to touch:**

- Cloud Build config: add a step
  `python evals/run_rosetta_eval.py --benchmark=rosetta-eval-v1 --gate "precision_at_10_semantic_field=0.10" --api-url ${_API_URL}`.
- The `--api-url` is a *staging* API for PR gating, prod for nightly.

**Decision:** gate against staging-API for PRs (cheap) vs prod-API
(authoritative but rate-limited). Default to staging; nightly cron
hits prod.

**Acceptance command:**

```bash
python evals/run_rosetta_eval.py --benchmark=rosetta-eval-v1 \
  --baseline=random --gate "precision_at_10_semantic_field=0.10" \
  --api-url <staging>
# exit 0 means the gate held; exit 1 means we'd block a PR
```

**Effort:** 0.25 day.

**Dependencies:** W0 (CI on Cloud Build), RG.2 (so the test job exists to bolt onto).

---

### RG.5 — README framing: architecture diagram + "what's novel"

**Goal:** the first 30 seconds of the README answers "what does this
project do and what's novel?" — currently it requires reading 200
lines.

**Files to touch:**

- `README.md`: insert a one-paragraph "What's novel" right under the
  title, before "Overview". Add an architecture diagram (Mermaid
  works directly in GitHub markdown; no SVG asset needed).
- `docs/architecture.md` for the long-form version.

**Diagram contents (Mermaid):**

```
Corpus (Larth + CIE) → normaliser → pgvector (LaBSE + xlmr-lora-v4)
                                       ↓
              FastAPI /neural/rosetta — cosine retrieval
                                       ↓
              rosetta-eval-v1 (random / Levenshtein / model)
                                       ↓
                          FINDINGS.md headline numbers
```

**Acceptance command:**

```bash
grep -E "## What's novel|```mermaid" README.md | wc -l
# must be >= 2 (one heading + one diagram fence)
```

**Effort:** 0.5 day.

**Dependencies:** none.

---

## Wave 2 — actual rigor

### RG.4 — Bootstrap confidence intervals on the eval

**Goal:** every precision@k number in the eval report carries a 95%
bootstrap CI. `0.1875 ± 0.06 (95% CI, n=16)` instead of `0.1875`.

**Files to touch:**

- [`evals/run_rosetta_eval.py`](../evals/run_rosetta_eval.py) — add
  `_bootstrap_ci(hits, n, n_resamples=10_000)` and call it per metric.
- Report shape gains a `precision_at_k_ci_95` sibling to
  `precision_at_k`.
- Tests for the bootstrap math.

**Acceptance command:**

```bash
python evals/run_rosetta_eval.py --benchmark=rosetta-eval-v1 \
  --baseline=random --api-url <prod> --json | \
  jq '.precision_at_k_ci_95["10"]'
# must produce a [lo, hi] pair where lo <= precision_at_k["10"] <= hi
```

**Effort:** 0.5 day.

**Dependencies:** none.

---

### RG.6 — One-line replication kit

**Goal:**

```bash
docker run --rm openetruscan/replicate-rosetta-eval-v1
```

prints the eval JSON to stdout in <2 min, from a freshly-pulled
machine with nothing but docker installed. Reviewers verify with zero
friction.

**Files to touch:**

- `replicate/Dockerfile` — pinned-deps image that wraps
  `evals/rosetta_eval_v1.sh`.
- `replicate/README.md` — one-paragraph instructions.
- CI: build + push to `ghcr.io/eddy1919/openetruscan-replicate:rosetta-eval-v1`.

**Acceptance command:**

```bash
docker pull ghcr.io/eddy1919/openetruscan-replicate:rosetta-eval-v1
docker run --rm ghcr.io/eddy1919/openetruscan-replicate:rosetta-eval-v1 \
  --api-url https://api.openetruscan.com | \
  jq '.model.precision_at_k_semantic_field["10"]'
```

**Effort:** 1 day.

**Dependencies:** W0, RG.1 (citation tagged on the image).

---

### RG.7 — HuggingFace Hub: model + dataset

**Goal:**

- `huggingface.co/openetruscan/etr-lora-v4` — the adapter, model card,
  example code.
- `huggingface.co/datasets/openetruscan/corpus` — the cleaned 6,567-row
  dataset (mirror of the Zenodo deposit, with a README pointing back to
  the Zenodo DOI as canonical).

**Files to touch:**

- `scripts/hub/push_adapter.py` — uses `huggingface_hub`; reads
  `HF_TOKEN` from env.
- `scripts/hub/push_dataset.py` — similar, for the dataset.
- Model card README at `models/etr-lora-v4/README.md` (pushed to Hub).

**Acceptance command:**

```bash
curl -sf https://huggingface.co/api/models/openetruscan/etr-lora-v4 | jq .modelId
curl -sf https://huggingface.co/api/datasets/openetruscan/corpus | jq .id
```

**Effort:** 1 day.

**Dependencies:** RG.1 (so the Hub README cites the Zenodo DOI).

---

### RG.8 — Paired-bootstrap significance test (v4 vs LaBSE)

**Goal:** the FINDINGS table's "v4 vs LaBSE" claim is gated on a
paired-bootstrap test. p<0.05 by N=10,000 resamples or it doesn't
land as a positive result.

**Files to touch:**

- `evals/significance.py` — new module with paired-bootstrap math.
- `evals/rosetta_eval_v1.sh` — emit a top-level `comparisons` key with
  paired p-values for each model-pair.
- FINDINGS.md table gains a "p-value (vs LaBSE)" column.

**Acceptance command:**

```bash
jq '.comparisons["v4_vs_labse"].p_value' eval/rosetta-eval-v1-<ts>.json
# must be in [0, 1]
```

**Effort:** 0.5 day.

**Dependencies:** RG.4 (shares the bootstrap infrastructure), WBS T2.4
(needs the v4 column to exist).

---

## Wave 3 — research output

### RG.9 — arXiv-ready paper draft

**Goal:** a 6-8 page IMRAD-style preprint at `paper/openetruscan-2026/`
(LaTeX or Markdown via Pandoc). Cites the corpus DOI, the frozen
benchmark, the methodology. Submittable to arXiv cs.CL.

**Sections (proposed):**

1. Introduction — Etruscan as a low-resource isolate; cross-lingual
   embedding retrieval as the methodological wager.
2. Corpus — 6,567 inscriptions, normaliser, Larth + CIE provenance,
   Zenodo DOI.
3. Method — LaBSE + XLM-R LoRA (v3/v4) + Procrustes (pre-pivot
   methodology mentioned + rejected for the published runs).
4. Evaluation — `rosetta-eval-v1`, baselines, semantic-field metric,
   coverage thresholds, paired-bootstrap significance.
5. Results — FINDINGS.md table, qualitative wins (CURATION_FINDINGS).
6. Limitations — small held-out test split (n=22), OOV rate, no
   primary-source attested anchors (until P4).
7. Reproducibility — replication kit, Zenodo DOI, frozen benchmark.

**Effort:** 3-7 days (variable). Write iteratively in PRs of ~1 section
each so it's reviewable.

**Dependencies:** WBS Phase 2 + Phase 3 (we need v4 numbers for the
Results section), RG.4 (CIs), RG.6 (replication kit), RG.7 (Hub).

---

### RG.10 — Continuous benchmark dashboard

**Goal:** static page at `openetruscan.com/research/benchmarks` (or a
sibling Vercel deploy) that shows `rosetta-eval-v1` numbers over
time. Updates from a nightly Cloud Build job.

**Files to touch:**

- `frontend/app/research/benchmarks/page.tsx` (or equivalent in the
  Vercel app) — reads the latest `eval/rosetta-eval-v1-*.json` from
  the repo via the GitHub raw API.
- Cloud Build trigger: nightly cron at 03:00 UTC running
  `evals/rosetta_eval_v1.sh --output auto` and pushing the new JSON
  to main via a bot account.

**Effort:** 2 days.

**Dependencies:** W0 (Cloud Build), RG.5 (architecture page exists
in frontend to link from).

---

### RG.11 — Mirror WBS to GitHub Issues

**Goal:** each WBS task becomes a GitHub Issue with labels (`phase-1`,
`critical-path`, `rg.N`) and a Project board for the public view.

**Files to touch:**

- `.github/ISSUE_TEMPLATE/wbs-task.yml` — issue template that mirrors
  the WBS task block structure.
- `scripts/ops/sync_wbs_issues.py` — one-shot script that reads
  EXECUTION_WBS.md + SOTA_ROADMAP.md and opens/updates issues via
  `gh issue create`.

**Acceptance command:**

```bash
gh issue list --label rg.1 --json number,title --jq 'length'
# must be >= 1 once the sync runs
```

**Effort:** 0.5 day.

**Dependencies:** none.

---

## Surfacing on other surfaces

The roadmap items above are repo-internal. Each item that produces a
citable artifact has a parallel surfacing step:

| Item | Surfaced on frontend | Surfaced on HF Hub | Surfaced on Zenodo |
|---|---|---|---|
| RG.1 (citation) | `/cite` page or footer | Model card "Citation" section | Release-tagged auto-deposit |
| RG.3 (eval gate) | `/research/benchmarks` (live status) | Model card "Evaluation" section | n/a |
| RG.4 (CIs) | Numbers shown with error bars on `/research/benchmarks` | Eval section gains CIs | n/a |
| RG.6 (replication kit) | "Reproduce locally" link in footer | Model card "Replication" section | n/a |
| RG.7 (HF Hub) | "Models" page links to Hub | n/a (this IS the surfacing) | Linked in deposit metadata |
| RG.9 (paper) | `/research/paper` PDF embed | Model card "Citation" → arXiv link | Paper deposit on Zenodo too |

**Sequencing rule:** surfacing always lags the source-of-truth landing
by one PR — never co-modify three repos in one go. The source-of-truth
PR lands; the frontend / Hub / Zenodo PRs come next, referencing the
already-committed artifact.

---

## Status

Tracking is in the chat session via TodoWrite. Source of truth for
completed work is `git log --oneline` on the PRs that close each
RG-ID.
