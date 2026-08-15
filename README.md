# Ad Campaign Performance & Fraud Monitoring System

A portfolio project simulating the three responsibilities most ad-ops /
marketing-analytics job descriptions ask for: **pacing health checks**,
**fraud & anomaly detection** on click traffic, and **A/B testing** between
creatives — built with a synthetic-but-realistic dataset where every
anomaly is deliberately injected and documented as ground truth, so every
detection claim below is independently verifiable, not just asserted.

Built with Python, SQL (SQLite), pandas, scikit-learn, statsmodels, and
matplotlib.

---

## Results at a glance

**Fraud detection — validated against 3 known-injected fraud patterns
(click farm, bot traffic, scripted clicks):**

| Method | Precision | Recall | F1 |
|---|---|---|---|
| Rule-based (click velocity + CTR z-score + conversion-free binomial test) | 1.00 | 1.00 | 1.00 |
| Poisson hourly anomaly modeling | 1.00 | 0.67 | 0.80 |
| Sliding-window interval regularity scan | 1.00 | 0.33 | 0.50 |
| Isolation Forest (unsupervised ML) | 1.00 | 0.33 | 0.50 |

Every method achieves perfect precision (zero false positives); recall
varies by what each method is designed to catch — see
[METHODOLOGY.md](METHODOLOGY.md) for why each method finds what it finds
(and misses what it misses).

**A/B testing — validated against 3 campaigns with a genuine injected
effect (~17-38% relative lift):**

12/15 campaigns correctly classified (fraud-contaminated campaigns
excluded from analysis before testing). The 3 "misclassified" campaigns
are a deliberate, honest finding: the injected effect is real, but the
power analysis correctly identifies the actual sample size as
insufficient to detect it reliably at α=0.05 — precisely the
"real-world A/B tests are often underpowered" problem the module is
built to surface.

A sequential-testing simulation demonstrates the peeking problem
directly: checking significance daily and stopping at the first "win"
inflates the false-positive rate from a theoretical ~5% to **25.4%**
across 500 simulated null-effect tests.

**Pacing monitoring:** correctly classifies all 4 ground-truth pacing
campaigns (2 overpacing, 2 underpacing) and projects days-to-budget-
exhaustion using a 3-day rolling spend average.

---

## Architecture
A synthetic ad-platform "warehouse": raw click/spend events feed SQL
aggregation views, which feed three independent Python analysis modules,
each producing a markdown report and (for pacing) charts.

---

## Reproducing this locally

Raw data files are not committed to this repo — they're fully
reproducible with a fixed random seed (42), so anyone cloning this repo
regenerates the exact same dataset and gets the exact same results shown
above.

```powershell
python -m venv venv
venv\Scripts\Activate.ps1        # Windows PowerShell
# source venv/bin/activate       # Mac/Linux

pip install -r requirements.txt

python src\generate_data.py      # builds data/adops.db + data/ground_truth.json
python src\pacing.py             # -> reports/pacing_report.md + charts
python src\fraud_detection.py    # -> reports/fraud_report.md
python src\ab_testing.py         # -> reports/ab_test_report.md
```

---

## Ground truth validation

This is the core design decision behind the whole project: rather than
building fraud/pacing/AB-testing code and just *claiming* it works, the
synthetic data generator plants **known** anomalies (documented in
`data/ground_truth.json`) before any detection code ever sees the data.
Every number in the "Results at a glance" section above is a direct,
reproducible comparison against that answer key — not a subjective
assessment.

Specifically injected:
- 2 overpacing campaigns (125-150% of target spend), 2 underpacing (50-75%)
- A click-farm pattern: 25 clicks from one IP in a 2-minute window, repeated daily
- Bot traffic: elevated click volume with conversion rate held near zero
- Scripted clicks: a subsequence of clicks at exact 30-second intervals
- 3 campaigns with a genuine ~17-38% relative A/B lift; all others with no true effect

See [METHODOLOGY.md](METHODOLOGY.md) for the reasoning behind every
statistical method, threshold, and the real debugging lessons learned
building this (including a couple of genuine bugs caught by this
validation process, which is exactly the point of building it this way).

---

## Why this project

Structured to demonstrate the three named responsibilities in most
ad-ops / marketing-analytics job postings, using synthetic-but-realistic
data with a China-Africa cross-border e-commerce/logistics angle drawn
from prior portfolio work, rather than a generic Kaggle dataset writeup.
