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

- [x] **Import on PostGIS-less databases** — fixed in
  `podc/s1-geom-degrade` (schema-aware inserts, honest compose header,
  regression suite `tests/test_corpus_geom.py`); CI-verified.
- [x] **Frontend craft nits from PR #10/#11** — keyboard-operable chips
  and copy-link feedback shipped (`f9cb035`), the rest in the four
  audit-fix rounds. Known limitation stands (not queued): missing ids
  return HTTP 200 + `noindex` + 404 UI — Next ≥15.2 streams metadata,
  so `notFound()` cannot reach the status line on this route.
- [ ] **Design-audit residuals (site scored 92/100, 2026-07-18).** Five
  taste items from the fourth audit, none blocking: (1) results-count
  numerals lack thousands separators + `tabular-nums`
  (`ClientSearch.tsx:748-755`); (2) reserve a 2-line findspot min-height
  so grid rows stop staggering 201/233px (`~:897`); (3) card hover
  `duration-400` → ~250ms (`:853`); (4) explorer initial framing can
  leave the northernmost cluster under the mobile toggle strip — add top
  padding to the initial `fitBounds` (`ExplorerContent.tsx:~165,532`);
  (5) the clamped findspot's full text lives in `title`, unreachable on
  touch — consider tap-to-expand or defer to the dossier.
- [x] **`add_genetic_sample()` geom bug** — resolved by removal: the
  archaeogenetics runtime was retired in v1.2.0 (`s3/surface-retire`);
  the method no longer exists.
- [ ] **`_PG_SCHEMA` cannot bootstrap an empty database.** Its
  `CREATE TABLE inscriptions` references `source_detail` in the
  `fts_canonical` generated column without defining it, so
  `_ensure_db()`'s base-schema block raises on a truly empty DB —
  bootstrap only works via alembic. Either fix the inline schema or
  delete it and make alembic the only bootstrap path (honest error
  message included).
- [x] **Contract enforcement** — `scripts/ops/generate_openapi.py` +
  the CI drift gate landed in `s2/repair-openapi`; spec regenerated at
  1.2.0.
- [ ] **E2E baseline.** Frontend CI (lint/tsc/vitest) is live; the
  Playwright suite still runs only locally/post-deploy — wire it into CI
  against a seeded database (the s8 harness under the agents'
  scratchpad proved the seeding approach). Flaky tests are quarantined
  with a tracking note, not retried into passing.
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
