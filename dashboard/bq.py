"""
Shared BigQuery client and cached query helpers for the DataPulse dashboard.

All query functions are decorated with @st.cache_data(ttl=3600) so BigQuery is
not re-queried on every Streamlit rerender. The client itself is cached as a
resource (one connection per process).

On Cloud Run the attached runtime service account is used automatically (ADC).
Locally, set GOOGLE_APPLICATION_CREDENTIALS or run `gcloud auth application-default login`.
"""
import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google.cloud import bigquery
from google.cloud.exceptions import NotFound

load_dotenv()


def _p() -> str:
    return os.environ["GCP_PROJECT_ID"]


@st.cache_resource
def get_client() -> bigquery.Client:
    return bigquery.Client(project=_p())


@st.cache_data(ttl=3600)
def table_exists(dataset: str, table: str) -> bool:
    try:
        get_client().get_table(f"{_p()}.{dataset}.{table}")
        return True
    except NotFound:
        return False


# ---------------------------------------------------------------------------
# Overview queries
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def load_kpis() -> dict:
    client = get_client()
    project = _p()

    orders_sql = f"""
        SELECT
            ROUND(SUM(total_payment_value), 2)  AS total_revenue,
            COUNT(DISTINCT order_id)             AS order_count,
            ROUND(AVG(total_payment_value), 2)   AS aov
        FROM `{project}.gold.fct_orders`
        WHERE order_status = 'delivered'
    """
    row = client.query(orders_sql).to_dataframe().iloc[0]

    inactive_sql = f"""
        SELECT ROUND(AVG(CAST(is_inactive AS INT64)) * 100, 1) AS inactive_pct
        FROM `{project}.gold.dim_customers`
    """
    inactive_pct = client.query(inactive_sql).to_dataframe().iloc[0]["inactive_pct"]

    return {
        "total_revenue": float(row["total_revenue"]),
        "order_count": int(row["order_count"]),
        "aov": float(row["aov"]),
        "inactive_pct": float(inactive_pct),
    }


@st.cache_data(ttl=3600)
def load_revenue_over_time() -> pd.DataFrame:
    project = _p()
    sql = f"""
        SELECT
            order_month,
            ROUND(SUM(total_payment_value), 2) AS revenue,
            COUNT(DISTINCT order_id)           AS order_count
        FROM `{project}.gold.fct_orders`
        WHERE order_status = 'delivered'
          AND order_month IS NOT NULL
        GROUP BY order_month
        ORDER BY order_month
    """
    return get_client().query(sql).to_dataframe()


@st.cache_data(ttl=3600)
def load_orders_by_state() -> pd.DataFrame:
    project = _p()
    sql = f"""
        SELECT
            customer_state,
            COUNT(DISTINCT order_id)           AS order_count,
            ROUND(SUM(total_payment_value), 2) AS revenue
        FROM `{project}.gold.fct_orders`
        WHERE order_status = 'delivered'
          AND customer_state IS NOT NULL
        GROUP BY customer_state
        ORDER BY order_count DESC
    """
    return get_client().query(sql).to_dataframe()


# ---------------------------------------------------------------------------
# Customer queries
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def load_cohorts() -> pd.DataFrame:
    project = _p()
    sql = f"""
        WITH cohort_size AS (
            SELECT cohort_month, active_customers AS cohort_size
            FROM `{project}.gold.customer_cohorts`
            WHERE months_since_first = 0
        )
        SELECT
            c.cohort_month,
            c.months_since_first,
            c.active_customers,
            SAFE_DIVIDE(c.active_customers, cs.cohort_size) AS retention_rate
        FROM `{project}.gold.customer_cohorts` c
        JOIN cohort_size cs ON c.cohort_month = cs.cohort_month
        ORDER BY c.cohort_month, c.months_since_first
    """
    return get_client().query(sql).to_dataframe()


@st.cache_data(ttl=3600)
def load_segments() -> pd.DataFrame:
    project = _p()
    sql = f"""
        SELECT
            segment_name,
            COUNT(*)               AS customer_count,
            ROUND(AVG(monetary), 2)      AS avg_monetary,
            ROUND(AVG(recency_days), 0)  AS avg_recency_days,
            ROUND(AVG(rfm_score), 2)     AS avg_rfm_score
        FROM `{project}.gold.customer_segments`
        GROUP BY segment_name
        ORDER BY avg_monetary DESC
    """
    return get_client().query(sql).to_dataframe()


