"""
Replays historical Olist orders as real-time events using log replay.
Compresses 2 years of history by re-timestamping events relative to now.
Run from the project root: python kafka/producer.py
"""
import pandas as pd
import json
import time
from kafka import KafkaProducer
from datetime import datetime, timedelta

BOOTSTRAP_SERVERS = 'localhost:9092'
TOPIC = 'olist.orders'
# 1 real minute = 30 historical days
COMPRESSION_RATIO = 60 * 24 * 30

producer = KafkaProducer(
    bootstrap_servers=BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8'),
)

orders = pd.read_csv('data/olist_orders_dataset.csv')
orders['order_purchase_timestamp'] = pd.to_datetime(orders['order_purchase_timestamp'])
orders = orders.sort_values('order_purchase_timestamp').reset_index(drop=True)

first_ts = orders['order_purchase_timestamp'].min()
replay_start = datetime.now()

print(f"Replaying {len(orders):,} orders. Press Ctrl+C to stop.")

for _, row in orders.iterrows():
    historical_offset = (row['order_purchase_timestamp'] - first_ts).total_seconds()
    replay_offset = historical_offset / COMPRESSION_RATIO
    target_time = replay_start + timedelta(seconds=replay_offset)

    sleep_secs = (target_time - datetime.now()).total_seconds()
    if sleep_secs > 0:
        time.sleep(sleep_secs)

    event = row.to_dict()
    event['event_timestamp'] = datetime.now().isoformat()
    producer.send(TOPIC, value=event)
    print(f"Sent order {event['order_id']}")

producer.flush()
print("Done — all orders replayed.")
