-- daily_pacing.sql
-- Computes cumulative actual spend vs. expected spend per campaign per day.
-- pacing_pct > 100 = overpacing, < 100 = underpacing, ~100 = healthy.
-- Feeds src/pacing.py in Phase 3.

WITH campaign_days AS (
    SELECT
        campaign_id,
        date,
        spend,
        SUM(spend) OVER (
            PARTITION BY campaign_id
            ORDER BY date
        ) AS cum_spend,
        ROW_NUMBER() OVER (
            PARTITION BY campaign_id
            ORDER BY date
        ) AS day_number
    FROM daily_spend
)
SELECT
    cd.campaign_id,
    c.campaign_name,
    cd.date,
    cd.day_number,
    cd.spend AS daily_spend,
    cd.cum_spend,
    c.total_budget,
    c.daily_budget_target,
    ROUND(c.daily_budget_target * cd.day_number, 2) AS expected_cum_spend,
    ROUND(
        cd.cum_spend / (c.daily_budget_target * cd.day_number) * 100,
        1
    ) AS pacing_pct
FROM campaign_days cd
JOIN campaigns c ON c.campaign_id = cd.campaign_id
ORDER BY cd.campaign_id, cd.date;