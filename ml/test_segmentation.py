"""
Unit tests for segmentation.py — no BigQuery connection required.
Run from src/: pytest ml/test_segmentation.py -v
"""
import numpy as np
import pandas as pd
import pytest

from segmentation import label_segments, safe_qcut, RFM_Q


def _make_centers(recency, frequency, monetary) -> pd.DataFrame:
    """Build a centers_df in the format label_segments() expects."""
    return pd.DataFrame(
        {
            "cluster": list(range(len(recency))),
            "recency_days": recency,
            "frequency": frequency,
            "monetary": monetary,
        }
    )


# ---------------------------------------------------------------------------
# label_segments()
# ---------------------------------------------------------------------------


def test_label_segments_champions_has_lowest_recency_highest_fm():
    """
    Champions = low recency (most recent), high frequency, high monetary.
    Set up 5 clusters where cluster 0 is clearly the best.
    """
    centers = _make_centers(
        recency=[5, 50, 150, 300, 600],     # cluster 0 = most recent
        frequency=[10, 7, 4, 2, 1],         # cluster 0 = highest
        monetary=[1000, 700, 400, 200, 50], # cluster 0 = highest
    )
    mapping = label_segments(centers)
    assert mapping[0] == "Champions"


def test_label_segments_at_risk_has_highest_recency_lowest_fm():
    """At Risk = high recency (stale), low frequency, low monetary."""
    centers = _make_centers(
        recency=[5, 50, 150, 300, 600],
        frequency=[10, 7, 4, 2, 1],
        monetary=[1000, 700, 400, 200, 50],
    )
    mapping = label_segments(centers)
    assert mapping[4] == "At Risk"


def test_label_segments_returns_all_five_standard_names():
    centers = _make_centers(
        recency=[5, 50, 150, 300, 600],
        frequency=[10, 7, 4, 2, 1],
        monetary=[1000, 700, 400, 200, 50],
    )
    mapping = label_segments(centers)
    expected = {"Champions", "Loyal Customers", "Potential Loyalists", "New Customers", "At Risk"}
    assert set(mapping.values()) == expected


def test_label_segments_k_gt_5_pads_with_extra_names():
    centers = _make_centers(
        recency=[5, 50, 150, 300, 600, 900],
        frequency=[10, 7, 4, 2, 1, 1],
        monetary=[1000, 700, 400, 200, 50, 30],
    )
    mapping = label_segments(centers)
    assert len(mapping) == 6
    assert "Segment 6" in mapping.values()


def test_label_segments_is_deterministic():
    """Pure function — calling twice must return the same mapping."""
    centers = _make_centers(
        recency=[5, 50, 150, 300, 600],
        frequency=[10, 7, 4, 2, 1],
        monetary=[1000, 700, 400, 200, 50],
    )
    assert label_segments(centers) == label_segments(centers)


# ---------------------------------------------------------------------------
# safe_qcut()
# ---------------------------------------------------------------------------


def test_safe_qcut_normal_series():
    s = pd.Series(range(100))
    result = safe_qcut(s, q=5, labels=[1, 2, 3, 4, 5])
    assert result.notna().all()
    assert set(result.unique()) == {1, 2, 3, 4, 5}


def test_safe_qcut_handles_mostly_duplicate_values():
    """Simulates the ~97% frequency=1 scenario that breaks standard pd.qcut."""
    s = pd.Series([1] * 97 + [2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
    result = safe_qcut(s, q=5, labels=[1, 2, 3, 4, 5])
    assert result.notna().all()
    assert len(result) == 107


def test_safe_qcut_reverse_labels():
    """Lower values should get higher labels when labels are reversed."""
    s = pd.Series(range(10))
    result = safe_qcut(s, q=5, labels=[5, 4, 3, 2, 1])
    result_int = result.astype(int)
    # The lowest-value bin should have label 5
    assert result_int.iloc[0] == 5


# ---------------------------------------------------------------------------
# rfm_score production (integration with label pipeline)
# ---------------------------------------------------------------------------


def test_rfm_score_range_is_valid():
    """
    rfm_score = r_score + f_score + m_score, each in 1..RFM_Q.
    So rfm_score must be in [3, 3*RFM_Q].
    """
    s_recency = pd.Series(np.random.default_rng(0).integers(1, 500, size=200).astype(float))
    s_freq = pd.Series([1] * 180 + list(range(2, 22)))  # skewed like real data
    s_monetary = pd.Series(np.random.default_rng(1).uniform(10, 1000, size=200))

    r_score = safe_qcut(s_recency, q=RFM_Q, labels=[5, 4, 3, 2, 1]).astype(float)
    f_score = safe_qcut(s_freq, q=RFM_Q, labels=[1, 2, 3, 4, 5]).astype(float)
    m_score = safe_qcut(s_monetary, q=RFM_Q, labels=[1, 2, 3, 4, 5]).astype(float)
    rfm_score = r_score + f_score + m_score

    assert rfm_score.min() >= 3
    assert rfm_score.max() <= 3 * RFM_Q
