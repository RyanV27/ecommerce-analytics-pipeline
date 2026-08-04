# Airflow orchestration infra: a GKE Autopilot cluster (Airflow itself is
# deployed on top via Helm — see infra/helm/ + infra/deploy_airflow.ps1, kept
# out of Terraform per the project's durable-infra/ephemeral-action split)
# plus the Workload Identity bindings that let in-cluster pods act as GCP
# service accounts with no key files or gcloud-config seeding.
#
# Operating model: destroy-when-idle, same as the MLflow/Cloud SQL stack.

resource "google_project_service" "container" {
  service            = "container.googleapis.com"
  disable_on_destroy = false
}

data "google_project" "current" {}

# No custom node_config.service_account -> nodes run as the default Compute
# Engine SA, which newer projects no longer auto-grant roles to.
resource "google_project_iam_member" "default_node_sa_container_role" {
  project = var.project_id
  role    = "roles/container.defaultNodeServiceAccount"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

# Same gap also breaks image pulls: this project's gcr.io is backed by
# Artifact Registry (not the legacy GCS-backed registry), so nodes need
# artifactregistry.reader under their own SA to pull datapulse-airflow/ml/mlflow.
resource "google_project_iam_member" "default_node_sa_gcr_pull" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

# Autopilot enables Workload Identity implicitly (it cannot be disabled on
# Autopilot clusters), so no explicit workload_identity_config block is needed.
resource "google_container_cluster" "airflow" {
  name                = "datapulse-airflow"
  location            = var.region
  enable_autopilot    = true
  deletion_protection = false

  depends_on = [google_project_service.container]
}

# Identity for the Airflow scheduler/webserver/triggerer pods (bound to the
# `airflow` KSA in namespace `airflow` via Workload Identity below).
resource "google_service_account" "airflow_gke" {
  account_id   = "airflow-gke"
  display_name = "DataPulse Airflow (GKE Workload Identity)"
}

locals {
  airflow_gke_project_roles = [
    "roles/storage.objectViewer",  # raw CSV reads (GCSToBigQueryOperator)
    "roles/bigquery.jobUser",      # dbt / BQ load jobs
    "roles/bigquery.dataEditor",   # dbt builds into silver/gold
    "roles/aiplatform.user",       # submits the repeat-purchase Vertex CustomJob
  ]
}

resource "google_project_iam_member" "airflow_gke_roles" {
  for_each = toset(local.airflow_gke_project_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.airflow_gke.email}"
}

# Lets airflow_gke attach the ml_training SA to the Vertex CustomJob it
# submits (aiplatform.CustomJob.run(service_account=...) requires the caller
# to be able to act as that service account).
resource "google_service_account_iam_member" "airflow_actas_ml_training" {
  service_account_id = google_service_account.ml_training.name
  role                = "roles/iam.serviceAccountUser"
  member              = "serviceAccount:${google_service_account.airflow_gke.email}"
}

# Task pods are ephemeral under KubernetesExecutor — without remote logging,
# task logs vanish when the pod is deleted. Reuses the existing MLflow
# artifacts bucket rather than provisioning a dedicated one.
resource "google_storage_bucket_iam_member" "airflow_logs" {
  bucket = google_storage_bucket.mlflow_artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.airflow_gke.email}"
}

# Workload Identity bindings: let the in-cluster KSAs impersonate the GSAs
# above. The apache-airflow chart creates one KSA per component (there is no
# single shared "airflow" KSA, despite the top-level `serviceAccount:` name
# in airflow-values.yaml/deploy_airflow.ps1 -- that value has no effect since
# this chart has no top-level serviceAccount key, see Tier 3 finding 6 in
# docs/phase_4_6_test_results.md), so every real component KSA that runs
# GCP-calling code needs its own binding to airflow_gke GSA.
# `ml-training` KSA (KubernetesPodOperator training pods) -> ml_training GSA
# (the same identity already used by the Vertex jobs).
locals {
  airflow_component_ksas = [
    "airflow-scheduler",  # GCSToBigQueryOperator / dbt BQ calls / task submission
    "airflow-webserver",  # remote log fetch from GCS after task pod deletion
    "airflow-triggerer",
    "airflow-worker",     # KubernetesExecutor task pod template service account
  ]
}

resource "google_service_account_iam_member" "airflow_gke_workload_identity" {
  for_each            = toset(local.airflow_component_ksas)
  service_account_id  = google_service_account.airflow_gke.name
  role                = "roles/iam.workloadIdentityUser"
  member              = "serviceAccount:${var.project_id}.svc.id.goog[airflow/${each.value}]"
}

resource "google_service_account_iam_member" "ml_training_workload_identity" {
  service_account_id = google_service_account.ml_training.name
  role                = "roles/iam.workloadIdentityUser"
  member              = "serviceAccount:${var.project_id}.svc.id.goog[airflow/ml-training]"
}
