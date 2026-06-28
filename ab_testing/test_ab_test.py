"""
pytest suite for ab_test.py.

Covers: proportion (significant / null / edge cases) and continuous
(normal → t-test, non-normal → Mann-Whitney U) branches.
"""
import numpy as np
import pytest

from ab_test import ABTestResult, run_ab_test

RNG = np.random.default_rng(seed=0)


# ---------------------------------------------------------------------------
# Proportion tests
# ---------------------------------------------------------------------------


def test_proportion_significant():
    control = np.array([0] * 900 + [1] * 100)
    variant = np.array([0] * 800 + [1] * 200)
    result = run_ab_test(control, variant, metric_type="proportion")
    assert result.significant
    assert result.p_value < 0.05


def test_proportion_null():
    # Negligible difference — should not be significant
    control = np.array([0] * 900 + [1] * 100)
    variant = np.array([0] * 901 + [1] * 99)
    result = run_ab_test(control, variant, metric_type="proportion")
    assert not result.significant


def test_proportion_zero_control_rate():
    control = np.zeros(100)
    variant = np.array([0] * 90 + [1] * 10)
    result = run_ab_test(control, variant, metric_type="proportion")
    assert "N/A" in result.lift


def test_proportion_equal_rates():
    arr = np.array([0, 1] * 50)
    result = run_ab_test(arr, arr.copy(), metric_type="proportion")
    assert not result.significant


def test_proportion_invalid_values():
    with pytest.raises(ValueError, match="0/1"):
        run_ab_test([0, 1, 2], [0, 1], metric_type="proportion")


# ---------------------------------------------------------------------------
# Continuous — normal path (Welch's t-test)
# ---------------------------------------------------------------------------


def test_continuous_normal_significant():
    a = RNG.normal(loc=10.0, scale=1.0, size=200)
    b = RNG.normal(loc=12.0, scale=1.0, size=200)
    result = run_ab_test(a, b, metric_type="continuous")
    assert result.significant
    assert result.p_value < 0.05


def test_continuous_normal_null():
    a = RNG.normal(loc=10.0, scale=1.0, size=200)
    b = RNG.normal(loc=10.05, scale=1.0, size=200)
    result = run_ab_test(a, b, metric_type="continuous")
    assert not result.significant


# ---------------------------------------------------------------------------
# Continuous — non-normal path (Mann-Whitney U)
# ---------------------------------------------------------------------------


def test_continuous_nonnormal_significant():
    a = RNG.exponential(scale=1.0, size=300)
    b = RNG.exponential(scale=3.0, size=300)
    result = run_ab_test(a, b, metric_type="continuous")
    assert result.significant
    assert "Mann-Whitney" in result.assumptions


def test_continuous_nonnormal_null():
    a = RNG.exponential(scale=1.0, size=300)
    b = RNG.exponential(scale=1.02, size=300)
    result = run_ab_test(a, b, metric_type="continuous")
    assert not result.significant


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_small_arrays_no_crash():
    result = run_ab_test([1, 0, 1], [0, 1, 0], metric_type="proportion")
    assert isinstance(result, ABTestResult)


def test_invalid_metric_type():
    with pytest.raises(ValueError, match="metric_type"):
        run_ab_test([1, 2, 3], [4, 5, 6], metric_type="invalid")


def test_result_fields_populated():
    result = run_ab_test(
        [0] * 50 + [1] * 50, [0] * 40 + [1] * 60, metric_type="proportion"
    )
    assert result.conclusion
    assert result.assumptions
    assert result.confidence_interval is not None
    assert result.lift is not None
    assert isinstance(result.significant, bool)


def test_continuous_ci_direction():
    a = RNG.normal(10, 1, 200)
    b = RNG.normal(12, 1, 200)
    result = run_ab_test(a, b, metric_type="continuous")
    lo, hi = result.confidence_interval
    # With a clear 2-unit shift the CI should be entirely positive
    assert lo > 0 and hi > 0


# ---------------------------------------------------------------------------
# Gap tests (added per phase 3 test plan §5)
# ---------------------------------------------------------------------------


def test_continuous_n1_single_arm_no_crash():
    """n=1 in one arm falls to shapiro_n<3 → Mann-Whitney; no crash."""
    result = run_ab_test([5.0], [5.0, 6.0, 7.0], metric_type="continuous")
    assert isinstance(result, ABTestResult)
    assert "Mann-Whitney" in result.assumptions


def test_sample_size_continuous_identical_arrays_is_none():
    """Identical control and variant → diff=0 → recommended_sample_size is None."""
    identical = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = run_ab_test(identical, identical.copy(), metric_type="continuous")
    assert result.recommended_sample_size is None


def test_continuous_nonnormal_significant_ci_excludes_zero():
    """Mann-Whitney significant case: bootstrap CI should exclude zero."""
    a = RNG.exponential(scale=1.0, size=300)
    b = RNG.exponential(scale=3.0, size=300)
    result = run_ab_test(a, b, metric_type="continuous")
    assert result.significant
    lo, hi = result.confidence_interval
    assert not (lo <= 0 <= hi), f"CI [{lo:.4f}, {hi:.4f}] should exclude zero"
