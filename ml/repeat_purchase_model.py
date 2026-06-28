"""
XGBoost repeat-purchase propensity model.

Source: gold.repeat_purchase_training (leakage-safe forward-window mart).
Output: gold.customer_repeat_purchase_scores (ML-owned table — not managed by dbt).
"""
import datetime
import logging
import os

import matplotlib.pyplot as plt
import mlflow
import mlflow.xgboost
import pandas as pd
from google.cloud.bigquery import LoadJobConfig, SchemaField, WriteDisposition
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    average_precision_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from bq import get_client
from mlflow_utils import init_mlflow

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

FEATURES = [
    "frequency",
    "monetary",
    "avg_order_value",
    "tenure_days",
    "recency_at_T",
    "max_installments_used",
    "used_credit_card",
    "used_boleto",
    "used_voucher",
    "avg_review_score",
    "reviewed_order_count",
    "has_review",
]

# Columns that would constitute target leakage for this label definition
BANNED_COLS = frozenset(
    {"last_order_date", "recency_days", "snapshot_date", "outcome_end_date", "horizon_days"}
)

XGB_PARAMS = {
    "n_estimators": 200,
    "max_depth": 5,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 42,
    "eval_metric": "logloss",
}


def load_training_data(client, project: str) -> pd.DataFrame:
    query = f"""
        SELECT
            customer_unique_id,
            frequency, monetary, avg_order_value,
            tenure_days, recency_at_T,
            max_installments_used, used_credit_card, used_boleto, used_voucher,
            avg_review_score, reviewed_order_count,
            will_repeat,
            CAST(snapshot_date AS STRING) AS snapshot_date,
            DATE_DIFF(outcome_end_date, snapshot_date, DAY) AS horizon_days
        FROM `{project}.gold.repeat_purchase_training`
    """
    return client.query(query).to_dataframe()


def preprocess(
    df: pd.DataFrame, review_median: float | None = None
) -> tuple[pd.DataFrame, pd.Series]:
    X = df[[c for c in FEATURES if c != "has_review"]].copy()

    # Median must be supplied from the training split to avoid leaking test statistics
    if review_median is None:
        review_median = float(X["avg_review_score"].median())
    X["has_review"] = (~X["avg_review_score"].isna()).astype(int)
    X["avg_review_score"] = X["avg_review_score"].fillna(review_median)
    X = X.fillna(0)

    # Enforce feature order so predict order matches fit order
    X = X[FEATURES]

    y = df["will_repeat"].astype(int)
    return X, y


