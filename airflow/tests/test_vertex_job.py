import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "dags"))

from vertex_job import render_vertex_template  # noqa: E402

REPEAT_JOB_TEMPLATE = Path(__file__).parents[2] / "infra" / "vertex" / "vertex_repeat_job.yaml"


def test_render_vertex_template_substitutes_all_placeholders():
    template_text = (
        "serviceAccount: __ML_TRAINING_SA__\n"
        "workerPoolSpecs:\n"
        "  - containerSpec:\n"
        "      imageUri: gcr.io/__PROJECT_ID__/datapulse-ml\n"
        "      env:\n"
        "        - name: MLFLOW_TRACKING_URI\n"
        "          value: __MLFLOW_TRACKING_URI__\n"
    )

    spec = render_vertex_template(
        template_text,
        project_id="my-project",
        mlflow_uri="https://mlflow.example.com",
        training_sa="ml-training@my-project.iam.gserviceaccount.com",
    )

    assert spec["serviceAccount"] == "ml-training@my-project.iam.gserviceaccount.com"
    assert spec["workerPoolSpecs"][0]["containerSpec"]["imageUri"] == "gcr.io/my-project/datapulse-ml"


def test_render_vertex_template_raises_on_unsubstituted_placeholder():
    template_text = "serviceAccount: __ML_TRAINING_SA__\n"

    with pytest.raises(ValueError):
        render_vertex_template(
            template_text,
            project_id="my-project",
            mlflow_uri="https://mlflow.example.com",
            training_sa="__ML_TRAINING_SA__",  # deliberately unresolved
        )


def test_render_committed_repeat_job_template():
    """Renders the real committed vertex_repeat_job.yaml so template drift breaks CI."""
    template_text = REPEAT_JOB_TEMPLATE.read_text()

    spec = render_vertex_template(
        template_text,
        project_id="my-project",
        mlflow_uri="https://mlflow.example.com",
        training_sa="ml-training@my-project.iam.gserviceaccount.com",
    )

    assert spec["serviceAccount"] == "ml-training@my-project.iam.gserviceaccount.com"
    assert spec["workerPoolSpecs"][0]["containerSpec"]["imageUri"] == "gcr.io/my-project/datapulse-ml"
    assert spec["workerPoolSpecs"][0]["containerSpec"]["args"] == ["ml/repeat_purchase_model.py"]
