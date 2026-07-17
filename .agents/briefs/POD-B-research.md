# Pod B — Research & ML

**Goal.** Make every reported number scientifically defensible, then advance
the classifier, restorer, and Rosetta strands. `research/ROADMAP.md`
Milestone 1 is the current focus; `research/FINDINGS.md` is the honest state
and must stay that way.

**Owned paths.** `research/`, `eval/`, `models/`, `services/`,
`scripts/ml/`, `scripts/training/`, `scripts/research/`, and the ML test
files in `tests/`.

**Non-goals.** Data ingestion (Pod A). API or frontend changes (Pod C).
Celebrating any metric before it clears Milestone 1's bars.

## Task queue

- [ ] **Trivial baselines.** Levenshtein-only retrieval baseline and the
  analytic random-baseline precision@k against the current eval set, as
  ROADMAP Milestone 1 specifies. If the model does not beat edit distance,
  that result is reported, not buried.
- [ ] **Held-out split.** Record the split of the 62 anchor pairs in
  `eval/harness/` so no future run can train on its own eval.
- [ ] **Replication runbooks.** For each number currently in `FINDINGS.md`,
  a runbook with exact command, environment, and seed. This is what the
  Grok replication pass executes verbatim — a claim without a runbook is
  removed from `FINDINGS.md`, not grandfathered.
- [ ] **Harness-artifact audit.** Re-examine the eval harness for the
  failure class behind the retracted finding: seed leakage, eval-set
  contamination, metric definitions that reward surface-form matching.
- [ ] **Historical column re-run (newly unblocked).** The embedding vectors
  `docs/REPRODUCE.md` §6 declared lost survive in
  `gs://openetruscan-rosetta-vai/embeddings/` (`labse-v1.jsonl` and
  `etr-xlmr-lora-v4.jsonl` MD5-verified against the manifest in
  `research/notes/reproduce-rosetta-eval-v1.md` on 2026-07-17). Re-run
  rosetta-eval-v1 against the historical column and update that note's
  recovery status.
- [ ] **Split-count corrections (from Pod A escalations).** The frozen
  split is 39/22 = 61 pairs (regeneration-verified); `FINDINGS.md:450`
  still says 40/22. Confirm where the superseded 62nd pair went, correct
  FINDINGS.md, and fix `compute_lacuna_v2.py`'s hardcoded "v2.0.2" stdout
  banner (it mislabels v2.0.3 re-runs).
- [ ] **Restorer eval parity.** Give `services/byt5-restorer` the same
  discipline: a held-out eval, a trivial baseline, a runbook.

## Definition of done

Every claim in `FINDINGS.md` has a runbook, beats its trivial baseline or
says so, and has been independently re-run in a different harness.

## Status & escalations

(pod-owned — append dated entries here)
