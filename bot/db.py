import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    def get_conn():
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn

    PLACEHOLDER = "%s"
    UPSERT_USER = """
        INSERT INTO users (telegram_id, username, first_name, last_active)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT(telegram_id) DO UPDATE SET
            username = EXCLUDED.username,
            first_name = EXCLUDED.first_name,
            last_active = NOW()
    """
    NOW_FN = "NOW()"
    DATE_OFFSET = "CURRENT_DATE + INTERVAL '28 days'"

else:
    import sqlite3

    DB_PATH = os.getenv("DB_PATH", "prisutstvuy.db")

    def get_conn():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    PLACEHOLDER = "?"
    UPSERT_USER = """
        INSERT INTO users (telegram_id, username, first_name, last_active)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(telegram_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_active = datetime('now')
    """
    NOW_FN = "datetime('now')"
    DATE_OFFSET = "date('now', '+28 days')"


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id     BIGINT PRIMARY KEY,
            username        TEXT,
            first_name      TEXT,
            subscription    TEXT DEFAULT 'free',
            morning_time    TEXT DEFAULT '08:00',
            evening_time    TEXT DEFAULT '21:00',
            timezone        TEXT DEFAULT 'Europe/Moscow',
            reminders_on    INTEGER DEFAULT 1,
            last_active     TIMESTAMP,
            followup_due    DATE,
            gift_story      TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS checkins (
            id              BIGSERIAL PRIMARY KEY,
            telegram_id     BIGINT REFERENCES users(telegram_id),
            state           TEXT,
            state_word      TEXT,
            source          TEXT DEFAULT 'manual',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS evening_notes (
            id              BIGSERIAL PRIMARY KEY,
            telegram_id     BIGINT REFERENCES users(telegram_id),
            note            TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.commit()
    logger.info("БД инициализирована")


def _execute(query, params=()):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()


def _fetchone(query, params=()):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None


def _fetchall(query, params=()):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]


def upsert_user(telegram_id, username, first_name):
    _execute(UPSERT_USER, (telegram_id, username, first_name))


def get_user(telegram_id):
    p = PLACEHOLDER
    return _fetchone(f"SELECT * FROM users WHERE telegram_id = {p}", (telegram_id,))


def set_subscription(telegram_id, plan):
    p = PLACEHOLDER
    _execute(f"UPDATE users SET subscription = {p} WHERE telegram_id = {p}", (plan, telegram_id))


def save_gift_story(telegram_id, story):
    p = PLACEHOLDER
    _execute(
        f"UPDATE users SET gift_story = {p}, followup_due = {DATE_OFFSET} WHERE telegram_id = {p}",
        (story, telegram_id)
    )


def add_checkin(telegram_id, state, state_word, source="manual"):
    p = PLACEHOLDER
    _execute(
        f"INSERT INTO checkins (telegram_id, state, state_word, source) VALUES ({p},{p},{p},{p})",
        (telegram_id, state, state_word, source)
    )


def add_evening_note(telegram_id, note):
    p = PLACEHOLDER
    _execute(
        f"INSERT INTO evening_notes (telegram_id, note) VALUES ({p},{p})",
        (telegram_id, note)
    )


def get_last_checkin(telegram_id):
    p = PLACEHOLDER
    return _fetchone(
        f"SELECT * FROM checkins WHERE telegram_id = {p} ORDER BY created_at DESC LIMIT 1",
        (telegram_id,)
    )


def get_week_checkins(telegram_id):
    p = PLACEHOLDER
    if DATABASE_URL:
        date_filter = "created_at >= NOW() - INTERVAL '7 days'"
    else:
        date_filter = "created_at >= date('now', '-7 days')"
    return _fetchall(
        f"SELECT state, state_word, created_at FROM checkins WHERE telegram_id = {p} AND {date_filter} ORDER BY created_at DESC",
        (telegram_id,)
    )


def get_all_users_for_schedule():
    return _fetchall(
        "SELECT telegram_id, morning_time, evening_time, timezone, reminders_on FROM users WHERE reminders_on = 1"
    )


def touch_last_active(telegram_id):
    p = PLACEHOLDER
    _execute(f"UPDATE users SET last_active = {NOW_FN} WHERE telegram_id = {p}", (telegram_id,))

def get_onboarding_day(telegram_id):
    p = PLACEHOLDER
    row = _fetchone(
        f"SELECT onboarding_day FROM users WHERE telegram_id = {p}",
        (telegram_id,)
    )
    if not row:
        return 1
    return row.get("onboarding_day") or 1

def advance_onboarding(telegram_id):
    p = PLACEHOLDER
    _execute(
        f"UPDATE users SET onboarding_day = COALESCE(onboarding_day, 1) + 1 WHERE telegram_id = {p}",
        (telegram_id,)
    )
