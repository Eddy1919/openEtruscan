# Cloud Build — CI/CD for openEtruscan

This directory replaces `.github/workflows/`. The migration moved CI/CD
off GitHub Actions and onto Cloud Build for three reasons:

1. **Native GCP auth** — no more Workload Identity Federation gymnastics;
   the Cloud Build SA gets Secret Manager + IAP + Artifact Registry
   access directly.
2. **Single billing surface** — builds, secrets, and infra live in the
   same project.
3. **Faster status-poll loop** — Cloud Build's GitHub App posts commit
   status directly; PR feedback is sub-3 minutes vs the 6-8 minutes the
   GH-Actions matrix was burning.

## Project layout

| Project | Role |
|---|---|
| **`long-facet-427508-j2`** | **Where all Cloud Build runs execute, alongside the deploy target.** Project number `19927826393`. Hosts the prod GCE VM `openetruscan-eu`, the Artifact Registry repo `openetruscan/api`, the GitHub App connection, the build secrets, and the deploy SA `gh-actions-deployer@long-facet-427508-j2.iam.gserviceaccount.com`. Builds run as that SA directly — no cross-project impersonation. |
| **`double-runway-465420-h9`** | **Batch jobs only** (Vertex training submissions, eval jobs that touch the prod corpus). Not in the CI/CD critical path; do NOT point `cloudbuild/*.yaml` at this project. The "spending/training-on-double-runway, infra-on-long-facet" split is the project-billing rule. |
| **`openetruscan-rosetta`** | AI workload storage (`gs://openetruscan-rosetta/` for adapters, embeddings, corpus). Read-only from Cloud Build steps that need the v4 JSONL etc. |

## Files

| File | Trigger | Purpose |
|---|---|---|
| [`ci.yaml`](ci.yaml) | PR to main | Fast PR lane: ruff + pytest (Python 3.12) + mypy + pyright + OpenAPI schema verify. Sub-3-min feedback. |
| [`ci-matrix.yaml`](ci-matrix.yaml) | Push to main | Full Python matrix (3.10/3.11/3.12/3.13). Catches version-specific regressions that the PR lane skips for speed. |
| [`deploy.yaml`](deploy.yaml) | Push to main (path-filtered) | Build image, push to Artifact Registry in long-facet, IAP SSH into the VM, run alembic migrations, rotate compose services. |
| [`security.yaml`](security.yaml) | Push to main + weekly cron | Gitleaks secret-detection. Bandit / Semgrep / pip-audit dropped from the GH-Actions era — chronically red, no actionable signal. |
| [`pypi.yaml`](pypi.yaml) | Release tag `v[0-9]+.[0-9]+.[0-9]+*` | Build wheel/sdist, upload to PyPI. |

## One-time setup runbook

This is the runbook you run **once** to wire Cloud Build up. After that
every trigger is self-serving from these YAMLs.

### 1. Connect GitHub to Cloud Build

Install the **Cloud Build GitHub App** on `Eddy1919/openEtruscan`:
<https://github.com/apps/google-cloud-build>

In the Cloud Build console for `long-facet-427508-j2`:

```
Settings → Connections → Connect repository → GitHub (Cloud Build GitHub App)
```

Pick the openEtruscan repo. This is what makes commit statuses post back to PRs.

### 2. Grant the deploy SA the build-runner role

The triggers below are configured to run as
`gh-actions-deployer@long-facet-427508-j2.iam.gserviceaccount.com`,
which already has IAP-Tunnel + GCE-SSH + Artifact-Registry-write +
Secret-Manager-read roles from the GH-Actions era. The only thing it
typically lacks is `roles/cloudbuild.builds.builder` (needed when an
SA runs a Cloud Build, not just submits one):

```bash
PROJECT=long-facet-427508-j2
SA=gh-actions-deployer@${PROJECT}.iam.gserviceaccount.com

for ROLE in \
  roles/cloudbuild.builds.builder \
  roles/logging.logWriter \
  roles/secretmanager.secretAccessor ; do
    gcloud projects add-iam-policy-binding $PROJECT \
      --member="serviceAccount:$SA" \
      --role="$ROLE" --condition=None
done
```

If you prefer to run builds as the default Cloud Build SA
(`19927826393@cloudbuild.gserviceaccount.com`) instead, grant the
default SA the same three roles plus `roles/iap.tunnelResourceAccessor`
and `roles/compute.osLogin` on the VM. The trigger commands below
default to running as `gh-actions-deployer` since it's simpler.

### 3. Create the secrets in Secret Manager

```bash
PROJECT=long-facet-427508-j2

# Only one new secret is needed: the PyPI API token for the release
# workflow. Other deploy-time secrets (oe-database-url, etc.) already
# exist in this project.
echo -n "<your PyPI API token>" | gcloud secrets create pypi-api-token \
  --project=$PROJECT \
  --replication-policy=automatic --data-file=-
```

If trusted publishing (OIDC) gets configured later, `pypi-api-token`
becomes unnecessary — see the comment in [`pypi.yaml`](pypi.yaml).

### 4. Create the triggers

Run these from your local shell with `gcloud config set project long-facet-427508-j2` first.

