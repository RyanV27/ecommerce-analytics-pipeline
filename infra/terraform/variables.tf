variable "project_id" {
  description = "GCP project ID (matches GCP_PROJECT_ID in .env)"
  type        = string
}

variable "region" {
  description = "Region for Cloud Run services/jobs"
  type        = string
  default     = "us-central1"
}

variable "mlflow_image" {
  description = "Fully qualified image for the MLflow tracking server (build first via mlflow_server/cloudbuild.yaml)"
  type        = string
  default     = "gcr.io/PROJECT_ID/datapulse-mlflow"
}

variable "ml_training_image" {
  description = "Fully qualified image shared by the segmentation Cloud Run Job and the Vertex training jobs (build first via ml/cloudbuild.yaml)"
  type        = string
  default     = "gcr.io/PROJECT_ID/datapulse-ml"
}

variable "db_tier" {
  description = "Cloud SQL machine tier for the MLflow backend store."
  type        = string
  default     = "db-f1-micro"
}

variable "db_version" {
  description = "Cloud SQL Postgres version."
  type        = string
  default     = "POSTGRES_15"
}
