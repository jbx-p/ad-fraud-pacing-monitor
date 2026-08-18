"""
Exports flat, dashboard-ready CSVs for the Tableau dashboard (Phase 6).
Pulls from adops.db + the ground truth + already-computed report data,
pre-joining everything so Tableau needs zero live SQL logic -- just
drag-and-drop fields onto shelves.

Run directly: python src/export_dashboard_data.py
Outputs: dashboard/data/*.csv
"""

import json
import os

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import create_engine, text

DB_PATH = "data/adops.db"
GROUND_TRUTH_PATH = "data/ground_truth.json"
OUT_DIR = "dashboard/data"

os.makedirs(OUT_DIR, exist_ok=True)


def export_pacing_data(engine, ground_truth):
    with open("sql/queries/daily_pacing.sql") as f:
        sql = f.read()
    df = pd.read_sql(text(sql), engine)

    def band(pct):
        if pct > 115:
            return "Overpacing"
        elif pct < 85:
            return "Underpacing"
        return "Healthy"

    df["health_band"] = df["pacing_pct"].apply(band)
    df["is_ground_truth_flagged"] = df["campaign_id"].astype(str).isin(
        [str(k) for k, v in ground_truth["pacing_behavior"].items() if v != "healthy"]
    )

    df.to_csv(f"{OUT_DIR}/pacing_daily.csv", index=False)
    print(f"  pacing_daily.csv: {len(df)} rows")

    # Latest-day summary for KPI cards / urgency table
    latest = df.sort_values("date").groupby("campaign_id").tail(1).copy()
    latest = latest.sort_values("pacing_pct", ascending=False)
    latest.to_csv(f"{OUT_DIR}/pacing_latest_summary.csv", index=False)
    print(f"  pacing_latest_summary.csv: {len(latest)} rows")


def export_fraud_data(engine, ground_truth):
    click_events = pd.read_sql(text("SELECT * FROM click_events"), engine)
    click_events["timestamp"] = pd.to_datetime(click_events["timestamp"])
    click_events["hour"] = click_events["timestamp"].dt.hour
    click_events["date"] = click_events["timestamp"].dt.date.astype(str)

    campaigns = pd.read_sql(text("SELECT campaign_id, campaign_name FROM campaigns"), engine)

    fraud_ids = {
        ground_truth["fraud"]["click_farm_campaign"],
        ground_truth["fraud"]["bot_traffic_campaign"],
        ground_truth["fraud"]["scripted_campaign"],
    }

    # Heatmap: click volume by campaign x hour-of-day
    heatmap = click_events.groupby(["campaign_id", "hour"]).size().reset_index(name="click_count")
    heatmap = heatmap.merge(campaigns, on="campaign_id")
    heatmap["is_fraud_campaign"] = heatmap["campaign_id"].isin(fraud_ids)
    heatmap.to_csv(f"{OUT_DIR}/fraud_heatmap.csv", index=False)
    print(f"  fraud_heatmap.csv: {len(heatmap)} rows")

    # Top flagged IPs (click velocity signal)
    with open("sql/queries/click_velocity.sql") as f:
        sql = f.read()
    velocity_df = pd.read_sql(text(sql), engine)
    velocity_df = velocity_df.merge(campaigns, on="campaign_id")
    velocity_df.to_csv(f"{OUT_DIR}/fraud_flagged_ips.csv", index=False)
    print(f"  fraud_flagged_ips.csv: {len(velocity_df)} rows")

    # Precision/recall summary (hardcoded from validated Phase 4 results --
    # these are the FINAL scored numbers from fraud_detection.py's output)
    precision_recall = pd.DataFrame([
        {"method": "Rule-based (combined)", "precision": 1.00, "recall": 1.00, "f1": 1.00},
        {"method": "Poisson hourly", "precision": 1.00, "recall": 0.67, "f1": 0.80},
        {"method": "Interval regularity", "precision": 1.00, "recall": 0.33, "f1": 0.50},
        {"method": "Isolation Forest", "precision": 1.00, "recall": 0.33, "f1": 0.50},
    ])
    precision_recall.to_csv(f"{OUT_DIR}/fraud_precision_recall.csv", index=False)
    print(f"  fraud_precision_recall.csv: {len(precision_recall)} rows")


