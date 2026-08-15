# A/B Testing Report

**Ground truth campaigns with a real injected effect:** [5, 6, 7]

**Excluded from analysis (known fraud-contaminated traffic):** [8, 9, 10] -- see fraud_report.md. Conversion-rate comparisons on contaminated traffic aren't trustworthy regardless of p-value; these campaigns should be re-tested after fraud is filtered from the underlying click data.

Significance level (alpha): 0.05 | Target power: 0.8 | Minimum detectable relative lift used for power sizing: 10% | Minimum meaningful relative lift required for a verdict: 5.0%

p-values are also reported after Benjamini-Hochberg correction for running multiple simultaneous per-campaign tests.

## Per-Campaign Results

| Campaign | A rate (n) | B rate (n) | Lift % | p-value | BH-corrected p | Power | Bayesian P(B>A) | Verdict |
|---|---|---|---|---|---|---|---|---|
| Whiteboard One-To-One Web-Readiness Campaign (ID 1) | 7.47% (n=870) | 6.29% (n=922) | -15.8% | 0.3232 | 0.58169 | 0.164 | 0.1633 | **UNDERPOWERED - inconclusive** |
| Innovate E-Business Applications Campaign (ID 2) | 7.04% (n=1548) | 7.17% (n=1548) | 1.8% | 0.88874 | 0.95222 | 0.052 | 0.5584 | **UNDERPOWERED - inconclusive** |
| Enhance Proactive Schemas Campaign (ID 3) | 5.55% (n=1621) | 4.96% (n=1633) | -10.7% | 0.44927 | 0.58271 | 0.118 | 0.2263 | **UNDERPOWERED - inconclusive** |
| Incubate Next-Generation E-Services Campaign (ID 4) | 5.62% (n=569) | 4.20% (n=500) | -25.3% | 0.28457 | 0.58169 | 0.181 | 0.1466 | **UNDERPOWERED - inconclusive** |
| Implement Granular E-Commerce Campaign (ID 5) | 3.19% (n=659) | 4.40% (n=614) | 38.0% | 0.25713 | 0.58169 | 0.2 | 0.8697 | **UNDERPOWERED - inconclusive** |
| Engineer Cross-Platform Platforms Campaign (ID 6) | 4.03% (n=1242) | 4.73% (n=1290) | 17.5% | 0.38779 | 0.58169 | 0.137 | 0.8054 | **UNDERPOWERED - inconclusive** |
| Iterate Cross-Media Metrics Campaign (ID 7) | 5.80% (n=1242) | 6.92% (n=1344) | 19.4% | 0.24325 | 0.58169 | 0.209 | 0.8788 | **UNDERPOWERED - inconclusive** |
| Synergize Efficient Bandwidth Campaign (ID 11) | 3.36% (n=655) | 2.50% (n=681) | -25.7% | 0.34921 | 0.58169 | 0.153 | 0.1771 | **UNDERPOWERED - inconclusive** |
| Repurpose Real-Time Methodologies Campaign (ID 12) | 3.57% (n=1654) | 5.04% (n=1766) | 41.3% | 0.03443 | 0.42585 | 0.553 | 0.9835 | **SIGNIFICANT WINNER (B)** |
| Incentivize Granular Bandwidth Campaign (ID 13) | 6.75% (n=1423) | 6.95% (n=1382) | 3.0% | 0.83377 | 0.95222 | 0.055 | 0.5857 | **UNDERPOWERED - inconclusive** |
| Scale Magnetic Methodologies Campaign (ID 14) | 7.03% (n=583) | 4.42% (n=566) | -37.2% | 0.05678 | 0.42585 | 0.479 | 0.0291 | **UNDERPOWERED - inconclusive** |
| Enhance Robust Vortals Campaign (ID 15) | 3.30% (n=970) | 4.06% (n=986) | 23.0% | 0.37349 | 0.58169 | 0.144 | 0.8102 | **UNDERPOWERED - inconclusive** |
| Maximize Turn-Key E-Tailers Campaign (ID 16) | 5.25% (n=1486) | 4.25% (n=1435) | -19.0% | 0.20524 | 0.58169 | 0.242 | 0.1046 | **UNDERPOWERED - inconclusive** |
| Orchestrate Back-End Channels Campaign (ID 17) | 7.81% (n=1267) | 7.04% (n=1179) | -9.9% | 0.46617 | 0.58271 | 0.111 | 0.235 | **UNDERPOWERED - inconclusive** |
| Morph Cutting-Edge Applications Campaign (ID 18) | 4.95% (n=727) | 4.89% (n=654) | -1.2% | 0.95972 | 0.95972 | 0.05 | 0.4836 | **UNDERPOWERED - inconclusive** |

