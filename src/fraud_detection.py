"""
Fraud & anomaly detection module.

Three layers of increasing sophistication:
  1. Rule-based signals (click velocity, CTR outliers, conversion-free clicks)
  2. Statistical anomaly detection (Poisson hourly modeling, sliding-window
     click-interval regularity scan)
  3. ML-based detection (Isolation Forest)

Each layer's flagged campaigns are scored against data/ground_truth.json's
known-injected fraud campaigns (precision/recall/F1), so the module proves
it actually works rather than just claiming to.

Run directly: python src/fraud_detection.py
Outputs: reports/fraud_report.md
"""

import json
import os

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import IsolationForest
from sqlalchemy import create_engine, text

DB_PATH = "data/adops.db"
GROUND_TRUTH_PATH = "data/ground_truth.json"
REPORT_PATH = "reports/fraud_report.md"
CLICK_VELOCITY_SQL = "sql/queries/click_velocity.sql"

# ---- Thresholds (documented, not hardcoded silently) ----
CTR_ZSCORE_THRESHOLD = 3.0
CONVERSION_FREE_MIN_CLICKS = 50
CONVERSION_FREE_ALPHA = 0.01
CONVERSION_FREE_RATIO_THRESHOLD = 0.5

POISSON_PERCENTILE = 0.99
# A campaign is flagged only if its count of anomalous hours is a
# meaningful OUTLIER relative to other campaigns' counts (z-score across
# campaigns), not merely "had at least one anomalous hour" -- at 1440
# observed hours per campaign, ~14 hours will cross a 99th-percentile
# threshold in EVERY campaign by chance alone, so that naive rule flags
# almost everyone. Comparing counts across campaigns filters out that
# expected statistical noise floor.
CAMPAIGN_ANOMALY_ZSCORE_THRESHOLD = 1.5

# Sliding-window scan for click-interval regularity: rather than one CV
# across a campaign's ENTIRE click history (which dilutes a small
# embedded regular subsequence into meaninglessness), scan windows of
# INTERVAL_WINDOW_SIZE consecutive clicks and flag the campaign if ANY
# window's CV falls below INTERVAL_CV_THRESHOLD. This finds a scripted
# burst hiding inside otherwise-normal traffic.
INTERVAL_WINDOW_SIZE = 10
INTERVAL_CV_THRESHOLD = 0.05

ISOLATION_FOREST_CONTAMINATION = 0.05


def load_data():
    engine = create_engine(f"sqlite:///{DB_PATH}")
    click_events = pd.read_sql(text("SELECT * FROM click_events"), engine)
    click_events["timestamp"] = pd.to_datetime(click_events["timestamp"])
    daily_spend = pd.read_sql(text("SELECT * FROM daily_spend"), engine)
    campaigns = pd.read_sql(text("SELECT * FROM campaigns"), engine)

    with open(GROUND_TRUTH_PATH) as f:
        ground_truth = json.load(f)

    return click_events, daily_spend, campaigns, ground_truth, engine


# =========================================================
# LAYER 1: RULE-BASED SIGNALS
# =========================================================

def rule_click_velocity(engine):
    """
    Reuses click_velocity.sql. Returns the set of campaign_ids that have
    at least one IP exceeding the 5-clicks-in-5-minutes threshold.
    """
    with open(CLICK_VELOCITY_SQL) as f:
        sql = f.read()
    df = pd.read_sql(text(sql), engine)
    flagged_campaigns = set(df["campaign_id"].unique())
    return flagged_campaigns, df


def rule_ctr_outliers(click_events, daily_spend, campaigns):
    """
    Actual CTR computed from click_events (which includes injected fraud
    clicks) joined against daily_spend's impressions. daily_spend's own
    'clicks' column is generated independently in Phase 1 and does NOT
    include fraud-injected clicks -- using it here would make this rule
    structurally blind to fraud regardless of threshold.

    z-scored within each day across campaigns; anything more than
    CTR_ZSCORE_THRESHOLD standard deviations above that day's
    cross-campaign mean CTR is flagged.
    """
    ce = click_events.copy()
    ce["date"] = ce["timestamp"].dt.date.astype(str)
    daily_actual_clicks = ce.groupby(["campaign_id", "date"]).size().reset_index(name="actual_clicks")

    df = daily_spend[["campaign_id", "date", "impressions"]].merge(
        daily_actual_clicks, on=["campaign_id", "date"], how="left"
    )
    df["actual_clicks"] = df["actual_clicks"].fillna(0)
    df["ctr"] = df["actual_clicks"] / df["impressions"].replace(0, np.nan)

    daily_stats = df.groupby("date")["ctr"].agg(["mean", "std"]).rename(
        columns={"mean": "daily_mean_ctr", "std": "daily_std_ctr"}
    )
    df = df.join(daily_stats, on="date")
    df["ctr_zscore"] = (df["ctr"] - df["daily_mean_ctr"]) / df["daily_std_ctr"].replace(0, np.nan)

    outliers = df[df["ctr_zscore"] > CTR_ZSCORE_THRESHOLD]
    flagged_campaigns = set(outliers["campaign_id"].unique())
    return flagged_campaigns, outliers


