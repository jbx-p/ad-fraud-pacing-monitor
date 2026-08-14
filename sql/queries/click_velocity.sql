-- click_velocity.sql
-- Flags IPs generating an unusually high number of clicks within short
-- time windows (rolling 5-minute buckets). This is the core signal for
-- catching click-farm fraud (ground truth: campaign_id 8, IP 203.0.113.77).
--
-- SQLite doesn't support a native rolling time-window join well, so this
-- uses a fixed 5-minute bucket approach: group timestamps into 5-minute
-- buckets, then count clicks per (ip_address, bucket). This is a
-- deliberate simplification vs. a true rolling window — documented as
-- such rather than silently approximated, see METHODOLOGY.md.

SELECT
    ip_address,
    campaign_id,
    -- Bucket timestamps into 5-minute windows by truncating to the
    -- nearest 300-second boundary since epoch
    (CAST(strftime('%s', timestamp) AS INTEGER) / 300) * 300 AS bucket_start_epoch,
    datetime((CAST(strftime('%s', timestamp) AS INTEGER) / 300) * 300, 'unixepoch') AS bucket_start,
    COUNT(*) AS clicks_in_window,
    COUNT(DISTINCT device_type) AS distinct_devices,
    COUNT(DISTINCT user_agent) AS distinct_user_agents
FROM click_events
GROUP BY ip_address, campaign_id, bucket_start_epoch
HAVING COUNT(*) >= 5   -- threshold: 5+ clicks from one IP in 5 minutes is suspicious
ORDER BY clicks_in_window DESC;