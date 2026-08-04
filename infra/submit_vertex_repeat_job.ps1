<#
.SYNOPSIS
    Renders the Vertex AI CustomJobSpec template and submits the
    repeat-purchase training job to Vertex AI.

.DESCRIPTION
    infra/vertex/vertex_repeat_job.yaml is a template with __TOKEN__
    placeholders — it is NOT runnable as-is. This script fills in the real
    project id, MLflow URL, and ml_training service-account email, writes a
    rendered copy to the temp dir, and calls `gcloud ai custom-jobs create`.

    This is the manual / Windows-dev path for launching the repeat-purchase
    Vertex job during setup and testing. The weekly `retrain_models` Airflow
    DAG submits the same job via the aiplatform Python SDK
    (airflow/dags/retrain_models.py: submit_vertex_repeat_job) — both render
    the same committed YAML template, so the job spec stays a single source
    of truth. (Segmentation and forecasting no longer use Vertex AI — they
    run as KubernetesPodOperator tasks on the GKE Airflow cluster.)

    Prerequisites:
      - gcloud SDK authenticated (`gcloud auth login`) with the target project.
      - The datapulse-ml image built and pushed (see docs/cloud_training_setup.md).
      - Terraform applied (so the ml_training SA + MLflow service exist).
      - GCP_PROJECT_ID and MLFLOW_TRACKING_URI set in the environment (or src/.env).
        ML_TRAINING_SA is read from the environment if set, otherwise from
        `terraform output`.

.EXAMPLE
    cd src/infra ; ./submit_vertex_repeat_job.ps1
#>

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VertexDir = Join-Path $ScriptDir "vertex"
$Region = "us-central1"

# Fall back to src/.env if the vars are not already exported.
if ((-not $env:GCP_PROJECT_ID) -or (-not $env:MLFLOW_TRACKING_URI)) {
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

if (-not $env:GCP_PROJECT_ID) {
    throw "GCP_PROJECT_ID is not set. Export it or populate src/.env first."
}
if (-not $env:MLFLOW_TRACKING_URI) {
    throw "MLFLOW_TRACKING_URI is not set. Use the mlflow_url Terraform output."
}

$MlTrainingSa = $env:ML_TRAINING_SA
if (-not $MlTrainingSa) {
    Push-Location (Join-Path $ScriptDir "terraform")
    try {
        $MlTrainingSa = (terraform output -raw ml_training_service_account_email)
    } finally {
        Pop-Location
    }
}
if (-not $MlTrainingSa) {
    throw "Could not resolve the ml_training service account. Set ML_TRAINING_SA or run terraform apply first."
}

$SpecFile = "vertex_repeat_job.yaml"
$DisplayName = "datapulse-repeat-purchase-training"
$srcPath = Join-Path $VertexDir $SpecFile
$tmpPath = Join-Path $env:TEMP "$SpecFile.rendered.yaml"

(Get-Content $srcPath -Raw) `
    -replace '__PROJECT_ID__', $env:GCP_PROJECT_ID `
    -replace '__MLFLOW_TRACKING_URI__', $env:MLFLOW_TRACKING_URI `
    -replace '__ML_TRAINING_SA__', $MlTrainingSa |
    Set-Content -Path $tmpPath -Encoding utf8

Write-Host "Submitting $DisplayName ..."
gcloud ai custom-jobs create `
    --region=$Region `
    --display-name=$DisplayName `
    --config=$tmpPath
if ($?) { Write-Host "$DisplayName submitted." }
