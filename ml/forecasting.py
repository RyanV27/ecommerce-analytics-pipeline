"""
Per-category demand forecasting using Prophet (with statsmodels fallback).

Source: gold.fct_order_items + gold.fct_orders + gold.dim_products.
The Olist series ends ~2018-08; the final TRIM_TAIL_WEEKS partial weeks are
dropped before fitting to avoid a spurious demand-collapse artefact.
"""
import logging
import os
import warnings

import matplotlib.pyplot as plt
import mlflow
import numpy as np
import pandas as pd

from bq import get_client
from mlflow_utils import init_mlflow

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

MIN_WEEKS = 10
FORECAST_PERIODS = 12
TOP_N_CATEGORIES = 10
# Drop last N weeks: Olist data is sparse/truncated at the series end
TRIM_TAIL_WEEKS = 2


def load_data(client, project: str) -> pd.DataFrame:
    query = f"""
        SELECT
            date_trunc(date(o.order_purchase_timestamp), week) AS week_start,
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
    return client.query(query).to_dataframe()


def get_top_categories(df: pd.DataFrame, n: int) -> list[str]:
    return (
        df.groupby("category")["order_count"]
        .sum()
        .nlargest(n)
        .index.tolist()
    )


def _smape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    denom = np.abs(y_true) + np.abs(y_pred) + 1e-9
    return float(np.mean(2 * np.abs(y_true - y_pred) / denom))


def _mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = y_true != 0
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])))


def fit_forecast(weekly_df: pd.DataFrame, category: str) -> dict | None:
    series = (
        weekly_df[weekly_df["category"] == category]
        .sort_values("week_start")
        .copy()
    )

    # Drop tail partial weeks before fitting
    if len(series) > TRIM_TAIL_WEEKS:
        series = series.iloc[:-TRIM_TAIL_WEEKS]

    if len(series) < MIN_WEEKS:
        log.warning(f"Skip '{category}': only {len(series)} weeks after trim")
        return None

    if (series["order_count"] == 0).mean() > 0.5:
        log.warning(f"Skip '{category}': >50% zero-count weeks")
        return None

    # Hold out last 12 weeks (or 25% of series) for back-test
    holdout = min(FORECAST_PERIODS, max(1, len(series) // 4))
    train = series.iloc[:-holdout]
    test = series.iloc[-holdout:]

    try:
        from prophet import Prophet

        def _fit_prophet(subset: pd.DataFrame) -> tuple:
            ph_df = subset.rename(
                columns={"week_start": "ds", "order_count": "y"}
            ).copy()
            ph_df["ds"] = pd.to_datetime(ph_df["ds"])
            m = Prophet(
                weekly_seasonality=True,
                yearly_seasonality=True,
                interval_width=0.95,
            )
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                m.fit(ph_df)
            return m, ph_df

        m_train, _ = _fit_prophet(train)
        fc_test = m_train.predict(
            pd.DataFrame({"ds": pd.to_datetime(test["week_start"])})
        )
        y_true = test["order_count"].values.astype(float)
        y_pred = np.maximum(fc_test["yhat"].values, 0)
        mae = float(np.mean(np.abs(y_true - y_pred)))
        smape = _smape(y_true, y_pred)
        mape = _mape(y_true, y_pred)

        # Refit on full series for the forward forecast
        m_full, full_df = _fit_prophet(series)
        future = m_full.make_future_dataframe(periods=FORECAST_PERIODS, freq="W")
        forecast = m_full.predict(future)
        model_name = "prophet"

    except ImportError:
        log.warning("Prophet not available — using statsmodels ExponentialSmoothing")
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        y_train = train["order_count"].values.astype(float)
        try:
            # Clamp to a period that fits within 2 cycles (ES requirement)
            safe_seasonal = min(52, max(4, len(y_train) // 2))
            es = ExponentialSmoothing(
                y_train, trend="add", seasonal="add", seasonal_periods=safe_seasonal
            )
            fit = es.fit()
        except Exception:
            es = ExponentialSmoothing(y_train, trend="add")
            fit = es.fit()

        fc_all = fit.forecast(holdout + FORECAST_PERIODS)
        y_true = test["order_count"].values.astype(float)
        y_pred = np.maximum(fc_all[:holdout], 0)
        mae = float(np.mean(np.abs(y_true - y_pred)))
        smape = _smape(y_true, y_pred)
        mape = _mape(y_true, y_pred)

        future_dates = pd.date_range(
            start=pd.to_datetime(series["week_start"].max()) + pd.Timedelta(weeks=1),
            periods=FORECAST_PERIODS,
            freq="W",
        )
        forecast = pd.DataFrame(
            {"ds": future_dates, "yhat": np.maximum(fc_all[-FORECAST_PERIODS:], 0)}
        )
        full_df = series.rename(columns={"week_start": "ds", "order_count": "y"}).copy()
        full_df["ds"] = pd.to_datetime(full_df["ds"])
        model_name = "exponential_smoothing"

    return {
        "model": model_name,
        "mae": mae,
        "smape": smape,
        "mape": mape,
        "forecast": forecast,
        "series": full_df,
    }


def main() -> None:
    init_mlflow("demand_forecasting")
    client = get_client()
    project = os.environ["GCP_PROJECT_ID"]

    log.info("Loading weekly order data from BigQuery…")
    df = load_data(client, project)
    df["week_start"] = pd.to_datetime(df["week_start"])
    log.info(f"Loaded {len(df):,} category-week rows")

    top_cats = get_top_categories(df, TOP_N_CATEGORIES)
    log.info(f"Top {TOP_N_CATEGORIES} categories: {top_cats}")

    all_results: list[dict] = []

    with mlflow.start_run(run_name="demand_forecasting_top10"):
        mlflow.log_param("categories", ",".join(top_cats))
        mlflow.log_param("forecast_periods", FORECAST_PERIODS)
        mlflow.log_param("min_weeks", MIN_WEEKS)
        mlflow.log_param("trim_tail_weeks", TRIM_TAIL_WEEKS)

        for cat in top_cats:
            log.info(f"Fitting: {cat}")
            result = fit_forecast(df, cat)
            if result is None:
                continue

            safe = cat.replace(" ", "_").replace("/", "_")
            mlflow.log_param(f"model_{safe}", result["model"])
            mlflow.log_metric(f"{safe}_mae", result["mae"])
            mlflow.log_metric(f"{safe}_smape", result["smape"])
            if not np.isnan(result["mape"]):
                mlflow.log_metric(f"{safe}_mape", result["mape"])
            log.info(
                f"  {cat}: MAE={result['mae']:.2f}  sMAPE={result['smape']:.4f}"
            )

            series = result["series"]
            forecast = result["forecast"]
            fig, ax = plt.subplots(figsize=(12, 4))
            ax.plot(series["ds"], series["y"], label="Actual", color="steelblue")
            future_mask = forecast["ds"] > series["ds"].max()
            fc_future = forecast[future_mask]
            ax.plot(
                fc_future["ds"],
                fc_future["yhat"],
                label="Forecast",
                color="darkorange",
                linestyle="--",
            )
            if "yhat_lower" in forecast.columns:
                ax.fill_between(
                    fc_future["ds"],
                    fc_future["yhat_lower"],
                    fc_future["yhat_upper"],
                    alpha=0.2,
                    color="darkorange",
                )
            ax.set_title(f"Demand Forecast: {cat} ({result['model']})")
            ax.set_xlabel("Week")
            ax.set_ylabel("Delivered Order Count")
            ax.legend()
            fig.tight_layout()
            mlflow.log_figure(fig, f"forecast_{safe}.png")
            plt.close(fig)

            all_results.append(
                {
                    "category": cat,
                    "model": result["model"],
                    "mae": round(result["mae"], 2),
                    "smape": round(result["smape"], 4),
                    "mape": round(result["mape"], 4) if not np.isnan(result["mape"]) else None,
                }
            )

        if all_results:
            summary = pd.DataFrame(all_results)
            fig3, ax3 = plt.subplots(figsize=(12, max(3, len(all_results) * 0.5)))
            ax3.axis("off")
            tbl = ax3.table(
                cellText=summary.values,
                colLabels=summary.columns,
                loc="center",
            )
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(8)
            fig3.tight_layout()
            mlflow.log_figure(fig3, "forecast_metrics_summary.png")
            plt.close(fig3)

        run_id = mlflow.active_run().info.run_id

    log.info(f"MLflow run: {run_id}")
    log.info("Forecasting complete.")


if __name__ == "__main__":
    main()
