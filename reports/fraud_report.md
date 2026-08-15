# Fraud & Anomaly Detection Report

**Ground truth injected fraud campaigns:** [8, 9, 10]

## Validation Summary (Precision / Recall / F1)

| Method | Flagged Campaigns | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|
| Rule-based (combined) | [8, 9, 10] | 3 | 0 | 0 | 1.0 | 1.0 | 1.0 |
| Poisson hourly | [8, 10] | 2 | 0 | 1 | 1.0 | 0.667 | 0.8 |
| Interval regularity | [10] | 1 | 0 | 2 | 1.0 | 0.333 | 0.5 |
| Isolation Forest | [8] | 1 | 0 | 2 | 1.0 | 0.333 | 0.5 |

## Method Notes

- **Rule-based:** click velocity (IP burst detection) + CTR z-score outliers + binomial test for conversion-free click campaigns.
- **Poisson hourly:** per-campaign hourly click counts fitted to a Poisson distribution; campaigns flagged when their COUNT of 99th-percentile-exceeding hours is a z-score outlier relative to peer campaigns (not merely 'had one').
- **Interval regularity:** sliding-window scan (window=10 consecutive clicks) for an embedded near-perfectly-regular interval subsequence, which survives even when a scripted burst is a small fraction of a campaign's total traffic.
- **Isolation Forest:** unsupervised ML on 5 engineered hourly features; campaigns flagged when their RATE of anomalous hours is a z-score outlier relative to peer campaigns.

Note: injected fraud in this dataset is MIXED with legitimate traffic on the same campaigns, not the campaign's only traffic -- a realistic constraint that dilutes naive signals and motivated the campaign-level aggregation approach used above.