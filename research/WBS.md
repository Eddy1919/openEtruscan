# Work-Breakdown Structure — Rosetta Vector Space

Concrete tasks, derived from [`ROADMAP.md`](ROADMAP.md). Each task has:
**deliverable**, **acceptance criterion**, **est. effort**, and
**dependencies**. Effort is calendar-time for one engineer focused
~half-time, *not* head-down hours.

A task is "done" only when its acceptance criterion holds, the change
is on `main`, and any docs / tests that needed updating got updated.

If a task gets reframed mid-execution, update its row here in the same
PR.

---

## Milestone 1 — Defensible eval

### M1.1 — Levenshtein baseline

- **Deliverable:** `--baseline=levenshtein` mode in
  [`evals/run_rosetta_eval.py`](../evals/run_rosetta_eval.py). Ranks
  Latin candidates by edit distance to the Etruscan query (over the
  full Latin vocab present in `language_word_embeddings`), produces
  the same metric tables as the model run.
- **Acceptance:**
  - `python evals/run_rosetta_eval.py --baseline=levenshtein --json`
    returns a complete report with the same shape as the model run.
  - Test added: `tests/test_rosetta_eval.py` verifies the baseline
    produces non-zero precision when the source word is present
    verbatim in the Latin vocab.
  - `FINDINGS.md` updated with the baseline numbers in the headline
    table.
- **Effort:** 0.5 day.
- **Dependencies:** none.

### M1.2 — Random baseline

- **Deliverable:** analytical computation of expected precision@k
  under uniform random retrieval given the Latin vocab size. Added
  to the report as a constant column.
- **Acceptance:** report shows `precision@k_random` for each k, with
  the math documented in a docstring.
- **Effort:** 0.25 day.
- **Dependencies:** none.

### M1.3 — Held-out anchor split

- **Deliverable:** `evals/rosetta_eval_pairs.py` declares an explicit
  `EVAL_SPLIT` field per pair (`train` / `test`). Default split:
  ~40 train / ~22 test, stratified by category and confidence tier.
  Helper `eval_pairs(split=...)` to filter.
- **Acceptance:**
  - The split is committed and documented; the seed used to
    generate it is recorded in the module.
  - The eval harness defaults to the `test` half.
  - Tests updated to verify the split is balanced.
- **Effort:** 0.5 day.
- **Dependencies:** none. (But: blocks any future training that uses
  anchor pairs as positives.)

### M1.4 — Coverage-at-cosine-threshold

- **Deliverable:** the eval harness records the cosine of the top-1
  Latin neighbour for each Etruscan query, then reports
  `coverage_at_threshold[c]` = fraction of evaluated pairs whose
  top-1 cosine ≥ c, for c ∈ {0.5, 0.7, 0.85}.
- **Acceptance:** the stub `coverage_any_hit` in the report is
  replaced with the real metric, and unit-tested.
- **Effort:** 0.5 day.
- **Dependencies:** API endpoint must return cosines (already does).

### M1.5 — Frozen `rosetta-eval-v1` reference benchmark

- **Deliverable:** a single `make rosetta-eval` (or equivalent
  shell/Python entrypoint) that reproduces the headline numbers in
  the current `FINDINGS.md` from a freshly-checked-out repo. Pinned:
  embedding model, vocabulary file, eval split, metric definitions.
- **Acceptance:**
  - Running the entrypoint on a fresh machine produces numbers
    that match the published headlines within 0.005.
  - `research/notes/reproduce-current-eval.md` documents the
    pinned versions / GCS paths / API URL.
- **Effort:** 1 day.
- **Dependencies:** M1.1 + M1.2 + M1.3 + M1.4 (so the frozen report
  has all the columns).

---

## Milestone 2 — Qualitative-review pipeline

### M2.1 — Sample selection

- **Deliverable:** `scripts/research/select_review_words.py` —
  draws N (default 80) Etruscan words from the prod inscription
  vocab, filtering out: anchor-set members, single-character /
  punctuation tokens, hapaxes (single-occurrence) below a frequency
  cutoff. Output: a JSONL with each word + its inscription contexts
  (top-5 inscriptions ranked by length).
- **Acceptance:** running the script produces a deterministic JSONL
  with N entries, reviewable by hand.
