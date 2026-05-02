# Workload Identity Federation Setup

This runbook documents the one-time Google Cloud setup required to allow GitHub Actions to securely push Docker images to Artifact Registry without using long-lived JSON service account keys.

## 1. Create the Service Account

This service account will be impersonated by GitHub Actions.

```bash
PROJECT_ID="long-facet-427508-j2"

gcloud iam service-accounts create github-ci \
  --display-name="GitHub Actions CI" \
  --project="${PROJECT_ID}"
```

## 2. Grant Artifact Registry Permissions

Allow the service account to write to the Docker registry:

```bash
gcloud artifacts repositories add-iam-policy-binding openetruscan \
  --location=europe-west4 \
  --member="serviceAccount:github-ci@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer" \
  --project="${PROJECT_ID}"
```

## 3. Create the Workload Identity Pool and Provider

```bash
# Create the pool
gcloud iam workload-identity-pools create github-pool \
  --location="global" \
  --display-name="GitHub Actions Pool" \
  --project="${PROJECT_ID}"

# Create the OIDC provider for GitHub
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --project="${PROJECT_ID}"
```

## 4. Bind the GitHub Repository to the Service Account

Allow tokens originating from the `Eddy1919/openEtruscan` repository to impersonate the service account:

```bash
export REPO="Eddy1919/openEtruscan"
export WORKLOAD_IDENTITY_POOL_ID=$(gcloud iam workload-identity-pools describe github-pool \
  --project="${PROJECT_ID}" --location="global" --format="value(name)")

gcloud iam service-accounts add-iam-policy-binding "github-ci@${PROJECT_ID}.iam.gserviceaccount.com" \
  --project="${PROJECT_ID}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/${WORKLOAD_IDENTITY_POOL_ID}/attribute.repository/${REPO}"
```

## 5. Get the Provider Name for GitHub Actions

Extract the fully qualified provider name to use in `.github/workflows/ci.yml` (`workload_identity_provider`):

```bash
gcloud iam workload-identity-pools providers describe github-provider \
  --project="${PROJECT_ID}" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --format="value(name)"
```

Update your `.github/workflows/ci.yml` if the generated provider name differs from what is currently hardcoded.
