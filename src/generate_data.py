"""
Synthetic data generator for the Ad Campaign Performance & Fraud Monitoring project.

This script creates 18 fake ad campaigns over a 60-day window, deliberately
injecting known pacing issues, fraud patterns, and A/B test effects. The "answer
key" for everything injected is written to data/ground_truth.json so the
detection modules built in later phases can be scored against known truth.
"""

import json
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from faker import Faker
from sqlalchemy import create_engine

fake = Faker()
Faker.seed(42)
random.seed(42)
np.random.seed(42)

# ---- CONFIG ----
N_CAMPAIGNS = 18
SIM_START_DATE = datetime(2025, 12, 1)
SIM_DAYS = 60
DB_PATH = "data/adops.db"
GROUND_TRUTH_PATH = "data/ground_truth.json"

OBJECTIVES = ["conversions", "awareness", "traffic"]
FORMATS = ["banner", "video", "native"]
DEVICE_TYPES = ["mobile", "desktop", "tablet"]


def generate_campaigns():
    campaigns = []
    pacing_behavior = {}
    for cid in range(1, N_CAMPAIGNS + 1):
        if cid in [1, 2]:
            pacing_behavior[cid] = "overpacing"
        elif cid in [3, 4]:
            pacing_behavior[cid] = "underpacing"
        else:
            pacing_behavior[cid] = "healthy"

    for cid in range(1, N_CAMPAIGNS + 1):
        start = SIM_START_DATE + timedelta(days=random.randint(0, 5))
        end = start + timedelta(days=SIM_DAYS - random.randint(0, 5))
        total_budget = round(random.uniform(5000, 50000), 2)
        daily_target = round(total_budget / SIM_DAYS, 2)

        campaigns.append({
            "campaign_id": cid,
            "campaign_name": f"{fake.bs().title()} Campaign",
            "advertiser": fake.company(),
            "start_date": start.date().isoformat(),
            "end_date": end.date().isoformat(),
            "total_budget": total_budget,
            "daily_budget_target": daily_target,
            "objective": random.choice(OBJECTIVES),
        })

    return pd.DataFrame(campaigns), pacing_behavior


def generate_daily_spend(campaigns_df, pacing_behavior):
    """
    Returns the daily_spend DataFrame AND a dict of true_cvr_by_campaign —
    the clean, un-truncated ground-truth conversion rate per campaign. This
    dict is passed directly into generate_click_events() so click-level
    conversion probabilities are never derived from daily_spend's rounded
    integer conversion counts, which suffer from int() truncation on
    low-volume days (e.g. 0.6 conversions truncating to 0).
    """
    rows = []
    true_cvr_by_campaign = {}

    for _, camp in campaigns_df.iterrows():
        cid = camp["campaign_id"]
        daily_target = camp["daily_budget_target"]
        behavior = pacing_behavior[cid]

        true_ctr = np.random.uniform(0.01, 0.04)
        # Floor raised to 0.03 (from 0.02) so low-click days truncate to 0
        # conversions less often in the daily_spend table (used for pacing/
        # CTR reporting only — NOT used for A/B click-level conversions).
        true_cvr = np.random.uniform(0.03, 0.07)
        true_cvr_by_campaign[cid] = true_cvr

        for day in range(SIM_DAYS):
            date = SIM_START_DATE + timedelta(days=day)

            if behavior == "overpacing":
                multiplier = np.random.uniform(1.25, 1.5)
            elif behavior == "underpacing":
                multiplier = np.random.uniform(0.5, 0.75)
            else:
                multiplier = np.random.uniform(0.9, 1.1)

            spend = round(daily_target * multiplier, 2)
            impressions = random.randint(400, 2500)
            clicks = int(impressions * true_ctr * np.random.uniform(0.85, 1.15))
            conversions = int(clicks * true_cvr * np.random.uniform(0.85, 1.15))

            rows.append({
                "campaign_id": cid,
                "date": date.date().isoformat(),
                "spend": spend,
                "impressions": impressions,
                "clicks": max(clicks, 1),
                "conversions": max(conversions, 0),
            })

    return pd.DataFrame(rows), true_cvr_by_campaign


