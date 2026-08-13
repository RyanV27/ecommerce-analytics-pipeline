output "mlflow_url" {
  description = "MLflow tracking server URL — set as MLFLOW_TRACKING_URI for training jobs"
  value       = google_cloud_run_v2_service.mlflow.uri
}

output "mlflow_artifacts_bucket" {
  description = "GCS bucket backing MLflow artifact storage"
  value       = google_storage_bucket.mlflow_artifacts.name
}

output "ml_training_service_account_email" {
  description = "Identity used by KubernetesPodOperator training pods and the Vertex AI repeat-purchase job"
  value       = google_service_account.ml_training.email
}

output "gke_cluster_name" {
  description = "GKE Autopilot cluster running Airflow"
  value       = google_container_cluster.airflow.name
}

output "gke_region" {
  description = "Region of the GKE Autopilot cluster"
  value       = google_container_cluster.airflow.location
}

output "airflow_gke_service_account_email" {
  description = "Workload Identity GSA bound to the Airflow scheduler/webserver KSA"
  value       = google_service_account.airflow_gke.email
}

output "mlflow_db_connection_name" {
  description = "Cloud SQL connection name for the MLflow Postgres backend store (diagnostic)"
  value       = google_sql_database_instance.mlflow.connection_name
}

output "dbt_docs_bucket" {
  description = "GCS bucket serving the published dbt docs static site"
  value       = google_storage_bucket.dbt_docs.name
}

output "dbt_docs_url" {
  description = "Public URL for the published dbt lineage graph / docs site"
  value       = "https://storage.googleapis.com/${google_storage_bucket.dbt_docs.name}/index.html"
}
