FROM apache/airflow:2.8.0

USER root

# retrain_models DAG shells out to `gcloud run jobs execute` / `gcloud ai custom-jobs`
# directly via BashOperator, so the worker needs the CLI, not just the Python client libs.
RUN apt-get update && apt-get install -y --no-install-recommends curl gnupg ca-certificates \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" > /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && apt-get update && apt-get install -y --no-install-recommends google-cloud-cli \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY gcloud-entrypoint.sh /gcloud-entrypoint.sh
RUN chmod +x /gcloud-entrypoint.sh

USER airflow

RUN pip install --no-cache-dir \
    apache-airflow-providers-google==10.13.1 \
    google-cloud-bigquery==3.17.2 \
    google-cloud-storage==2.16.0 \
    dbt-core==1.7.17 \
    dbt-bigquery==1.7.8

# Seeds gcloud CLI config from the read-only host mount before handing off to
# the base image's own entrypoint (see gcloud-entrypoint.sh). airflow-init
# overrides this with `entrypoint: /bin/bash` in docker-compose.yml since it
# doesn't need gcloud.
ENTRYPOINT ["/gcloud-entrypoint.sh"]
