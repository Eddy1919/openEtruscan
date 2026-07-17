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

- [ ] **Coverage ratchet.** CI already gates at `--cov-fail-under=45`.
  Raise the floor whenever merged tests lift real coverage above it —
  never lower it to make a PR pass.
- [ ] **Local mypy gate is dead.** With dev extras installed, mypy 2.3.0
  under `python_version = "3.10"` aborts on numpy's `type`-statement
  stubs before checking a single project file — locally it gates
  nothing (CI is unaffected only because its lint job installs no
  numpy). Fix the config (bump `python_version` or exclude the stub)
  so local and CI runs check the same thing.
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
