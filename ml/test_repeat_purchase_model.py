"""
Unit tests for repeat_purchase_model.py — no BigQuery connection required.
Run from src/: pytest ml/test_repeat_purchase_model.py -v
"""
import numpy as np
import pandas as pd
import pytest

import repeat_purchase_model as m


def _make_df(n: int = 20, include_nans: bool = False) -> pd.DataFrame:
    """Minimal dataframe with all columns preprocess() needs."""
    rng = np.random.default_rng(0)
    df = pd.DataFrame(
        {
            "frequency": rng.integers(1, 5, size=n).astype(float),
            "monetary": rng.uniform(50, 500, size=n),
            "avg_order_value": rng.uniform(50, 500, size=n),
            "tenure_days": rng.integers(10, 500, size=n).astype(float),
            "recency_at_T": rng.integers(1, 200, size=n).astype(float),
            "max_installments_used": rng.integers(1, 12, size=n).astype(float),
            "used_credit_card": rng.integers(0, 2, size=n).astype(float),
            "used_boleto": rng.integers(0, 2, size=n).astype(float),
            "used_voucher": rng.integers(0, 2, size=n).astype(float),
            "avg_review_score": rng.uniform(1, 5, size=n),
            "reviewed_order_count": rng.integers(0, 5, size=n).astype(float),
            "will_repeat": rng.integers(0, 2, size=n),
            "snapshot_date": "2018-06-01",
        }
    )
    if include_nans:
        df.loc[::4, "avg_review_score"] = np.nan
    return df


# ---------------------------------------------------------------------------
# preprocess() column contract
# ---------------------------------------------------------------------------


def test_preprocess_columns_match_features_exactly():
    df = _make_df()
    X, y = m.preprocess(df)
    assert list(X.columns) == m.FEATURES, (
        f"Column order mismatch.\nExpected: {m.FEATURES}\nGot: {list(X.columns)}"
    )


def test_preprocess_row_count_preserved():
    df = _make_df(n=30)
    X, y = m.preprocess(df)
    assert len(X) == 30
    assert len(y) == 30


# ---------------------------------------------------------------------------
# NaN avg_review_score handling
# ---------------------------------------------------------------------------


def test_nan_review_score_sets_has_review_zero():
    df = _make_df(n=10)
    df.loc[0, "avg_review_score"] = np.nan
    X, _ = m.preprocess(df)
    assert X.loc[0, "has_review"] == 0


def test_non_nan_review_score_sets_has_review_one():
    df = _make_df(n=10)
    X, _ = m.preprocess(df)
    assert (X["has_review"] == 1).all()


def test_nan_review_score_filled_with_median():
    df = _make_df(n=20, include_nans=True)
    non_null = df["avg_review_score"].dropna()
    expected_median = float(non_null.median())

    X, _ = m.preprocess(df)
    # Rows that had NaN should now equal the median
    nan_rows = df["avg_review_score"].isna()
    filled_values = X.loc[nan_rows, "avg_review_score"]
    assert np.allclose(filled_values.values, expected_median)


def test_preprocess_uses_supplied_review_median():
    """Passing a custom median overrides the data-derived median."""
    df = _make_df(n=10, include_nans=True)
    custom_median = 999.0
    X, _ = m.preprocess(df, review_median=custom_median)
    nan_rows = df["avg_review_score"].isna()
    assert np.allclose(X.loc[nan_rows, "avg_review_score"].values, custom_median)


def test_preprocess_no_remaining_nans():
    df = _make_df(n=20, include_nans=True)
    X, _ = m.preprocess(df)
    assert not X.isna().any().any()


# ---------------------------------------------------------------------------
# BANNED_COLS guard
# ---------------------------------------------------------------------------


def test_banned_cols_not_in_output_when_df_has_them():
    """Even if df contains a banned column name, preprocess must exclude it from X."""
    df = _make_df(n=10)
    df["recency_days"] = 100.0      # banned — must not survive into X
    df["snapshot_date_col"] = "x"
    X, _ = m.preprocess(df)
    for col in m.BANNED_COLS:
        assert col not in X.columns, f"Banned column '{col}' leaked into X"


def test_banned_cols_assertion_fires_if_feature_patched(monkeypatch):
    """
    If FEATURES is accidentally edited to include a banned column,
    the assertion in main() must fire.  We simulate this by monkeypatching
    FEATURES and then running the assertion logic directly.
    """
    patched_features = list(m.FEATURES) + ["recency_days"]
    monkeypatch.setattr(m, "FEATURES", patched_features)

    df = _make_df(n=10)
    df["recency_days"] = 50.0
    # preprocess now pulls recency_days into X
    X, _ = m.preprocess(df)
    leaked = set(X.columns) & m.BANNED_COLS
    assert leaked, "Expected banned col to appear in X when FEATURES is patched"
    with pytest.raises(AssertionError, match="Leakage"):
        assert not leaked, f"Leakage columns in features: {leaked}"
