output "mlflow_url" {
  description = "MLflow tracking server URL — set as MLFLOW_TRACKING_URI for training jobs"
  value       = google_cloud_run_v2_service.mlflow.uri
}

output "mlflow_artifacts_bucket" {
  description = "GCS bucket backing MLflow artifact storage"
  value       = google_storage_bucket.mlflow_artifacts.name
}

output "ml_training_service_account_email" {
  description = "Identity used by the segmentation Cloud Run Job and both Vertex AI training jobs"
  value       = google_service_account.ml_training.email
}

output "segmentation_job_name" {
  description = "Cloud Run Job name — run with: gcloud run jobs execute <name> --region <region> --wait"
  value       = google_cloud_run_v2_job.segmentation.name
}

output "mlflow_db_connection_name" {
  description = "Cloud SQL connection name for the MLflow Postgres backend store (diagnostic)"
  value       = google_sql_database_instance.mlflow.connection_name
}