def rule_conversion_free_clicks(click_events, campaigns):
    """
    Binomial test per campaign: is the observed conversion rate
    statistically indistinguishable from zero, given a large click sample?
    """
    campaign_stats = click_events.groupby("campaign_id").agg(
        total_clicks=("event_id", "count"),
        total_conversions=("is_conversion", "sum"),
    ).reset_index()
    campaign_stats["observed_cvr"] = campaign_stats["total_conversions"] / campaign_stats["total_clicks"]

    overall_cvr = click_events["is_conversion"].mean()

    flagged = []
    for _, row in campaign_stats.iterrows():
        if row["total_clicks"] < CONVERSION_FREE_MIN_CLICKS:
            continue
        result = stats.binomtest(
            int(row["total_conversions"]), int(row["total_clicks"]),
            p=overall_cvr, alternative="less"
        )
        if result.pvalue < CONVERSION_FREE_ALPHA and row["observed_cvr"] < overall_cvr * CONVERSION_FREE_RATIO_THRESHOLD:
            flagged.append(row["campaign_id"])

    flagged_campaigns = set(flagged)
    return flagged_campaigns, campaign_stats


# =========================================================
# LAYER 2: STATISTICAL ANOMALY DETECTION
# =========================================================

def poisson_hourly_anomalies(click_events):
    """
    Models expected clicks-per-hour per campaign as a Poisson process.
    Fits lambda from the campaign's own hourly click counts, flags hours
    exceeding the 99th percentile of that fitted distribution, THEN
    z-scores each campaign's total anomalous-hour COUNT against its peers
    -- flagging only campaigns with meaningfully more anomalous hours
    than expected by chance, not merely "had one."
    """
    df = click_events.copy()
    df["date_hour"] = df["timestamp"].dt.floor("h")
    hourly_counts = df.groupby(["campaign_id", "date_hour"]).size().reset_index(name="click_count")

    campaign_summary = []
    for cid, group in hourly_counts.groupby("campaign_id"):
        lam = group["click_count"].mean()
        threshold = stats.poisson.ppf(POISSON_PERCENTILE, lam)
        anomalous_count = (group["click_count"] > threshold).sum()
        campaign_summary.append({
            "campaign_id": cid,
            "total_hours_observed": len(group),
            "anomalous_hour_count": int(anomalous_count),
            "poisson_lambda": round(lam, 2),
        })

    summary_df = pd.DataFrame(campaign_summary)
    mean_count = summary_df["anomalous_hour_count"].mean()
    std_count = summary_df["anomalous_hour_count"].std()
    summary_df["zscore"] = (
        (summary_df["anomalous_hour_count"] - mean_count) / std_count if std_count > 0 else 0
    )

    flagged = summary_df[summary_df["zscore"] > CAMPAIGN_ANOMALY_ZSCORE_THRESHOLD]
    flagged_campaigns = set(flagged["campaign_id"])
    return flagged_campaigns, summary_df.sort_values("anomalous_hour_count", ascending=False)


def click_interval_regularity(click_events):
    """
    Sliding-window scan for embedded regular-interval subsequences.

    A global CV across a campaign's entire click history dilutes a small
    scripted burst (e.g. 40 exact-30-second clicks) into meaninglessness
    when surrounded by tens of thousands of normally-timed clicks. Instead,
    this scans a rolling window of INTERVAL_WINDOW_SIZE consecutive
    inter-click intervals and looks for the MINIMUM coefficient of
    variation found anywhere in that scan -- if any window is
    near-perfectly regular (CV close to 0), that's the scripted subsequence
    revealing itself, regardless of how much normal traffic surrounds it.
    """
    df = click_events.sort_values(["campaign_id", "timestamp"]).copy()
    df["prev_ts"] = df.groupby("campaign_id")["timestamp"].shift(1)
    df["interval_sec"] = (df["timestamp"] - df["prev_ts"]).dt.total_seconds()

    results = []
    flagged_campaigns = set()

    for cid, group in df.groupby("campaign_id"):
        intervals = group["interval_sec"].dropna()
        intervals = intervals[intervals > 0].reset_index(drop=True)
        if len(intervals) < INTERVAL_WINDOW_SIZE:
            continue

        rolling_mean = intervals.rolling(INTERVAL_WINDOW_SIZE).mean()
        rolling_std = intervals.rolling(INTERVAL_WINDOW_SIZE).std()
        rolling_cv = rolling_std / rolling_mean

        min_cv = rolling_cv.min()
        min_cv_idx = rolling_cv.idxmin() if not pd.isna(min_cv) else None
        window_mean_at_min = rolling_mean.iloc[min_cv_idx] if min_cv_idx is not None else None

        results.append({
            "campaign_id": cid,
            "n_intervals": len(intervals),
            "min_rolling_cv": round(min_cv, 4) if not pd.isna(min_cv) else None,
            "interval_sec_at_min_cv": round(window_mean_at_min, 1) if window_mean_at_min is not None else None,
        })

        if not pd.isna(min_cv) and min_cv < INTERVAL_CV_THRESHOLD:
            flagged_campaigns.add(cid)

    results_df = pd.DataFrame(results).sort_values("min_rolling_cv")
    return flagged_campaigns, results_df