- **Effort:** 0.5 day.
- **Dependencies:** none. (Requires a live API or DB read for vocab,
  but the inscription data is already on disk.)

### M2.2 — Review packet renderer

- **Deliverable:** turn the JSONL from M2.1 into one of: a Markdown
  document, a static HTML page, or a notebook — whichever is most
  ergonomic for the reviewer. Per-word section: inscription
  contexts, system top-10 with cosines, tick-box scoring schema
  (plausible / implausible / interesting).
- **Acceptance:** a generated review packet is reviewable end-to-end
  by someone without OpenEtruscan dev access (i.e. the document is
  self-contained).
- **Effort:** 1 day.
- **Dependencies:** M2.1.

### M2.3 — Score aggregation

- **Deliverable:** parser for the reviewer's filled-in packet that
  computes: per-pair scores, aggregate plausibility rate, novelty
  count, top "interesting" candidates worth deeper examination.
- **Acceptance:** parser is tested on a synthetic filled packet,
  then used on the first real reviewed packet to produce a summary
  artefact in `research/reviews/`.
- **Effort:** 0.5 day.
- **Dependencies:** M2.2 + at least one completed real review.

### M2.4 — First review round

- **Deliverable:** at least one collaborator reviews a generated
  packet of ~50 Etruscan words. Results parsed via M2.3.
- **Acceptance:**
  - Review completed.
  - Aggregate qualitative numbers reported in `FINDINGS.md`.
  - At least one "interesting" candidate written up in
    `research/notes/` for future investigation.
- **Effort:** ½ day on our side + collaborator's time.
- **Dependencies:** M2.1 + M2.2 + M2.3 + a reviewer.

---

## Milestone 3 — Primary-source attested-anchor mining

### M3.1 — LLM-as-parser script

- **Deliverable:** `scripts/research/llm_extract_anchors.py` —
  iterates over [`data/extracted/etruscan_passages.jsonl`](../data/extracted/etruscan_passages.jsonl),
  sends each passage to an LLM (Anthropic API) with a strictly-
  bounded extraction prompt (extract bilingual equivalences stated
  in the passage, refuse outside knowledge, return JSON list with
  verbatim evidence quotes), accumulates a candidate JSONL.
- **Acceptance:**
  - Script runs end-to-end on the 1,795 passages.
  - Output JSONL has structured fields: `etruscan_word`,
    `equivalent`, `equivalent_language`, `evidence_quote`,
    `source` (author + work + locus).
  - Cost report logged: token usage and total spend.
- **Effort:** 1 day.
- **Dependencies:** Anthropic API access. Approval to spend ~$5 on
  the run.

### M3.2 — Anchor review + dedup

- **Deliverable:** manually review the LLM-extracted candidates;
  remove false positives; deduplicate against the anchor set;
  produce `research/anchors/attested.jsonl` (the final attested
  anchor list).
