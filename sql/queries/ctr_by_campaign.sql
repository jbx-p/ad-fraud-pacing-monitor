-- ctr_by_campaign.sql
-- Daily CTR (click-through rate), CVR (conversion rate), and CPA
-- (cost per acquisition) rolled up per campaign.
-- Used as a general performance view and as an input feature for
-- the fraud detection module (Phase 4) — bot traffic shows up as
-- CTR/CVR that deviates sharply from a campaign's own baseline.

SELECT
    ds.campaign_id,
    c.campaign_name,
    ds.date,
    ds.impressions,
    ds.clicks,
    ds.conversions,
    ds.spend,
    ROUND(CAST(ds.clicks AS FLOAT) / NULLIF(ds.impressions, 0) * 100, 3) AS ctr_pct,
    ROUND(CAST(ds.conversions AS FLOAT) / NULLIF(ds.clicks, 0) * 100, 3) AS cvr_pct,
    ROUND(ds.spend / NULLIF(ds.conversions, 0), 2) AS cpa
FROM daily_spend ds
JOIN campaigns c ON c.campaign_id = ds.campaign_id
ORDER BY ds.campaign_id, ds.date;