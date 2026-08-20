# Morning Report — Ad Campaign Performance & Fraud Monitoring

Generated: 2026-08-20 07:46:03

## Pipeline Status

| Module | Status |
|---|---|
| Pacing Health Check | PASS |
| Fraud & Anomaly Detection | PASS |
| A/B Testing | PASS |

**Overall pipeline status: ALL CHECKS PASSED**


## Pacing Health Check

> # Pacing Health Report
> Generated from 2026-01-29 snapshot (18 campaigns)
> ## Summary

[Full report](pacing_report.md)

## Fraud & Anomaly Detection

> # Fraud & Anomaly Detection Report
> **Ground truth injected fraud campaigns:** [8, 9, 10]
> ## Validation Summary (Precision / Recall / F1)

[Full report](fraud_report.md)

## A/B Testing

> # A/B Testing Report
> **Ground truth campaigns with a real injected effect:** [5, 6, 7]
> **Excluded from analysis (known fraud-contaminated traffic):** [8, 9, 10] -- see fraud_report.md. Conversion-rate comparisons on contaminated traffic aren't trustworthy regardless of p-value; these campaigns should be re-tested after fraud is filtered from the underlying click data.

[Full report](ab_test_report.md)

---
*Generated automatically by run_daily_check.py at 2026-08-20 07:46:03*