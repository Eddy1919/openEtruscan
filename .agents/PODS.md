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
| B — Research | models, eval, findings | `research/`, `eval/`, `models/`, `services/`, `scripts/ml/`, `scripts/training/`, `scripts/research/`, ML tests | Claude | Grok (replication) |
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

## Operator runbook — pod sessions

`scripts/ops/pod.sh` creates the session worktree and branch (with the
next session number), prints the kickoff prompt, and copies it to the
clipboard:

```sh
scripts/ops/pod.sh start a <slug>    # new Pod A session
scripts/ops/pod.sh review <branch>   # detached reviewer worktree + prompt
scripts/ops/pod.sh status            # list sessions
scripts/ops/pod.sh done <worktree>   # clean up a finished session
```

Launch the pod's CLI inside the printed worktree: `kimi` (Pod A), `claude`
(Pods B–D), `grok` (reviews). For Pod C frontend work, run the script from
`~/openEtruscan-frontend` — same branch naming, gates in that repo's
`AGENTS.md`.

### Kickoff prompt

> You are Pod <X>. Read `AGENTS.md`, then your brief
> `.agents/briefs/POD-<X>-*.md` (from the frontend repo:
> `../openEtruscan/.agents/briefs/`). Work the first unchecked task in the
> queue. Stop at any escalation trigger and record it in the brief.

If the CLI does not load `AGENTS.md` automatically, the pasted prompt
covers it — reading the file is its first instruction.

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
