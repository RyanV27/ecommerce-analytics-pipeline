<#
.SYNOPSIS
    Deploys Airflow onto the Terraform-managed GKE Autopilot cluster via the
    official Helm chart (KubernetesExecutor, Workload Identity).

.DESCRIPTION
    Terraform owns the durable cluster + service accounts + Workload
    Identity bindings (infra/terraform/gke.tf). This script owns the
    ephemeral Helm release — matching the project's existing
    durable-infra-in-Terraform / ephemeral-actions-in-scripts split (see
    infra/submit_vertex_repeat_job.ps1 for the same pattern).

    Idempotent: safe to re-run (helm upgrade --install, kubectl apply).

    Prerequisites:
      - gcloud SDK authenticated, `gcloud components install gke-gcloud-auth-plugin`
      - kubectl and helm installed
      - terraform apply already run (cluster + SAs + WI bindings exist)
      - The datapulse-airflow image built and pushed:
          gcloud builds submit --config airflow/cloudbuild.yaml .   (from src/)
      - GCP_PROJECT_ID, GCS_BUCKET, MLFLOW_TRACKING_URI, ML_TRAINING_SA set in
        the environment or src/.env. MLFLOW_ARTIFACTS_BUCKET and the GKE
        cluster name/region/Airflow SA are resolved from `terraform output`
        if not already set.

.EXAMPLE
    cd src/infra ; ./deploy_airflow.ps1
#>

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$HelmDir = Join-Path $ScriptDir "helm"
$TerraformDir = Join-Path $ScriptDir "terraform"
$Namespace = "airflow"
$ChartVersion = "1.13.1"

# Fall back to src/.env if the vars are not already exported.
if ((-not $env:GCP_PROJECT_ID) -or (-not $env:GCS_BUCKET) -or (-not $env:MLFLOW_TRACKING_URI)) {
    $envFile = Join-Path (Split-Path -Parent $ScriptDir) ".env"
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            if ($line -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$') {
                $name = $Matches[1]
                $value = $Matches[2].Trim('"').Trim("'")
                if (-not (Get-Item "env:$name" -ErrorAction SilentlyContinue)) {
                    Set-Item "env:$name" $value
                }
            }
        }
    }
}

foreach ($required in @("GCP_PROJECT_ID", "GCS_BUCKET", "MLFLOW_TRACKING_URI")) {
    if (-not (Get-Item "env:$required" -ErrorAction SilentlyContinue)) {
        throw "$required is not set. Export it or populate src/.env first."
    }
}

function Get-TerraformOutput {
    param([string]$Name)
    Push-Location $TerraformDir
    try {
        return (terraform output -raw $Name)
    } finally {
        Pop-Location
    }
}

$MlTrainingSa = $env:ML_TRAINING_SA
if (-not $MlTrainingSa) { $MlTrainingSa = Get-TerraformOutput "ml_training_service_account_email" }
if (-not $MlTrainingSa) { throw "Could not resolve ml_training service account. Set ML_TRAINING_SA or run terraform apply first." }

$MlflowBucket = $env:MLFLOW_ARTIFACTS_BUCKET
if (-not $MlflowBucket) { $MlflowBucket = Get-TerraformOutput "mlflow_artifacts_bucket" }
if (-not $MlflowBucket) { throw "Could not resolve the MLflow artifacts bucket. Set MLFLOW_ARTIFACTS_BUCKET or run terraform apply first." }

$AirflowGkeSa = Get-TerraformOutput "airflow_gke_service_account_email"
if (-not $AirflowGkeSa) { throw "Could not resolve the airflow_gke service account. Run terraform apply first." }

$ClusterName = Get-TerraformOutput "gke_cluster_name"
$ClusterRegion = Get-TerraformOutput "gke_region"

Write-Host "Fetching cluster credentials for $ClusterName ($ClusterRegion) ..."
gcloud container clusters get-credentials $ClusterName --region $ClusterRegion --project $env:GCP_PROJECT_ID

Write-Host "Adding/updating the apache-airflow Helm repo ..."
helm repo add apache-airflow https://airflow.apache.org 2>$null
helm repo update apache-airflow | Out-Null

Write-Host "Ensuring namespace '$Namespace' exists ..."
kubectl create namespace $Namespace --dry-run=client -o yaml | kubectl apply -f -

Write-Host "Applying the ml-training KubernetesServiceAccount ..."
$renderedKsa = Join-Path $env:TEMP "ml-training-ksa.rendered.yaml"
(Get-Content (Join-Path $HelmDir "ml-training-ksa.yaml") -Raw) `
    -replace '__ML_TRAINING_SA__', $MlTrainingSa |
    Set-Content -Path $renderedKsa -Encoding utf8
kubectl apply -f $renderedKsa

Write-Host "Deploying Airflow via Helm (executor=KubernetesExecutor) ..."
helm upgrade --install airflow apache-airflow/airflow `
    --version $ChartVersion `
    --namespace $Namespace `
    --values (Join-Path $HelmDir "airflow-values.yaml") `
    --set images.airflow.repository="gcr.io/$($env:GCP_PROJECT_ID)/datapulse-airflow" `
    --set-string "scheduler.serviceAccount.annotations.iam\.gke\.io/gcp-service-account=$AirflowGkeSa" `
    --set-string "webserver.serviceAccount.annotations.iam\.gke\.io/gcp-service-account=$AirflowGkeSa" `
    --set-string "triggerer.serviceAccount.annotations.iam\.gke\.io/gcp-service-account=$AirflowGkeSa" `
    --set-string "workers.serviceAccount.annotations.iam\.gke\.io/gcp-service-account=$AirflowGkeSa" `
    --set-string "env[0].value=$($env:GCP_PROJECT_ID)" `
    --set-string "env[1].value=$($env:GCS_BUCKET)" `
    --set-string "env[2].value=$($env:MLFLOW_TRACKING_URI)" `
    --set-string "env[3].value=$MlTrainingSa" `
    --set-string "env[4].value=$MlflowBucket" `
    --set-string config.logging.remote_base_log_folder="gs://$MlflowBucket/airflow-logs"
if ($LASTEXITCODE -ne 0) { throw "helm upgrade failed (exit $LASTEXITCODE)" }
# No --wait: the scheduler/webserver pods block on a "wait-for-airflow-migrations"
# init container until the airflow-run-airflow-migrations Job (a post-upgrade
# hook) completes, but --wait blocks on those same pods becoming Ready *before*
# post-upgrade hooks run -- a real deadlock in this chart, not just a slow
# rollout. Watch readiness manually instead: `kubectl get pods -n airflow -w`.

Write-Host ""
Write-Host "Deploy complete. Watch pods come up with:"
Write-Host "  kubectl get pods -n $Namespace -w"
Write-Host "Then access the webserver with:"
Write-Host "  kubectl port-forward svc/airflow-webserver 8080:8080 -n $Namespace"
Write-Host "Open http://localhost:8080 (login: admin / admin)."