def generate_creatives(campaigns_df):
    creatives = []
    creative_id = 1
    ab_effect_campaigns = [5, 6, 7]

    for _, camp in campaigns_df.iterrows():
        cid = camp["campaign_id"]
        for variant in ["A", "B"]:
            creatives.append({
                "creative_id": creative_id,
                "campaign_id": cid,
                "creative_name": f"{camp['campaign_name']} - Variant {variant}",
                "variant": variant,
                "format": random.choice(FORMATS),
                "launch_date": camp["start_date"],
            })
            creative_id += 1

    return pd.DataFrame(creatives), ab_effect_campaigns


def generate_click_events(campaigns_df, creatives_df, daily_spend_df, ab_effect_campaigns, true_cvr_by_campaign):
    """
    Generates click-level events. Injects three fraud patterns on purpose:
      - Campaign 8: click-farm (IP cluster within a 2-min window)
      - Campaign 9: bot traffic (high clicks, near-zero conversions)
      - Campaign 10: script-clicked (perfectly regular time intervals)

    Conversion probability per click is driven by true_cvr_by_campaign
    (clean ground truth), NOT by daily_spend's rounded conversion counts.
    For ab_effect campaigns [5, 6, 7], variant B gets a genuine 30%
    RELATIVE lift over variant A's base rate — large enough to reliably
    clear sampling noise across ~1,200 clicks/variant, but still a
    realistic effect size for a real-world A/B test.
    """
    events = []
    event_id = 1
    fraud_ground_truth = {
        "click_farm_campaign": 8,
        "bot_traffic_campaign": 9,
        "scripted_campaign": 10,
        "injected_fraud_ip": "203.0.113.77",
    }

    creative_lookup = {}
    for cid, group in creatives_df.groupby("campaign_id"):
        creative_lookup[cid] = dict(zip(group["variant"], group["creative_id"]))

    total_campaigns = daily_spend_df["campaign_id"].nunique()
    processed = 0
    last_printed_cid = None

    for _, spend_row in daily_spend_df.iterrows():
        cid = spend_row["campaign_id"]

        if cid != last_printed_cid:
            processed += 1
            print(f"  campaign {cid} ({processed}/{total_campaigns})...", flush=True)
            last_printed_cid = cid

        date = datetime.fromisoformat(spend_row["date"])
        n_clicks = int(spend_row["clicks"])

        variant_A_creative = creative_lookup[cid]["A"]
        variant_B_creative = creative_lookup[cid]["B"]

        base_cvr = true_cvr_by_campaign[cid]
        if cid in ab_effect_campaigns:
            p_A = base_cvr
            p_B = base_cvr * 1.30
        else:
            p_A = base_cvr
            p_B = base_cvr

        for i in range(n_clicks):
            variant = np.random.choice(["A", "B"])
            creative_id = variant_A_creative if variant == "A" else variant_B_creative

            ts = date + timedelta(seconds=random.randint(0, 86399))
            p_convert = p_A if variant == "A" else p_B
            is_conv = random.random() < p_convert

            events.append({
                "event_id": event_id,
                "campaign_id": cid,
                "creative_id": creative_id,
                "timestamp": ts.isoformat(),
                "ip_address": fake.ipv4(),
                "user_agent": fake.user_agent(),
                "device_type": random.choice(DEVICE_TYPES),
                "is_conversion": int(is_conv),
            })
            event_id += 1

        if cid == fraud_ground_truth["click_farm_campaign"]:
            farm_ip = fraud_ground_truth["injected_fraud_ip"]
            burst_start = date + timedelta(hours=random.randint(2, 20))
            for j in range(25):
                ts = burst_start + timedelta(seconds=random.randint(0, 120))
                events.append({
                    "event_id": event_id,
                    "campaign_id": cid,
                    "creative_id": variant_A_creative,
                    "timestamp": ts.isoformat(),
                    "ip_address": farm_ip,
                    "user_agent": fake.user_agent(),
                    "device_type": "mobile",
                    "is_conversion": 0,
                })
                event_id += 1

        if cid == fraud_ground_truth["bot_traffic_campaign"]:
            for j in range(80):
                ts = date + timedelta(seconds=random.randint(0, 86399))
                events.append({
                    "event_id": event_id,
                    "campaign_id": cid,
                    "creative_id": variant_A_creative,
                    "timestamp": ts.isoformat(),
                    "ip_address": fake.ipv4(),
                    "user_agent": fake.user_agent(),
                    "device_type": "mobile",
                    "is_conversion": 0,
                })
                event_id += 1

        if cid == fraud_ground_truth["scripted_campaign"]:
            script_start = date + timedelta(hours=random.randint(1, 10))
            for j in range(40):
                ts = script_start + timedelta(seconds=30 * j)
                events.append({
                    "event_id": event_id,
                    "campaign_id": cid,
                    "creative_id": variant_A_creative,
                    "timestamp": ts.isoformat(),
                    "ip_address": fake.ipv4(),
                    "user_agent": "Mozilla/5.0 (compatible; script)",
                    "device_type": "desktop",
                    "is_conversion": 0,
                })
                event_id += 1

    return pd.DataFrame(events), fraud_ground_truth


