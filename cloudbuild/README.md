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
| **`double-runway-465420-h9`** | **Where all Cloud Build runs execute.** Default Cloud Build SA, Secret Manager, and the GitHub App connection live here. |
| **`long-facet-427508-j2`** | Hosts the prod GCE VM `openetruscan-eu` and the Artifact Registry repo `openetruscan/api`. The Cloud Build SA in double-runway impersonates `gh-actions-deployer@long-facet-427508-j2.iam.gserviceaccount.com` for any operation that needs to touch this project. |

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

In the Cloud Build console for `double-runway-465420-h9`:

```
Settings → Connections → Connect repository → GitHub (Cloud Build GitHub App)
```

Pick the openEtruscan repo. This is what makes commit statuses post back to PRs.

### 2. Grant the Cloud Build SA the IAM roles it needs

The default Cloud Build SA is
`<PROJECT_NUMBER>@cloudbuild.gserviceaccount.com` — for
`double-runway-465420-h9` (project number `27914760876`), that's
`27914760876@cloudbuild.gserviceaccount.com`.

Roles to grant in `double-runway-465420-h9` (the build project):

```bash
PROJECT=double-runway-465420-h9
CB_SA=27914760876@cloudbuild.gserviceaccount.com

for ROLE in \
  roles/cloudbuild.builds.builder \
  roles/secretmanager.secretAccessor \
  roles/storage.objectAdmin ; do
    gcloud projects add-iam-policy-binding $PROJECT \
      --member="serviceAccount:$CB_SA" \
      --role="$ROLE" --condition=None
done
```

Roles to grant in `long-facet-427508-j2` (the deploy project) so the
build SA can impersonate `gh-actions-deployer`:

```bash
DEPLOY_PROJECT=long-facet-427508-j2
DEPLOYER_SA=gh-actions-deployer@${DEPLOY_PROJECT}.iam.gserviceaccount.com

# Build SA can mint impersonation tokens for the deployer SA.
gcloud iam service-accounts add-iam-policy-binding $DEPLOYER_SA \
  --project=$DEPLOY_PROJECT \
  --member="serviceAccount:$CB_SA" \
  --role="roles/iam.serviceAccountTokenCreator"
```

The deployer SA already has IAP-Tunnel + GCE SSH + Artifact Registry
write roles in long-facet from the GH-Actions era — no new grants
needed on that side.

### 3. Create the secrets in Secret Manager

```bash
# Only one new secret is needed: the PyPI API token for the release
# workflow. Everything else (oe-database-url, etc.) already exists.
echo -n "<your PyPI API token>" | gcloud secrets create pypi-api-token \
  --project=double-runway-465420-h9 \
  --replication-policy=automatic --data-file=-
```

If trusted publishing (OIDC) gets configured later, `pypi-api-token`
becomes unnecessary — see the comment in [`pypi.yaml`](pypi.yaml).

### 4. Create the triggers

Run these from your local shell with `gcloud config set project double-runway-465420-h9` first.

```bash
PROJECT=double-runway-465420-h9
REPO=openEtruscan
OWNER=Eddy1919

# 4a. PR build (ci.yaml) — runs on every PR opened against main
gcloud builds triggers create github \
  --project=$PROJECT \
  --name=openetruscan-ci-pr \
  --repo-owner=$OWNER --repo-name=$REPO \
  --pull-request-pattern="^main$" \
  --build-config=cloudbuild/ci.yaml \
  --description="Fast PR lane: lint + py3.12 tests + types + openapi"

# 4b. Push-to-main matrix (ci-matrix.yaml)
gcloud builds triggers create github \
  --project=$PROJECT \
  --name=openetruscan-ci-matrix \
  --repo-owner=$OWNER --repo-name=$REPO \
  --branch-pattern="^main$" \
  --build-config=cloudbuild/ci-matrix.yaml \
  --description="Full Python matrix (3.10–3.13) on main pushes only"

# 4c. Deploy on main pushes when relevant paths change
gcloud builds triggers create github \
  --project=$PROJECT \
  --name=openetruscan-deploy \
  --repo-owner=$OWNER --repo-name=$REPO \
  --branch-pattern="^main$" \
  --build-config=cloudbuild/deploy.yaml \
  --included-files="src/**,Dockerfile,docker-compose.yml,nginx.conf,pyproject.toml,data/**,alembic.ini,scripts/ops/fetch-env-from-sm.sh" \
  --description="Build image + IAP SSH rotate to openetruscan-eu"

# 4d. Security scan on main pushes
gcloud builds triggers create github \
  --project=$PROJECT \
  --name=openetruscan-security \
  --repo-owner=$OWNER --repo-name=$REPO \
  --branch-pattern="^main$" \
  --build-config=cloudbuild/security.yaml \
  --description="Gitleaks secret detection"

# 4e. Weekly security scan via Cloud Scheduler hitting the trigger's webhook
#     (no Cloud Build native cron; use Scheduler → run-build invoker)
gcloud scheduler jobs create http openetruscan-security-weekly \
  --project=$PROJECT \
  --location=europe-west4 \
  --schedule="0 3 * * 1" \
  --uri="https://cloudbuild.googleapis.com/v1/projects/$PROJECT/triggers/openetruscan-security:run" \
  --http-method=POST \
  --message-body='{"branchName":"main"}' \
  --oauth-service-account-email=$CB_SA

# 4f. PyPI publish on release tags
gcloud builds triggers create github \
  --project=$PROJECT \
  --name=openetruscan-pypi-publish \
  --repo-owner=$OWNER --repo-name=$REPO \
  --tag-pattern="^v[0-9]+\.[0-9]+\.[0-9]+.*$" \
  --build-config=cloudbuild/pypi.yaml \
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
  --project=double-runway-465420-h9 \
  --branch=feature/whatever
```

### See history

```bash
gcloud builds list \
  --project=double-runway-465420-h9 \
  --filter='source.repoSource.repoName=github_Eddy1919_openEtruscan' \
  --limit=10
```

### Debug a failing build

The build's stderr is logged to Cloud Logging under
`logName="projects/double-runway-465420-h9/logs/cloudbuild"`. Filter
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
