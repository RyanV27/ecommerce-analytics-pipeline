"""
Overview page — revenue KPIs, order trends, geographic distribution.
"""
import json
import pathlib

import plotly.express as px
import streamlit as st

import _pathfix  # noqa: F401  (adds src/ to sys.path for the dashboard.* import below)

from dashboard.bq import load_kpis, load_orders_by_state, load_revenue_over_time

st.set_page_config(page_title="Overview — DataPulse", layout="wide")
st.title("Overview")

# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------
with st.spinner("Loading KPIs…"):
    kpis = load_kpis()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Revenue (BRL)", f"R$ {kpis['total_revenue']:,.0f}")
col2.metric("Total Orders (delivered)", f"{kpis['order_count']:,}")
col3.metric("Average Order Value", f"R$ {kpis['aov']:,.2f}")
col4.metric("Inactive Customers (>90d)", f"{kpis['inactive_pct']:.1f}%")

st.divider()

# ---------------------------------------------------------------------------
# Revenue over time
# ---------------------------------------------------------------------------
with st.spinner("Loading order history…"):
    df_time = load_revenue_over_time()

df_time["order_month"] = df_time["order_month"].astype(str)

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Monthly Revenue (BRL)")
    fig_rev = px.line(
        df_time,
        x="order_month",
        y="revenue",
        markers=True,
        labels={"order_month": "Month", "revenue": "Revenue (BRL)"},
    )
    fig_rev.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig_rev, use_container_width=True)

with col_right:
    st.subheader("Monthly Order Count")
    fig_orders = px.bar(
        df_time,
        x="order_month",
        y="order_count",
        labels={"order_month": "Month", "order_count": "Orders"},
    )
    fig_orders.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig_orders, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Orders by state — choropleth with bar chart fallback
# ---------------------------------------------------------------------------
st.subheader("Orders by State")

with st.spinner("Loading state data…"):
    df_state = load_orders_by_state()

_GEOJSON_PATH = pathlib.Path(__file__).parent.parent / "assets" / "brazil_states.geojson"

metric_choice = st.radio(
    "Metric", ["order_count", "revenue"], horizontal=True,
    format_func=lambda v: "Order Count" if v == "order_count" else "Revenue (BRL)",
)

if _GEOJSON_PATH.exists():
    with open(_GEOJSON_PATH) as f:
        geojson = json.load(f)

    fig_map = px.choropleth(
        df_state,
        geojson=geojson,
        locations="customer_state",
        featureidkey="properties.sigla",   # IBGE GeoJSON uses 'sigla' for the 2-letter UF
        color=metric_choice,
        color_continuous_scale="Blues",
        scope="south america",
        labels={"order_count": "Orders", "revenue": "Revenue (BRL)", "customer_state": "State"},
        title="Brazil — Orders by State",
    )
    fig_map.update_geos(fitbounds="locations", visible=False)
    fig_map.update_layout(margin={"r": 0, "t": 40, "l": 0, "b": 0})
    st.plotly_chart(fig_map, use_container_width=True)
else:
    st.info(
        "Choropleth map requires `dashboard/assets/brazil_states.geojson`. "
        "Showing bar chart instead. See `dashboard/assets/README.md` for download instructions."
    )
    fig_bar = px.bar(
        df_state.head(15),
        x="customer_state",
        y=metric_choice,
        labels={"customer_state": "State", "order_count": "Orders", "revenue": "Revenue (BRL)"},
        title="Top 15 States by " + ("Order Count" if metric_choice == "order_count" else "Revenue"),
        color=metric_choice,
        color_continuous_scale="Blues",
    )
    st.plotly_chart(fig_bar, use_container_width=True)

st.dataframe(df_state, use_container_width=True, hide_index=True)
