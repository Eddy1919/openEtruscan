# Pod charter

Four pods move OpenEtruscan forward in parallel without stepping on each
other. Each pod owns a domain and its paths; the lead (a Claude Code session
run by the operator) cuts briefs, routes reviews, and holds the merge gate.
Data is the ceiling for every product goal, so Pod A is the critical path.

The rules every pod follows are in [`AGENTS.md`](../AGENTS.md). This file is
the map and the runbook.

## Pod map

| Pod | Domain | Owned paths | Author | Adversarial reviewer |
|-----|--------|-------------|--------|----------------------|
| A — Corpus | data ingestion, provenance, validation | `data/`, `scripts/data_pipeline/`, `tests/test_corpus.py` | Kimi | Claude |
| B — Research | models, eval, findings | `research/`, `eval/`, `models/`, `services/`, `scripts/ml/`, `scripts/training/`, `scripts/research/`, `src/cv_pipeline/`, ML tests | Claude | Grok (replication) |
| C — Platform | API + frontend product surface | `src/openetruscan/`, API tests, the `openEtruscan-frontend` repo | Claude | Kimi or Grok |
| D — Quality | CI, security, test infra, docs freshness | `.github/`, `tests/conftest.py`, `tests/fixtures/`, `scripts/ops/`, `docs/`, top-level configs | Claude (lead) | Kimi or Grok |

Each pod also owns its own brief's *Status & escalations* section — nothing
else in `.agents/` is writable by pods. Path disputes go to the lead; when in
doubt, escalate rather than edit.

## Operating loop

1. The lead cuts or updates briefs in `.agents/briefs/`.
2. The operator initializes a pod session (runbook below). At most **three**
   pod sessions run concurrently — the merge gate is the bottleneck, and
   quality dies when it queues.
3. The pod works its task queue top-down, opens a PR, and records status in
   its brief.
4. Cross-model review runs (prompt below), then the lead verifies gates and
   merges. Merges are squash merges; messages follow the existing
   `type(scope): summary` convention.

## Operator runbook — starting a pod session

```sh
cd ~/openEtruscan
git worktree add .claude/worktrees/<slug> -b pod<letter>/s<n>-<slug>
cd .claude/worktrees/<slug>
# launch the pod's CLI here: kimi (Pod A), claude (Pods B–D), grok (reviews)
```

First prompt to the agent:

> You are Pod <X>. Read `AGENTS.md`, then `.agents/briefs/POD-<X>-*.md`.
> Work the first unchecked task in the queue. Stop at any escalation
> trigger and record it in the brief.

If the CLI does not load `AGENTS.md` automatically, paste that first prompt
anyway — reading the file is its first instruction. When the session ends:
`git worktree remove .claude/worktrees/<slug>` (the branch survives).

Frontend work (Pod C) happens directly in `~/openEtruscan-frontend`, same
branch naming, gates listed in that repo's `AGENTS.md`.

## Cross-model review prompt

Paste into a fresh Kimi or Grok session in a clean worktree of the branch:

> You are the adversarial reviewer for branch `<branch>`, written by
> `<model>`. Read `AGENTS.md`. Run `git diff main...<branch>`, read every
> changed file in full, and try to find the defect — do not bless the diff.
> Check: correctness at the edges, silent failure modes, tests that mirror
> the implementation instead of asserting behavior, duplication, provenance
> for data changes, replication runbooks for research claims. Output either
> `PASS` or a numbered list of findings with `file:line` and severity.
> Uncertain findings are worth listing; say why you are unsure.