# =========================================================
# LAYER 3: ML-BASED DETECTION (ISOLATION FOREST)
# =========================================================

def build_hourly_features(click_events):
    """
    Builds one row per (campaign_id, date_hour) with the feature set used
    by Isolation Forest: click count, unique IP ratio, avg inter-click
    interval, device diversity, conversion rate.
    """
    df = click_events.sort_values(["campaign_id", "timestamp"]).copy()
    df["date_hour"] = df["timestamp"].dt.floor("h")
    df["prev_ts"] = df.groupby("campaign_id")["timestamp"].shift(1)
    df["interval_sec"] = (df["timestamp"] - df["prev_ts"]).dt.total_seconds()

    features = df.groupby(["campaign_id", "date_hour"]).agg(
        click_count=("event_id", "count"),
        unique_ips=("ip_address", "nunique"),
        unique_devices=("device_type", "nunique"),
        avg_interval_sec=("interval_sec", "mean"),
        conversion_rate=("is_conversion", "mean"),
    ).reset_index()

    features["unique_ip_ratio"] = features["unique_ips"] / features["click_count"]
    features["device_diversity"] = features["unique_devices"] / features["click_count"]
    features["avg_interval_sec"] = features["avg_interval_sec"].fillna(features["avg_interval_sec"].median())

    return features


def isolation_forest_anomalies(features):
    """
    Fits Isolation Forest on the hourly feature set. Rather than flagging
    any campaign that merely CONTAINS one anomalous hour (which, at
    contamination=0.05 across ~1400 hours/campaign, ends up touching
    nearly every campaign), this aggregates to a per-campaign anomaly
    RATE and z-scores that rate across campaigns -- flagging only
    campaigns with a meaningfully higher concentration of anomalous
    hours than their peers.
    """
    
    # Filter out near-empty hours before fitting -- hours with very few
    # clicks produce extreme, noisy ratio features (e.g. 1 click implies
    # unique_ip_ratio=1.0 trivially) that dominate an unsupervised
    # distance-based model without reflecting genuine anomalous behavior.
    MIN_CLICKS_FOR_ML = 5
    features = features[features["click_count"] >= MIN_CLICKS_FOR_ML].copy()

    feature_cols = ["click_count", "unique_ip_ratio", "avg_interval_sec", "device_diversity", "conversion_rate"]
    X = features[feature_cols].fillna(0)

    model = IsolationForest(
        contamination=ISOLATION_FOREST_CONTAMINATION,
        random_state=42,
        n_estimators=200,
    )
    features = features.copy()
    features["anomaly_flag"] = model.fit_predict(X)
    features["anomaly_score_raw"] = model.decision_function(X)

    campaign_summary = features.groupby("campaign_id").agg(
        total_hours=("anomaly_flag", "count"),
        anomalous_hours=("anomaly_flag", lambda x: (x == -1).sum()),
    ).reset_index()
    campaign_summary["anomaly_rate"] = campaign_summary["anomalous_hours"] / campaign_summary["total_hours"]

    mean_rate = campaign_summary["anomaly_rate"].mean()
    std_rate = campaign_summary["anomaly_rate"].std()
    campaign_summary["zscore"] = (
        (campaign_summary["anomaly_rate"] - mean_rate) / std_rate if std_rate > 0 else 0
    )

    flagged = campaign_summary[campaign_summary["zscore"] > CAMPAIGN_ANOMALY_ZSCORE_THRESHOLD]
    flagged_campaigns = set(flagged["campaign_id"])
    return flagged_campaigns, campaign_summary.sort_values("anomalous_hours", ascending=False)


# =========================================================
# VALIDATION AGAINST GROUND TRUTH
# =========================================================

