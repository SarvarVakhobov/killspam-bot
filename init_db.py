#!/usr/bin/env python3
"""Create tables, then ensure ID columns are BIGINT (Telegram IDs overflow INT32).

create_all only creates missing tables; it won't widen columns on tables that
already exist, so the ALTERs below migrate older deploys. They're idempotent.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from spam_bot.db.session import engine
from spam_bot.db.models import Base

_BIGINT_COLS = [
    ("blocked_users", "telegram_id"), ("blocked_users", "group_id"),
    ("spam_reports", "telegram_id"), ("spam_reports", "group_id"),
    ("learned_patterns", "added_by"),
]

# create_all adds missing TABLES but never missing COLUMNS, so columns added to
# an existing table need an explicit (idempotent) ALTER.
_ADD_COLUMNS = [
    ("feedback_reports", "target_user_id", "BIGINT"),
    ("feedback_reports", "target_name", "VARCHAR"),
    ("learned_patterns", "group_id", "BIGINT"),
    ("feedback_reports", "group_id", "BIGINT"),
    ("group_config", "ai_enabled", "BOOLEAN"),
    ("group_config", "vt_key_encrypted", "VARCHAR"),
    ("group_config", "vt_key_set_by", "BIGINT"),
    ("group_config", "vt_key_set_at", "TIMESTAMP"),
    ("token_grants", "kind", "VARCHAR"),
]


def init_db():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    for tbl, col in _BIGINT_COLS:
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {tbl} ALTER COLUMN {col} TYPE BIGINT"))
        except Exception as e:
            print(f"  (skip {tbl}.{col}: {e})")
    for tbl, col, typ in _ADD_COLUMNS:
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col} {typ}"))
        except Exception as e:
            print(f"  (skip add {tbl}.{col}: {e})")
    print("Database tables created successfully!")


if __name__ == "__main__":
    init_db()
