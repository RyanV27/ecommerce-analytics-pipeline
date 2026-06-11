"""
Reads order events from Kafka and streams them into BigQuery bronze.orders_stream.
Run from the project root: python kafka/consumer.py
Requires: GCP_PROJECT_ID env var and GOOGLE_APPLICATION_CREDENTIALS set.
"""
import json
import math
import os
from kafka import KafkaConsumer
from google.cloud import bigquery

PROJECT_ID = os.environ['GCP_PROJECT_ID']
TABLE_ID = f'{PROJECT_ID}.bronze.orders_stream'
BOOTSTRAP_SERVERS = 'localhost:9092'
TOPIC = 'olist.orders'
BATCH_SIZE = 1    # 50

client = bigquery.Client(project=PROJECT_ID)

consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers=BOOTSTRAP_SERVERS,
    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
    group_id='datapulse-bq-consumer',
    auto_offset_reset='earliest',
)

def sanitize(row):
    return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()}

batch = []
print(f"Listening on {TOPIC}. Writing batches of {BATCH_SIZE} to {TABLE_ID}.")

for message in consumer:
    batch.append(sanitize(message.value))
    if len(batch) >= BATCH_SIZE:
        errors = client.insert_rows_json(TABLE_ID, batch)
        if errors:
            print(f"BQ insert errors: {errors}")
        else:
            print(f"Inserted {len(batch)} rows into {TABLE_ID}")
        batch = []