def score_method(flagged_campaigns, true_fraud_campaigns):
    flagged_campaigns = set(int(c) for c in flagged_campaigns)
    true_fraud_campaigns = set(int(c) for c in true_fraud_campaigns)

    tp = len(flagged_campaigns & true_fraud_campaigns)
    fp = len(flagged_campaigns - true_fraud_campaigns)
    fn = len(true_fraud_campaigns - flagged_campaigns)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "flagged": sorted(flagged_campaigns),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
    }


# =========================================================
# REPORT GENERATION
# =========================================================

def generate_report(results, true_fraud_campaigns):
    lines = []
    lines.append("# Fraud & Anomaly Detection Report\n")
    lines.append(f"**Ground truth injected fraud campaigns:** {sorted(true_fraud_campaigns)}\n")

    lines.append("## Validation Summary (Precision / Recall / F1)\n")
    lines.append("| Method | Flagged Campaigns | TP | FP | FN | Precision | Recall | F1 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for method_name, r in results.items():
        lines.append(
            f"| {method_name} | {r['flagged']} | {r['true_positives']} | {r['false_positives']} "
            f"| {r['false_negatives']} | {r['precision']} | {r['recall']} | {r['f1']} |"
        )

    lines.append("\n## Method Notes\n")
    lines.append("- **Rule-based:** click velocity (IP burst detection) + CTR z-score outliers + binomial test for conversion-free click campaigns.")
    lines.append("- **Poisson hourly:** per-campaign hourly click counts fitted to a Poisson distribution; campaigns flagged when their COUNT of 99th-percentile-exceeding hours is a z-score outlier relative to peer campaigns (not merely 'had one').")
    lines.append("- **Interval regularity:** sliding-window scan (window=10 consecutive clicks) for an embedded near-perfectly-regular interval subsequence, which survives even when a scripted burst is a small fraction of a campaign's total traffic.")
    lines.append("- **Isolation Forest:** unsupervised ML on 5 engineered hourly features; campaigns flagged when their RATE of anomalous hours is a z-score outlier relative to peer campaigns.")
    lines.append("\nNote: injected fraud in this dataset is MIXED with legitimate traffic on the same campaigns, not the campaign's only traffic -- a realistic constraint that dilutes naive signals and motivated the campaign-level aggregation approach used above.")

    os.makedirs("reports", exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(lines))


def main():
    print("Loading data...")
    click_events, daily_spend, campaigns, ground_truth, engine = load_data()

    true_fraud_campaigns = {
        ground_truth["fraud"]["click_farm_campaign"],
        ground_truth["fraud"]["bot_traffic_campaign"],
        ground_truth["fraud"]["scripted_campaign"],
    }
    print(f"Ground truth fraud campaigns: {sorted(true_fraud_campaigns)}")

    print("\n--- Layer 1: Rule-based signals ---")
    velocity_flagged, velocity_df = rule_click_velocity(engine)
    print(f"Click velocity flagged: {sorted(velocity_flagged)}")

    ctr_flagged, ctr_df = rule_ctr_outliers(click_events, daily_spend, campaigns)
    print(f"CTR outlier flagged: {sorted(ctr_flagged)}")

    convfree_flagged, convfree_df = rule_conversion_free_clicks(click_events, campaigns)
    print(f"Conversion-free flagged: {sorted(convfree_flagged)}")
    print(convfree_df.sort_values("observed_cvr").to_string(index=False))

    rule_based_flagged = velocity_flagged | ctr_flagged | convfree_flagged

    print("\n--- Layer 2: Statistical anomaly detection ---")
    poisson_flagged, poisson_df = poisson_hourly_anomalies(click_events)
    print(f"Poisson hourly flagged: {sorted(poisson_flagged)}")
    print(poisson_df.to_string(index=False))

    interval_flagged, interval_df = click_interval_regularity(click_events)
    print(f"\nInterval regularity flagged: {sorted(interval_flagged)}")
    print(interval_df.to_string(index=False))

    print("\n--- Layer 3: Isolation Forest ---")
    features = build_hourly_features(click_events)
    iso_flagged, iso_df = isolation_forest_anomalies(features)
    print(f"Isolation Forest flagged: {sorted(iso_flagged)}")
    print(iso_df.to_string(index=False))

    print("\n--- Validation against ground truth ---")
    results = {
        "Rule-based (combined)": score_method(rule_based_flagged, true_fraud_campaigns),
        "Poisson hourly": score_method(poisson_flagged, true_fraud_campaigns),
        "Interval regularity": score_method(interval_flagged, true_fraud_campaigns),
        "Isolation Forest": score_method(iso_flagged, true_fraud_campaigns),
    }

    for method, r in results.items():
        print(f"{method:25s} precision={r['precision']:.2f} recall={r['recall']:.2f} f1={r['f1']:.2f} flagged={r['flagged']}")

    print("\nGenerating report...")
    generate_report(results, true_fraud_campaigns)
    print(f"Report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
