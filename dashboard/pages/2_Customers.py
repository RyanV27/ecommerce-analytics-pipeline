"""
Customers page — cohort retention, RFM segments, LTV histogram, top/bottom customers.
"""
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import _pathfix  # noqa: F401  (adds src/ to sys.path for the dashboard.* import below)

from dashboard.bq import (
    load_cohorts,
    load_ltv_data,
    load_segments,
    load_top_customers,
    table_exists,
)

st.set_page_config(page_title="Customers — DataPulse", layout="wide")
st.title("Customer Analytics")

# ---------------------------------------------------------------------------
# Cohort retention heatmap
# ---------------------------------------------------------------------------
st.subheader("Cohort Retention")

with st.spinner("Loading cohort data…"):
    df_cohorts = load_cohorts()

df_cohorts["cohort_month"] = df_cohorts["cohort_month"].astype(str).str[:7]

pivot = (
    df_cohorts
    .pivot(index="cohort_month", columns="months_since_first", values="retention_rate")
    .sort_index()
)

fig_cohort = px.imshow(
    pivot,
    color_continuous_scale="Blues",
    zmin=0,
    zmax=1,
    labels={"x": "Months Since First Order", "y": "Cohort Month", "color": "Retention Rate"},
    title="Monthly Cohort Retention Rate",
    text_auto=".0%",
    aspect="auto",
)
fig_cohort.update_coloraxes(colorbar_tickformat=".0%")
st.plotly_chart(fig_cohort, use_container_width=True)

st.caption(
    "Each cell shows the share of customers from the cohort still active in that month. "
    "Month 0 = 100% (cohort definition month)."
)

st.divider()

# ---------------------------------------------------------------------------
# RFM segment treemap
# ---------------------------------------------------------------------------
st.subheader("RFM Customer Segments")

_SEGMENT_COLORS = {
    "Champions": "#1a6b3c",
    "Loyal Customers": "#2e8b57",
    "Potential Loyalists": "#52c07a",
    "New Customers": "#90cead",
    "At Risk": "#c0392b",
}

if table_exists("gold", "customer_segments"):
    with st.spinner("Loading segment data…"):
        df_seg = load_segments()

    col_tree, col_seg_table = st.columns([2, 1])

    with col_tree:
        df_seg["color"] = df_seg["segment_name"].map(_SEGMENT_COLORS).fillna("#888888")
        fig_tree = px.treemap(
            df_seg,
            path=["segment_name"],
            values="customer_count",
            color="avg_monetary",
            color_continuous_scale="Greens",
            labels={"avg_monetary": "Avg. Spend (BRL)", "customer_count": "Customers"},
            title="Customer Segments — Size by Count, Colour by Avg. Spend",
        )
        st.plotly_chart(fig_tree, use_container_width=True)

    with col_seg_table:
        st.markdown("**Segment summary**")
        display = df_seg.rename(columns={
            "segment_name": "Segment",
            "customer_count": "Customers",
            "avg_monetary": "Avg. Spend (BRL)",
            "avg_recency_days": "Avg. Recency (d)",
            "avg_rfm_score": "RFM Score",
        })
        st.dataframe(display, use_container_width=True, hide_index=True)
else:
    st.warning(
        "`gold.customer_segments` table not found. "
        "Run `python ml/segmentation.py` to generate segments."
    )

st.divider()

# ---------------------------------------------------------------------------
# LTV histogram
# ---------------------------------------------------------------------------
st.subheader("Customer Lifetime Value Distribution")

with st.spinner("Loading LTV data…"):
    df_ltv = load_ltv_data()

ltv_cap = st.slider(
    "Cap LTV at (BRL) — removes long tail for readability",
    min_value=500,
    max_value=10000,
    value=2000,
    step=100,
)

df_ltv_capped = df_ltv[df_ltv["monetary"] <= ltv_cap]

fig_ltv = px.histogram(
    df_ltv_capped,
    x="monetary",
    nbins=60,
    labels={"monetary": "Total Spend (BRL)", "count": "Customers"},
    title=f"LTV Distribution (capped at R$ {ltv_cap:,})",
    color_discrete_sequence=["#2e8b57"],
)
fig_ltv.update_layout(bargap=0.05)
st.plotly_chart(fig_ltv, use_container_width=True)

col_pct = st.columns(4)
for pct, col in zip([25, 50, 75, 90], col_pct):
    val = float(np.percentile(df_ltv["monetary"], pct))
    col.metric(f"p{pct} LTV", f"R$ {val:,.2f}")

st.divider()

# ---------------------------------------------------------------------------
# Top / bottom customers
# ---------------------------------------------------------------------------
st.subheader("Customer Leaderboard")

sort_dir = st.radio("Sort by spend", ["Highest", "Lowest"], horizontal=True)
ascending = sort_dir == "Lowest"

with st.spinner("Loading customers…"):
    df_top = load_top_customers(n=20, ascending=ascending)

df_top.columns = [c.replace("_", " ").title() for c in df_top.columns]
st.dataframe(df_top, use_container_width=True, hide_index=True)