def generate_ab_assignments(campaigns_df, click_events_df):
    assignments = []
    subset = click_events_df[["campaign_id", "ip_address", "device_type", "timestamp"]].drop_duplicates()

    for _, row in subset.iterrows():
        user_id = fake.uuid4()
        variant = random.choice(["A", "B"])
        assignments.append({
            "user_id": user_id,
            "campaign_id": row["campaign_id"],
            "variant": variant,
            "assigned_at": row["timestamp"],
        })

    return pd.DataFrame(assignments)


def main():
    print("Generating campaigns...")
    campaigns_df, pacing_behavior = generate_campaigns()

    print("Generating daily spend...")
    daily_spend_df, true_cvr_by_campaign = generate_daily_spend(campaigns_df, pacing_behavior)

    print("Generating creatives...")
    creatives_df, ab_effect_campaigns = generate_creatives(campaigns_df)

    print("Generating click events (this includes fraud injection)...")
    click_events_df, fraud_ground_truth = generate_click_events(
        campaigns_df, creatives_df, daily_spend_df, ab_effect_campaigns, true_cvr_by_campaign
    )

    print("Generating A/B test assignments...")
    ab_assignments_df = generate_ab_assignments(campaigns_df, click_events_df)

    campaigns_df.to_csv("data/raw/campaigns.csv", index=False)
    creatives_df.to_csv("data/raw/creatives.csv", index=False)
    daily_spend_df.to_csv("data/raw/daily_spend.csv", index=False)
    click_events_df.to_csv("data/raw/click_events.csv", index=False)
    ab_assignments_df.to_csv("data/raw/ab_test_assignments.csv", index=False)

    engine = create_engine(f"sqlite:///{DB_PATH}")
    campaigns_df.to_sql("campaigns", engine, if_exists="replace", index=False)
    creatives_df.to_sql("creatives", engine, if_exists="replace", index=False)
    daily_spend_df.to_sql("daily_spend", engine, if_exists="replace", index=False)
    click_events_df.to_sql("click_events", engine, if_exists="replace", index=False)
    ab_assignments_df.to_sql("ab_test_assignments", engine, if_exists="replace", index=False)

    ground_truth = {
        "pacing_behavior": pacing_behavior,
        "ab_effect_campaigns": ab_effect_campaigns,
        "true_cvr_by_campaign": true_cvr_by_campaign,
        "fraud": fraud_ground_truth,
        "generated_at": datetime.now().isoformat(),
        "seed": 42,
    }
    with open(GROUND_TRUTH_PATH, "w") as f:
        json.dump(ground_truth, f, indent=2)

    print(f"\nDone. {len(campaigns_df)} campaigns, {len(click_events_df)} click events.")
    print(f"Ground truth written to {GROUND_TRUTH_PATH}")


if __name__ == "__main__":
    main()
