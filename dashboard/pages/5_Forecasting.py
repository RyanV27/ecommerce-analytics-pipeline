"""
Forecasting page — per-category weekly demand forecasts with confidence bands.

Reads gold.demand_forecasts (future weeks, written by ml/forecasting.py) and
overlays historical weekly order counts from gold.fct_order_items. Degrades
gracefully with st.warning() when the forecasts table is absent.

Note: the ExponentialSmoothing fallback model writes NULL yhat_lower/yhat_upper
(only Prophet produces prediction intervals), so the CI band is drawn only when
bounds are present for the selected category.
"""
import plotly.graph_objects as go
import streamlit as st

import _pathfix  # noqa: F401  (adds src/ to sys.path for the dashboard.* import below)

from dashboard.bq import (
    load_forecast_actuals,
    load_forecasts,
    table_exists,
)

st.set_page_config(page_title="Forecasting — DataPulse", layout="wide")
st.title("Demand Forecasting")

_FORECASTS_TABLE = ("gold", "demand_forecasts")

if not table_exists(*_FORECASTS_TABLE):
    st.warning(
        "`gold.demand_forecasts` not found. "
        "Run `python ml/forecasting.py` from `src/` to populate this table."
    )
    st.stop()

with st.spinner("Loading forecasts…"):
    df_fc = load_forecasts()

if df_fc.empty:
    st.info("The forecasts table exists but is empty. Re-run `python ml/forecasting.py`.")
    st.stop()

categories = sorted(df_fc["category"].unique().tolist())
category = st.selectbox("Product category", categories)

cat_fc = df_fc[df_fc["category"] == category].sort_values("week")
model_used = cat_fc["model"].iloc[0] if len(cat_fc) else "—"

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------
col1, col2, col3 = st.columns(3)
col1.metric("Forecast horizon", f"{len(cat_fc)} weeks")
col2.metric("Model", model_used)
col3.metric("Avg. weekly orders (forecast)", f"{cat_fc['yhat'].mean():.1f}")

st.divider()

# ---------------------------------------------------------------------------
# Forecast chart: history + forecast + CI band
# ---------------------------------------------------------------------------
st.subheader(f"Weekly Demand — {category}")

with st.spinner("Loading history…"):
    df_actuals = load_forecast_actuals()
cat_actuals = df_actuals[df_actuals["category"] == category].sort_values("week")

fig = go.Figure()

# Confidence band (Prophet only — ES fallback leaves these NULL)
has_ci = cat_fc["yhat_lower"].notna().any() and cat_fc["yhat_upper"].notna().any()
if has_ci:
    fig.add_trace(
        go.Scatter(
            x=cat_fc["week"],
            y=cat_fc["yhat_upper"],
            mode="lines",
            line=dict(width=0),
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=cat_fc["week"],
            y=cat_fc["yhat_lower"],
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor="rgba(46, 139, 87, 0.2)",
            name="95% interval",
            hoverinfo="skip",
        )
    )

# Historical actuals
if not cat_actuals.empty:
    fig.add_trace(
        go.Scatter(
            x=cat_actuals["week"],
            y=cat_actuals["order_count"],
            mode="lines",
            line=dict(color="steelblue"),
            name="Actual",
        )
    )

# Forecast line
fig.add_trace(
    go.Scatter(
        x=cat_fc["week"],
        y=cat_fc["yhat"],
        mode="lines+markers",
        line=dict(color="#2e8b57", dash="dash"),
        name="Forecast",
    )
)

fig.update_layout(
    xaxis_title="Week",
    yaxis_title="Distinct delivered orders",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
st.plotly_chart(fig, use_container_width=True)

if not has_ci:
    st.caption(
        f"No confidence interval shown — `{category}` was fit with the "
        "ExponentialSmoothing fallback, which does not produce prediction intervals."
    )

st.divider()

# ---------------------------------------------------------------------------
# Forecast table
# ---------------------------------------------------------------------------
st.subheader("Forecast Detail")
st.dataframe(
    cat_fc[["week", "yhat", "yhat_lower", "yhat_upper", "model"]].rename(
        columns={
            "week": "Week",
            "yhat": "Forecast",
            "yhat_lower": "Lower (95%)",
            "yhat_upper": "Upper (95%)",
            "model": "Model",
        }
    ),
    use_container_width=True,
    hide_index=True,
)

st.divider()
st.caption(
    "Forecasts: Prophet (weekly + yearly seasonality, 95% interval) with a "
    "statsmodels ExponentialSmoothing fallback. Top categories by order volume; "
    "series with < 10 weeks or > 50% zero-count weeks are skipped. See MLflow "
    "for per-category back-test metrics (MAE, sMAPE, MAPE)."
)
