# AGENTS.md — rules for AI agents in this repo

Read this once per session, before touching anything. `docs/ARCHITECTURE.md`
describes the system; `research/FINDINGS.md` is the honest research state.
Work is organized into pods: the pod map and operator runbook are in
[`.agents/PODS.md`](.agents/PODS.md), your assignment is in
[`.agents/briefs/`](.agents/briefs/).

## Rules

1. **Stay inside your pod's owned paths** (map in `.agents/PODS.md`). If a
   task needs a change outside them, record it under *Status & escalations*
   in your brief and stop — the lead routes it. Never edit another pod's
   files, including its tests.
2. **One worktree and one branch per session.** Branch naming:
   `pod<letter>/s<n>-<slug>`, e.g. `poda/s3-provenance-manifest`. Never
   commit to `main`. Remove your worktree when the session ends.
3. **Stage explicit paths only.** `git add <path>...` — never `git add -A`,
   `git add .`, or `--all`.
4. **Run the gates locally before opening a PR:**
   `ruff check . && ruff format --check . && mypy src/openetruscan/ && pytest`.
   A CI failure on a pushed PR is a process defect, not a discovery.
5. **Cross-model review.** No PR merges reviewed only by the model that
   wrote it. State your model and harness in the PR description so the
   lead can route the review.
6. **Data provenance.** Anything added under `data/` or consumed by a
   pipeline must carry source, license, and retrieval date in the
   provenance manifest (layout in `data/README.md`). No ingestion of
   material whose license is unverified — this repo is public.
7. **Empirical claims are gated.** A number enters `research/FINDINGS.md`
   only with a replication runbook (exact command, environment, seed) and
   after an independent re-run in a different harness. This repo has
   already retracted one finding that turned out to be a harness artifact.
8. **Prose bar.** Write like a careful human: no filler, no boilerplate,
   no duplicated docs. Update the existing document instead of adding a
   new one. User-visible changes get a `CHANGELOG.md` entry.
9. **Secrets.** Never commit credentials or `.env` values. Anything
   secret-shaped in data or history: stop and escalate.

## Escalate (write it in your brief's *Status & escalations*, then stop) when

- the task requires paths outside your brief,
- a gate fails for reasons unrelated to your change,
- you would add a dependency, a service, or a CI change,
- licensing of a data source is unclear.
