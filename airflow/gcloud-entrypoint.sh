#!/usr/bin/env bash
# Wraps the base apache/airflow image's entrypoint to seed gcloud CLI config
# on every container start.
#
# Docker Desktop's Windows bind-mount driver can't satisfy SQLite's
# file-locking/chmod needs for gcloud's credentials.db, so the host's gcloud
# config is mounted read-only at a separate path (GCLOUD_HOST_CONFIG) and
# copied here, once per container lifetime, into CLOUDSDK_CONFIG on the
# container's own writable overlay -- the same class of problem as the
# GCS-FUSE/SQLite MLflow backend-store issue.
set -euo pipefail

GCLOUD_HOST_CONFIG="${GCLOUD_HOST_CONFIG:-/opt/airflow/gcloud-host}"

if [ -n "${CLOUDSDK_CONFIG:-}" ] && [ -d "${GCLOUD_HOST_CONFIG}" ] && [ ! -d "${CLOUDSDK_CONFIG}" ]; then
    mkdir -p "${CLOUDSDK_CONFIG}"
    cp -r "${GCLOUD_HOST_CONFIG}/." "${CLOUDSDK_CONFIG}/"
fi

exec /entrypoint "$@"
