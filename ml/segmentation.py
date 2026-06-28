"""
K-means customer segmentation (k=5) on RFM features.

Source: gold.dim_customers.
Output: gold.customer_segments (ML-owned table — not managed by dbt).
Segment names are derived from centroid rankings, not hardcoded cluster indices.
"""
import logging
import os

import matplotlib.pyplot as plt
import mlflow
import numpy as np
import pandas as pd
from google.cloud.bigquery import LoadJobConfig, SchemaField, WriteDisposition
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from bq import get_client
from mlflow_utils import init_mlflow

RFM_Q = 5  # number of quantile bins for rfm_score

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

K_FINAL = 5
K_RANGE = range(3, 9)
RANDOM_STATE = 42


def load_data(client, project: str) -> pd.DataFrame:
    query = f"""
        SELECT customer_unique_id, recency_days, frequency, monetary
        FROM `{project}.gold.dim_customers`
    """
    return client.query(query).to_dataframe()


def safe_qcut(series: pd.Series, q: int, labels: list) -> pd.Series:
    """qcut with rank-based tie-breaking to handle non-unique quantile edges."""
    try:
        return pd.qcut(series, q=q, labels=labels)
    except ValueError:
        return pd.qcut(series.rank(method="first"), q=q, labels=labels)


def label_segments(centers_df: pd.DataFrame) -> dict:
    """
    Assign segment names by ranking cluster centroids on R, F, M.
    Lower recency rank = more recent (better). Higher F/M rank = better.
    Combines ranks into a composite RFM score and names in order.
    """
    df = centers_df.copy()
    df["r_rank"] = df["recency_days"].rank(ascending=True)   # lower recency = better
    df["f_rank"] = df["frequency"].rank(ascending=False)
    df["m_rank"] = df["monetary"].rank(ascending=False)
    df["rfm_score"] = df["r_rank"] + df["f_rank"] + df["m_rank"]

    sorted_ids = df["rfm_score"].sort_values().index.tolist()
    names = [
        "Champions",
        "Loyal Customers",
        "Potential Loyalists",
        "New Customers",
        "At Risk",
    ]
    while len(names) < len(sorted_ids):
        names.append(f"Segment {len(names) + 1}")

    return {cluster_id: names[rank] for rank, cluster_id in enumerate(sorted_ids)}


def main() -> None:
    init_mlflow("customer_segmentation")
    client = get_client()
    project = os.environ["GCP_PROJECT_ID"]

    log.info("Loading gold.dim_customers from BigQuery…")
    df = load_data(client, project)
    log.info(f"Loaded {len(df):,} rows")

    # Log-transform right-skewed features before scaling
    df["log_monetary"] = np.log1p(df["monetary"])
    df["log_frequency"] = np.log1p(df["frequency"])

    features = ["recency_days", "log_frequency", "log_monetary"]
    X = df[features].fillna(0).values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    silhouette_scores: dict[int, float] = {}

    with mlflow.start_run():
        # Evaluate k = 3 … 8 to validate choice of k=5
        for k in K_RANGE:
            km = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE)
            labels_k = km.fit_predict(X_scaled)
            score = silhouette_score(
                X_scaled, labels_k, sample_size=min(5000, len(X_scaled))
            )
            silhouette_scores[k] = score
            mlflow.log_metric(f"silhouette_k{k}", score)
            log.info(f"k={k}: silhouette={score:.4f}")

        fig, ax = plt.subplots()
        ax.plot(list(silhouette_scores.keys()), list(silhouette_scores.values()), marker="o")
        ax.set_xlabel("k")
        ax.set_ylabel("Silhouette Score")
        ax.set_title("K-Means Silhouette Scores (k=3..8)")
        fig.tight_layout()
        mlflow.log_figure(fig, "silhouette_curve.png")
        plt.close(fig)

        # Commit to k=5 (per conventions)
        km_final = KMeans(n_clusters=K_FINAL, n_init=10, random_state=RANDOM_STATE)
        df["cluster"] = km_final.fit_predict(X_scaled)

        final_silhouette = silhouette_score(
            X_scaled, df["cluster"], sample_size=min(5000, len(X_scaled))
        )
        mlflow.log_metric("final_silhouette", final_silhouette)
        mlflow.log_param("model_name", "kmeans")
        mlflow.log_param("k_final", K_FINAL)
        mlflow.log_param("features", ",".join(features))
        log.info(f"Final silhouette (k={K_FINAL}): {final_silhouette:.4f}")

        # Name segments via centroid inspection — never by hardcoded cluster index
        centers_raw = scaler.inverse_transform(km_final.cluster_centers_)
        centers_df = pd.DataFrame(
            centers_raw, columns=["recency_days", "frequency", "monetary"]
        )
        centers_df.index.name = "cluster"
        centers_df = centers_df.reset_index()
        segment_map = label_segments(centers_df)
        df["segment_name"] = df["cluster"].map(segment_map)

        # RFM quantile scores: lower recency = better (5), higher F/M = better (5)
        df["r_score"] = safe_qcut(df["recency_days"], q=RFM_Q, labels=[5, 4, 3, 2, 1]).astype(float)
        df["f_score"] = safe_qcut(df["frequency"], q=RFM_Q, labels=[1, 2, 3, 4, 5]).astype(float)
        df["m_score"] = safe_qcut(df["monetary"], q=RFM_Q, labels=[1, 2, 3, 4, 5]).astype(float)
        df["rfm_score"] = df["r_score"] + df["f_score"] + df["m_score"]

        cluster_sizes = df.groupby("segment_name").size().to_dict()
        log.info(f"Segment sizes: {cluster_sizes}")
        for seg, count in cluster_sizes.items():
            mlflow.log_metric(f"size_{seg.replace(' ', '_')}", count)

        centroid_table = centers_df.copy()
        centroid_table["segment_name"] = centroid_table["cluster"].map(segment_map)
        fig2, ax2 = plt.subplots(figsize=(10, 3))
        ax2.axis("off")
        tbl = ax2.table(
            cellText=centroid_table.round(2).values,
            colLabels=centroid_table.columns,
            loc="center",
        )
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(9)
        fig2.tight_layout()
        mlflow.log_figure(fig2, "centroid_table.png")
        plt.close(fig2)

        run_id = mlflow.active_run().info.run_id

    log.info(f"MLflow run: {run_id}")

    out = df[["customer_unique_id", "cluster", "segment_name",
              "recency_days", "frequency", "monetary", "rfm_score"]].copy()
    out = out.rename(columns={"cluster": "segment_id"})
    out["model_run_id"] = run_id
    out["scored_at"] = pd.Timestamp.utcnow()

    schema = [
        SchemaField("customer_unique_id", "STRING"),
        SchemaField("segment_id", "INT64"),
        SchemaField("segment_name", "STRING"),
        SchemaField("recency_days", "FLOAT64"),
        SchemaField("frequency", "INT64"),
        SchemaField("monetary", "FLOAT64"),
        SchemaField("rfm_score", "FLOAT64"),
        SchemaField("model_run_id", "STRING"),
        SchemaField("scored_at", "TIMESTAMP"),
    ]
    job_config = LoadJobConfig(
        schema=schema, write_disposition=WriteDisposition.WRITE_TRUNCATE
    )
    table_id = f"{project}.gold.customer_segments"
    job = client.load_table_from_dataframe(out, table_id, job_config=job_config)
    job.result()
    log.info(f"Wrote {len(out):,} rows → {table_id}")


if __name__ == "__main__":
    main()
