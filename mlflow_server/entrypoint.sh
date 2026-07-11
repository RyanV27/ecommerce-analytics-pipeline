#!/bin/sh
set -e

# Cloud Run mounts the Cloud SQL Auth Proxy socket under /cloudsql/<conn>.
# psycopg2 reaches it via the ?host=/cloudsql/<conn> Unix-socket form.
BACKEND_URI="postgresql+psycopg2://${DB_USER}:${DB_PASS}@/${DB_NAME}?host=/cloudsql/${INSTANCE_CONNECTION_NAME}"

# Run schema migrations ONCE, before the server (and its gunicorn workers)
# start. Prevents a concurrent-migration collision ("relation already
# exists") if multiple workers or a restart raced the auto-migration that
# `mlflow server` would otherwise run on its own. mlflow db upgrade is
# idempotent.
mlflow db upgrade "${BACKEND_URI}"

# MLflow's security middleware defaults to localhost-only Host/CORS
# allowlists (DNS-rebinding protection) even with --host 0.0.0.0, which
# rejects Cloud Run's health-check probes and any real traffic. The Cloud
# Run URL isn't known before first deploy, so pin to '*' rather than a
# specific hostname -- consistent with this service already being
# unauthenticated/demo-grade (see infra/terraform/main.tf mlflow_public).
exec mlflow server \
  --host 0.0.0.0 --port 8080 \
  --backend-store-uri "${BACKEND_URI}" \
  --artifacts-destination "gs://${ARTIFACTS_BUCKET}/mlflow" \
  --serve-artifacts \
  --allowed-hosts '*' \
  --cors-allowed-origins '*'
