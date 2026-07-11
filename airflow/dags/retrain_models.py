from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

# Renders the __TOKEN__ placeholders in the committed infra/vertex/*.yaml specs
# and submits + polls the job via gcloud. Kept as an inline sed+gcloud
# BashOperator (not a .ps1) since the Airflow worker runs Linux; it renders the
# same templates infra/submit_vertex_jobs.ps1 uses for manual/Windows
# submission, so the job specs stay a single source of truth.
#
# `gcloud ai custom-jobs create` returns as soon as the job is submitted, not
# once it finishes, so the task polls job state until it reaches a terminal
# state and exits non-zero on failure (so Airflow retries behave correctly).
VERTEX_SUBMIT_TEMPLATE = """
set -e
RENDERED=$(mktemp)
sed \
    -e "s|__PROJECT_ID__|${{GCP_PROJECT_ID}}|g" \
    -e "s|__MLFLOW_TRACKING_URI__|${{MLFLOW_TRACKING_URI}}|g" \
    -e "s|__ML_TRAINING_SA__|${{ML_TRAINING_SA}}|g" \
    /opt/airflow/infra/vertex/{spec_file} > "$RENDERED"

JOB_NAME=$(gcloud ai custom-jobs create \
    --region=us-central1 \
    --display-name={display_name} \
    --config="$RENDERED" \
    --format="value(name)")

while true; do
    STATE=$(gcloud ai custom-jobs describe "$JOB_NAME" --region=us-central1 --format="value(state)")
    echo "job state: $STATE"
    case "$STATE" in
        JOB_STATE_SUCCEEDED) exit 0 ;;
        JOB_STATE_FAILED|JOB_STATE_CANCELLED) exit 1 ;;
    esac
    sleep 30
done
"""

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

    # Cloud Run Job execution; --wait blocks until the job completes so
    # downstream tasks only start once segmentation has finished writing to
    # the shared MLflow server.
    train_segmentation = BashOperator(
        task_id='train_segmentation',
        bash_command=(
            'gcloud run jobs execute datapulse-segmentation '
            '--region=us-central1 --wait'
        ),
    )

    train_repeat = BashOperator(
        task_id='train_repeat_purchase_model',
        bash_command=VERTEX_SUBMIT_TEMPLATE.format(
            spec_file='vertex_repeat_job.yaml',
            display_name='datapulse-repeat-purchase-training',
        ),
    )

    train_forecasting = BashOperator(
        task_id='train_forecasting',
        bash_command=VERTEX_SUBMIT_TEMPLATE.format(
            spec_file='vertex_forecasting_job.yaml',
            display_name='datapulse-forecasting-training',
        ),
    )

    # Serialized on purpose: the MLflow backend store is Cloud SQL Postgres
    # on a shared-core db-f1-micro instance, and the tracking server stays
    # min=max=1. Running the three training jobs one at a time keeps the
    # instance from being hammered concurrently and keeps run timelines
    # readable.
    train_segmentation >> train_repeat >> train_forecasting
