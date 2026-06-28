"""
Reusable A/B testing module — no BigQuery or MLflow dependencies.

Supports:
  - proportion metrics: two-proportion z-test
  - continuous metrics: Shapiro-Wilk → Welch's t-test (normal) or Mann-Whitney U (non-normal)

Returns an ABTestResult dataclass with p-value, CI, lift, recommended sample size,
test assumptions used, and a plain-English conclusion.
"""
import math
import random
import warnings
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
from scipy import stats


@dataclass
class ABTestResult:
    test_type: str
    statistic: float
    p_value: float
    confidence_interval: tuple[float, float]
    significant: bool
    lift: Optional[str]
    recommended_sample_size: Optional[int]
    conclusion: str
    assumptions: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _welch_ci(a: np.ndarray, b: np.ndarray, alpha: float) -> tuple[float, float]:
    """CI on (mean_b - mean_a) using Welch's t-distribution."""
    n1, n2 = len(a), len(b)
    m1, m2 = np.mean(a), np.mean(b)
    s1, s2 = np.std(a, ddof=1), np.std(b, ddof=1)
    se = math.sqrt(s1**2 / n1 + s2**2 / n2)

    num = (s1**2 / n1 + s2**2 / n2) ** 2
    den = (s1**2 / n1) ** 2 / (n1 - 1) + (s2**2 / n2) ** 2 / (n2 - 1)
    df = num / den if den > 0 else float(min(n1, n2) - 1)

    t_crit = stats.t.ppf(1 - alpha / 2, df)
    diff = m2 - m1
    return (diff - t_crit * se, diff + t_crit * se)


def _bootstrap_ci(
    a: np.ndarray, b: np.ndarray, alpha: float, n_boot: int = 2000
) -> tuple[float, float]:
    """Bootstrap CI on difference of means (mean_b - mean_a)."""
    rng = np.random.default_rng(42)
    diffs = (
        rng.choice(b, size=(n_boot, len(b)), replace=True).mean(axis=1)
        - rng.choice(a, size=(n_boot, len(a)), replace=True).mean(axis=1)
    )
    lo, hi = np.percentile(diffs, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return (float(lo), float(hi))


def _sample_size_proportion(
    p1: float, p2: float, alpha: float, power: float
) -> Optional[int]:
    if p1 == p2:
        return None
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)
    p_bar = (p1 + p2) / 2
    n = (
        z_alpha * math.sqrt(2 * p_bar * (1 - p_bar))
        + z_beta * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    ) ** 2 / (p2 - p1) ** 2
    return math.ceil(n)


def _sample_size_continuous(
    a: np.ndarray, b: np.ndarray, alpha: float, power: float
) -> Optional[int]:
    pooled_std = math.sqrt((np.var(a, ddof=1) + np.var(b, ddof=1)) / 2)
    diff = abs(np.mean(b) - np.mean(a))
    if diff == 0 or pooled_std == 0 or math.isnan(pooled_std):
        return None
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)
    n = ((z_alpha + z_beta) * pooled_std / diff) ** 2
    if math.isnan(n):
        return None
    return math.ceil(n)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_ab_test(
    control: Sequence,
    variant: Sequence,
    metric_type: str = "continuous",
    alpha: float = 0.05,
    power: float = 0.80,
) -> ABTestResult:
    """
    Run an A/B test and return a structured result.

    Parameters
    ----------
    control, variant : sequences of numeric observations
    metric_type      : "proportion" (0/1 arrays) or "continuous"
    alpha            : significance level, default 0.05
    power            : desired power for sample-size recommendation, default 0.80
    """
    if metric_type not in ("proportion", "continuous"):
        raise ValueError(
            f"metric_type must be 'proportion' or 'continuous', got '{metric_type}'"
        )

    a = np.asarray(control, dtype=float)
    b = np.asarray(variant, dtype=float)

    if metric_type == "proportion":
        for arr, name in [(a, "control"), (b, "variant")]:
            unique = set(np.unique(arr))
            if not unique.issubset({0.0, 1.0}):
                raise ValueError(
                    f"{name} must contain only 0/1 values for a proportion test; "
                    f"found: {unique}"
                )

        p1, p2 = float(a.mean()), float(b.mean())
        n1, n2 = len(a), len(b)

        p_pool = (p1 * n1 + p2 * n2) / (n1 + n2)
        se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))

        if se == 0:
            statistic, p_value = float("nan"), 1.0
        else:
            statistic = (p2 - p1) / se
            p_value = float(2 * (1 - stats.norm.cdf(abs(statistic))))

        ci_se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
        z_crit = stats.norm.ppf(1 - alpha / 2)
        ci = ((p2 - p1) - z_crit * ci_se, (p2 - p1) + z_crit * ci_se)

        lift = (
            f"{(p2 - p1) / p1 * 100:+.2f}% relative lift"
            if p1 > 0
            else "N/A (control rate is 0)"
        )
        ss = _sample_size_proportion(p1, p2, alpha, power)
        assumptions = (
            "Two-proportion z-test with normal approximation to the binomial. "
            "CI on absolute difference in proportions."
        )

    else:  # continuous
        shapiro_n = min(len(a), len(b), 50)

        if shapiro_n < 3:
            normal = False
        else:
            rng = random.Random(42)
            s_a = rng.sample(list(a), shapiro_n)
            s_b = rng.sample(list(b), shapiro_n)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                _, p_a = stats.shapiro(s_a)
                _, p_b = stats.shapiro(s_b)
            normal = (p_a > alpha) and (p_b > alpha)

        if normal:
            statistic, p_value = stats.ttest_ind(a, b, equal_var=False)
            ci = _welch_ci(a, b, alpha)
            assumptions = (
                f"Shapiro-Wilk normality not rejected (sample n={shapiro_n}); "
                "Welch's two-sample t-test (unequal variances). "
                "CI on difference of means via Welch's t-distribution."
            )
        else:
            statistic, p_value = stats.mannwhitneyu(a, b, alternative="two-sided")
            ci = _bootstrap_ci(a, b, alpha)
            assumptions = (
                f"Shapiro-Wilk normality rejected (sample n={shapiro_n}); "
                "Mann-Whitney U test (non-parametric). "
                "CI on difference of means via percentile bootstrap (2000 resamples)."
            )

        lift = f"{np.mean(b) - np.mean(a):+.4f} absolute difference in means"
        ss = _sample_size_continuous(a, b, alpha, power)

    significant = bool(p_value < alpha)
    direction = "higher" if (b.mean() > a.mean()) else "lower"
    conclusion = (
        f"The variant ({b.mean():.4f}) is "
        f"{'statistically significantly ' if significant else 'not significantly '}"
        f"{direction} than control ({a.mean():.4f}). "
        f"p={p_value:.4f} "
        f"({'significant' if significant else 'not significant'} at α={alpha})."
    )

    return ABTestResult(
        test_type=metric_type,
        statistic=float(statistic),
        p_value=float(p_value),
        confidence_interval=(float(ci[0]), float(ci[1])),
        significant=significant,
        lift=lift,
        recommended_sample_size=ss,
        conclusion=conclusion,
        assumptions=assumptions,
    )
