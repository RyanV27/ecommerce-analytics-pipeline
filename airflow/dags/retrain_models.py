from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

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

    train_repeat = BashOperator(
        task_id='train_repeat_purchase_model',
        bash_command='cd /opt/airflow && python ml/repeat_purchase_model.py',
    )

    train_segmentation = BashOperator(
        task_id='train_segmentation',
        bash_command='cd /opt/airflow && python ml/segmentation.py',
    )

    train_forecasting = BashOperator(
        task_id='train_forecasting',
        bash_command='cd /opt/airflow && python ml/forecasting.py',
    )

    # Models are independent — run in parallel
    [train_repeat, train_segmentation, train_forecasting]
