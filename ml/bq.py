import os
from dotenv import load_dotenv
from google.cloud import bigquery


def get_client() -> bigquery.Client:
    # load_dotenv is a no-op if env vars are already set (e.g. in Docker);
    # for local dev it picks up src/.env or any .env found by walking up.
    load_dotenv()
    project = os.environ["GCP_PROJECT_ID"]
    return bigquery.Client(project=project)