def main() -> None:
    init_mlflow("repeat_purchase_propensity")
    client = get_client()
    project = os.environ["GCP_PROJECT_ID"]

    log.info("Loading gold.repeat_purchase_training from BigQuery…")
    df = load_training_data(client, project)
    log.info(f"Loaded {len(df):,} rows")

    snapshot_date = str(df["snapshot_date"].iloc[0]) if "snapshot_date" in df.columns else "unknown"
    horizon_days = int(df["horizon_days"].iloc[0])

    # Split df rows before preprocessing so review_median is computed on train only
    df_train, df_test = train_test_split(
        df, test_size=0.2, stratify=df["will_repeat"], random_state=42
    )
    train_review_median = float(df_train["avg_review_score"].median())

    X_train, y_train = preprocess(df_train, review_median=train_review_median)
    X_test, y_test = preprocess(df_test, review_median=train_review_median)

    # Validate labels and guard against leakage columns
    X = X_train  # alias for downstream checks

    base_rate = float(pd.concat([y_train, y_test]).mean())
    log.info(f"Repeat-purchase base rate: {base_rate:.3f}")

    assert 0 < base_rate < 1, (
        f"Label has no variance (base_rate={base_rate}). "
        "Verify repeat_purchase_training forward-window logic."
    )

    leaked = set(X_train.columns) & BANNED_COLS
    assert not leaked, f"Leakage columns in features: {leaked}"

    n_pos = int(y_train.sum())
    n_neg = len(y_train) - n_pos
    # scale_pos_weight up-weights the minority positive class (returners, will_repeat=1)
    scale_pos_weight = n_neg / n_pos if n_pos > 0 else 1.0

    params = {**XGB_PARAMS, "scale_pos_weight": scale_pos_weight}

    with mlflow.start_run():
        mlflow.log_params(params)
        mlflow.log_param("snapshot_date", snapshot_date)
        mlflow.log_param("horizon_days", horizon_days)
        mlflow.log_param("train_rows", len(X_train))
        mlflow.log_param("test_rows", len(X_test))
        mlflow.log_param("train_review_median", round(train_review_median, 4))
        mlflow.log_param("base_rate", round(base_rate, 4))
        mlflow.log_param("feature_list", ",".join(X.columns.tolist()))

        model = XGBClassifier(**params)
        model.fit(X_train, y_train)

        y_prob = model.predict_proba(X_test)[:, 1]
        y_pred = (y_prob >= 0.5).astype(int)

        roc_auc = roc_auc_score(y_test, y_prob)
        pr_auc = average_precision_score(y_test, y_prob)
        report = classification_report(y_test, y_pred, output_dict=True)

        log.info(f"ROC-AUC: {roc_auc:.4f}  PR-AUC: {pr_auc:.4f}")

        mlflow.log_metric("test_roc_auc", roc_auc)
        mlflow.log_metric("test_pr_auc", pr_auc)
        mlflow.log_metric("test_precision", report["1"]["precision"])
        mlflow.log_metric("test_recall", report["1"]["recall"])
        mlflow.log_metric("test_f1", report["1"]["f1-score"])

        importances = pd.Series(
            model.feature_importances_, index=X.columns
        ).sort_values(ascending=False)
        log.info(
            f"Top feature: {importances.index[0]} "
            f"(importance={importances.iloc[0]:.3f})"
        )

        fig, ax = plt.subplots(figsize=(10, 6))
        importances.plot.barh(ax=ax)
        ax.set_title("XGBoost Feature Importance — Repeat-Purchase Model")
        ax.set_xlabel("Importance score")
        ax.invert_yaxis()
        fig.tight_layout()
        mlflow.log_figure(fig, "feature_importance.png")
        plt.close(fig)

        cm = confusion_matrix(y_test, y_pred)
        fig2, ax2 = plt.subplots()
        ConfusionMatrixDisplay(cm).plot(ax=ax2)
        ax2.set_title("Confusion Matrix")
        mlflow.log_figure(fig2, "confusion_matrix.png")
        plt.close(fig2)

        mlflow.xgboost.log_model(model, "xgb_repeat_purchase_model")
        run_id = mlflow.active_run().info.run_id

    log.info(f"MLflow run: {run_id}")

    if roc_auc < 0.70:
        # Olist is ~98% one-time buyers on a general marketplace — customers buy across
        # unrelated categories from different sellers, so purchase signals generalise
        # poorly. The 0.70 target is aspirational; 0.60 with 180d horizon is the
        # practical ceiling given the data's structural low repeat rate.
        log.warning(f"ROC-AUC {roc_auc:.4f} is below the 0.70 target.")

    # Score full eligible population so the dashboard has every customer
    # Coverage note: scores are written only for customers in repeat_purchase_training,
    # i.e. those with ≥1 delivered order on/before snapshot T (~2018-06-05).
    # Customers whose first order falls after T have no pre-T feature history and
    # cannot be scored. Phase 4 dashboard should handle their absence by showing
    # NULL or a "new customer" label rather than treating them as low-propensity.
    log.info("Scoring full population…")
    X_full, _ = preprocess(df, review_median=train_review_median)
    df["repeat_probability"] = model.predict_proba(X_full)[:, 1]
    df["repeat_prediction"] = (df["repeat_probability"] >= 0.5)
    df["model_run_id"] = run_id
    df["scored_at"] = datetime.datetime.utcnow()
    df["model_version"] = "xgb_v1"

    scores = df[
        [
            "customer_unique_id",
            "repeat_probability",
            "repeat_prediction",
            "model_run_id",
            "scored_at",
            "model_version",
        ]
    ].copy()

    schema = [
        SchemaField("customer_unique_id", "STRING"),
        SchemaField("repeat_probability", "FLOAT64"),
        SchemaField("repeat_prediction", "BOOL"),
        SchemaField("model_run_id", "STRING"),
        SchemaField("scored_at", "TIMESTAMP"),
        SchemaField("model_version", "STRING"),
    ]
    job_config = LoadJobConfig(
        schema=schema,
        write_disposition=WriteDisposition.WRITE_TRUNCATE,
    )
    table_id = f"{project}.gold.customer_repeat_purchase_scores"
    job = client.load_table_from_dataframe(scores, table_id, job_config=job_config)
    job.result()
    log.info(f"Wrote {len(scores):,} rows → {table_id}")


if __name__ == "__main__":
    main()