def export_ab_verdicts():
    """
    Re-runs the core A/B analysis (power, z-test, BH correction, min-lift
    gate) and exports one row per non-fraud campaign with verdict, p-value,
    and achieved power -- the fields the dashboard's verdict table needs
    that aren't in the raw variant_performance query output.
    """
    import subprocess
    import sys

    # Reuse ab_testing.py's own functions directly instead of re-implementing
    sys.path.insert(0, "src")
    import ab_testing as abt

    variant_df, _ = abt.load_variant_data()
    with open(GROUND_TRUTH_PATH) as f:
        ground_truth = json.load(f)

    true_effect_campaigns = set(ground_truth["ab_effect_campaigns"])
    fraud_campaign_ids = {
        ground_truth["fraud"]["click_farm_campaign"],
        ground_truth["fraud"]["bot_traffic_campaign"],
        ground_truth["fraud"]["scripted_campaign"],
    }

    campaigns = variant_df[["campaign_id", "campaign_name"]].drop_duplicates()
    campaigns = campaigns[~campaigns["campaign_id"].isin(fraud_campaign_ids)]

    results = []
    for _, camp in campaigns.iterrows():
        r = abt.analyze_campaign(camp["campaign_id"], camp["campaign_name"], variant_df)
        if r:
            results.append(r)

    pvals = [r["p_value"] for r in results]
    from statsmodels.stats.multitest import multipletests
    reject, pvals_corrected, _, _ = multipletests(pvals, alpha=abt.ALPHA, method="fdr_bh")
    for r, rej, p_corr in zip(results, reject, pvals_corrected):
        r["p_value_bh_corrected"] = round(p_corr, 5)
        r["significant_after_correction"] = bool(rej)
        r["ground_truth_real_effect"] = r["campaign_id"] in true_effect_campaigns

    out_df = pd.DataFrame(results)[[
        "campaign_id", "campaign_name", "rate_A", "rate_B",
        "relative_lift_pct", "p_value", "p_value_bh_corrected",
        "achieved_power", "verdict", "ground_truth_real_effect",
    ]]
    out_df.to_csv(f"{OUT_DIR}/ab_verdicts.csv", index=False)
    print(f"  ab_verdicts.csv: {len(out_df)} rows")


def export_ab_data(engine, ground_truth):
    with open("sql/queries/variant_performance.sql") as f:
        sql = f.read()
    df = pd.read_sql(text(sql), engine)

    fraud_ids = {
        ground_truth["fraud"]["click_farm_campaign"],
        ground_truth["fraud"]["bot_traffic_campaign"],
        ground_truth["fraud"]["scripted_campaign"],
    }
    df = df[~df["campaign_id"].isin(fraud_ids)].copy()

    # Wilson CI per row, for error bars in Tableau
    def wilson_bounds(row):
        n = row["total_clicks"]
        conv = row["total_conversions"]
        if n == 0:
            return pd.Series([0.0, 0.0])
        low, high = stats.beta.ppf(
            [0.025, 0.975],
            [conv + 0.5, conv + 0.5],
            [n - conv + 0.5, n - conv + 0.5],
        ) if False else (None, None)
        # Use statsmodels-equivalent Wilson formula directly for portability:
        z = 1.96
        phat = conv / n
        denom = 1 + z**2 / n
        center = (phat + z**2 / (2 * n)) / denom
        margin = (z * np.sqrt((phat * (1 - phat) + z**2 / (4 * n)) / n)) / denom
        return pd.Series([max(center - margin, 0), min(center + margin, 1)])

    df[["ci_low", "ci_high"]] = df.apply(wilson_bounds, axis=1)
    df["ground_truth_real_effect"] = df["campaign_id"].isin(ground_truth["ab_effect_campaigns"])

    df.to_csv(f"{OUT_DIR}/ab_variant_performance.csv", index=False)
    print(f"  ab_variant_performance.csv: {len(df)} rows")


def main():
    engine = create_engine(f"sqlite:///{DB_PATH}")
    with open(GROUND_TRUTH_PATH) as f:
        ground_truth = json.load(f)

    print("Exporting pacing data...")
    export_pacing_data(engine, ground_truth)

    print("Exporting fraud data...")
    export_fraud_data(engine, ground_truth)

    print("Exporting A/B test data...")
    export_ab_data(engine, ground_truth)
    export_ab_verdicts()

    print(f"\nAll dashboard CSVs written to {OUT_DIR}/")


if __name__ == "__main__":
    main()
