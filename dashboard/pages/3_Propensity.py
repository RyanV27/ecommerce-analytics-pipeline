"""
Propensity page — repeat-purchase model scores, confusion matrix, feature importance.

The three ML tables (customer_repeat_purchase_scores, repeat_purchase_feature_importance,
repeat_purchase_training) must exist before this page renders fully. Each section
degrades gracefully with st.warning() when a table is absent.

Coverage note: scores exist only for customers in gold.repeat_purchase_training
(those with ≥1 delivered order on/before snapshot T). Customers with a first order
after T appear in dim_customers but not in the scores table — they are new customers
excluded by the forward-window design.
"""
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import _pathfix  # noqa: F401  (adds src/ to sys.path for the dashboard.* import below)

from dashboard.bq import (
    load_confusion_matrix_data,
    load_feature_importance,
    load_high_propensity,
    load_repeat_scores,
    table_exists,
)

st.set_page_config(page_title="Propensity — DataPulse", layout="wide")
st.title("Repeat-Purchase Propensity Model")

_SCORES_TABLE = ("gold", "customer_repeat_purchase_scores")
_FI_TABLE = ("gold", "repeat_purchase_feature_importance")

scores_ready = table_exists(*_SCORES_TABLE)
fi_ready = table_exists(*_FI_TABLE)

if not scores_ready:
    st.warning(
        "`gold.customer_repeat_purchase_scores` not found. "
        "Run `python ml/repeat_purchase_model.py` from `src/` to populate this table."
    )

# ---------------------------------------------------------------------------
# Score distribution
# ---------------------------------------------------------------------------
st.subheader("Score Distribution")

if scores_ready:
    with st.spinner("Loading scores…"):
        df_scores = load_repeat_scores()

    threshold = st.slider(
        "Decision threshold", min_value=0.1, max_value=0.9, value=0.5, step=0.05,
        help="Customers above this probability are predicted as repeat buyers.",
    )

    fig_hist = px.histogram(
        df_scores,
        x="repeat_probability",
        nbins=50,
        labels={"repeat_probability": "Repeat-Purchase Probability", "count": "Customers"},
        title="Distribution of Repeat-Purchase Scores",
        color_discrete_sequence=["#2e8b57"],
    )
    fig_hist.add_vline(
        x=threshold, line_dash="dash", line_color="red",
        annotation_text=f"Threshold = {threshold}", annotation_position="top right",
    )
    st.plotly_chart(fig_hist, use_container_width=True)

    n_positive = int((df_scores["repeat_probability"] >= threshold).sum())
    pct_positive = n_positive / len(df_scores) * 100
    col1, col2, col3 = st.columns(3)
    col1.metric("Scored Customers", f"{len(df_scores):,}")
    col2.metric(f"Predicted Repeat (≥{threshold})", f"{n_positive:,}")
    col3.metric("Predicted Rate", f"{pct_positive:.1f}%")
else:
    st.info("Score distribution unavailable — scores table missing.")

st.divider()

# ---------------------------------------------------------------------------
# High-propensity customer table
# ---------------------------------------------------------------------------
st.subheader("High-Propensity Customers")

if scores_ready:
    with st.spinner("Loading top customers…"):
        df_high = load_high_propensity(limit=100)

    st.dataframe(
        df_high.rename(columns={c: c.replace("_", " ").title() for c in df_high.columns}),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("High-propensity table unavailable.")

st.divider()

# ---------------------------------------------------------------------------
# Confusion matrix (live SQL join of scores ↔ training labels)
# ---------------------------------------------------------------------------
st.subheader("Confusion Matrix")
st.caption(
    "Computed by joining `customer_repeat_purchase_scores.repeat_prediction` "
    "to `repeat_purchase_training.will_repeat` at threshold = 0.5."
)

if scores_ready:
    with st.spinner("Computing confusion matrix…"):
        df_cm = load_confusion_matrix_data()

    if len(df_cm) > 0:
        pivot_cm = df_cm.pivot(
            index="will_repeat", columns="repeat_prediction", values="count"
        ).fillna(0).astype(int)

        row_labels = {False: "Actual: No Repeat", True: "Actual: Repeat"}
        col_labels = {False: "Predicted: No Repeat", True: "Predicted: Repeat"}

        pivot_cm.index = [row_labels.get(v, str(v)) for v in pivot_cm.index]
        pivot_cm.columns = [col_labels.get(v, str(v)) for v in pivot_cm.columns]

        # Ensure consistent ordering: Actual No / Actual Yes rows
        ordered_rows = ["Actual: No Repeat", "Actual: Repeat"]
        ordered_cols = ["Predicted: No Repeat", "Predicted: Repeat"]
        pivot_cm = pivot_cm.reindex(index=ordered_rows, columns=ordered_cols, fill_value=0)

        fig_cm = px.imshow(
            pivot_cm,
            color_continuous_scale="Blues",
            text_auto=True,
            labels={"color": "Count"},
            title="Confusion Matrix (test-set approximation via full-population join)",
            aspect="auto",
        )
        fig_cm.update_layout(width=500, height=400)
        st.plotly_chart(fig_cm)

        total = pivot_cm.values.sum()
        if total > 0:
            tn = pivot_cm.loc["Actual: No Repeat", "Predicted: No Repeat"]
            tp = pivot_cm.loc["Actual: Repeat", "Predicted: Repeat"]
            fp = pivot_cm.loc["Actual: No Repeat", "Predicted: Repeat"]
            fn = pivot_cm.loc["Actual: Repeat", "Predicted: No Repeat"]
            accuracy = (tn + tp) / total
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            cm_col1, cm_col2, cm_col3, cm_col4 = st.columns(4)
            cm_col1.metric("Accuracy", f"{accuracy:.3f}")
            cm_col2.metric("Precision", f"{precision:.3f}")
            cm_col3.metric("Recall", f"{recall:.3f}")
            cm_col4.metric("F1 Score", f"{f1:.3f}")
    else:
        st.warning("No overlap found between scores and training labels.")
else:
    st.info("Confusion matrix unavailable — scores table missing.")

st.divider()

# ---------------------------------------------------------------------------
# Feature importance
# ---------------------------------------------------------------------------
st.subheader("Feature Importance")

if fi_ready:
    with st.spinner("Loading feature importance…"):
        df_fi = load_feature_importance()

    fig_fi = px.bar(
        df_fi,
        x="importance",
        y="feature",
        orientation="h",
        labels={"importance": "Importance Score", "feature": "Feature"},
        title="XGBoost Feature Importance — Repeat-Purchase Model",
        color="importance",
        color_continuous_scale="Greens",
    )
    fig_fi.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=False)
    st.plotly_chart(fig_fi, use_container_width=True)
else:
    st.warning(
        "`gold.repeat_purchase_feature_importance` not found. "
        "This table is created by `repeat_purchase_model.py`. "
        "Re-run the script after the Phase 4 update to generate it."
    )

st.divider()
st.caption(
    "Model: XGBoost (n_estimators=200, max_depth=5, lr=0.05). "
    "Target AUC > 0.70 — structural ceiling ~0.60 due to Olist's ~98% one-time buyer rate. "
    "See MLflow for full run metrics."
)
