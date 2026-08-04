"""Airflow-free helper for rendering the committed Vertex AI CustomJobSpec
template. Kept separate from retrain_models.py so it can be unit-tested
without an Airflow install (see airflow/tests/test_vertex_job.py).
"""
import yaml

PLACEHOLDERS = {
    "__PROJECT_ID__": "project_id",
    "__MLFLOW_TRACKING_URI__": "mlflow_uri",
    "__ML_TRAINING_SA__": "training_sa",
}


def render_vertex_template(template_text: str, project_id: str, mlflow_uri: str, training_sa: str) -> dict:
    """Substitutes the __TOKEN__ placeholders in a Vertex CustomJobSpec YAML
    template and parses the result into a dict."""
    values = {
        "__PROJECT_ID__": project_id,
        "__MLFLOW_TRACKING_URI__": mlflow_uri,
        "__ML_TRAINING_SA__": training_sa,
    }
    rendered_text = template_text
    for placeholder, value in values.items():
        rendered_text = rendered_text.replace(placeholder, value)

    for placeholder in PLACEHOLDERS:
        if placeholder in rendered_text:
            raise ValueError(f"Unsubstituted placeholder {placeholder!r} remains in the rendered template")

    return yaml.safe_load(rendered_text)
