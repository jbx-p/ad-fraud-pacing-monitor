"""
Pacing health check module.

Classifies each campaign-day into overpacing / healthy / underpacing bands,
projects days-to-budget-exhaustion, and flags campaigns trending toward a
band boundary before they cross it. Consumes sql/queries/daily_pacing.sql.

Run directly: python src/pacing.py
Outputs: reports/pacing_report.md + reports/charts/pacing_<campaign_id>.png
for every campaign currently flagged overpacing or underpacing.
"""

import os

import matplotlib
matplotlib.use("Agg")  # no GUI backend needed, we are only saving files
import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import create_engine, text

DB_PATH = "data/adops.db"
SQL_PATH = "sql/queries/daily_pacing.sql"
REPORT_PATH = "reports/pacing_report.md"
CHARTS_DIR = "reports/charts"

# ---- Configurable health bands ----
OVERPACING_THRESHOLD = 115.0
UNDERPACING_THRESHOLD = 85.0

# How many trailing days to average for the run-rate used in the
# days-to-exhaustion projection. 3 days smooths out single-day spend
# spikes/dips without reacting too slowly to a real trend change.
RUN_RATE_WINDOW = 3

# How many consecutive days a campaign must move toward a boundary
# before we call it a "trend" worth flagging early.
TREND_WINDOW = 3


def load_pacing_data():
    engine = create_engine(f"sqlite:///{DB_PATH}")
    with open(SQL_PATH, "r") as f:
        sql = f.read()
    return pd.read_sql(text(sql), engine)


def classify_band(pacing_pct):
    if pacing_pct > OVERPACING_THRESHOLD:
        return "overpacing"
    elif pacing_pct < UNDERPACING_THRESHOLD:
        return "underpacing"
    else:
        return "healthy"


def add_health_bands(df):
    df = df.copy()
    df["health_band"] = df["pacing_pct"].apply(classify_band)
    return df


def compute_days_to_exhaustion(df):
    """
    For each campaign, on its MOST RECENT day, project days remaining
    until total_budget is hit, using the average daily spend over the
    last RUN_RATE_WINDOW days as the run-rate.

    days_to_exhaustion = (total_budget - cum_spend) / avg_recent_daily_spend

    A negative or infinite result (avg_recent_daily_spend == 0) is
    reported as "N/A" rather than crashing or showing a nonsense number.
    """
    results = []
    for cid, group in df.groupby("campaign_id"):
        group = group.sort_values("date")
        latest = group.iloc[-1]

        recent = group.tail(RUN_RATE_WINDOW)
        avg_daily_spend = recent["daily_spend"].mean()

        remaining_budget = latest["total_budget"] - latest["cum_spend"]

        if avg_daily_spend > 0:
            days_left = remaining_budget / avg_daily_spend
        else:
            days_left = float("inf")

        results.append({
            "campaign_id": cid,
            "campaign_name": latest["campaign_name"],
            "latest_date": latest["date"],
            "latest_pacing_pct": latest["pacing_pct"],
            "health_band": latest["health_band"],
            "cum_spend": latest["cum_spend"],
            "total_budget": latest["total_budget"],
            "avg_recent_daily_spend": round(avg_daily_spend, 2),
            "days_to_exhaustion": round(days_left, 1) if days_left != float("inf") else None,
        })

    return pd.DataFrame(results)


def detect_trend(df):
    """
    Flags a campaign if, over its last TREND_WINDOW days, pacing_pct moved
    consistently in one direction (monotonically increasing OR decreasing),
    which signals it's heading toward a band boundary even if it hasn't
    crossed yet. This is what makes the module "monitoring" rather than
    just a snapshot report.
    """
    trend_flags = {}
    for cid, group in df.groupby("campaign_id"):
        group = group.sort_values("date")
        recent = group.tail(TREND_WINDOW)["pacing_pct"].tolist()

        if len(recent) < TREND_WINDOW:
            trend_flags[cid] = "insufficient_data"
            continue

        increasing = all(recent[i] < recent[i + 1] for i in range(len(recent) - 1))
        decreasing = all(recent[i] > recent[i + 1] for i in range(len(recent) - 1))

        if increasing:
            trend_flags[cid] = "trending_up"
        elif decreasing:
            trend_flags[cid] = "trending_down"
        else:
            trend_flags[cid] = "stable"

    return trend_flags


def severity_rank(row):
    """
    Lower value = more urgent. Used to sort the report so the worst
    problems appear first. Overpacing and underpacing both rank ahead of
    healthy; within each band, further from the healthy range is worse.
    """
    if row["health_band"] == "overpacing":
        return -abs(row["latest_pacing_pct"] - OVERPACING_THRESHOLD) - 1000
    elif row["health_band"] == "underpacing":
        return -abs(UNDERPACING_THRESHOLD - row["latest_pacing_pct"]) - 1000
    else:
        return 0


