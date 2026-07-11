"""
A/B Test Runner — interactive statistical significance calculator.

Imports run_ab_test from ab_testing.ab_test. Works in Docker (PYTHONPATH=/app)
and locally (PYTHONPATH=src or via _pathfix).
"""
import numpy as np
import streamlit as st

import _pathfix  # noqa: F401  (adds src/ to sys.path for the ab_testing.* import below)

try:
    from ab_testing.ab_test import ABTestResult, run_ab_test
except ImportError as e:
    st.error(f"Could not import ab_testing module: {e}")
    st.stop()

st.set_page_config(page_title="A/B Test Runner — DataPulse", layout="wide")
st.title("A/B Test Runner")
st.markdown(
    "Paste your control and variant data, choose a metric type, and run the test. "
    "Results include p-value, confidence interval, lift, recommended sample size, and a plain-English conclusion."
)

# ---------------------------------------------------------------------------
# Input form
# ---------------------------------------------------------------------------
col_ctrl, col_var = st.columns(2)

with col_ctrl:
    st.subheader("Control group")
    control_raw = st.text_area(
        "Paste values (one per line or comma-separated)",
        placeholder="0\n1\n0\n1\n0",
        height=200,
        key="control_input",
    )

with col_var:
    st.subheader("Variant group")
    variant_raw = st.text_area(
        "Paste values (one per line or comma-separated)",
        placeholder="0\n1\n1\n0\n1",
        height=200,
        key="variant_input",
    )

col_cfg1, col_cfg2, col_cfg3 = st.columns(3)
with col_cfg1:
    metric_type = st.selectbox(
        "Metric type",
        ["proportion", "continuous"],
        format_func=lambda v: "Proportion (0/1 values)" if v == "proportion" else "Continuous (numeric values)",
    )
with col_cfg2:
    alpha = st.slider("Significance level (α)", min_value=0.01, max_value=0.20, value=0.05, step=0.01)
with col_cfg3:
    power = st.slider("Target power (1−β)", min_value=0.60, max_value=0.99, value=0.80, step=0.01)


def _parse_input(raw: str) -> np.ndarray:
    """Parse newline- or comma-separated numbers into a float array."""
    raw = raw.replace(",", "\n")
    vals = [v.strip() for v in raw.splitlines() if v.strip()]
    return np.array([float(v) for v in vals])


# ---------------------------------------------------------------------------
# Run test
# ---------------------------------------------------------------------------
if st.button("Run A/B Test", type="primary"):
    if not control_raw.strip() or not variant_raw.strip():
        st.error("Both control and variant data are required.")
    else:
        try:
            control = _parse_input(control_raw)
            variant = _parse_input(variant_raw)
        except ValueError as exc:
            st.error(f"Could not parse input as numbers: {exc}")
            st.stop()

        try:
            result: ABTestResult = run_ab_test(
                control, variant, metric_type=metric_type, alpha=alpha, power=power
            )
        except ValueError as exc:
            st.error(f"Test input error: {exc}")
            st.stop()
        except Exception as exc:
            st.error(f"Unexpected error running test: {exc}")
            st.stop()

        # ------------------------------------------------------------------
        # Results card
        # ------------------------------------------------------------------
        st.divider()
        st.subheader("Results")

        if result.significant:
            st.success("**Statistically significant result** — the difference is unlikely due to chance.")
        else:
            st.info("**Not statistically significant** — insufficient evidence to reject the null hypothesis.")

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Test type", result.test_type)
        r2.metric("p-value", f"{result.p_value:.4f}")
        r3.metric("Significance (α)", f"{alpha:.2f}")
        r4.metric("Lift", result.lift)

        st.markdown("**Confidence interval** (difference between groups):")
        ci_lo, ci_hi = result.confidence_interval
        st.code(f"[{ci_lo:.4f}, {ci_hi:.4f}]")

        if result.recommended_sample_size is not None:
            st.metric(
                "Recommended sample size per group",
                f"{result.recommended_sample_size:,}",
                help="Minimum n to detect this effect size at the given α and power.",
            )

        with st.expander("Conclusion & assumptions", expanded=True):
            st.markdown(f"**Conclusion:** {result.conclusion}")
            st.markdown(f"**Assumptions:** {result.assumptions}")

        with st.expander("Raw statistics"):
            st.json({
                "test_type": result.test_type,
                "statistic": round(result.statistic, 6),
                "p_value": round(result.p_value, 6),
                "confidence_interval": [round(ci_lo, 6), round(ci_hi, 6)],
                "significant": result.significant,
                "lift": result.lift,
                "recommended_sample_size": result.recommended_sample_size,
            })

# ---------------------------------------------------------------------------
# Usage guide
# ---------------------------------------------------------------------------
with st.expander("Usage guide"):
    st.markdown(
        """
**Proportion test** — use for conversion rates, click-through rates, etc.
- Values must be `0` or `1` (integer flags).
- Runs a two-proportion z-test.

**Continuous test** — use for revenue, session duration, order value, etc.
- Values can be any numeric measurement.
- Normality tested with Shapiro-Wilk (on up to 50 samples).
- Normal → Welch's t-test; non-normal → Mann-Whitney U.

**Example — proportion:**
```
Control:  0,1,0,0,1,0,1,0,0,0
Variant:  1,1,0,1,1,0,1,1,0,1
```

**Example — continuous:**
```
Control:  12.5, 8.3, 22.1, 15.0, 9.8
Variant:  18.2, 25.0, 13.7, 30.1, 22.5
```
        """
    )
