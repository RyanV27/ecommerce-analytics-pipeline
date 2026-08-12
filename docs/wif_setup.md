# One-Time GCP Setup — Workload Identity Federation + Service Accounts

This is the one-time manual setup for keyless GitHub Actions → GCP authentication used by the dashboard's CD pipeline (`.github/workflows/deploy.yml`). It creates a Workload Identity Pool + GitHub OIDC provider and the two service accounts that pipeline needs. Run all commands in PowerShell from the repo root; replace placeholders with your actual values.

> **Scope note:** this covers the *manual* WIF setup for GitHub Actions. The other service accounts in this project (`ml_training`, `mlflow_server`, `airflow_gke`) and the GKE-side Workload Identity bindings they use are created automatically by `terraform apply` (`infra/terraform/main.tf`, `infra/terraform/gke.tf`) — no manual steps needed for those. See the [Other service accounts in this project](#other-service-accounts-in-this-project) section below.

```powershell
$PROJECT    = "project-837f8c23-eea0-4cd3-975"
$REGION     = "us-central1"
$REPO_OWNER = "YOUR_GITHUB_USERNAME"   # e.g. ryanv
$REPO_NAME  = "YOUR_REPO_NAME"        # e.g. end-to-end-analytics-pipeline
$POOL_ID    = "github-actions-pool"
$PROVIDER_ID = "github-provider"
$DEPLOYER_SA = "datapulse-deployer@$PROJECT.iam.gserviceaccount.com"
$RUNTIME_SA  = "datapulse-cloudrun@$PROJECT.iam.gserviceaccount.com"
```

---

## 1 — Enable required APIs

```powershell
gcloud services enable `
  run.googleapis.com `
  cloudbuild.googleapis.com `
  artifactregistry.googleapis.com `
  containerregistry.googleapis.com `
  iamcredentials.googleapis.com `
  --project $PROJECT
```

---

## 2 — Create service accounts

```powershell
# Deployer SA — used by GitHub Actions to build and deploy
gcloud iam service-accounts create datapulse-deployer `
  --display-name "DataPulse GitHub Actions Deployer" `
  --project $PROJECT

# Runtime SA — attached to the Cloud Run service; queries BigQuery
gcloud iam service-accounts create datapulse-cloudrun `
  --display-name "DataPulse Cloud Run Runtime" `
  --project $PROJECT
```

---

## 3 — Grant IAM roles

### Deployer SA — needs to build images and deploy Cloud Run services

```powershell
# Build and push images
gcloud projects add-iam-policy-binding $PROJECT `
  --member "serviceAccount:$DEPLOYER_SA" `
  --role "roles/cloudbuild.builds.editor"

gcloud projects add-iam-policy-binding $PROJECT `
  --member "serviceAccount:$DEPLOYER_SA" `
  --role "roles/storage.admin"

# Deploy Cloud Run services
gcloud projects add-iam-policy-binding $PROJECT `
  --member "serviceAccount:$DEPLOYER_SA" `
  --role "roles/run.admin"

# Act as the Cloud Run runtime SA (required for --service-account flag)
gcloud iam service-accounts add-iam-policy-binding $RUNTIME_SA `
  --member "serviceAccount:$DEPLOYER_SA" `
  --role "roles/iam.serviceAccountUser" `
  --project $PROJECT
```

### Runtime SA — queries BigQuery Gold tables

```powershell
gcloud projects add-iam-policy-binding $PROJECT `
  --member "serviceAccount:$RUNTIME_SA" `
  --role "roles/bigquery.dataViewer"

gcloud projects add-iam-policy-binding $PROJECT `
  --member "serviceAccount:$RUNTIME_SA" `
  --role "roles/bigquery.jobUser"
```

---

## 4 — Create Workload Identity Pool and GitHub OIDC provider

```powershell
# Create the pool
gcloud iam workload-identity-pools create $POOL_ID `
  --location global `
  --display-name "GitHub Actions Pool" `
  --project $PROJECT

# Get the pool resource name (needed later)
$POOL_NAME = gcloud iam workload-identity-pools describe $POOL_ID `
  --location global `
  --project $PROJECT `
  --format "value(name)"

# Create the GitHub OIDC provider
gcloud iam workload-identity-pools providers create-oidc $PROVIDER_ID `
  --location global `
  --workload-identity-pool $POOL_ID `
  --display-name "GitHub Provider" `
  --issuer-uri "https://token.actions.githubusercontent.com" `
  --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" `
  --attribute-condition "attribute.repository == '${REPO_OWNER}/${REPO_NAME}'" `
  --project $PROJECT
```

---

## 5 — Bind the provider identity to the deployer SA

```powershell
$PROVIDER_NAME = gcloud iam workload-identity-pools providers describe $PROVIDER_ID `
  --location global `
  --workload-identity-pool $POOL_ID `
  --project $PROJECT `
  --format "value(name)"

gcloud iam service-accounts add-iam-policy-binding $DEPLOYER_SA `
  --role "roles/iam.workloadIdentityUser" `
  --member "principalSet://iam.googleapis.com/${POOL_NAME}/attribute.repository/${REPO_OWNER}/${REPO_NAME}" `
  --project $PROJECT
```

---

## 6 — Get the values for GitHub Secrets

```powershell
# workload_identity_provider value for deploy.yml
Write-Host "WIF_PROVIDER:"
gcloud iam workload-identity-pools providers describe $PROVIDER_ID `
  --location global `
  --workload-identity-pool $POOL_ID `
  --project $PROJECT `
  --format "value(name)"

# service_account value for deploy.yml
Write-Host "WIF_SERVICE_ACCOUNT: $DEPLOYER_SA"
Write-Host "GCP_PROJECT_ID: $PROJECT"
```

Add these three values as **GitHub Actions repository secrets** (Settings → Secrets and variables → Actions):

| Secret name | Value |
|---|---|
| `WIF_PROVIDER` | Output from the command above |
| `WIF_SERVICE_ACCOUNT` | `datapulse-deployer@PROJECT.iam.gserviceaccount.com` |
| `GCP_PROJECT_ID` | `project-837f8c23-eea0-4cd3-975` |

---

## 7 — Attach the runtime SA to the Cloud Run service

After the first deploy, pin the runtime SA:

```powershell
gcloud run services update datapulse-dashboard `
  --service-account $RUNTIME_SA `
  --region $REGION `
  --project $PROJECT
```

Subsequent deploys via `deploy.yml` will inherit this setting.

---

## Other service accounts in this project

These are provisioned automatically by `terraform apply` (`infra/terraform/main.tf` and `infra/terraform/gke.tf`) — nothing to run manually:

| Service account | Used by | Bound via |
|---|---|---|
| `ml_training` | KubernetesPodOperator training pods (segmentation, forecasting) + Vertex AI CustomJob (repeat-purchase) | Workload Identity binding to the `ml-training` KSA in the `airflow` namespace |
| `mlflow_server` | MLflow tracking server on Cloud Run | Attached directly as the Cloud Run service's runtime identity (not Workload Identity — Cloud Run services can use a service account directly) |
| `airflow_gke` | Airflow scheduler/webserver/triggerer/worker pods | Workload Identity binding to each of the four per-component KSAs the Airflow Helm chart creates (`airflow-scheduler`, `airflow-webserver`, `airflow-triggerer`, `airflow-worker`) |

If you need to recreate or inspect these bindings by hand, see the resources under `google_service_account.*` and `google_service_account_iam_member.*_workload_identity` in `infra/terraform/main.tf` / `infra/terraform/gke.tf`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `iam.workloadIdentityUser` binding fails | Ensure the pool exists before binding; pool creation takes ~30 s |
| GitHub Actions auth step fails with "invalid token" | Check that `permissions: id-token: write` is set in `deploy.yml` |
| Cloud Run returns 403 on BigQuery | Confirm the **runtime** SA has `bigquery.dataViewer` + `bigquery.jobUser`, not the deployer SA |
| Image not found during deploy | Run `gcloud auth configure-docker` if using Container Registry; or enable Artifact Registry |
| Provider path typo | Copy the exact `name` field output by `gcloud iam workload-identity-pools providers describe` — do not hand-edit it |
| Airflow pod gets `403` on a real GCP API call despite a passing WI *email* metadata probe | The email probe is annotation-only and doesn't check IAM; confirm the Workload Identity binding targets the KSA name the Helm chart actually created for that component, not a single shared `airflow` KSA |
