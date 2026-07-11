"""
Generate copy-paste inputs for the DataPulse A/B Test Runner (Page 4).

Produces two test cases from the Olist Gold layer:
  1. Proportion  — on-time vs late delivery → satisfaction rate (review_score >= 4)
  2. Continuous  — credit-card vs boleto orders → total payment value

Run from src/ with:
    conda activate datapulse_venv
    $env:PYTHONPATH = "."
    python ab_testing/generate_ab_test_inputs.py
"""

import sys
import os
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.bq import get_client

SAMPLE_SIZE = 500  # rows per arm — keeps text areas manageable


def _run(client, sql: str):
    return client.query(sql).result().to_dataframe()


def case1_proportion(client) -> tuple[list, list]:
    """On-time vs late delivery → satisfied (review_score >= 4)."""
    sql = f"""
    WITH base AS (
      SELECT
        delivered_on_time,
        IF(review_score >= 4, 1, 0) AS satisfied,
        ROW_NUMBER() OVER (PARTITION BY delivered_on_time ORDER BY RAND()) AS rn
      FROM `{client.project}.gold.fct_orders`
      WHERE order_status = 'delivered'
        AND review_score IS NOT NULL
        AND delivered_on_time IS NOT NULL
    )
    SELECT delivered_on_time, satisfied
    FROM base
    WHERE rn <= {SAMPLE_SIZE}
    ORDER BY delivered_on_time, RAND()
    """
    df = _run(client, sql)
    control = df.loc[df["delivered_on_time"] == False, "satisfied"].tolist()   # late
    variant = df.loc[df["delivered_on_time"] == True,  "satisfied"].tolist()   # on-time
    return control, variant


def case2_continuous(client) -> tuple[list, list]:
    """Credit card vs boleto → total payment value (BRL)."""
    sql = f"""
    WITH base AS (
      SELECT
        CASE
          WHEN used_credit_card = 1 THEN 'credit_card'
          WHEN used_boleto      = 1 THEN 'boleto'
        END AS payment_type,
        total_payment_value,
        ROW_NUMBER() OVER (
          PARTITION BY (CASE WHEN used_credit_card = 1 THEN 'credit_card'
                             WHEN used_boleto      = 1 THEN 'boleto' END)
          ORDER BY RAND()
        ) AS rn
      FROM `{client.project}.gold.fct_orders`
      WHERE order_status = 'delivered'
        AND total_payment_value > 0
        AND (used_credit_card = 1 OR used_boleto = 1)
        AND NOT (used_credit_card = 1 AND used_boleto = 1)
    )
    SELECT payment_type, total_payment_value
    FROM base
    WHERE rn <= {SAMPLE_SIZE}
    """
    df = _run(client, sql)
    control = df.loc[df["payment_type"] == "boleto",      "total_payment_value"].round(2).tolist()
    variant  = df.loc[df["payment_type"] == "credit_card","total_payment_value"].round(2).tolist()
    return control, variant


def fmt(values: list, per_line: int = 10) -> str:
    """Format as comma-separated values, 10 per line for readability."""
    chunks = [
        ", ".join(str(v) for v in values[i : i + per_line])
        for i in range(0, len(values), per_line)
    ]
    return "\n".join(chunks)


def main():
    client = get_client()

    print("=" * 70)
    print("TEST CASE 1 — Proportion: late vs on-time delivery → satisfaction")
    print("  metric_type : proportion")
    print("  Hypothesis  : on-time delivery raises satisfaction (review >= 4)")
    print("  Expected    : significant, positive lift, p < 0.05")
    print("=" * 70)

    c1, v1 = case1_proportion(client)
    print(f"\nControl  (late delivery, n={len(c1)})")
    print("Paste into the CONTROL text area:")
    print(fmt(c1))
    print(f"\nVariant  (on-time delivery, n={len(v1)})")
    print("Paste into the VARIANT text area:")
    print(fmt(v1))

    rate_c = sum(c1) / len(c1) if c1 else 0
    rate_v = sum(v1) / len(v1) if v1 else 0
    print(f"\n  Late satisfaction rate   : {rate_c:.1%}")
    print(f"  On-time satisfaction rate: {rate_v:.1%}")
    print(f"  Raw lift                 : {rate_v - rate_c:+.1%}")

    print()
    print("=" * 70)
    print("TEST CASE 2 — Continuous: boleto vs credit card → order value (BRL)")
    print("  metric_type : continuous")
    print("  Hypothesis  : credit card orders have higher average value")
    print("  Expected    : Shapiro test decides t-test vs Mann-Whitney U")
    print("=" * 70)

    c2, v2 = case2_continuous(client)
    print(f"\nControl  (boleto, n={len(c2)})")
    print("Paste into the CONTROL text area:")
    print(fmt(c2))
    print(f"\nVariant  (credit card, n={len(v2)})")
    print("Paste into the VARIANT text area:")
    print(fmt(v2))

    mean_c = sum(c2) / len(c2) if c2 else 0
    mean_v = sum(v2) / len(v2) if v2 else 0
    print(f"\n  Boleto mean order value     : R$ {mean_c:.2f}")
    print(f"  Credit card mean order value: R$ {mean_v:.2f}")
    print(f"  Raw lift                    : R$ {mean_v - mean_c:+.2f}")
    print()


if __name__ == "__main__":
    main()