## Confidence Intervals (Wilson score, 95%)

| Campaign | A: rate [CI] | B: rate [CI] |
|---|---|---|
| Whiteboard One-To-One Web-Readiness Campaign (ID 1) | 7.47% [5.90%, 9.41%] | 6.29% [4.90%, 8.05%] |
| Innovate E-Business Applications Campaign (ID 2) | 7.04% [5.87%, 8.43%] | 7.17% [5.99%, 8.56%] |
| Enhance Proactive Schemas Campaign (ID 3) | 5.55% [4.54%, 6.78%] | 4.96% [4.01%, 6.12%] |
| Incubate Next-Generation E-Services Campaign (ID 4) | 5.62% [4.01%, 7.83%] | 4.20% [2.76%, 6.34%] |
| Implement Granular E-Commerce Campaign (ID 5) | 3.19% [2.09%, 4.82%] | 4.40% [3.04%, 6.32%] |
| Engineer Cross-Platform Platforms Campaign (ID 6) | 4.03% [3.07%, 5.27%] | 4.73% [3.70%, 6.03%] |
| Iterate Cross-Media Metrics Campaign (ID 7) | 5.80% [4.63%, 7.24%] | 6.92% [5.68%, 8.40%] |
| Synergize Efficient Bandwidth Campaign (ID 11) | 3.36% [2.23%, 5.03%] | 2.50% [1.56%, 3.96%] |
| Repurpose Real-Time Methodologies Campaign (ID 12) | 3.57% [2.78%, 4.57%] | 5.04% [4.11%, 6.16%] |
| Incentivize Granular Bandwidth Campaign (ID 13) | 6.75% [5.56%, 8.17%] | 6.95% [5.72%, 8.41%] |
| Scale Magnetic Methodologies Campaign (ID 14) | 7.03% [5.23%, 9.40%] | 4.42% [3.01%, 6.44%] |
| Enhance Robust Vortals Campaign (ID 15) | 3.30% [2.35%, 4.62%] | 4.06% [2.99%, 5.48%] |
| Maximize Turn-Key E-Tailers Campaign (ID 16) | 5.25% [4.23%, 6.50%] | 4.25% [3.32%, 5.42%] |
| Orchestrate Back-End Channels Campaign (ID 17) | 7.81% [6.46%, 9.42%] | 7.04% [5.71%, 8.64%] |
| Morph Cutting-Edge Applications Campaign (ID 18) | 4.95% [3.60%, 6.78%] | 4.89% [3.49%, 6.83%] |

## Sequential Testing / Peeking Problem Demonstration

Simulated 500 A/B tests where both arms have the SAME true conversion rate (5%) -- i.e. there is truly NO effect. Compared two stopping rules over 30 days of accumulating data:

- **Pre-committed (check once, at the end):** false positive rate = 4.0% (expected ~5%, matches theory)
- **Peek daily (stop the moment p < 0.05 is EVER seen):** false positive rate = 25.4%

Checking significance every day and stopping at the first 'win' inflates the false positive rate well above the nominal 5% alpha.