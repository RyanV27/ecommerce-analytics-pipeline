## A/B testing (`ab_testing/ab_test.py`)

- Proportion metrics → two-proportion z-test
- Continuous metrics → Shapiro-Wilk normality test on 50-row sample; t-test if normal, Mann-Whitney U if not
- Default alpha = 0.05, power = 0.80
- Always report: p-value, confidence interval, recommended sample size, and a plain-English conclusion string