- **Acceptance:**
  - Reviewed list is in git, with provenance.
  - Yield report: how many candidates survived review, broken down
    by source.
  - `FINDINGS.md` updated with the yield and any notable
    individual finds (e.g. corroboration of Suetonius's `aesar`).
- **Effort:** 1 day.
- **Dependencies:** M3.1 output.

### M3.3 — LaBSE contrastive fine-tune (conditional)

- **Deliverable:** if M3.2 yielded ≥ 30 attested pairs (after dedup
  with the eval set), train a LaBSE adapter via
  `MultipleNegativesRankingLoss` on the attested pairs. Re-embed
  the prod vocab through the adapted model and re-eval.
- **Acceptance:**
  - The adapted model improves *semantic-field* @5 on the held-out
    eval split by ≥ 1.5× over the un-adapted baseline.
  - If the threshold isn't reached, document the negative result
    and *do not* ship the adapter to prod.
- **Effort:** 1.5 days.
- **Dependencies:** M1.3 (held-out split must exist), M3.2 (anchors
  must be reviewed).

### M3.4 — External primary sources (Festus / Macrobius / Hesychius)

- **Deliverable:** locate clean digital editions of the missing
  high-yield grammatical sources, ingest into the same passages
  pipeline.
- **Acceptance:** at least one of {Festus, Macrobius, Hesychius} is
  ingested and produces ≥ 10 additional attested pairs.
- **Effort:** unknown — depends on source availability. Could be
  0.5 day (find it, parse it) or could be a dead end.
- **Dependencies:** none, but bounded by primary-source
  availability outside paywalled academic databases.

---

## Milestone 4 — Multi-language expansion

### M4.1 — Phoenician populate

- **Deliverable:** Phoenician vocab list (top-N from KAI digitisation
  or equivalent), populate via the existing pipeline through
  base LaBSE.
- **Acceptance:** the API answers `/neural/rosetta?from=phn&to=lat`
  for at least 50 Phoenician query words with non-empty top-k.
- **Effort:** 0.5 day (assuming KAI is accessible) — 1 day if
  ingestion is needed.
- **Dependencies:** none.

### M4.2 — Oscan populate

- **Deliverable:** Oscan vocab list (ImagInes Italicae or
  equivalent), populate via base LaBSE.
- **Acceptance:** as above for `from=osc&to=lat`.
- **Effort:** 0.5 day if corpus accessible.
- **Dependencies:** none.

### M4.3 — Per-language eval extension

- **Deliverable:** add Phoenician↔Latin and Oscan↔Latin anchor pairs
  to the eval (Pyrgi Tablets for Phoenician; cognate attestations
  for Oscan). New per-language sub-reports in the eval harness.
- **Acceptance:** the eval harness reports per-language strict +
  field metrics; numbers are documented in `FINDINGS.md`.
- **Effort:** 1 day.
- **Dependencies:** M4.1 + M4.2 (otherwise no vectors to evaluate
  against).

---

## Milestone 5 — Discovery experiments

### M5.1 — Pre-registration

- **Deliverable:** `research/discovery_experiment_v1.md` — a
  pre-registered experiment design before any results are
  inspected. Specifies: word selection criteria, blinding,
  reviewer profile, success criteria.
- **Acceptance:** pre-registration is committed *before* M5.2
  starts.
- **Effort:** 0.5 day.
- **Dependencies:** Milestone 1 + 2 complete (so the methodology
  is mature).

### M5.2 — Run + write-up

- **Deliverable:** execute M5.1 protocol; analyse results;
  write paper draft suitable for a digital classics venue.
- **Acceptance:**
  - Either: ≥ 1 plausible non-trivial candidate per 10 reviewed
    words. → publish positive finding.
  - Or: reviewer feedback overwhelmingly negative. → publish
    honest negative result.
- **Effort:** 1-2 weeks (this is the actual research output, not
  just engineering).
- **Dependencies:** M5.1 + a reviewer who's a working
  Etruscanist.

---

## Cross-cutting tasks

These don't fit a milestone but are needed throughout:

### CC.1 — Reproducibility manifest

- **Deliverable:** `research/notes/reproduce.md` — single doc
  recording: pinned model, pinned vocab, GCS paths, API URL,
  eval split version, code commit hashes. Updated on every
  milestone completion.
- **Effort:** 0.25 day initial; ongoing 0.1 day per milestone.

### CC.2 — Quarterly findings refresh

- **Deliverable:** every quarter, `FINDINGS.md` is reviewed against
  the actual current state of the system. Stale numbers are
  updated; conclusions that no longer hold are marked.
- **Effort:** 0.5 day per quarter.

### CC.3 — Open-source housekeeping

- **Deliverable:** the repository navigation stays clean — no
  orphan scripts in random folders, no `data/extracted/external/`-
  style failed-experiment debris, no broken links between docs.
- **Effort:** 0.25 day every couple of months.

---

## Effort summary

| Milestone | Total estimated effort | Calendar (one engineer at half-time) |
|---|---|---|
| M1 — Defensible eval | 2.75 days | ~2 weeks |
| M2 — Qualitative-review | 2.5 days + reviewer time | ~3 weeks |
| M3 — Primary-source mining | 4 days + ~$5 LLM | ~3-4 weeks |
| M4 — Multi-language | 2 days | ~2 weeks |
| M5 — Discovery experiments | 2-3 weeks | ~6-8 weeks |
| Total | ~15 days + 6-8 weeks experiments | ~4-5 months |

A focused full-time effort could compress this to 6-8 weeks. Half-time
realistic delivery: 4-5 months for a publishable result.
