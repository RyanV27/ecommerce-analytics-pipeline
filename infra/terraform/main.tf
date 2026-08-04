# DataPulse model-training infrastructure.
#
# Scope: MLflow tracking server, artifacts bucket, and the ml_training
# service account + IAM (now the identity shared by KubernetesPodOperator
# training pods and the retained Vertex AI repeat-purchase job — see gke.tf
# for the GKE cluster and Workload Identity bindings). The dashboard's own
# Cloud Run service stays on the existing gcloud/WIF pipeline
# (deploy.yml + cloudbuild.yaml) and is NOT managed here.
#
# Prerequisite: build & push both images before `terraform apply` —
#   gcloud builds submit --config mlflow_server/cloudbuild.yaml .
#   gcloud builds submit --config ml/cloudbuild.yaml .
# (run from src/). See docs/cloud_training_setup.md for the full runbook.

resource "google_storage_bucket" "mlflow_artifacts" {
  name                        = "datapulse-mlflow-${var.project_id}"
  location                    = "US"
  uniform_bucket_level_access = true
  force_destroy               = false
}

resource "google_service_account" "ml_training" {
  account_id   = "datapulse-ml-training"
  display_name = "DataPulse ML training (Cloud Run Job + Vertex AI)"
}

locals {
  ml_training_project_roles = [
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
    "roles/aiplatform.user",
  ]
}

resource "google_project_iam_member" "ml_training_roles" {
  for_each = toset(local.ml_training_project_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.ml_training.email}"
}

# Scoped to the artifacts bucket rather than a project-wide storage role —
# training jobs only need to read/write MLflow artifacts + the GCS-mounted
# SQLite store, not every bucket in the project.
resource "google_storage_bucket_iam_member" "ml_training_artifacts_admin" {
  bucket = google_storage_bucket.mlflow_artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ml_training.email}"
}

# --- MLflow backend store: Cloud SQL for Postgres --------------------------
#
# Supersedes the original SQLite-on-a-GCS-mount backend store, which
# crash-looped in production: gcsfuse cannot honor SQLite's rollback-journal
# file-locking semantics. Postgres has no database *file* and no filesystem
# for gcsfuse to mishandle, eliminating the failure mode outright. See
# plans/phase_4_5_mlflow_cloud_sql_plan.md for the full design rationale.
#
# Operating model: destroy-when-idle. This instance bills continuously
# (~$8-10/mo) — there is no scale-to-zero for Cloud SQL. Provision for a
# verification/demo window, `terraform destroy` when idle.
resource "google_project_service" "sqladmin" {
  service            = "sqladmin.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "secretmanager" {
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

# random_id suffix dodges Cloud SQL's ~1-week instance-name-reuse cooldown
# after a delete, so a same-day destroy -> re-provision doesn't collide.
resource "random_id" "db_suffix" {
  byte_length = 2
}

resource "google_sql_database_instance" "mlflow" {
  name                = "datapulse-mlflow-db-${random_id.db_suffix.hex}"
  database_version    = var.db_version
  region              = var.region
  deletion_protection = false
  depends_on          = [google_project_service.sqladmin]

  settings {
    tier              = var.db_tier
    availability_type = "ZONAL"
    disk_size         = 10
    disk_autoresize   = false

    ip_configuration {
      ipv4_enabled = true
      # Deliberately no authorized_networks — Cloud Run's built-in Cloud SQL
      # Auth Proxy authenticates via IAM (roles/cloudsql.client), so the
      # instance is never exposed directly to the internet.
    }

    backup_configuration {
      enabled = false
    }
  }
}

resource "google_sql_database" "mlflow" {
  name     = "mlflow"
  instance = google_sql_database_instance.mlflow.name
}

resource "random_password" "db" {
  length  = 32
  special = false # avoid URL-encoding pain in the psycopg2 connection URI
}

resource "google_sql_user" "mlflow" {
  name     = "mlflow"
  instance = google_sql_database_instance.mlflow.name
  password = random_password.db.result
}

resource "google_secret_manager_secret" "db_password" {
  secret_id = "mlflow-db-password"
  replication {
    auto {}
  }
  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db.result
}

# Dedicated MLflow-server identity. The service previously ran as the
# ml_training SA, which has no Cloud SQL / Secret Manager grants and would
# not have been able to reach a Postgres backend even if SQLite hadn't
# crash-looped first.
resource "google_service_account" "mlflow_server" {
  account_id   = "datapulse-mlflow-server"
  display_name = "DataPulse MLflow tracking server"
}

resource "google_project_iam_member" "mlflow_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.mlflow_server.email}"
}

resource "google_secret_manager_secret_iam_member" "mlflow_secret_access" {
  secret_id = google_secret_manager_secret.db_password.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.mlflow_server.email}"
}

resource "google_storage_bucket_iam_member" "mlflow_artifacts_access" {
  bucket = google_storage_bucket.mlflow_artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.mlflow_server.email}"
}

# --- MLflow tracking server -------------------------------------------------
#
# Backend store is Cloud SQL Postgres, reached over the Unix socket that
# Cloud Run's native Cloud SQL integration mounts at /cloudsql/<connection
# name> (no VPC connector needed). Artifacts still go to GCS via
# --serve-artifacts. scaling { min=1, max=1 }: Postgres itself would tolerate
# more than one instance, but this plan deliberately keeps max=1 and the
# retrain DAG's serialized job chain — see
# plans/phase_4_5_mlflow_cloud_sql_plan.md §12 decision 4.
resource "google_cloud_run_v2_service" "mlflow" {
  name     = "datapulse-mlflow"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.mlflow_server.email

    scaling {
      min_instance_count = 1
      max_instance_count = 1
    }

    containers {
      image = var.mlflow_image

      ports {
        container_port = 8080
      }

      env {
        name  = "ARTIFACTS_BUCKET"
        value = google_storage_bucket.mlflow_artifacts.name
      }

      env {
        name  = "INSTANCE_CONNECTION_NAME"
        value = google_sql_database_instance.mlflow.connection_name
      }

      env {
        name  = "DB_NAME"
        value = google_sql_database.mlflow.name
      }

      env {
        name  = "DB_USER"
        value = google_sql_user.mlflow.name
      }

      env {
        name = "DB_PASS"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      resources {
        limits = {
          memory = "2Gi" # mlflow 3.x's dependency set OOMs at 1Gi (1042Mi used)
          cpu    = "1"
        }
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.mlflow.connection_name]
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_secret_manager_secret_version.db_password,
    google_sql_database.mlflow,
  ]
}

# Demo-grade: unauthenticated, same posture as the dashboard's Cloud Run
# service. Locking this down to IAM-authenticated invocations (bearer token
# in MLFLOW_TRACKING_URI callers) is a documented future improvement, not
# implemented here.
resource "google_cloud_run_v2_service_iam_member" "mlflow_public" {
  location = google_cloud_run_v2_service.mlflow.location
  name     = google_cloud_run_v2_service.mlflow.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
