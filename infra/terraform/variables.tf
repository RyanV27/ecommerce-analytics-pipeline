variable "project_id" {
  description = "GCP project ID (matches GCP_PROJECT_ID in .env)"
  type        = string
}

variable "region" {
  description = "Region for Cloud Run services/jobs"
  type        = string
  default     = "us-central1"
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
