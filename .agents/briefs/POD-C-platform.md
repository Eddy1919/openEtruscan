# Pod C — Platform

**Goal.** A product surface that holds a big-tech bar: the API contract is
generated and enforced, the frontend is tested end-to-end, and performance
is measured before it is optimized.

**Owned paths.** `src/openetruscan/`, the API test files in `tests/`, and
the `openEtruscan-frontend` repo (its `AGENTS.md` carries the
frontend-specific gates).

**Non-goals.** Model or eval changes (Pod B). Alembic schema migrations
without a lead-approved plan. Visual redesigns not driven by a task here.

## Task queue

- [ ] **BLOCKING — import fails on PostGIS-less databases.** `_ensure_db()`
  silently rolls back the PostGIS step when the extension is unavailable
  (`corpus.py:659-676`), but `add()`/`add_batch()` reference `geom`
  unconditionally (`corpus.py:753-761`) → `UndefinedColumn`, 100% import
  failure in the dev stack (`docker-compose.dev.yml` ships pgvector
  without PostGIS — deliberately). Fix in code: make the insert degrade
  with the actual schema (omit `geom` when the column is absent), correct
  the compose header's "everything else works" claim, and add a
  regression test that imports against a PostGIS-less Postgres. Full
  reproduction in POD-A-corpus.md, escalation 1.
- [ ] **Frontend craft nits (residual from PR #10/#11 verdicts).** The
  should-fix findings all shipped in `openEtruscan-frontend#12`; what
  remains is small: (1) filter/match chips in `ClientSearch` are
  non-focusable NextUI `Chip`s with `role="tab"` + `onClick` — keyboard
  users cannot operate the classification or match-mode filters; use real
  buttons or restore Tab semantics; (2) the dossier "Copy permanent link"
  button gives no copied feedback. (The PR #11 normalizer-hydration nit
  was retracted — React ignores input `value` mismatches at hydration,
  and the eslint `set-state-in-effect` rule rejects the "fix".) Known
  limitation, not queued: missing inscription ids return HTTP 200 +
  `noindex` + 404 UI, not a 404 status — Next ≥15.2 streams metadata, so
  `notFound()` cannot reach the status line on this route; a real 404
  needs per-route streaming off or a global `htmlLimitedBots` widening,
  both worse trades than the `noindex` Next already emits.
- [ ] **Same geom bug class in `add_genetic_sample()`.** The
  podc/s1-geom-degrade fix covers inscriptions only; genetic-sample
  ingestion still inserts into `geom` unconditionally and fails on a
  PostGIS-less database. Apply the same schema-aware treatment.
- [ ] **`_PG_SCHEMA` cannot bootstrap an empty database.** Its
  `CREATE TABLE inscriptions` references `source_detail` in the
  `fts_canonical` generated column without defining it, so
  `_ensure_db()`'s base-schema block raises on a truly empty DB —
  bootstrap only works via alembic. Either fix the inline schema or
  delete it and make alembic the only bootstrap path (honest error
  message included).
- [ ] **Contract enforcement.** Regenerate `docs/openapi.json` from the
  FastAPI app and add a CI check that fails when the committed spec drifts
  from the code. The spec is the Pod B/C ↔ frontend boundary; a stale spec
  is a silent integration bug.
- [ ] **E2E baseline.** Get the Playwright suite in `openEtruscan-frontend`
  green and blocking in that repo's CI. Flaky tests are quarantined with a
  tracking note, not retried into passing.
- [ ] **Latency budget.** Measure p50/p95 for the search endpoints and the
  PostGIS vector-tile path under realistic data volume. Record the numbers
  first; optimization tasks get cut from the measurements, not from
  intuition.
- [ ] **Failure-state audit.** Walk the UI's empty, error, and slow-network
  states against the live API; list what is missing or lying to the user.

## Definition of done

CI fails on contract drift; e2e blocks frontend merges; latency numbers are
recorded with the method to reproduce them.

## Status & escalations

(pod-owned — append dated entries here)
