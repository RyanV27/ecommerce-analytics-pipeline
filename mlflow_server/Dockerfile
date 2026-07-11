FROM python:3.11-slim

RUN pip install --no-cache-dir mlflow psycopg2-binary google-cloud-storage

COPY mlflow_server/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

# Backend store is Cloud SQL Postgres, reached over the Unix socket Cloud
# Run mounts at /cloudsql/<INSTANCE_CONNECTION_NAME> (see infra/terraform).
# --serve-artifacts routes artifact reads/writes through this service to the
# GCS artifacts bucket. entrypoint.sh runs schema migrations before serving.
ENTRYPOINT ["/entrypoint.sh"]
