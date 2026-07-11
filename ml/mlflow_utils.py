import os
import mlflow

# Anchor mlruns.db to the src/ directory so CWD doesn't scatter database files.
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def init_mlflow(experiment_name: str) -> None:
    default_uri = f"sqlite:///{os.path.join(_SRC_DIR, 'mlruns.db')}"
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", default_uri)
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
