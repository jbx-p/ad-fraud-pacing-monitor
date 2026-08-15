# Methodology

This document explains the reasoning behind the statistical methods,
thresholds, and architecture decisions in this project — including
several real bugs found and fixed during development via the
ground-truth validation process, which is exactly what that process is
for.

## Why SQLite

Chosen deliberately, not as a limitation. SQL skills (window functions,
CTEs, aggregations) transfer 1:1 to Snowflake/BigQuery/Postgres, and
SQLite removes all setup friction (no service to install, configure, or
authenticate against) for a project whose value is in the analysis, not
the database administration.

## Why synthetic data with injected ground truth

Real fraud/AB-test datasets don't come with an answer key — you never
actually know which clicks were fraudulent or whether an A/B effect was
real. By generating the data myself with a fixed random seed (42) and
recording exactly what was injected in `ground_truth.json`, every
detection method's precision/recall/F1 becomes independently
verifiable and reproducible, rather than an unfalsifiable claim.

## Phase 3 — Pacing

- **3-day rolling average for days-to-exhaustion**, rather than a
  single most-recent day, to avoid one unusual day (a spend spike or
  dip) distorting the projection.
- **Trend detection uses strict monotonic movement** over 3 consecutive
  days (all increasing or all decreasing) rather than a regression
  slope. This is a deliberately simple, conservative definition — a
  single flat or reversed day breaks the streak, which avoids false
  alarms from noise but is also a real limitation. A production version
  would likely use a regression slope over a longer window instead.

## Phase 4 — Fraud detection

### Click velocity (rule-based)
Uses fixed 5-minute buckets rather than a true rolling window, because
SQLite handles time-range window joins poorly compared to
Postgres/Snowflake. This is a documented simplification, not a silent
approximation — a production system would use a genuine rolling window.

### CTR outliers — a real bug found via ground-truth validation
The first version computed CTR from `daily_spend`'s `clicks` column,
which is generated independently from `click_events` in this synthetic
dataset and does not include injected fraud clicks. That made the rule
structurally blind to fraud regardless of threshold — it would never
have caught anything, at any sensitivity. Fixed by computing CTR from
actual `click_events` volume joined against `daily_spend`'s impressions.
This is the kind of bug that's easy to miss without a validation step
that actually checks results against a known answer.

### Interval regularity — global CV vs. sliding window
The first version computed one coefficient of variation across a
campaign's entire click history. This diluted a small embedded scripted
subsequence (40 clicks at exact 30-second intervals) into meaninglessness
when surrounded by tens of thousands of normally-timed clicks — the
method scored 0/0/0 recall despite the pattern being clearly present in
the data. Fixed with a sliding-window scan (window=10) that looks for
the *minimum* CV found anywhere in the sequence, which surfaces a small
embedded regular pattern regardless of how much normal traffic surrounds
it.

### Poisson hourly modeling and Isolation Forest — naive thresholds at scale
Both methods initially flagged nearly every campaign. At ~1,440 observed
hours per campaign, a 99th-percentile threshold produces roughly 14
"anomalous" hours *by chance alone* in every campaign — flagging a
campaign for having any single anomalous hour is not a real signal at
this scale. Fixed by aggregating to a per-campaign anomalous-hour count
(Poisson) or rate (Isolation Forest), then z-scoring that count/rate
*across* campaigns — flagging only campaigns with meaningfully more
anomalous hours than their peers, not merely "had one."

Isolation Forest also initially produced a false positive on the
lowest-volume (underpacing) campaign: low click-count hours produce
extreme, noisy ratio features (e.g. 1 click implies a trivial 1.0 unique
IP ratio) that dominate a distance-based model without reflecting real
anomalous behavior. Fixed with a minimum-clicks-per-hour filter before
fitting.

## Phase 5 — A/B testing

### Required vs. achieved power
`required_sample_size` asks "how much data would I need to reliably
detect a given lift" (a pre-launch planning question). `achieved_power`
asks "given what I actually collected, how likely was I to detect the
effect I observed" (a post-hoc diagnostic). These are kept as separate
functions deliberately — conflating them is a common real-world mistake.

### Wilson score intervals over normal approximation
At small samples or extreme rates, a normal-approximation confidence
interval can extend below 0% or above 100%, which is nonsensical for a
proportion. Wilson intervals are bounded within [0,1] by construction.

### Benjamini-Hochberg correction — added after a real false positive
Running one hypothesis test per campaign (18 total) at α=0.05 without
correction produces an expected ~0.9 false positives by chance alone.
This showed up concretely: campaign 12, with no true injected effect,
initially registered as a "significant winner" at raw p=0.034. After
Benjamini-Hochberg correction (controlling the false discovery rate
across all 18 simultaneous tests), its corrected p-value rose to 0.43 —
correctly reclassified as noise.

### Minimum meaningful effect size gate
Statistical significance alone isn't sufficient at large sample sizes.
This surfaced directly: two fraud-contaminated campaigns (bot traffic
and scripted clicks) initially showed p≈0.000 with relative lifts of
332% and 127% — driven by fraud clicks diluting each variant's real
conversion rate toward zero, at which point tiny absolute differences in
leftover legitimate conversions produce enormous *relative* percentages.
The correct fix was not a statistical threshold at all, but **excluding
known-fraudulent campaigns from A/B analysis entirely** — contaminated
traffic doesn't produce a trustworthy experiment regardless of how the
p-value is adjusted. In a production pipeline, the fraud-detection
module's flagged output would feed this exclusion directly.

### The peeking problem demonstration
Uses independently-simulated data (500 repeated null-effect trials), not
the project's real click data — demonstrating the peeking problem
requires many repeated trials to get a stable false-positive-rate
estimate, which a single real dataset can't provide. Result: a
pre-committed single-check rule lands at 4.0% false positives (matching
the theoretical 5% alpha), while checking significance daily and
stopping at the first "win" inflates that to 25.4% — a direct,
reproducible illustration of why live A/B dashboards shouldn't be
treated as a stopping rule.

### On campaigns 5, 6, 7 remaining "underpowered"
These three campaigns have a genuine injected ~17-38% relative lift, but
the module correctly flags them as underpowered given their actual
sample size (~600-1,300 clicks/variant) rather than a false "no effect"
or an inflated false-positive "win." This is treated as a feature, not a
bug: it's a direct, honest demonstration of the exact real-world problem
(underpowered tests) that the power-analysis component of this module is
designed to catch.

## Known limitations

- Click-velocity fraud detection uses fixed time buckets, not a true
  rolling window (SQLite constraint, documented above).
- Trend detection in pacing uses strict monotonic movement, not a
  statistical slope test.
- The synthetic dataset mixes fraud traffic into legitimate campaign
  traffic rather than modeling it as fully separate populations — this
  is realistic (real fraud is rarely 100% of a campaign's traffic) but
  does mean rule thresholds tuned here may not transfer directly to a
  dataset with a different fraud/legitimate ratio.