@st.cache_data(ttl=3600)
def load_ltv_data() -> pd.DataFrame:
    project = _p()
    sql = f"""
        SELECT monetary
        FROM `{project}.gold.dim_customers`
        WHERE monetary IS NOT NULL AND monetary > 0
    """
    return get_client().query(sql).to_dataframe()


@st.cache_data(ttl=3600)
def load_top_customers(n: int = 20, ascending: bool = False) -> pd.DataFrame:
    project = _p()
    order = "ASC" if ascending else "DESC"
    sql = f"""
        SELECT
            customer_unique_id,
            customer_state,
            ROUND(monetary, 2)         AS total_spent,
            frequency                  AS order_count,
            ROUND(avg_order_value, 2)  AS avg_order_value,
            recency_days
        FROM `{project}.gold.dim_customers`
        ORDER BY monetary {order}
        LIMIT {n}
    """
    return get_client().query(sql).to_dataframe()


# ---------------------------------------------------------------------------
# Propensity queries
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def load_repeat_scores() -> pd.DataFrame:
    project = _p()
    sql = f"""
        SELECT repeat_probability, repeat_prediction
        FROM `{project}.gold.customer_repeat_purchase_scores`
    """
    return get_client().query(sql).to_dataframe()


@st.cache_data(ttl=3600)
def load_high_propensity(limit: int = 100) -> pd.DataFrame:
    project = _p()
    sql = f"""
        SELECT
            s.customer_unique_id,
            ROUND(s.repeat_probability, 4) AS repeat_probability,
            s.repeat_prediction,
            dc.customer_state,
            dc.frequency,
            ROUND(dc.monetary, 2)          AS total_spent,
            dc.recency_days
        FROM `{project}.gold.customer_repeat_purchase_scores` s
        LEFT JOIN `{project}.gold.dim_customers` dc
            ON s.customer_unique_id = dc.customer_unique_id
        ORDER BY s.repeat_probability DESC
        LIMIT {limit}
    """
    return get_client().query(sql).to_dataframe()


@st.cache_data(ttl=3600)
def load_confusion_matrix_data() -> pd.DataFrame:
    project = _p()
    sql = f"""
        SELECT
            t.will_repeat,
            s.repeat_prediction,
            COUNT(*) AS count
        FROM `{project}.gold.customer_repeat_purchase_scores` s
        JOIN `{project}.gold.repeat_purchase_training` t
            ON s.customer_unique_id = t.customer_unique_id
        GROUP BY t.will_repeat, s.repeat_prediction
        ORDER BY t.will_repeat, s.repeat_prediction
    """
    return get_client().query(sql).to_dataframe()


@st.cache_data(ttl=3600)
def load_feature_importance() -> pd.DataFrame:
    project = _p()
    sql = f"""
        SELECT feature, ROUND(importance, 6) AS importance
        FROM `{project}.gold.repeat_purchase_feature_importance`
        ORDER BY importance DESC
    """
    return get_client().query(sql).to_dataframe()


# ---------------------------------------------------------------------------
# Forecasting queries
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def load_forecasts() -> pd.DataFrame:
    """Future-week demand forecasts written by ml/forecasting.py."""
    project = _p()
    sql = f"""
        SELECT
            category,
            week,
            yhat,
            yhat_lower,
            yhat_upper,
            model
        FROM `{project}.gold.demand_forecasts`
        ORDER BY category, week
    """
    return get_client().query(sql).to_dataframe()


@st.cache_data(ttl=3600)
def load_forecast_actuals() -> pd.DataFrame:
    """
    Weekly historical order counts per category, so the Forecasting page can
    overlay actuals behind the forecast. Mirrors the aggregation in
    ml/forecasting.py:load_data (delivered orders, English category name).
    """
    project = _p()
    sql = f"""
        SELECT
            date_trunc(date(o.order_purchase_timestamp), week) AS week,
            p.product_category_name_english                    AS category,
            COUNT(DISTINCT oi.order_id)                        AS order_count
        FROM `{project}.gold.fct_order_items`  oi
        JOIN `{project}.gold.fct_orders`        o  ON oi.order_id   = o.order_id
        JOIN `{project}.gold.dim_products`      p  ON oi.product_id = p.product_id
        WHERE o.order_status = 'delivered'
          AND p.product_category_name_english IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 1, 2
    """
    return get_client().query(sql).to_dataframe()
