# Pod D — Quality gate

**Goal.** Make the other pods' output trustworthy: CI that actually blocks,
a security posture with no known gaps, and docs that describe the system as
it is. This pod is run by the lead.

**Owned paths.** `.github/`, `tests/conftest.py`, `tests/fixtures/`,
`scripts/ops/`, `docs/`, and top-level config files (`pyproject.toml`,
`.pre-commit-config.yaml`, `.gitleaks.toml`, Docker files).

**Non-goals.** Feature work of any kind. Rewriting other pods' tests —
test *infrastructure* only.

## Task queue

- [ ] **Coverage ratchet.** Measure current pytest coverage, set the CI
  floor at that number, and raise it only when real tests raise it. No
  aspirational thresholds.
- [ ] **Security workflow audit.** Verify `security.yml` (gitleaks,
  semgrep) actually blocks merges rather than reporting into the void; add
  dependency auditing (`pip-audit`) to CI.
- [ ] **Duplication gate.** Add a jscpd check over PR diffs so the no-dedup
  bar is enforced by a machine, not by review vigilance.
- [ ] **Frontend CI parity.** Confirm lint, typecheck, unit, and e2e all
  block in `openEtruscan-frontend`; close whatever gap exists.
- [ ] **Docs freshness pass.** Diff `docs/ARCHITECTURE.md` and
  `docs/DEVELOPMENT.md` against the actual code and fix what has rotted.

## Definition of done

Every gate above blocks in CI; a new contributor following the docs gets a
working environment on the first try.

## Status & escalations

(pod-owned — append dated entries here)
