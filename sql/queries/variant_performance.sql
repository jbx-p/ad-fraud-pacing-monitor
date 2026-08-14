-- variant_performance.sql
-- Aggregates clicks and conversions by creative variant (A vs B) per
-- campaign. This is the direct input to the two-proportion z-test in
-- the A/B testing module (Phase 5).
--
-- Ground truth: campaigns 5, 6, 7 have a real effect (variant B truly
-- converts better). All other campaigns should show no significant
-- difference between A and B.

SELECT
    ce.campaign_id,
    c.campaign_name,
    cr.variant,
    COUNT(*) AS total_clicks,
    SUM(ce.is_conversion) AS total_conversions,
    ROUND(
        CAST(SUM(ce.is_conversion) AS FLOAT) / COUNT(*) * 100,
        3
    ) AS conversion_rate_pct
FROM click_events ce
JOIN creatives cr ON cr.creative_id = ce.creative_id
JOIN campaigns c ON c.campaign_id = ce.campaign_id
GROUP BY ce.campaign_id, cr.variant
ORDER BY ce.campaign_id, cr.variant;