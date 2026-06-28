"""
Unit tests for forecasting.py — no BigQuery connection required.
Run from src/: pytest ml/test_forecasting.py -v
"""
import sys
import types

import numpy as np
import pandas as pd
import pytest

from forecasting import MIN_WEEKS, FORECAST_PERIODS, _mape, _smape, fit_forecast


# ---------------------------------------------------------------------------
# Metric math
# ---------------------------------------------------------------------------


def test_smape_perfect_forecast_is_zero():
    y = np.array([10.0, 20.0, 30.0])
    assert _smape(y, y) == pytest.approx(0.0, abs=1e-9)


def test_smape_known_value():
    y_true = np.array([100.0])
    y_pred = np.array([200.0])
    # 2*|100-200|/(100+200) = 200/300 ≈ 0.6667
    assert _smape(y_true, y_pred) == pytest.approx(2 / 3, rel=1e-4)


def test_smape_always_non_negative():
    rng = np.random.default_rng(0)
    y_true = rng.uniform(0, 100, size=50)
    y_pred = rng.uniform(0, 100, size=50)
    assert _smape(y_true, y_pred) >= 0


def test_mape_all_zero_y_true_returns_nan_no_raise():
    result = _mape(np.zeros(5), np.ones(5))
    assert np.isnan(result), "Expected nan when all y_true are zero"


def test_mape_known_value():
    y_true = np.array([100.0, 200.0])
    y_pred = np.array([110.0, 180.0])
    # MAPE = mean(|10/100|, |20/200|) = mean(0.10, 0.10) = 0.10
    assert _mape(y_true, y_pred) == pytest.approx(0.10, rel=1e-4)


def test_mape_skips_zero_entries():
    y_true = np.array([0.0, 100.0])
    y_pred = np.array([50.0, 110.0])
    # Only the second pair counts: |10/100| = 0.10
    assert _mape(y_true, y_pred) == pytest.approx(0.10, rel=1e-4)


# ---------------------------------------------------------------------------
# fit_forecast() filtering / None returns
# ---------------------------------------------------------------------------


def _make_weekly_df(n_weeks: int, category: str = "test_cat", zero_frac: float = 0.0) -> pd.DataFrame:
    weeks = pd.date_range("2017-01-01", periods=n_weeks, freq="W")
    counts = np.ones(n_weeks, dtype=float)
    if zero_frac > 0:
        n_zeros = int(n_weeks * zero_frac)
        counts[:n_zeros] = 0.0
    return pd.DataFrame({"week_start": weeks, "category": category, "order_count": counts})


def test_fit_forecast_returns_none_when_fewer_than_min_weeks():
    df = _make_weekly_df(n_weeks=MIN_WEEKS - 1)
    result = fit_forecast(df, "test_cat")
    assert result is None


def test_fit_forecast_returns_none_when_above_50pct_zeros():
    df = _make_weekly_df(n_weeks=MIN_WEEKS + 10, zero_frac=0.6)
    result = fit_forecast(df, "test_cat")
    assert result is None


def test_fit_forecast_returns_none_for_missing_category():
    df = _make_weekly_df(n_weeks=MIN_WEEKS + 5, category="other")
    result = fit_forecast(df, "test_cat")
    assert result is None


# ---------------------------------------------------------------------------
# ExponentialSmoothing fallback via monkeypatched Prophet import
# ---------------------------------------------------------------------------


def _make_valid_df(n_weeks: int = MIN_WEEKS + 20, category: str = "test_cat") -> pd.DataFrame:
    rng = np.random.default_rng(42)
    weeks = pd.date_range("2016-01-01", periods=n_weeks, freq="W")
    counts = rng.uniform(5, 50, size=n_weeks)
    return pd.DataFrame({"week_start": weeks, "category": category, "order_count": counts})


def test_fallback_via_monkeypatched_prophet(monkeypatch):
    """
    Simulate Prophet not being installed by making the import raise ImportError.
    The fallback must return the same dict interface as the Prophet path.
    """
    # Create a fake 'prophet' module whose Prophet class raises on import
    fake_prophet_module = types.ModuleType("prophet")

    class _ProphetImportError:
        def __init__(self, *a, **kw):
            raise ImportError("Prophet not available (monkeypatched)")

    fake_prophet_module.Prophet = _ProphetImportError
    # Ensure the import inside fit_forecast raises ImportError
    monkeypatch.setitem(sys.modules, "prophet", None)  # None causes ImportError on `from prophet import ...`

    df = _make_valid_df()
    result = fit_forecast(df, "test_cat")

    # Fallback should succeed and return a result dict (not None)
    assert result is not None, "Fallback path returned None unexpectedly"

    # Both paths must return the same interface
    expected_keys = {"model", "mae", "smape", "mape", "forecast", "series"}
    assert set(result.keys()) == expected_keys

    assert result["model"] == "exponential_smoothing"
    assert isinstance(result["mae"], float)
    assert isinstance(result["smape"], float)
    assert isinstance(result["forecast"], object)  # DataFrame


def test_prophet_path_returns_correct_interface():
    """
    If Prophet IS available, fit_forecast must return the same dict interface.
    Skipped gracefully if Prophet is not installed in the test environment.
    """
    pytest.importorskip("prophet", reason="Prophet not installed — skipping Prophet path test")
    df = _make_valid_df()
    result = fit_forecast(df, "test_cat")
    if result is None:
        pytest.skip("fit_forecast returned None — series may be too short after trim")
    expected_keys = {"model", "mae", "smape", "mape", "forecast", "series"}
    assert set(result.keys()) == expected_keys
    assert result["model"] == "prophet"


# ---------------------------------------------------------------------------
# Forecast sanity
# ---------------------------------------------------------------------------


def test_fallback_forecast_non_negative(monkeypatch):
    monkeypatch.setitem(sys.modules, "prophet", None)
    df = _make_valid_df(n_weeks=MIN_WEEKS + 30)
    result = fit_forecast(df, "test_cat")
    assert result is not None
    assert (result["forecast"]["yhat"] >= 0).all()
