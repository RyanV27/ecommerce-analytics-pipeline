import os
from airflow import DAG
from airflow.providers.google.cloud.transfers.gcs_to_bigquery import GCSToBigQueryOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from datetime import datetime, timedelta

PROJECT_ID = os.environ.get('GCP_PROJECT_ID', 'YOUR_PROJECT_ID')
GCS_BUCKET = os.environ.get('GCS_BUCKET', f'datapulse-raw-{PROJECT_ID}')

# Maps BigQuery table name → GCS object path under olist/
TABLES = {
    'orders':                           'olist/olist_orders_dataset.csv',
    'customers':                        'olist/olist_customers_dataset.csv',
    'order_items':                      'olist/olist_order_items_dataset.csv',
    'order_payments':                   'olist/olist_order_payments_dataset.csv',
    'order_reviews':                    'olist/olist_order_reviews_dataset.csv',
    'products':                         'olist/olist_products_dataset.csv',
    'sellers':                          'olist/olist_sellers_dataset.csv',
    'geolocation':                      'olist/olist_geolocation_dataset.csv',
    'product_category_name_translation': 'olist/product_category_name_translation.csv',
}

with DAG(
    dag_id='ingest_olist_batch',
    schedule_interval='0 2 * * *',
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args={
        'retries': 2,
        'retry_delay': timedelta(minutes=5),
    },
    tags=['ingestion', 'bronze'],
) as dag:

    load_tasks = []
    for table, gcs_path in TABLES.items():
        task = GCSToBigQueryOperator(
            task_id=f'load_{table}',
            bucket=GCS_BUCKET,
            source_objects=[gcs_path],
            destination_project_dataset_table=f'{PROJECT_ID}.bronze.{table}',
            write_disposition='WRITE_TRUNCATE',
            autodetect=True,
            skip_leading_rows=1,
        )
        load_tasks.append(task)

    trigger_dbt = TriggerDagRunOperator(
        task_id='trigger_dbt_run',
        trigger_dag_id='run_dbt_transformations',
    )

    load_tasks >> trigger_dbt
