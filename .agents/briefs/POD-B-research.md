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

- [x] **Trivial baselines.** Already implemented pre-brief; PR #82 did the
  rule-7 verification instead — the committed random column replicates
  exactly from independent math, and the fabricated-V fallback it found
  is fixed.
- [x] **Held-out split.** Recorded in the eval module and content-hash
  pinned: 61 pairs, 39/22 (this queue earlier said 62 — the module is
  the source of truth).
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
- [x] **Split-count corrections (from Pod A escalations).** FINDINGS and
  ROADMAP corrected to 61 / 39-22 in PR #82 (the pre-squash history that
  would explain the 62nd pair is gone; the note says so). The
  `compute_lacuna_v2.py` banner now prints the jury filename instead of
  a hardcoded version.
- [ ] **Restorer eval parity.** Give `services/byt5-restorer` the same
  discipline: a held-out eval, a trivial baseline, a runbook.

## Definition of done

Every claim in `FINDINGS.md` has a runbook, beats its trivial baseline or
says so, and has been independently re-run in a different harness.

## Status & escalations

(pod-owned — append dated entries here)

**2026-07-17 (podb/s1-baselines, Claude Fable 5 / Claude Code).**
Task 1 (trivial baselines) and task 2 (held-out split) were already
implemented pre-brief; this session did the rule-7 verification instead
of re-writing them. Random column of the committed
`rosetta-eval-v1-20260511T080032Z.json` replicates exactly from an
independent implementation of the closed-form math (V=50,000);
Levenshtein column is consistent with its own per-pair records;
FINDINGS table matches the JSON. Fixed one harness-artifact-class
defect found during verification: `--baseline random` silently
substituted V=100,000 when the vocab fetch failed (and a test asserted
the fabricated value) — now hard-fails; both baseline columns record
`vocab_size`. Corrected anchor count 62→61 / 40-22→39-22 in FINDINGS +
ROADMAP; re-anchored the benchmark definition in content hashes (the
pinned SHAs died in the July squash). PR opened from this branch.

*Escalations:*
- Brief task queue says "62 anchor pairs"; the module holds 61. Queue
  text is lead-owned — please reconcile.
- Local pytest: docker-dependent modules (`test_server`,
  `test_prosopography`, `test_neural`) fail identically on a clean
  tree in this environment (testcontainers gets HTTP 500 from colima's
  docker API at container setup). Unrelated to this diff; rosetta eval
  module passes 30/30, ruff/format/mypy clean. CI is the authoritative
  run for those modules.
