FROM apache/airflow:2.8.0

RUN pip install --no-cache-dir \
    apache-airflow-providers-google==10.13.1 \
    apache-airflow-providers-cncf-kubernetes==7.13.0 \
    google-cloud-bigquery==3.17.2 \
    google-cloud-storage==2.16.0 \
    google-cloud-aiplatform>=1.38.0 \
    pyyaml \
    dbt-core==1.7.17 \
    dbt-bigquery==1.7.8

# DAGs, the dbt project, and the Vertex job template are baked in (no gitSync);
# paths match what run_dbt.py and vertex_job.py already expect.
COPY --chown=airflow:root airflow/dags/ /opt/airflow/dags/
COPY --chown=airflow:root dbt/ /opt/airflow/dbt/
COPY --chown=airflow:root infra/vertex/ /opt/airflow/infra/vertex/

# dbt deps needs no warehouse connection; bake packages so task pods start clean.
RUN cd /opt/airflow/dbt/datapulse && dbt deps --profiles-dir /opt/airflow/dbt
