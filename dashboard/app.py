"""
DataPulse — Streamlit dashboard entry point.

Streamlit auto-discovers pages/ directory; numeric prefixes control sidebar order.
Run locally:
    cd src
    $env:PYTHONPATH = "."
    streamlit run dashboard/app.py
"""
import streamlit as st

st.set_page_config(
    page_title="DataPulse",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("DataPulse")
st.subheader("E-Commerce Analytics — Olist Brazilian Dataset")

st.markdown(
    """
    An end-to-end analytics platform built on the
    [Olist Brazilian E-Commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
    (100K orders, 9 source tables).

    **Use the sidebar to navigate between pages.**

    | Page | Contents |
    |------|----------|
    | Overview | Revenue KPIs, order trends, geographic distribution |
    | Customers | Cohort retention, RFM segments, lifetime value |
    | Propensity | Repeat-purchase model scores and feature importance |
    | A/B Test Runner | Interactive statistical significance calculator |
    """
)

st.divider()

col1, col2, col3 = st.columns(3)
with col1:
    st.info("**Data layer:** Google BigQuery (Gold)")
with col2:
    st.info("**ML:** XGBoost propensity · K-Means RFM · Prophet forecasting")
with col3:
    st.info("**Stats:** Two-proportion z-test · Welch t-test · Mann-Whitney U")

st.caption("Data refreshes hourly. Queries cached for 60 minutes.")
