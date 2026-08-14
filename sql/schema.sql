-- ============================================
-- Ad Campaign Performance & Fraud Monitoring
-- Schema Definition
-- ============================================

DROP TABLE IF EXISTS ab_test_assignments;
DROP TABLE IF EXISTS click_events;
DROP TABLE IF EXISTS daily_spend;
DROP TABLE IF EXISTS creatives;
DROP TABLE IF EXISTS campaigns;

CREATE TABLE campaigns (
    campaign_id         INTEGER PRIMARY KEY,
    campaign_name       TEXT NOT NULL,
    advertiser          TEXT NOT NULL,
    start_date          DATE NOT NULL,
    end_date            DATE NOT NULL,
    total_budget        REAL NOT NULL,
    daily_budget_target REAL NOT NULL,
    objective           TEXT NOT NULL
);

CREATE TABLE creatives (
    creative_id     INTEGER PRIMARY KEY,
    campaign_id     INTEGER NOT NULL,
    creative_name   TEXT NOT NULL,
    variant         TEXT NOT NULL CHECK (variant IN ('A', 'B')),
    format          TEXT NOT NULL,
    launch_date     DATE NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
);

CREATE TABLE daily_spend (
    campaign_id     INTEGER NOT NULL,
    date            DATE NOT NULL,
    spend           REAL NOT NULL,
    impressions     INTEGER NOT NULL,
    clicks          INTEGER NOT NULL,
    conversions     INTEGER NOT NULL,
    PRIMARY KEY (campaign_id, date),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
);

CREATE TABLE click_events (
    event_id        INTEGER PRIMARY KEY,
    campaign_id     INTEGER NOT NULL,
    creative_id     INTEGER NOT NULL,
    timestamp       DATETIME NOT NULL,
    ip_address      TEXT NOT NULL,
    user_agent      TEXT NOT NULL,
    device_type     TEXT NOT NULL,
    is_conversion   BOOLEAN NOT NULL DEFAULT 0,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id),
    FOREIGN KEY (creative_id) REFERENCES creatives(creative_id)
);

CREATE TABLE ab_test_assignments (
    user_id         TEXT NOT NULL,
    campaign_id     INTEGER NOT NULL,
    variant         TEXT NOT NULL CHECK (variant IN ('A', 'B')),
    assigned_at     DATETIME NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
);

-- Indexes for the queries you'll run heavily in Phase 4 (fraud detection)
CREATE INDEX idx_click_events_ip ON click_events(ip_address);
CREATE INDEX idx_click_events_campaign_time ON click_events(campaign_id, timestamp);
CREATE INDEX idx_daily_spend_campaign ON daily_spend(campaign_id);