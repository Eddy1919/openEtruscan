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
- [ ] **Frontend PR #10 review follow-ups.** The dossier-restore PR merged
  with four should-fix findings (full verdict in the PR description,
  `openEtruscan-frontend#10`): (1) `MobileFooter` in the root layout now
  queries the DB during static generation of every page and a hanging
  connection fails the whole build — add a ~3s timeout race inside
  `getLiveCorpusSize` and `revalidate = 3600` on `/` and `/downloads`,
  which also unfreezes the build-frozen "live" corpus totals; (2) extract
  the duplicated `/api/stats/summary` `useEffect` in `Footer.tsx` /
  `_DesktopHome.tsx` into a shared client hook; (3) `fetchAttestedAnchors`
  in `lib/corpus.ts` has no callers — wire the inscription page to it or
  delete the dead server path; (4) the space-encoding assertion in
  `e2e/smoke.spec.ts:53` is vacuous and can never fail — assert
  unconditionally; (5, found post-merge in production) missing inscription
  ids soft-404 — HTTP 200 with the not-found UI — because the async layout
  flushes before the page's `notFound()`; call `notFound()` from
  `generateMetadata` on a miss so the status is set pre-stream. Nits in
  the verdict are fair game in the same branch.
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
