from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

with DAG(
    dag_id='run_dbt_transformations',
    schedule_interval=None,  # triggered by ingest_olist_batch
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args={
        'retries': 1,
        'retry_delay': timedelta(minutes=5),
    },
    tags=['dbt', 'transformation'],
) as dag:

    dbt_run = BashOperator(
        task_id='dbt_run',
        bash_command='cd /opt/airflow/dbt/datapulse && dbt run --profiles-dir /opt/airflow/dbt',
    )

    dbt_test = BashOperator(
        task_id='dbt_test',
        bash_command='cd /opt/airflow/dbt/datapulse && dbt test --profiles-dir /opt/airflow/dbt',
    )

    dbt_run >> dbt_test