```bash
PROJECT=long-facet-427508-j2
SA=projects/$PROJECT/serviceAccounts/gh-actions-deployer@${PROJECT}.iam.gserviceaccount.com
REPO=openEtruscan
OWNER=Eddy1919

# 4a. PR build (ci.yaml) — runs on every PR opened against main
gcloud builds triggers create github \
  --project=$PROJECT \
  --name=openetruscan-ci-pr \
  --repo-owner=$OWNER --repo-name=$REPO \
  --pull-request-pattern="^main$" \
  --build-config=cloudbuild/ci.yaml \
  --service-account=$SA \
  --description="Fast PR lane: lint + py3.12 tests + types + openapi"

# 4b. Push-to-main matrix (ci-matrix.yaml)
gcloud builds triggers create github \
  --project=$PROJECT \
  --name=openetruscan-ci-matrix \
  --repo-owner=$OWNER --repo-name=$REPO \
  --branch-pattern="^main$" \
  --build-config=cloudbuild/ci-matrix.yaml \
  --service-account=$SA \
  --description="Full Python matrix (3.10–3.13) on main pushes only"

# 4c. Deploy on main pushes when relevant paths change
gcloud builds triggers create github \
  --project=$PROJECT \
  --name=openetruscan-deploy \
  --repo-owner=$OWNER --repo-name=$REPO \
  --branch-pattern="^main$" \
  --build-config=cloudbuild/deploy.yaml \
  --service-account=$SA \
  --included-files="src/**,Dockerfile,docker-compose.yml,nginx.conf,pyproject.toml,data/**,alembic.ini,scripts/ops/fetch-env-from-sm.sh" \
  --description="Build image + IAP SSH rotate to openetruscan-eu"

# 4d. Security scan on main pushes
gcloud builds triggers create github \
  --project=$PROJECT \
  --name=openetruscan-security \
  --repo-owner=$OWNER --repo-name=$REPO \
  --branch-pattern="^main$" \
  --build-config=cloudbuild/security.yaml \
  --service-account=$SA \
  --description="Gitleaks secret detection"

# 4e. Weekly security scan via Cloud Scheduler hitting the trigger's webhook.
#     Cloud Build has no native cron; we use Scheduler → triggers.run.
#     This is non-trivial because the caller SA needs:
#       (a) builds.builder + builds.editor on the project,
#       (b) the Scheduler service-agent needs tokenCreator on the caller SA,
#       (c) the caller SA needs serviceAccountUser on the *trigger's* SA.
#     All three are wired by:
bash scripts/ops/setup_weekly_security_cron.sh
#     The job name is `openetruscan-weekly-security`, location `europe-west6`,
#     schedule `0 7 * * 1` UTC. Test-fire it with:
#       gcloud scheduler jobs run openetruscan-weekly-security \
#         --location=europe-west6 --project=long-facet-427508-j2

# 4f. PyPI publish on release tags
gcloud builds triggers create github \
  --project=$PROJECT \
  --name=openetruscan-pypi-publish \
  --repo-owner=$OWNER --repo-name=$REPO \
  --tag-pattern="^v[0-9]+\.[0-9]+\.[0-9]+.*$" \
  --build-config=cloudbuild/pypi.yaml \
  --service-account=$SA \
  --description="Publish to PyPI on tagged releases"
```

### 5. Verify

After creating the triggers, open a no-op PR against main and confirm:

- The Cloud Build GitHub App posts a commit status.
- `ci.yaml` runs in the Cloud Build console.
- The status link in the PR navigates to the build log.

Merge the PR; `ci-matrix.yaml` + `deploy.yaml` should fire. Watch the
deploy step in the console for the alembic + container-rotation output.

## Day-to-day operations

### Re-run a build

From the Cloud Build console, or:

```bash
gcloud builds triggers run openetruscan-ci-pr \
  --project=long-facet-427508-j2 \
  --branch=feature/whatever
```

### See history

```bash
gcloud builds list \
  --project=long-facet-427508-j2 \
  --filter='source.repoSource.repoName=github_Eddy1919_openEtruscan' \
  --limit=10
```

### Debug a failing build

The build's stderr is logged to Cloud Logging under
`logName="projects/long-facet-427508-j2/logs/cloudbuild"`. Filter
on the build ID printed in the trigger output.

## What's intentionally different from the GH-Actions era

- **No Bandit / Semgrep / pip-audit.** Chronic false positives. Replaced
  by the trust we already place in Gitleaks (real value: catches
  credentials) and the fact that pip security advisories are aggressively
  re-scanned by Dependabot via GitHub's native dependency tab.
- **Python matrix runs on main pushes only**, not on every PR. PRs
  test against 3.12 (the prod version). Faster feedback for the 95% of
  PRs that don't need 3.10 verification; main-push matrix is the safety
  net for the 5%.
- **No `continue-on-error` workarounds** for mypy/pyright. They still
  print warnings (non-blocking), but the syntax is explicit at the
  step level rather than buried in workflow metadata.
- **Deploy pulls from Artifact Registry by reference** (after the
  build step in `deploy.yaml`). The on-VM `docker compose build api`
  step is preserved for parity but we can drop it in a follow-up once
  the AR flow is verified.

## Rollback plan

If Cloud Build breaks badly:

1. Re-add the workflow files from git: `git checkout <pre-migration-commit> .github/workflows/`
2. Disable the Cloud Build triggers via the console (don't delete; keeps the config for retry).
3. Push the restored workflows to main; GH-Actions resumes.

This rollback path stays viable because the workflows were rich enough
to deploy on their own — we're not deleting code that the new system
depends on, only configuration.
