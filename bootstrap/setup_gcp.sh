#!/usr/bin/env bash
# =============================================================================
# One-time Google Cloud bootstrap (idempotent: safe to re-run).
#
# Creates a CI/CD service account and a Workload Identity Federation pool that
# lets GitHub Actions of ONE repository impersonate it with short-lived OIDC
# tokens. No service account key is ever created or downloaded.
#
# Usage:
#   GCP_PROJECT_ID=my-project GITHUB_REPOSITORY=owner/repo ./bootstrap/setup_gcp.sh
#
# Optional:
#   CONFIGURE_GITHUB=true    store the outputs as GitHub secrets with the gh CLI
#   BUDGET_AMOUNT=1          create a monthly budget alert (USD) on the billing account
# =============================================================================
set -euo pipefail

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
: "${GITHUB_REPOSITORY:?Set GITHUB_REPOSITORY (owner/repo)}"

SERVICE_ACCOUNT_NAME="bq-ecommerce-cicd"
POOL_ID="github"
PROVIDER_ID="github-oidc"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
PROJECT_NUMBER="$(gcloud projects describe "$GCP_PROJECT_ID" --format='value(projectNumber)')"

echo "==> Enabling APIs"
gcloud services enable \
  bigquery.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project "$GCP_PROJECT_ID"

echo "==> Service account"
if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT" --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
    --project "$GCP_PROJECT_ID" \
    --display-name "BigQuery e-commerce CI/CD" \
    --description "Runs bqchange migrations and dbt from GitHub Actions"
fi

# jobUser: run queries and load jobs. dataOwner: create/drop datasets and
# apply dataset-level GRANT statements (A__grants.sql). See docs/runbook.md for
# narrowing dataOwner with IAM conditions on dataset name prefixes.
for role in roles/bigquery.jobUser roles/bigquery.dataOwner; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member "serviceAccount:${SERVICE_ACCOUNT}" \
    --role "$role" \
    --condition None \
    --quiet >/dev/null
done

echo "==> Workload Identity Federation"
if ! gcloud iam workload-identity-pools describe "$POOL_ID" --location global \
    --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "$POOL_ID" \
    --project "$GCP_PROJECT_ID" \
    --location global \
    --display-name "GitHub Actions"
fi

if ! gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" \
    --workload-identity-pool "$POOL_ID" --location global \
    --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
    --project "$GCP_PROJECT_ID" \
    --location global \
    --workload-identity-pool "$POOL_ID" \
    --display-name "GitHub OIDC" \
    --issuer-uri "https://token.actions.githubusercontent.com" \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition "assertion.repository == '${GITHUB_REPOSITORY}'"
fi

# Only workflows of this repository may impersonate the service account.
gcloud iam service-accounts add-iam-policy-binding "$SERVICE_ACCOUNT" \
  --project "$GCP_PROJECT_ID" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${GITHUB_REPOSITORY}" \
  --quiet >/dev/null

PROVIDER="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/providers/${PROVIDER_ID}"

if [ -n "${BUDGET_AMOUNT:-}" ]; then
  echo "==> Budget alert (${BUDGET_AMOUNT} USD / month)"
  gcloud services enable billingbudgets.googleapis.com --project "$GCP_PROJECT_ID"
  BILLING_ACCOUNT="$(gcloud billing projects describe "$GCP_PROJECT_ID" --format='value(billingAccountName)' | sed 's|billingAccounts/||')"
  gcloud billing budgets create \
    --billing-account "$BILLING_ACCOUNT" \
    --display-name "bigquery-schemachange" \
    --budget-amount "${BUDGET_AMOUNT}USD" \
    --filter-projects "projects/${GCP_PROJECT_ID}" \
    --threshold-rule percent=0.5 \
    --threshold-rule percent=1.0
fi

if [ "${CONFIGURE_GITHUB:-false}" = "true" ]; then
  echo "==> GitHub secrets and variables (${GITHUB_REPOSITORY})"
  gh secret set GCP_PROJECT_ID --repo "$GITHUB_REPOSITORY" --body "$GCP_PROJECT_ID"
  gh secret set GCP_WORKLOAD_IDENTITY_PROVIDER --repo "$GITHUB_REPOSITORY" --body "$PROVIDER"
  gh secret set GCP_SERVICE_ACCOUNT --repo "$GITHUB_REPOSITORY" --body "$SERVICE_ACCOUNT"
  gh variable set GCP_ENABLED --repo "$GITHUB_REPOSITORY" --body "true"
  echo "Done. Values are stored as secrets so they are masked in public workflow logs."
else
  cat <<EOF

Add these as GitHub Actions *secrets* (Settings > Secrets and variables > Actions):
  GCP_PROJECT_ID                  ${GCP_PROJECT_ID}
  GCP_WORKLOAD_IDENTITY_PROVIDER  ${PROVIDER}
  GCP_SERVICE_ACCOUNT             ${SERVICE_ACCOUNT}
Then create the repository *variable* GCP_ENABLED=true.
EOF
fi
