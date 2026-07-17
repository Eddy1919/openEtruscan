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
