import os
import re
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s

from vertex_job import render_vertex_template

_CAMEL_TO_SNAKE_RE = re.compile(r"(?<!^)(?=[A-Z])")


def _camel_to_snake_keys(obj):
    """Recursively converts dict keys from camelCase to snake_case.

    vertex_repeat_job.yaml is camelCase (the REST/gcloud config format
    infra/submit_vertex_repeat_job.ps1 needs). aiplatform.CustomJob's
    worker_pool_specs, however, builds a proto-plus message directly from
    the dict, and proto-plus fields are snake_case -- passing the raw
    camelCase dict raises `Protocol message WorkerPoolSpec has no
    "machineSpec" field.` This conversion only touches the DAG's in-memory
    copy; the shared YAML stays camelCase for the gcloud path.
    """
    if isinstance(obj, dict):
        return {
            _CAMEL_TO_SNAKE_RE.sub("_", k).lower(): _camel_to_snake_keys(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_camel_to_snake_keys(v) for v in obj]
    return obj

NAMESPACE = "airflow"
ML_IMAGE = f"gcr.io/{os.environ['GCP_PROJECT_ID']}/datapulse-ml:latest"
TASK_ENV = [
    k8s.V1EnvVar(name="GCP_PROJECT_ID", value=os.environ["GCP_PROJECT_ID"]),
    k8s.V1EnvVar(name="MLFLOW_TRACKING_URI", value=os.environ.get("MLFLOW_TRACKING_URI", "")),
]
TASK_RESOURCES = k8s.V1ResourceRequirements(requests={"cpu": "2", "memory": "4Gi"})

VERTEX_TEMPLATE_PATH = "/opt/airflow/infra/vertex/vertex_repeat_job.yaml"


def submit_vertex_repeat_job():
    """Submits the repeat-purchase training job to Vertex AI via the
    aiplatform SDK, reusing the committed CustomJobSpec YAML as the single
    source of truth shared with infra/submit_vertex_repeat_job.ps1 (the
    manual submission path)."""
    from google.cloud import aiplatform

    with open(VERTEX_TEMPLATE_PATH) as f:
        template_text = f.read()

    spec = render_vertex_template(
        template_text,
        project_id=os.environ["GCP_PROJECT_ID"],
        mlflow_uri=os.environ["MLFLOW_TRACKING_URI"],
        training_sa=os.environ["ML_TRAINING_SA"],
    )

    aiplatform.init(
        project=os.environ["GCP_PROJECT_ID"],
        location="us-central1",
        staging_bucket=f"gs://{os.environ['MLFLOW_ARTIFACTS_BUCKET']}",
    )
    job = aiplatform.CustomJob(
        display_name="datapulse-repeat-purchase-training",
        worker_pool_specs=_camel_to_snake_keys(spec["workerPoolSpecs"]),
    )
    job.run(service_account=spec["serviceAccount"], sync=True)


with DAG(
    dag_id='retrain_models',
    schedule_interval='0 3 * * 1',  # weekly, Monday 03:00 UTC
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args={
        'retries': 1,
        'retry_delay': timedelta(minutes=10),
    },
    tags=['ml', 'training'],
) as dag:

    train_segmentation = KubernetesPodOperator(
        task_id='train_segmentation',
        name='train-segmentation',
        namespace=NAMESPACE,
        image=ML_IMAGE,
        arguments=['ml/segmentation.py'],
        env_vars=TASK_ENV,
        container_resources=TASK_RESOURCES,
        service_account_name='ml-training',
        get_logs=True,
        is_delete_operator_pod=True,
        startup_timeout_seconds=600,  # Autopilot node provisioning can take minutes
    )

    train_repeat = PythonOperator(
        task_id='train_repeat_purchase_model',
        python_callable=submit_vertex_repeat_job,
    )

    train_forecasting = KubernetesPodOperator(
        task_id='train_forecasting',
        name='train-forecasting',
        namespace=NAMESPACE,
        image=ML_IMAGE,
        arguments=['ml/forecasting.py'],
        env_vars=TASK_ENV,
        container_resources=TASK_RESOURCES,
        service_account_name='ml-training',
        get_logs=True,
        is_delete_operator_pod=True,
        startup_timeout_seconds=600,
    )

    # Serialized on purpose: the MLflow backend store is Cloud SQL Postgres
    # on a shared-core db-f1-micro instance, and the tracking server stays
    # min=max=1. Running the three training jobs one at a time keeps the
    # instance from being hammered concurrently and keeps run timelines
    # readable.
    train_segmentation >> train_repeat >> train_forecasting
