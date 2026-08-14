"""
Throwaway script to verify each Phase 2 SQL file runs cleanly against
adops.db and returns sane-looking results. Not part of the final project
structure — delete this file once Phase 2 is confirmed working.
"""

import pandas as pd
from sqlalchemy import create_engine, text

engine = create_engine("sqlite:///data/adops.db")

queries = {
    "daily_pacing": "sql/queries/daily_pacing.sql",
    "ctr_by_campaign": "sql/queries/ctr_by_campaign.sql",
    "click_velocity": "sql/queries/click_velocity.sql",
    "variant_performance": "sql/queries/variant_performance.sql",
}

for name, path in queries.items():
    print(f"\n{'='*60}\n{name}\n{'='*60}")
    with open(path, "r") as f:
        sql = f.read()
    try:
        df = pd.read_sql(text(sql), engine)
        print(f"Rows returned: {len(df)}")
        print(df.head(8).to_string())
    except Exception as e:
        print(f"ERROR: {e}")