def generate_chart(campaign_id, campaign_name, df):
    """
    Actual vs. expected cumulative spend line chart for one campaign.
    Saved to reports/charts/pacing_<campaign_id>.png

    Uses day_number (Day 1, Day 2, ...) on the x-axis instead of raw
    calendar dates -- 60 individual date-string ticks were unreadable.
    Only every 5th day is labeled to keep the axis clean.
    """
    group = df[df["campaign_id"] == campaign_id].sort_values("day_number")

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(group["day_number"], group["cum_spend"], label="Actual cumulative spend", linewidth=2)
    ax.plot(group["day_number"], group["expected_cum_spend"], label="Expected cumulative spend", linestyle="--", linewidth=2)
    ax.set_title(f"Pacing: {campaign_name} (Campaign {campaign_id})")
    ax.set_xlabel("Day of Campaign")
    ax.set_ylabel("Cumulative Spend ($)")
    ax.legend()

    # Label every 5th day only, so the x-axis stays readable
    max_day = int(group["day_number"].max())
    tick_step = 5
    ax.set_xticks(range(0, max_day + 1, tick_step))

    fig.tight_layout()

    os.makedirs(CHARTS_DIR, exist_ok=True)
    out_path = f"{CHARTS_DIR}/pacing_{campaign_id}.png"
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def generate_report(summary_df, trend_flags, raw_df):
    """
    Writes reports/pacing_report.md, ranked by severity (worst first),
    and generates a chart for every campaign NOT in the healthy band.
    """
    summary_df = summary_df.copy()
    summary_df["trend"] = summary_df["campaign_id"].map(trend_flags)
    summary_df["severity"] = summary_df.apply(severity_rank, axis=1)
    summary_df = summary_df.sort_values("severity")

    lines = []
    lines.append("# Pacing Health Report\n")
    lines.append(f"Generated from {raw_df['date'].max()} snapshot ({len(summary_df)} campaigns)\n")

    flagged = summary_df[summary_df["health_band"] != "healthy"]
    healthy = summary_df[summary_df["health_band"] == "healthy"]

    lines.append(f"## Summary\n")
    lines.append(f"- **Overpacing:** {(summary_df['health_band'] == 'overpacing').sum()} campaigns")
    lines.append(f"- **Underpacing:** {(summary_df['health_band'] == 'underpacing').sum()} campaigns")
    lines.append(f"- **Healthy:** {(summary_df['health_band'] == 'healthy').sum()} campaigns\n")

    lines.append("## Flagged Campaigns (ranked by severity)\n")
    lines.append("| Campaign | Band | Pacing % | Trend | Days to Exhaustion | Spend / Budget |")
    lines.append("|---|---|---|---|---|---|")

    chart_paths = []
    for _, row in flagged.iterrows():
        dte = row["days_to_exhaustion"] if row["days_to_exhaustion"] is not None else "N/A"
        lines.append(
            f"| {row['campaign_name']} (ID {row['campaign_id']}) "
            f"| {row['health_band']} "
            f"| {row['latest_pacing_pct']}% "
            f"| {row['trend']} "
            f"| {dte} "
            f"| ${row['cum_spend']:,.0f} / ${row['total_budget']:,.0f} |"
        )
        path = generate_chart(row["campaign_id"], row["campaign_name"], raw_df)
        chart_paths.append((row["campaign_id"], path))

    lines.append("\n## Healthy Campaigns\n")
    lines.append("| Campaign | Pacing % | Trend |")
    lines.append("|---|---|---|")
    for _, row in healthy.iterrows():
        lines.append(f"| {row['campaign_name']} (ID {row['campaign_id']}) | {row['latest_pacing_pct']}% | {row['trend']} |")

    lines.append("\n## Charts\n")
    for cid, path in chart_paths:
        lines.append(f"![Campaign {cid} pacing]({os.path.relpath(path, 'reports')})")

    os.makedirs("reports", exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(lines))

    return summary_df


def print_daily_summary(summary_df):
    """
    One-line-per-campaign console output — the "run this every morning"
    version of the report, printed straight to stdout.
    """
    print("\n=== Daily Pacing Summary ===")
    for _, row in summary_df.sort_values("severity").iterrows():
        flag = "" if row["health_band"] == "healthy" else "  <-- FLAGGED"
        dte = row["days_to_exhaustion"] if row["days_to_exhaustion"] is not None else "N/A"
        print(
            f"[{row['health_band'].upper():12s}] Campaign {row['campaign_id']:>3} "
            f"'{row['campaign_name'][:35]:35s}' "
            f"pacing={row['latest_pacing_pct']:>6.1f}%  "
            f"trend={row['trend']:14s}  "
            f"days_left={dte}{flag}"
        )


def main():
    print("Loading pacing data...")
    raw_df = load_pacing_data()

    print("Classifying health bands...")
    raw_df = add_health_bands(raw_df)

    print("Computing days-to-exhaustion...")
    summary_df = compute_days_to_exhaustion(raw_df)

    print("Detecting trends...")
    trend_flags = detect_trend(raw_df)

    print("Generating report and charts...")
    summary_df = generate_report(summary_df, trend_flags, raw_df)

    print_daily_summary(summary_df)

    print(f"\nReport written to {REPORT_PATH}")
    print(f"Charts written to {CHARTS_DIR}/")


if __name__ == "__main__":
    main()
