"""Portal database — users, API keys, usage logs.

Uses stdlib sqlite3 + asyncio.to_thread (Python 3.11).
WAL mode so 8081 proxy and 8080 portal can both write safely.
"""
import sqlite3
import secrets
import hashlib
import time
import random
import fcntl
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import date, datetime, timedelta
import asyncio

DB_PATH = Path.home() / ".kiro-proxy" / "portal.db"
INIT_LOCK_PATH = Path.home() / ".kiro-proxy" / ".db_init.lock"

USD_PER_CNY = 1 / 6.834547
LEGACY_BALANCE_USD_PER_1M = round(6.5 * USD_PER_CNY, 8)  # Align legacy token quota to Kimi K2.6 input pricing.

OFFICIAL_MODEL_PRICES = {
    "gpt-image-2": {
        "input": 0.50,
        "output": 2.00,
    },
    "gpt-5.2": {
        "input": 1.50,
        "output": 6.00,
    },
    "gpt-5.4": {
        "input": 2.50,
        "output": 10.00,
    },
    "gpt-5.4-mini": {
        "input": 0.15,
        "output": 0.60,
    },
    "claude-haiku-4.5": {
        "input": 1.00,
        "output": 5.00,
        "cache_write": 1.25,
        "cache_read": 0.10,
    },
    "claude-sonnet-4.5": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-sonnet-4.6": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-opus-4.6": {
        "input": 5.00,
        "output": 25.00,
        "cache_write": 6.25,
        "cache_read": 0.50,
    },
    "claude-opus-4.7": {
        "input": 5.00,
        "output": 25.00,
        "cache_write": 6.25,
        "cache_read": 0.50,
    },
    "kimi-k2.6": {
        "input": round(6.5 * USD_PER_CNY, 8),
        "output": round(27.0 * USD_PER_CNY, 8),
        "cache_read": round(1.1 * USD_PER_CNY, 8),
        "cache_write": round(6.5 * USD_PER_CNY, 8),
    },
    "mimo-v2.5-pro": {
        "input": 1.00,
        "output": 3.00,
    },
    "mimo-v2.5": {
        "input": 1.00,
        "output": 3.00,
    },
    "mimo-v2.5-tts": {
        "input": 1.00,
        "output": 3.00,
    },
    "mimo-v2.5-tts-voicedesign": {
        "input": 1.00,
        "output": 3.00,
    },
    "mimo-v2.5-tts-voiceclone": {
        "input": 1.00,
        "output": 3.00,
    },
    "mimo-v2-pro": {
        "input": 1.00,
        "output": 3.00,
    },
    "mimo-v2-flash": {
        "input": 1.00,
        "output": 3.00,
    },
    "mimo-v2-omni": {
        "input": 1.00,
        "output": 3.00,
    },
    "mimo-v2-tts": {
        "input": 1.00,
        "output": 3.00,
    },
    "default": {
        "input": round(6.5 * USD_PER_CNY, 8),
        "output": round(27.0 * USD_PER_CNY, 8),
        "cache_read": round(1.1 * USD_PER_CNY, 8),
        "cache_write": round(6.5 * USD_PER_CNY, 8),
    },
}

# Allowed models for user-issued keys
ALLOWED_USER_MODELS = {
    "claude-haiku-4.5",
    "claude-haiku-4.5-thinking",
    "claude-haiku-4-5-thinking",
    "claude-haiku-4.5-agentic",
    "claude-haiku-4-5-agentic",
    "claude-sonnet-4.5",
    "claude-sonnet-4.5-thinking",
    "claude-sonnet-4-5-thinking",
    "claude-sonnet-4.5-agentic",
    "claude-sonnet-4-5-agentic",
    "claude-sonnet-4.6",
    "claude-sonnet-4-6",
    "claude-sonnet-4.6-thinking",
    "claude-sonnet-4-6-thinking",
    "claude-sonnet-4.6-agentic",
    "claude-sonnet-4-6-agentic",
    "kimi-k2.6",
    "mimo-v2.5-pro",
    "mimo-v2.5",
    "mimo-v2.5-tts",
    "mimo-v2.5-tts-voicedesign",
    "mimo-v2.5-tts-voiceclone",
    "mimo-v2-pro",
    "mimo-v2-flash",
    "mimo-v2-omni",
    "mimo-v2-tts",
    "gpt-5.2",
    "gpt-5.4",
    "gpt-5.4-mini",
}

DEFAULT_TOKEN_QUOTA = 5_000_000  # 500万 tokens
ALLOWED_KEY_GROUPS = {"claude", "kimi", "mimo", "gpt"}

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT UNIQUE NOT NULL,
    display_name TEXT,
    email TEXT,
    email_verified INTEGER DEFAULT 0,
    email_verified_at TEXT,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    is_active INTEGER DEFAULT 1,
    total_tokens INTEGER DEFAULT 5000000,
    used_tokens INTEGER DEFAULT 0,
    balance_usd REAL DEFAULT 0,
    balance_migrated INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    avatar TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS email_verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT 'register',
    code_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    attempt_count INTEGER DEFAULT 0,
    created_ip TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_email_verifications_email ON email_verifications(email, purpose, created_at DESC);

CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_prefix TEXT NOT NULL,
    key_hash TEXT UNIQUE NOT NULL,
    name TEXT DEFAULT 'My Key',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    last_used_at TEXT,
    is_active INTEGER DEFAULT 1,
    used_tokens INTEGER DEFAULT 0,
    used_usd REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS usage_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    key_prefix TEXT,
    timestamp TEXT DEFAULT (datetime('now', 'localtime')),
    model TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    status TEXT DEFAULT 'success'
);

CREATE TABLE IF NOT EXISTS balance_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    source_type TEXT,
    source_id INTEGER,
    delta_usd REAL NOT NULL,
    balance_after_usd REAL,
    related_model TEXT,
    description TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(source_type, source_id)
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_logs_user ON usage_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_logs_ts ON usage_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_logs_key ON usage_logs(key_prefix);
CREATE INDEX IF NOT EXISTS idx_balance_events_user ON balance_events(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS image_playground_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    source_mode TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    status TEXT DEFAULT 'success',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_image_pg_user_date ON image_playground_usage(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    created_by TEXT DEFAULT 'admin',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS checkin_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    checkin_date TEXT NOT NULL,
    tokens_awarded INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(user_id, checkin_date)
);

CREATE TABLE IF NOT EXISTS checkin_config (
    id INTEGER PRIMARY KEY DEFAULT 1,
    min_tokens INTEGER NOT NULL DEFAULT 1000,
    max_tokens INTEGER NOT NULL DEFAULT 5000,
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_by TEXT DEFAULT 'admin',
    CHECK (id = 1),
    CHECK (min_tokens > 0 AND max_tokens >= min_tokens)
);

CREATE INDEX IF NOT EXISTS idx_checkin_user ON checkin_records(user_id);
CREATE INDEX IF NOT EXISTS idx_checkin_date ON checkin_records(checkin_date DESC);

INSERT OR IGNORE INTO checkin_config (id, min_tokens, max_tokens)
VALUES (1, 1000, 5000);

CREATE TABLE IF NOT EXISTS playground_tasks (
    task_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'processing',  -- 'processing', 'done', 'error'
    result_json TEXT,         -- JSON result (created + data array) when done
    error_message TEXT,       -- error message when error
    created_at REAL NOT NULL  -- time.time() epoch seconds for TTL cleanup
);

CREATE INDEX IF NOT EXISTS idx_playground_tasks_status ON playground_tasks(status);
"""


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _get_model_price(model: str) -> dict:
    if model in OFFICIAL_MODEL_PRICES:
        return OFFICIAL_MODEL_PRICES[model]
    parts = model.split("-")
    for i in range(len(parts), 0, -1):
        prefix = "-".join(parts[:i])
        if prefix in OFFICIAL_MODEL_PRICES:
            return OFFICIAL_MODEL_PRICES[prefix]
    return OFFICIAL_MODEL_PRICES["default"]


def _calculate_cost_usd(model: str, input_tokens: int, output_tokens: int,
                        cache_read_tokens: int = 0, cache_creation_tokens: int = 0) -> float:
    price = _get_model_price(model)
    total = (
        input_tokens * float(price.get("input", 0.0))
        + output_tokens * float(price.get("output", 0.0))
        + cache_creation_tokens * float(price.get("cache_write", price.get("input", 0.0)))
        + cache_read_tokens * float(price.get("cache_read", 0.0))
    ) / 1e6
    return round(total, 8)


def _sync_backfill_usd_fields(conn: sqlite3.Connection):
    rows = conn.execute(
        "SELECT id, model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, COALESCE(cost_usd, 0) as cost_usd FROM usage_logs"
    ).fetchall()
    for row in rows:
        cost_usd = _calculate_cost_usd(
            row["model"] or "default",
            int(row["input_tokens"] or 0),
            int(row["output_tokens"] or 0),
            int(row["cache_read_tokens"] or 0),
            int(row["cache_creation_tokens"] or 0),
        )
        if abs(float(row["cost_usd"] or 0.0) - cost_usd) > 1e-9:
            conn.execute("UPDATE usage_logs SET cost_usd=? WHERE id=?", (cost_usd, row["id"]))

    usage_rows = conn.execute(
        "SELECT id, user_id, model, timestamp, COALESCE(cost_usd, 0) as cost_usd FROM usage_logs WHERE COALESCE(cost_usd, 0) > 0"
    ).fetchall()
    for row in usage_rows:
        exists = conn.execute(
            "SELECT id, delta_usd, related_model FROM balance_events WHERE source_type='usage_log' AND source_id=?",
            (row["id"],)
        ).fetchone()
        if exists:
            expected_delta = -round(float(row["cost_usd"] or 0.0), 8)
            if abs(float(exists["delta_usd"] or 0.0) - expected_delta) > 1e-9 or (exists["related_model"] or "") != (row["model"] or ""):
                conn.execute(
                    """UPDATE balance_events
                       SET delta_usd=?, related_model=?, created_at=?, description=?
                       WHERE id=?""",
                    (
                        expected_delta,
                        row["model"],
                        row["timestamp"],
                        "API usage",
                        exists["id"],
                    ),
                )
            continue
        conn.execute(
            """INSERT INTO balance_events
               (user_id, event_type, source_type, source_id, delta_usd, related_model, created_at, description)
               VALUES (?, 'spend', 'usage_log', ?, ?, ?, ?, ?)""",
            (
                row["user_id"],
                row["id"],
                -round(float(row["cost_usd"] or 0.0), 8),
                row["model"],
                row["timestamp"],
                "API usage",
            ),
        )

    checkin_rows = conn.execute(
        "SELECT id, user_id, tokens_awarded, created_at FROM checkin_records"
    ).fetchall()
    for row in checkin_rows:
        exists = conn.execute(
            "SELECT id, delta_usd FROM balance_events WHERE source_type='checkin' AND source_id=?",
            (row["id"],)
        ).fetchone()
        usd_awarded = round(int(row["tokens_awarded"] or 0) * LEGACY_BALANCE_USD_PER_1M / 1e6, 6)
        if exists:
            if abs(float(exists["delta_usd"] or 0.0) - usd_awarded) > 1e-9:
                conn.execute(
                    "UPDATE balance_events SET delta_usd=?, created_at=?, description=? WHERE id=?",
                    (usd_awarded, row["created_at"], "Daily check-in", exists["id"]),
                )
            continue
        conn.execute(
            """INSERT INTO balance_events
               (user_id, event_type, source_type, source_id, delta_usd, created_at, description)
               VALUES (?, 'checkin', 'checkin', ?, ?, ?, ?)""",
            (
                row["user_id"],
                row["id"],
                usd_awarded,
                row["created_at"],
                "Daily check-in",
            ),
        )

    users = conn.execute("SELECT id, total_tokens, used_tokens, balance_usd, balance_migrated FROM users").fetchall()
    for user in users:
        consumed_usd = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM usage_logs WHERE user_id=?",
            (user["id"],)
        ).fetchone()[0]
        if not int(user["balance_migrated"] or 0):
            remaining_tokens = max(0, int(user["total_tokens"] or 0) - int(user["used_tokens"] or 0))
            balance_usd = round(remaining_tokens * LEGACY_BALANCE_USD_PER_1M / 1e6, 6)
            conn.execute(
                "UPDATE users SET balance_usd=?, balance_migrated=1 WHERE id=?",
                (balance_usd, user["id"]),
            )
        key_rows = conn.execute(
            "SELECT id, key_prefix FROM api_keys WHERE user_id=?",
            (user["id"],)
        ).fetchall()
        for key in key_rows:
            key_used_usd = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM usage_logs WHERE user_id=? AND key_prefix=?",
                (user["id"], key["key_prefix"]),
            ).fetchone()[0]
            conn.execute("UPDATE api_keys SET used_usd=? WHERE id=?", (round(key_used_usd or 0.0, 6), key["id"]))

    conn.commit()


def _sync_init():
    INIT_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(INIT_LOCK_PATH, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            return __sync_init_locked()
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def __sync_init_locked():
    conn = _get_conn()
    for col, definition in [
        ("email", "TEXT"),
        ("email_verified", "INTEGER DEFAULT 0"),
        ("email_verified_at", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users(email) WHERE email IS NOT NULL")
    conn.commit()

    # Migrate: add cache token columns if not present (SQLite doesn't support IF NOT EXISTS for columns)
    for col, definition in [
        ("cache_read_tokens", "INTEGER DEFAULT 0"),
        ("cache_creation_tokens", "INTEGER DEFAULT 0"),
        ("cost_usd", "REAL DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE usage_logs ADD COLUMN {col} {definition}")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    for col, definition in [
        ("group_name", "TEXT DEFAULT 'default'"),
        ("expires_at", "TEXT"),
        ("quota_limit", "INTEGER DEFAULT 0"),
        ("used_usd", "REAL DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE api_keys ADD COLUMN {col} {definition}")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # Dummy block to match replaced code exactly
    for col, definition in [
        ("cache_read_tokens", "INTEGER DEFAULT 0"),
        ("cache_creation_tokens", "INTEGER DEFAULT 0"),
        ("cost_usd", "REAL DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE usage_logs ADD COLUMN {col} {definition}")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    for col, definition in [
        ("group_name", "TEXT DEFAULT 'default'"),
        ("expires_at", "TEXT"),
        ("quota_limit", "INTEGER DEFAULT 0"),
        ("used_usd", "REAL DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE api_keys ADD COLUMN {col} {definition}")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # Dummy block to match replaced code exactly
    for col, definition in [
        ("cache_read_tokens", "INTEGER DEFAULT 0"),
        ("cache_creation_tokens", "INTEGER DEFAULT 0"),
        ("cost_usd", "REAL DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE usage_logs ADD COLUMN {col} {definition}")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    for col, definition in [
        ("group_name", "TEXT DEFAULT 'default'"),
        ("expires_at", "TEXT"),
        ("quota_limit", "INTEGER DEFAULT 0"),
        ("used_usd", "REAL DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE api_keys ADD COLUMN {col} {definition}")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # Dummy block to match replaced code exactly
    for col, definition in [
        ("cache_read_tokens", "INTEGER DEFAULT 0"),
        ("cache_creation_tokens", "INTEGER DEFAULT 0"),
        ("cost_usd", "REAL DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE usage_logs ADD COLUMN {col} {definition}")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
    for col, definition in [
        ("balance_usd", "REAL DEFAULT 0"),
        ("balance_migrated", "INTEGER DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    _sync_backfill_usd_fields(conn)
    for col, definition in [
        ("avatar", "TEXT DEFAULT ''"),
    ]:
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


async def init_db():
    await asyncio.to_thread(_sync_init)


# ─── Password helpers ────────────────────────────────────────────────────────

def _hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return h.hex(), salt


def _verify_password(password: str, stored_hash: str, salt: str) -> bool:
    h, _ = _hash_password(password, salt)
    return secrets.compare_digest(h, stored_hash)


def _hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _gen_api_key() -> tuple[str, str, str]:
    """Returns (full_key, prefix, hash)"""
    raw = secrets.token_hex(24)
    key = f"kp-{raw}"
    prefix = f"kp-{raw[:8]}..."
    return key, prefix, _hash_api_key(key)


# ─── User operations ─────────────────────────────────────────────────────────

def _sync_create_user(student_id: str, password: str, display_name: str = None) -> dict:
    conn = _get_conn()
    try:
        # Check existing
        row = conn.execute("SELECT id FROM users WHERE student_id=?", (student_id,)).fetchone()
        if row:
            return {"ok": False, "error": "学号已注册"}
        ph, salt = _hash_password(password)
        default_balance_usd = round(DEFAULT_TOKEN_QUOTA * LEGACY_BALANCE_USD_PER_1M / 1e6, 6)
        conn.execute(
            "INSERT INTO users (student_id, display_name, password_hash, password_salt, balance_usd, balance_migrated) VALUES (?,?,?,?,?,1)",
            (student_id, display_name or student_id, ph, salt, default_balance_usd)
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def _sync_create_email_verification(email: str, purpose: str, code_hash: str, client_ip: str = "", user_id: int = None) -> dict:
    conn = _get_conn()
    try:
        exists = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if exists and (user_id is None or int(exists["id"]) != int(user_id)):
            return {"ok": False, "error": "该邮箱已被注册"}

        recent = conn.execute(
            """SELECT id FROM email_verifications
               WHERE email=? AND purpose=? AND datetime(created_at) > datetime('now','localtime','-60 seconds')
               ORDER BY id DESC LIMIT 1""",
            (email, purpose),
        ).fetchone()
        if recent:
            return {"ok": False, "error": "验证码发送过于频繁，请稍后再试"}

        expires_at = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT INTO email_verifications
               (email, purpose, code_hash, expires_at, created_ip)
               VALUES (?, ?, ?, ?, ?)""",
            (email, purpose, code_hash, expires_at, client_ip[:64]),
        )
        conn.commit()
        return {"ok": True, "expires_in_seconds": 600}
    finally:
        conn.close()


def _sync_register_user_with_email_verification(
    student_id: str,
    password: str,
    email: str,
    code_hash: str,
    display_name: str = None,
) -> dict:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT id FROM users WHERE student_id=?", (student_id,)).fetchone()
        if row:
            return {"ok": False, "error": "学号已注册"}
        email_row = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if email_row:
            return {"ok": False, "error": "该邮箱已被注册"}

        ver = conn.execute(
            """SELECT id, code_hash, expires_at, attempt_count
               FROM email_verifications
               WHERE email=? AND purpose='register' AND used_at IS NULL
               ORDER BY id DESC LIMIT 1""",
            (email,),
        ).fetchone()
        if not ver:
            return {"ok": False, "error": "请先发送邮箱验证码"}
        if int(ver["attempt_count"] or 0) >= 5:
            return {"ok": False, "error": "验证码错误次数过多，请重新发送"}
        if datetime.strptime(ver["expires_at"], "%Y-%m-%d %H:%M:%S") < datetime.now():
            return {"ok": False, "error": "验证码已过期，请重新发送"}
        if (ver["code_hash"] or "") != code_hash:
            conn.execute(
                "UPDATE email_verifications SET attempt_count=attempt_count+1 WHERE id=?",
                (ver["id"],),
            )
            conn.commit()
            return {"ok": False, "error": "邮箱验证码错误"}

        ph, salt = _hash_password(password)
        default_balance_usd = round(DEFAULT_TOKEN_QUOTA * LEGACY_BALANCE_USD_PER_1M / 1e6, 6)
        conn.execute("BEGIN TRANSACTION")
        cursor = conn.execute(
            """INSERT INTO users
               (student_id, display_name, email, email_verified, email_verified_at, password_hash, password_salt, balance_usd, balance_migrated)
               VALUES (?,?,?,?,datetime('now','localtime'),?,?,?,1)""",
            (student_id, display_name or student_id, email, 1, ph, salt, default_balance_usd),
        )
        conn.execute(
            "UPDATE email_verifications SET used_at=datetime('now','localtime') WHERE id=?",
            (ver["id"],),
        )
        conn.commit()
        return {"ok": True, "user_id": cursor.lastrowid}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _sync_bind_email_with_verification(user_id: int, email: str, code_hash: str) -> dict:
    conn = _get_conn()
    try:
        user = conn.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            return {"ok": False, "error": "用户不存在"}
        email_row = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if email_row and int(email_row["id"]) != int(user_id):
            return {"ok": False, "error": "该邮箱已被注册"}

        ver = conn.execute(
            """SELECT id, code_hash, expires_at, attempt_count
               FROM email_verifications
               WHERE email=? AND purpose='bind_email' AND used_at IS NULL
               ORDER BY id DESC LIMIT 1""",
            (email,),
        ).fetchone()
        if not ver:
            return {"ok": False, "error": "请先发送邮箱验证码"}
        if int(ver["attempt_count"] or 0) >= 5:
            return {"ok": False, "error": "验证码错误次数过多，请重新发送"}
        if datetime.strptime(ver["expires_at"], "%Y-%m-%d %H:%M:%S") < datetime.now():
            return {"ok": False, "error": "验证码已过期，请重新发送"}
        if (ver["code_hash"] or "") != code_hash:
            conn.execute(
                "UPDATE email_verifications SET attempt_count=attempt_count+1 WHERE id=?",
                (ver["id"],),
            )
            conn.commit()
            return {"ok": False, "error": "邮箱验证码错误"}

        conn.execute("BEGIN TRANSACTION")
        conn.execute(
            """UPDATE users
               SET email=?, email_verified=1, email_verified_at=datetime('now','localtime')
               WHERE id=?""",
            (email, user_id),
        )
        conn.execute(
            "UPDATE email_verifications SET used_at=datetime('now','localtime') WHERE id=?",
            (ver["id"],),
        )
        conn.commit()
        return {"ok": True}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _sync_change_password(user_id: int, current_password: str, new_password: str) -> dict:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT password_hash, password_salt FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "用户不存在"}
        if not _verify_password(current_password, row["password_hash"], row["password_salt"]):
            return {"ok": False, "error": "当前密码错误"}

        ph, salt = _hash_password(new_password)
        conn.execute(
            "UPDATE users SET password_hash=?, password_salt=? WHERE id=?",
            (ph, salt, user_id),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def _sync_login_user(student_id: str, password: str) -> Optional[dict]:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, student_id, display_name, email, email_verified, password_hash, password_salt, is_active, total_tokens, used_tokens, balance_usd FROM users WHERE student_id=?",
            (student_id,)
        ).fetchone()
        if not row:
            return None
        if not row["is_active"]:
            return None
        if not _verify_password(password, row["password_hash"], row["password_salt"]):
            return None
        return dict(row)
    finally:
        conn.close()


def _sync_get_user_by_student_id(student_id: str) -> Optional[dict]:
    conn = _get_conn()
    try:
        row = conn.execute(
            """SELECT id, student_id, display_name, email, email_verified, is_active, total_tokens, used_tokens,
                      balance_usd, created_at, notes, avatar
               FROM users WHERE student_id=?""",
            (student_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _sync_reset_password_with_email_verification(student_id: str, email: str, code_hash: str, new_password: str) -> dict:
    conn = _get_conn()
    try:
        user = conn.execute(
            "SELECT id, email, is_active FROM users WHERE student_id=?",
            (student_id,),
        ).fetchone()
        if not user:
            return {"ok": False, "error": "账号不存在"}
        if not user["is_active"]:
            return {"ok": False, "error": "账号已被禁用"}
        stored_email = (user["email"] or "").strip().lower()
        if not stored_email:
            return {"ok": False, "error": "该账号未绑定邮箱，无法重置密码"}
        if stored_email != (email or "").strip().lower():
            return {"ok": False, "error": "账号与邮箱不匹配"}

        ver = conn.execute(
            """SELECT id, code_hash, expires_at, attempt_count
               FROM email_verifications
               WHERE email=? AND purpose='reset_password' AND used_at IS NULL
               ORDER BY id DESC LIMIT 1""",
            (stored_email,),
        ).fetchone()
        if not ver:
            return {"ok": False, "error": "请先发送邮箱验证码"}
        if int(ver["attempt_count"] or 0) >= 5:
            return {"ok": False, "error": "验证码错误次数过多，请重新发送"}
        if datetime.strptime(ver["expires_at"], "%Y-%m-%d %H:%M:%S") < datetime.now():
            return {"ok": False, "error": "验证码已过期，请重新发送"}
        if (ver["code_hash"] or "") != code_hash:
            conn.execute(
                "UPDATE email_verifications SET attempt_count=attempt_count+1 WHERE id=?",
                (ver["id"],),
            )
            conn.commit()
            return {"ok": False, "error": "邮箱验证码错误"}

        ph, salt = _hash_password(new_password)
        conn.execute("BEGIN TRANSACTION")
        conn.execute(
            "UPDATE users SET password_hash=?, password_salt=? WHERE id=?",
            (ph, salt, user["id"]),
        )
        conn.execute(
            "UPDATE email_verifications SET used_at=datetime('now','localtime') WHERE id=?",
            (ver["id"],),
        )
        conn.commit()
        return {"ok": True}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _sync_change_password_with_email_verification(user_id: int, current_password: str, new_password: str, code_hash: str) -> dict:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT email, password_hash, password_salt FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "用户不存在"}
        if not _verify_password(current_password, row["password_hash"], row["password_salt"]):
            return {"ok": False, "error": "当前密码错误"}
        email = (row["email"] or "").strip().lower()
        if not email:
            return {"ok": False, "error": "请先绑定邮箱后再修改密码"}

        ver = conn.execute(
            """SELECT id, code_hash, expires_at, attempt_count
               FROM email_verifications
               WHERE email=? AND purpose='change_password' AND used_at IS NULL
               ORDER BY id DESC LIMIT 1""",
            (email,),
        ).fetchone()
        if not ver:
            return {"ok": False, "error": "请先发送邮箱验证码"}
        if int(ver["attempt_count"] or 0) >= 5:
            return {"ok": False, "error": "验证码错误次数过多，请重新发送"}
        if datetime.strptime(ver["expires_at"], "%Y-%m-%d %H:%M:%S") < datetime.now():
            return {"ok": False, "error": "验证码已过期，请重新发送"}
        if (ver["code_hash"] or "") != code_hash:
            conn.execute(
                "UPDATE email_verifications SET attempt_count=attempt_count+1 WHERE id=?",
                (ver["id"],),
            )
            conn.commit()
            return {"ok": False, "error": "邮箱验证码错误"}

        ph, salt = _hash_password(new_password)
        conn.execute("BEGIN TRANSACTION")
        conn.execute(
            "UPDATE users SET password_hash=?, password_salt=? WHERE id=?",
            (ph, salt, user_id),
        )
        conn.execute(
            "UPDATE email_verifications SET used_at=datetime('now','localtime') WHERE id=?",
            (ver["id"],),
        )
        conn.commit()
        return {"ok": True}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _sync_get_user(user_id: int) -> Optional[dict]:
    conn = _get_conn()
    try:
        row = conn.execute(
            """SELECT id, student_id, display_name, email, email_verified, is_active, total_tokens, used_tokens,
                      balance_usd, created_at, notes, avatar
               FROM users WHERE id=?""",
            (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _sync_get_all_users() -> List[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT u.id, u.student_id, u.display_name, u.email, u.email_verified, u.is_active, u.total_tokens, u.used_tokens,
                      u.balance_usd, u.created_at, u.notes, COALESCE(SUM(l.cost_usd), 0) as total_cost_usd
               FROM users u
               LEFT JOIN usage_logs l ON l.user_id = u.id
               GROUP BY u.id
               ORDER BY u.created_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _sync_update_user(user_id: int, **kwargs) -> bool:
    allowed = {"total_tokens", "is_active", "notes", "display_name", "balance_usd"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    conn = _get_conn()
    try:
        sets = ", ".join(f"{k}=?" for k in updates)
        conn.execute(f"UPDATE users SET {sets} WHERE id=?", (*updates.values(), user_id))
        conn.commit()
        return True
    finally:
        conn.close()


def _sync_update_profile(user_id: int, display_name: str = None, avatar: str = None) -> dict:
    conn = _get_conn()
    try:
        updates = []
        values = []
        if display_name is not None:
            name = str(display_name).strip()[:64]
            if not name:
                return {"ok": False, "error": "显示名称不能为空"}
            updates.append("display_name=?")
            values.append(name)
        if avatar is not None:
            updates.append("avatar=?")
            values.append(str(avatar).strip())
        if not updates:
            return {"ok": False, "error": "没有需要更新的字段"}
        values.append(user_id)
        sets = ", ".join(updates)
        conn.execute(f"UPDATE users SET {sets} WHERE id=?", values)
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ─── API key operations ───────────────────────────────────────────────────────

def _normalize_group_name(group_name: str) -> str:
    normalized = (group_name or "").strip().lower()
    return normalized if normalized in ALLOWED_KEY_GROUPS else "claude"


def _sync_create_key(user_id: int, name: str, group_name: str = 'claude', expires_at: str = None, quota_limit: float = 0) -> dict:
    conn = _get_conn()
    try:
        # Max 10 keys per user
        count = conn.execute("SELECT COUNT(*) FROM api_keys WHERE user_id=? AND is_active=1", (user_id,)).fetchone()[0]
        if count >= 50: # Increased limit to 50
            return {"ok": False, "error": "最多创建50个Key"}
        full_key, prefix, key_hash = _gen_api_key()
        group_name = _normalize_group_name(group_name)
        conn.execute(
            "INSERT INTO api_keys (user_id, key_prefix, key_hash, name, group_name, expires_at, quota_limit) VALUES (?,?,?,?,?,?,?)",
            (user_id, prefix, key_hash, name or "My Key", group_name, expires_at, quota_limit)
        )
        conn.commit()
        return {"ok": True, "key": full_key, "prefix": prefix}
    finally:
        conn.close()


def _sync_list_keys(user_id: int) -> List[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT id, key_prefix, name, group_name, created_at, last_used_at, is_active, used_tokens,
                      used_usd, quota_limit
               FROM api_keys WHERE user_id=? ORDER BY created_at DESC""",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _sync_delete_key(key_id: int, user_id: int) -> bool:
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM api_keys WHERE id=? AND user_id=?", (key_id, user_id))
        conn.commit()
        return True
    finally:
        conn.close()


def _sync_validate_key(full_key: str) -> dict | str:
    """Validate a user API key. Returns user+key info dict, or error string."""
    if not full_key.startswith("kp-"):
        return "invalid_format"
    kh = _hash_api_key(full_key)
    conn = _get_conn()
    try:
        row = conn.execute(
            """SELECT k.id as key_id, k.user_id, k.key_prefix, k.is_active as key_active,
                      k.group_name, k.quota_limit, k.used_usd,
                      u.is_active as user_active, u.total_tokens, u.used_tokens, u.balance_usd, u.student_id
               FROM api_keys k JOIN users u ON k.user_id=u.id
               WHERE k.key_hash=?""",
            (kh,)
        ).fetchone()
        if not row:
            return "not_found"
        d = dict(row)
        if not d["key_active"] or not d["user_active"]:
            return "inactive"
        if float(d.get("balance_usd") or 0.0) <= 0:
            return "quota_exceeded"
        key_quota = float(d.get("quota_limit") or 0.0)
        key_used_usd = float(d.get("used_usd") or 0.0)
        if key_quota > 0 and key_used_usd >= key_quota:
            return "quota_exceeded"
        return d
    finally:
        conn.close()


# ─── Usage logging ────────────────────────────────────────────────────────────

def _sync_log_usage(user_id: int, key_prefix: str, model: str,
                    input_tokens: int, output_tokens: int, status: str = "success",
                    cache_read_tokens: int = 0, cache_creation_tokens: int = 0,
                    cost_usd: float = 0.0):
    total = input_tokens + output_tokens
    effective_cost_usd = round(float(cost_usd or 0.0), 8)
    if effective_cost_usd <= 0 and (
        input_tokens > 0 or output_tokens > 0 or cache_read_tokens > 0 or cache_creation_tokens > 0
    ):
        effective_cost_usd = _calculate_cost_usd(
            model or "default",
            int(input_tokens or 0),
            int(output_tokens or 0),
            int(cache_read_tokens or 0),
            int(cache_creation_tokens or 0),
        )
    # Quota cost: cache_read tokens are charged at 10% (matching Anthropic pricing)
    # cache_creation tokens are charged at 125% (they cost more to write)
    quota_cost = (
        input_tokens + output_tokens
        + cache_creation_tokens  # Already 1x; Anthropic actually charges 1.25x but we keep 1x for simplicity
        + max(0, int(cache_read_tokens * 0.1))  # Cache reads cost only 10%
    )
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "INSERT INTO usage_logs (user_id, key_prefix, model, input_tokens, output_tokens, total_tokens, cache_read_tokens, cache_creation_tokens, cost_usd, status) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (user_id, key_prefix, model, input_tokens, output_tokens, total, cache_read_tokens, cache_creation_tokens, effective_cost_usd, status)
        )
        conn.execute(
            "UPDATE users SET used_tokens=used_tokens+? WHERE id=?",
            (quota_cost, user_id)
        )
        conn.execute(
            "UPDATE users SET balance_usd=MAX(0, balance_usd-?) WHERE id=?",
            (effective_cost_usd, user_id)
        )
        conn.execute(
            "UPDATE api_keys SET used_tokens=used_tokens+?, last_used_at=datetime('now','localtime') WHERE key_prefix=? AND user_id=?",
            (quota_cost, key_prefix, user_id)
        )
        conn.execute(
            "UPDATE api_keys SET used_usd=used_usd+? WHERE key_prefix=? AND user_id=?",
            (effective_cost_usd, key_prefix, user_id)
        )
        balance_after = conn.execute("SELECT balance_usd FROM users WHERE id=?", (user_id,)).fetchone()[0]
        conn.execute(
            """INSERT OR IGNORE INTO balance_events
               (user_id, event_type, source_type, source_id, delta_usd, balance_after_usd, related_model, description)
               VALUES (?, 'spend', 'usage_log', ?, ?, ?, ?, ?)""",
            (
                user_id,
                cursor.lastrowid,
                -effective_cost_usd,
                round(float(balance_after or 0.0), 6),
                model,
                f"{key_prefix} usage",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _sync_get_logs(user_id: int, limit: int = 50, offset: int = 0) -> List[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, key_prefix, timestamp, model, input_tokens, output_tokens, total_tokens, cache_read_tokens, cache_creation_tokens, cost_usd, status FROM usage_logs WHERE user_id=? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset)
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            price = _get_model_price(item.get("model") or "default")
            input_price = float(price.get("input", 0.0))
            output_price = float(price.get("output", 0.0))
            cache_read_price = float(price.get("cache_read", input_price * 0.5))
            cache_write_price = float(price.get("cache_write", input_price))
            input_tokens = int(item.get("input_tokens") or 0)
            output_tokens = int(item.get("output_tokens") or 0)
            cache_read_tokens = int(item.get("cache_read_tokens") or 0)
            cache_creation_tokens = int(item.get("cache_creation_tokens") or 0)

            item["input_price_per_1m"] = input_price
            item["output_price_per_1m"] = output_price
            item["cache_read_price_per_1m"] = cache_read_price
            item["cache_write_price_per_1m"] = cache_write_price
            item["input_cost_usd"] = round(input_tokens * input_price / 1e6, 8)
            item["output_cost_usd"] = round(output_tokens * output_price / 1e6, 8)
            item["cache_read_cost_usd"] = round(cache_read_tokens * cache_read_price / 1e6, 8)
            item["cache_write_cost_usd"] = round(cache_creation_tokens * cache_write_price / 1e6, 8)
            result.append(item)
        return result
    finally:
        conn.close()


def _sync_get_stats(user_id: int) -> dict:
    conn = _get_conn()
    try:
        user = conn.execute("SELECT total_tokens, used_tokens FROM users WHERE id=?", (user_id,)).fetchone()
        balance_usd = conn.execute("SELECT balance_usd FROM users WHERE id=?", (user_id,)).fetchone()[0]
        today_tokens = conn.execute(
            "SELECT COALESCE(SUM(total_tokens),0) FROM usage_logs WHERE user_id=? AND date(timestamp)=date('now','localtime')",
            (user_id,)
        ).fetchone()[0]
        today_cost_usd = conn.execute(
            "SELECT COALESCE(SUM(cost_usd),0) FROM usage_logs WHERE user_id=? AND date(timestamp)=date('now','localtime')",
            (user_id,)
        ).fetchone()[0]
        req_count = conn.execute("SELECT COUNT(*) FROM usage_logs WHERE user_id=?", (user_id,)).fetchone()[0]
        usd_req_count = conn.execute("SELECT COUNT(*) FROM usage_logs WHERE user_id=? AND cost_usd > 0", (user_id,)).fetchone()[0]
        cache_row = conn.execute(
            "SELECT COALESCE(SUM(cache_read_tokens),0) as cache_read, COALESCE(SUM(cache_creation_tokens),0) as cache_write FROM usage_logs WHERE user_id=?",
            (user_id,)
        ).fetchone()
        model_breakdown = conn.execute(
            "SELECT model, SUM(total_tokens) as tokens, SUM(cost_usd) as cost_usd, COUNT(*) as reqs FROM usage_logs WHERE user_id=? GROUP BY model ORDER BY tokens DESC",
            (user_id,)
        ).fetchall()
        total_cost_usd = conn.execute(
            "SELECT COALESCE(SUM(cost_usd),0) FROM usage_logs WHERE user_id=?",
            (user_id,)
        ).fetchone()[0]
        total_cache_read = cache_row["cache_read"] if cache_row else 0
        total_cache_write = cache_row["cache_write"] if cache_row else 0
        # Tokens saved = cache_read_tokens * 0.9 (we only charged 10% instead of 100%)
        cache_saved = int(total_cache_read * 0.9)
        return {
            "total_tokens": user["total_tokens"],
            "used_tokens": user["used_tokens"],
            "remaining_tokens": user["total_tokens"] - user["used_tokens"],
            "balance_usd": round(balance_usd or 0.0, 6),
            "today_tokens": today_tokens,
            "request_count": req_count,
            "total_cost_usd": round(total_cost_usd or 0.0, 6),
            "today_cost_usd": round(today_cost_usd or 0.0, 6),
            "usd_request_count": usd_req_count,
            "cache_read_tokens": total_cache_read,
            "cache_creation_tokens": total_cache_write,
            "cache_saved_tokens": cache_saved,
            "model_breakdown": [dict(r) for r in model_breakdown],
        }
    finally:
        conn.close()


def _sync_admin_get_stats() -> dict:
    conn = _get_conn()
    try:
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        active_users = conn.execute("SELECT COUNT(*) FROM users WHERE is_active=1").fetchone()[0]
        total_tokens_used = conn.execute("SELECT COALESCE(SUM(used_tokens),0) FROM users").fetchone()[0]
        total_balance_usd = conn.execute("SELECT COALESCE(SUM(balance_usd),0) FROM users").fetchone()[0]
        total_requests = conn.execute("SELECT COUNT(*) FROM usage_logs").fetchone()[0]
        today_requests = conn.execute(
            "SELECT COUNT(*) FROM usage_logs WHERE date(timestamp)=date('now','localtime')"
        ).fetchone()[0]
        return {
            "total_users": total_users,
            "active_users": active_users,
            "total_tokens_used": total_tokens_used,
            "total_balance_usd": round(total_balance_usd or 0.0, 6),
            "total_requests": total_requests,
            "today_requests": today_requests,
        }
    finally:
        conn.close()


def _sync_admin_get_full_stats() -> dict:
    conn = _get_conn()
    try:
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        active_users = conn.execute("SELECT COUNT(*) FROM users WHERE is_active=1").fetchone()[0]
        total_tokens_used = conn.execute("SELECT COALESCE(SUM(used_tokens),0) FROM users").fetchone()[0]
        total_tokens_quota = conn.execute("SELECT COALESCE(SUM(total_tokens),0) FROM users").fetchone()[0]
        total_balance_usd = conn.execute("SELECT COALESCE(SUM(balance_usd),0) FROM users").fetchone()[0]
        total_cost_usd = conn.execute("SELECT COALESCE(SUM(cost_usd),0) FROM usage_logs").fetchone()[0]
        total_requests = conn.execute("SELECT COUNT(*) FROM usage_logs").fetchone()[0]
        today_requests = conn.execute(
            "SELECT COUNT(*) FROM usage_logs WHERE date(timestamp)=date('now','localtime')"
        ).fetchone()[0]
        today_tokens = conn.execute(
            "SELECT COALESCE(SUM(total_tokens),0) FROM usage_logs WHERE date(timestamp)=date('now','localtime')"
        ).fetchone()[0]
        today_cost_usd = conn.execute(
            "SELECT COALESCE(SUM(cost_usd),0) FROM usage_logs WHERE date(timestamp)=date('now','localtime')"
        ).fetchone()[0]
        active_keys = conn.execute("SELECT COUNT(*) FROM api_keys WHERE is_active=1").fetchone()[0]
        model_breakdown = conn.execute(
            """SELECT model, SUM(total_tokens) as tokens, SUM(cost_usd) as cost_usd, COUNT(*) as reqs
               FROM usage_logs GROUP BY model ORDER BY tokens DESC LIMIT 10"""
        ).fetchall()
        return {
            "total_users": total_users,
            "active_users": active_users,
            "total_tokens_used": total_tokens_used,
            "total_tokens_quota": total_tokens_quota,
            "total_balance_usd": round(total_balance_usd or 0.0, 6),
            "total_cost_usd": round(total_cost_usd or 0.0, 6),
            "total_requests": total_requests,
            "today_requests": today_requests,
            "today_tokens": today_tokens,
            "today_cost_usd": round(today_cost_usd or 0.0, 6),
            "active_keys": active_keys,
            "model_breakdown": [dict(r) for r in model_breakdown],
        }
    finally:
        conn.close()


def _sync_cleanup_usage_models() -> dict:
    """Normalize usage_logs.model and remove rows outside portal allowlist."""
    from ..config import map_model_name

    conn = _get_conn()
    try:
        rows = conn.execute("SELECT id, model FROM usage_logs").fetchall()
        total_rows = len(rows)
        updated = 0
        deleted = 0
        unchanged = 0

        for row in rows:
            row_id = row["id"]
            raw_model = (row["model"] or "").strip()
            normalized = map_model_name(raw_model) if raw_model else ""

            if normalized in ALLOWED_USER_MODELS:
                if raw_model != normalized:
                    conn.execute("UPDATE usage_logs SET model=? WHERE id=?", (normalized, row_id))
                    updated += 1
                else:
                    unchanged += 1
            else:
                conn.execute("DELETE FROM usage_logs WHERE id=?", (row_id,))
                deleted += 1

        conn.commit()
        return {
            "ok": True,
            "total_rows": total_rows,
            "updated": updated,
            "deleted": deleted,
            "unchanged": unchanged,
            "allowed_models": sorted(ALLOWED_USER_MODELS),
        }
    finally:
        conn.close()


def _sync_admin_get_all_keys() -> List[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT k.id, k.user_id, k.key_prefix, k.name, k.created_at, k.last_used_at,
                      k.group_name, k.is_active, k.used_tokens, k.used_usd, k.quota_limit, u.student_id
               FROM api_keys k JOIN users u ON k.user_id=u.id
               ORDER BY k.created_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _sync_admin_toggle_key(key_id: int, is_active: int) -> bool:
    conn = _get_conn()
    try:
        conn.execute("UPDATE api_keys SET is_active=? WHERE id=?", (is_active, key_id))
        conn.commit()
        return True
    finally:
        conn.close()


def _sync_admin_delete_any_key(key_id: int) -> bool:
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM api_keys WHERE id=?", (key_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def _sync_admin_add_quota(user_id: int, amount: float) -> bool:
    conn = _get_conn()
    try:
        conn.execute("UPDATE users SET balance_usd=MAX(0, balance_usd+?) WHERE id=?", (float(amount), user_id))
        balance_after = conn.execute("SELECT balance_usd FROM users WHERE id=?", (user_id,)).fetchone()[0]
        event_type = "welfare" if float(amount) > 0 else "adjustment"
        conn.execute(
            """INSERT INTO balance_events
               (user_id, event_type, delta_usd, balance_after_usd, description)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, event_type, round(float(amount), 8), round(float(balance_after or 0.0), 6), "Admin balance change"),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def _sync_admin_set_quota(user_id: int, amount: float) -> bool:
    conn = _get_conn()
    try:
        prev = conn.execute("SELECT balance_usd FROM users WHERE id=?", (user_id,)).fetchone()
        prev_balance = float(prev[0] if prev else 0.0)
        conn.execute("UPDATE users SET balance_usd=MAX(0, ?) WHERE id=?", (float(amount), user_id))
        balance_after = conn.execute("SELECT balance_usd FROM users WHERE id=?", (user_id,)).fetchone()[0]
        delta = round(float(balance_after or 0.0) - prev_balance, 8)
        conn.execute(
            """INSERT INTO balance_events
               (user_id, event_type, delta_usd, balance_after_usd, description)
               VALUES (?, 'adjustment', ?, ?, ?)""",
            (user_id, delta, round(float(balance_after or 0.0), 6), "Admin set balance"),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def _sync_admin_get_all_logs(limit: int = 50, offset: int = 0) -> List[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT l.id, l.user_id, l.key_prefix, l.timestamp, l.model,
                      l.input_tokens, l.output_tokens, l.total_tokens, l.cost_usd, l.status,
                      u.student_id
               FROM usage_logs l LEFT JOIN users u ON l.user_id=u.id
               ORDER BY l.timestamp DESC LIMIT ? OFFSET ?""",
            (limit, offset)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _sync_admin_save_announcement(content: str, created_by: str = "admin") -> int:
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "INSERT INTO announcements (content, created_by) VALUES (?,?)",
            (content, created_by)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def _sync_admin_get_announcements(limit: int = 20) -> List[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, content, created_by, created_at, is_active FROM announcements ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _sync_admin_delete_announcement(ann_id: int) -> bool:
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM announcements WHERE id=?", (ann_id,))
        conn.commit()
        return True
    finally:
        conn.close()


# ─── Checkin operations ────────────────────────────────────────────────────────

def _sync_checkin_user(user_id: int) -> dict:
    conn = _get_conn()
    try:
        today = date.today().isoformat()

        # Check if already checked in today
        existing = conn.execute(
            "SELECT tokens_awarded, created_at FROM checkin_records WHERE user_id=? AND checkin_date=?",
            (user_id, today)
        ).fetchone()

        if existing:
            usd_awarded = round(existing["tokens_awarded"] * LEGACY_BALANCE_USD_PER_1M / 1e6, 6)
            return {
                "ok": False,
                "error": "今日已签到",
                "already_checked_in": True,
                "tokens_awarded": existing["tokens_awarded"],
                "usd_awarded": usd_awarded,
                "checkin_time": existing["created_at"]
            }

        # Get config
        config = conn.execute("SELECT min_tokens, max_tokens FROM checkin_config WHERE id=1").fetchone()
        if not config:
            return {"ok": False, "error": "签到配置未初始化"}

        min_tokens = config["min_tokens"]
        max_tokens = config["max_tokens"]
        tokens_awarded = random.randint(min_tokens, max_tokens)
        usd_awarded = round(tokens_awarded * LEGACY_BALANCE_USD_PER_1M / 1e6, 6)

        # Transaction: insert record and update user tokens
        try:
            conn.execute("BEGIN TRANSACTION")
            cursor = conn.execute(
                "INSERT INTO checkin_records (user_id, checkin_date, tokens_awarded) VALUES (?,?,?)",
                (user_id, today, tokens_awarded)
            )
            conn.execute(
                "UPDATE users SET total_tokens=total_tokens+? WHERE id=?",
                (tokens_awarded, user_id)
            )
            conn.execute(
                "UPDATE users SET balance_usd=balance_usd+? WHERE id=?",
                (usd_awarded, user_id)
            )
            conn.commit()

            # Get updated total
            user = conn.execute("SELECT total_tokens, balance_usd FROM users WHERE id=?", (user_id,)).fetchone()
            new_total = user["total_tokens"] if user else 0
            balance_after = round(float(user["balance_usd"] if user else 0.0), 6)
            conn.execute(
                """INSERT OR IGNORE INTO balance_events
                   (user_id, event_type, source_type, source_id, delta_usd, balance_after_usd, description)
                   VALUES (?, 'checkin', 'checkin', ?, ?, ?, ?)""",
                (
                    user_id,
                    cursor.lastrowid,
                    usd_awarded,
                    balance_after,
                    "Daily check-in",
                ),
            )
            conn.commit()

            return {
                "ok": True,
                "tokens_awarded": tokens_awarded,
                "usd_awarded": usd_awarded,
                "new_total": new_total,
                "new_balance_usd": balance_after,
                "message": f"签到成功！余额增加 {usd_awarded} USD"
            }
        except sqlite3.IntegrityError:
            conn.rollback()
            return {
                "ok": False,
                "error": "今日已签到",
                "already_checked_in": True
            }
    finally:
        conn.close()


def _sync_get_checkin_status(user_id: int, date_str: str) -> dict:
    conn = _get_conn()
    try:
        record = conn.execute(
            "SELECT tokens_awarded, created_at FROM checkin_records WHERE user_id=? AND checkin_date=?",
            (user_id, date_str)
        ).fetchone()

        if record:
            usd_awarded = round(record["tokens_awarded"] * LEGACY_BALANCE_USD_PER_1M / 1e6, 6)
            return {
                "checked_in": True,
                "tokens_awarded": record["tokens_awarded"],
                "usd_awarded": usd_awarded,
                "checkin_time": record["created_at"],
                "checkin_date": date_str
            }
        else:
            return {
                "checked_in": False,
                "can_checkin": True
            }
    finally:
        conn.close()


def _sync_get_checkin_history(user_id: int, limit: int = 30) -> dict:
    conn = _get_conn()
    try:
        records = conn.execute(
            "SELECT checkin_date, tokens_awarded, created_at FROM checkin_records WHERE user_id=? ORDER BY checkin_date DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()

        total_count = conn.execute(
            "SELECT COUNT(*) FROM checkin_records WHERE user_id=?",
            (user_id,)
        ).fetchone()[0]

        total_tokens_earned = conn.execute(
            "SELECT COALESCE(SUM(tokens_awarded), 0) FROM checkin_records WHERE user_id=?",
            (user_id,)
        ).fetchone()[0]
        total_usd_earned = round(total_tokens_earned * LEGACY_BALANCE_USD_PER_1M / 1e6, 6)

        history = []
        for r in records:
            item = dict(r)
            item["usd_awarded"] = round(item["tokens_awarded"] * LEGACY_BALANCE_USD_PER_1M / 1e6, 6)
            history.append(item)

        return {
            "history": history,
            "total_count": total_count,
            "total_tokens_earned": total_tokens_earned,
            "total_usd_earned": total_usd_earned,
        }
    finally:
        conn.close()


def _sync_get_checkin_config() -> dict:
    conn = _get_conn()
    try:
        config = conn.execute(
            "SELECT min_tokens, max_tokens, updated_at, updated_by FROM checkin_config WHERE id=1"
        ).fetchone()

        if config:
            return dict(config)
        else:
            return {
                "min_tokens": 1000,
                "max_tokens": 5000,
                "updated_at": None,
                "updated_by": "admin"
            }
    finally:
        conn.close()


def _sync_update_checkin_config(min_tokens: int, max_tokens: int, admin: str) -> dict:
    if not isinstance(min_tokens, int) or not isinstance(max_tokens, int):
        return {"ok": False, "error": "参数必须是整数"}

    if min_tokens <= 0 or max_tokens < min_tokens:
        return {"ok": False, "error": "min_tokens 必须大于 0 且小于等于 max_tokens"}

    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE checkin_config SET min_tokens=?, max_tokens=?, updated_at=datetime('now','localtime'), updated_by=? WHERE id=1",
            (min_tokens, max_tokens, admin)
        )
        conn.commit()

        config = conn.execute(
            "SELECT min_tokens, max_tokens, updated_at, updated_by FROM checkin_config WHERE id=1"
        ).fetchone()

        return {
            "ok": True,
            "config": dict(config) if config else {}
        }
    finally:
        conn.close()


def _sync_get_checkin_stats(days: int = 7) -> dict:
    conn = _get_conn()
    try:
        # Daily stats
        daily_stats = conn.execute(
            """SELECT checkin_date as date, COUNT(*) as checkin_count,
                      COALESCE(SUM(tokens_awarded), 0) as total_tokens_awarded
               FROM checkin_records
               WHERE checkin_date >= date('now', 'localtime', '-' || ? || ' days')
               GROUP BY checkin_date
               ORDER BY checkin_date DESC""",
            (days,)
        ).fetchall()

        # Summary stats
        summary = conn.execute(
            """SELECT COUNT(*) as total_checkins,
                      COALESCE(SUM(tokens_awarded), 0) as total_tokens_awarded,
                      COUNT(DISTINCT user_id) as unique_users
               FROM checkin_records
               WHERE checkin_date >= date('now', 'localtime', '-' || ? || ' days')""",
            (days,)
        ).fetchone()

        stats_list = [dict(r) for r in daily_stats]
        for item in stats_list:
            item["total_usd_awarded"] = round(item["total_tokens_awarded"] * LEGACY_BALANCE_USD_PER_1M / 1e6, 6)
        summary_dict = dict(summary) if summary else {}

        # Calculate average
        if summary_dict.get("total_checkins", 0) > 0:
            summary_dict["avg_tokens_per_checkin"] = int(
                summary_dict["total_tokens_awarded"] / summary_dict["total_checkins"]
            )
        else:
            summary_dict["avg_tokens_per_checkin"] = 0
        summary_dict["total_usd_awarded"] = round(summary_dict.get("total_tokens_awarded", 0) * LEGACY_BALANCE_USD_PER_1M / 1e6, 6)
        summary_dict["avg_usd_per_checkin"] = round(summary_dict.get("avg_tokens_per_checkin", 0) * LEGACY_BALANCE_USD_PER_1M / 1e6, 6)

        return {
            "stats": stats_list,
            "summary": summary_dict
        }
    finally:
        conn.close()


def _sync_get_image_playground_quota(user_id: int, daily_limit: int = 3) -> dict:
    conn = _get_conn()
    try:
        conn.execute(
            """UPDATE image_playground_usage
               SET status='error'
               WHERE status='pending'
                 AND datetime(created_at) < datetime('now','localtime','-10 minutes')"""
        )
        used = conn.execute(
            """SELECT COUNT(*) FROM image_playground_usage
               WHERE user_id=? AND source_mode='nexus' AND status IN ('pending','success')
                 AND date(created_at)=date('now','localtime')""",
            (user_id,),
        ).fetchone()[0]
        return {
            "daily_limit": daily_limit,
            "used": used,
            "remaining": max(0, daily_limit - used),
        }
    finally:
        conn.close()


def _sync_reserve_image_playground_usage(user_id: int, action: str, model: str, daily_limit: int = 3) -> int | None:
    conn = _get_conn()
    try:
        conn.execute(
            """UPDATE image_playground_usage
               SET status='error'
               WHERE status='pending'
                 AND datetime(created_at) < datetime('now','localtime','-10 minutes')"""
        )
        used = conn.execute(
            """SELECT COUNT(*) FROM image_playground_usage
               WHERE user_id=? AND source_mode='nexus' AND status IN ('pending','success')
                 AND date(created_at)=date('now','localtime')""",
            (user_id,),
        ).fetchone()[0]
        if used >= daily_limit:
            return None
        cursor = conn.execute(
            """INSERT INTO image_playground_usage
               (user_id, action, source_mode, model, status)
               VALUES (?, ?, 'nexus', ?, 'pending')""",
            (user_id, action, model),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def _sync_log_image_playground_usage(
    user_id: int,
    action: str,
    source_mode: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    status: str = "success",
) -> bool:
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO image_playground_usage
               (user_id, action, source_mode, model, input_tokens, output_tokens, cost_usd, status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                user_id,
                action,
                source_mode,
                model,
                int(input_tokens or 0),
                int(output_tokens or 0),
                round(float(cost_usd or 0.0), 8),
                status,
            ),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def _sync_finalize_image_playground_usage(
    usage_id: int,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    status: str = "success",
) -> bool:
    conn = _get_conn()
    try:
        conn.execute(
            """UPDATE image_playground_usage
               SET input_tokens=?, output_tokens=?, cost_usd=?, status=?
               WHERE id=?""",
            (int(input_tokens or 0), int(output_tokens or 0), round(float(cost_usd or 0.0), 8), status, usage_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


# ── Playground image task store (SQLite-backed, cross-worker safe) ──────────

def _sync_create_playground_task(task_id: str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO playground_tasks (task_id, status, created_at) VALUES (?, 'processing', ?)",
            (task_id, time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def _sync_update_playground_task(task_id: str, status: str, result_json: str | None = None, error_message: str | None = None) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE playground_tasks SET status=?, result_json=?, error_message=? WHERE task_id=?",
            (status, result_json, error_message, task_id),
        )
        conn.commit()
    finally:
        conn.close()


def _sync_get_playground_task(task_id: str) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT task_id, status, result_json, error_message, created_at FROM playground_tasks WHERE task_id=?",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


def _sync_cleanup_playground_tasks(ttl: float = 600.0) -> int:
    conn = _get_conn()
    try:
        cutoff = time.time() - ttl
        cur = conn.execute("DELETE FROM playground_tasks WHERE created_at < ?", (cutoff,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


async def create_playground_task(task_id: str) -> None:
    await asyncio.to_thread(_sync_create_playground_task, task_id)


async def update_playground_task(task_id: str, status: str, result_json: str | None = None, error_message: str | None = None) -> None:
    await asyncio.to_thread(_sync_update_playground_task, task_id, status, result_json, error_message)


async def get_playground_task(task_id: str) -> dict | None:
    return await asyncio.to_thread(_sync_get_playground_task, task_id)


async def cleanup_playground_tasks(ttl: float = 600.0) -> int:
    return await asyncio.to_thread(_sync_cleanup_playground_tasks, ttl)


def _sync_get_balance_history(user_id: int, limit: int = 200) -> dict:
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT id, event_type, delta_usd, balance_after_usd, related_model, description, created_at
               FROM (
                 SELECT id, event_type, delta_usd, balance_after_usd, related_model, description, created_at
                 FROM balance_events
                 WHERE user_id=?
                 ORDER BY datetime(created_at) DESC, id DESC
                 LIMIT ?
               ) recent
               ORDER BY datetime(created_at) ASC, id ASC""",
            (user_id, limit)
        ).fetchall()

        total_change = 0.0
        spend_cum = 0.0
        checkin_cum = 0.0
        welfare_cum = 0.0
        adjustment_cum = 0.0
        if rows:
            first = rows[0]
            prior = conn.execute(
                """SELECT
                     COALESCE(SUM(delta_usd), 0) AS total_delta,
                     COALESCE(SUM(CASE WHEN event_type='spend' THEN delta_usd ELSE 0 END), 0) AS spend_delta,
                     COALESCE(SUM(CASE WHEN event_type='checkin' THEN delta_usd ELSE 0 END), 0) AS checkin_delta,
                     COALESCE(SUM(CASE WHEN event_type='welfare' THEN delta_usd ELSE 0 END), 0) AS welfare_delta,
                     COALESCE(SUM(CASE WHEN event_type NOT IN ('spend', 'checkin', 'welfare') THEN delta_usd ELSE 0 END), 0) AS adjustment_delta
                   FROM balance_events
                   WHERE user_id=?
                     AND (
                       datetime(created_at) < datetime(?)
                       OR (datetime(created_at) = datetime(?) AND id < ?)
                     )""",
                (user_id, first["created_at"], first["created_at"], first["id"]),
            ).fetchone()
            total_change = round(float(prior["total_delta"] or 0.0), 8)
            spend_cum = round(float(prior["spend_delta"] or 0.0), 8)
            checkin_cum = round(float(prior["checkin_delta"] or 0.0), 8)
            welfare_cum = round(float(prior["welfare_delta"] or 0.0), 8)
            adjustment_cum = round(float(prior["adjustment_delta"] or 0.0), 8)
        points = []

        for row in rows:
            item = dict(row)
            delta = round(float(item.get("delta_usd") or 0.0), 8)
            total_change += delta
            event_type = item.get("event_type")
            spend_delta = 0.0
            checkin_delta = 0.0
            welfare_delta = 0.0
            adjustment_delta = 0.0

            if event_type == "spend":
                spend_delta = delta
                spend_cum += delta
            elif event_type == "checkin":
                checkin_delta = delta
                checkin_cum += delta
            elif event_type == "welfare":
                welfare_delta = delta
                welfare_cum += delta
            else:
                adjustment_delta = delta
                adjustment_cum += delta

            points.append({
                "id": item["id"],
                "timestamp": item["created_at"],
                "event_type": event_type,
                "delta_usd": round(delta, 8),
                "balance_after_usd": round(float(item.get("balance_after_usd") or 0.0), 6),
                "related_model": item.get("related_model"),
                "description": item.get("description") or "",
                "total_change_usd": round(total_change, 8),
                "spend_delta_usd": round(spend_delta, 8),
                "checkin_delta_usd": round(checkin_delta, 8),
                "welfare_delta_usd": round(welfare_delta, 8),
                "adjustment_delta_usd": round(adjustment_delta, 8),
                "spend_cumulative_usd": round(spend_cum, 8),
                "checkin_cumulative_usd": round(checkin_cum, 8),
                "welfare_cumulative_usd": round(welfare_cum, 8),
                "adjustment_cumulative_usd": round(adjustment_cum, 8),
            })

        return {"points": points, "count": len(points)}
    finally:
        conn.close()


# ─── Async wrappers ───────────────────────────────────────────────────────────

async def create_user(student_id: str, password: str, display_name: str = None) -> dict:
    return await asyncio.to_thread(_sync_create_user, student_id, password, display_name)

async def create_email_verification(email: str, purpose: str, code_hash: str, client_ip: str = "", user_id: int = None) -> dict:
    return await asyncio.to_thread(_sync_create_email_verification, email, purpose, code_hash, client_ip, user_id)

async def register_user_with_email_verification(student_id: str, password: str, email: str, code_hash: str, display_name: str = None) -> dict:
    return await asyncio.to_thread(_sync_register_user_with_email_verification, student_id, password, email, code_hash, display_name)

async def bind_email_with_verification(user_id: int, email: str, code_hash: str) -> dict:
    return await asyncio.to_thread(_sync_bind_email_with_verification, user_id, email, code_hash)

async def change_password(user_id: int, current_password: str, new_password: str) -> dict:
    return await asyncio.to_thread(_sync_change_password, user_id, current_password, new_password)

async def change_password_with_email_verification(user_id: int, current_password: str, new_password: str, code_hash: str) -> dict:
    return await asyncio.to_thread(_sync_change_password_with_email_verification, user_id, current_password, new_password, code_hash)

async def login_user(student_id: str, password: str) -> Optional[dict]:
    return await asyncio.to_thread(_sync_login_user, student_id, password)

async def get_user_by_student_id(student_id: str) -> Optional[dict]:
    return await asyncio.to_thread(_sync_get_user_by_student_id, student_id)

async def reset_password_with_email_verification(student_id: str, email: str, code_hash: str, new_password: str) -> dict:
    return await asyncio.to_thread(_sync_reset_password_with_email_verification, student_id, email, code_hash, new_password)

async def get_user(user_id: int) -> Optional[dict]:
    return await asyncio.to_thread(_sync_get_user, user_id)

async def get_all_users() -> List[dict]:
    return await asyncio.to_thread(_sync_get_all_users)

async def update_user(user_id: int, **kwargs) -> bool:
    return await asyncio.to_thread(_sync_update_user, user_id, **kwargs)

async def update_profile(user_id: int, display_name: str = None, avatar: str = None) -> dict:
    return await asyncio.to_thread(_sync_update_profile, user_id, display_name, avatar)

async def create_key(user_id: int, name: str, group_name: str = 'claude', expires_at: str = None, quota_limit: int = 0) -> dict:
    return await asyncio.to_thread(_sync_create_key, user_id, name, group_name, expires_at, quota_limit)

async def list_keys(user_id: int) -> List[dict]:
    return await asyncio.to_thread(_sync_list_keys, user_id)

async def delete_key(key_id: int, user_id: int) -> bool:
    return await asyncio.to_thread(_sync_delete_key, key_id, user_id)

async def validate_key(full_key: str) -> dict | str:
    return await asyncio.to_thread(_sync_validate_key, full_key)

async def log_usage(user_id: int, key_prefix: str, model: str,
                    input_tokens: int, output_tokens: int, status: str = "success",
                    cache_read_tokens: int = 0, cache_creation_tokens: int = 0,
                    cost_usd: float = 0.0):
    await asyncio.to_thread(
        _sync_log_usage,
        user_id,
        key_prefix,
        model,
        input_tokens,
        output_tokens,
        status,
        cache_read_tokens,
        cache_creation_tokens,
        cost_usd,
    )

async def get_logs(user_id: int, limit: int = 50, offset: int = 0) -> List[dict]:
    return await asyncio.to_thread(_sync_get_logs, user_id, limit, offset)

async def get_stats(user_id: int) -> dict:
    return await asyncio.to_thread(_sync_get_stats, user_id)

async def admin_get_stats() -> dict:
    return await asyncio.to_thread(_sync_admin_get_stats)

async def admin_get_full_stats() -> dict:
    return await asyncio.to_thread(_sync_admin_get_full_stats)

async def cleanup_usage_models() -> dict:
    return await asyncio.to_thread(_sync_cleanup_usage_models)

async def admin_get_all_keys() -> List[dict]:
    return await asyncio.to_thread(_sync_admin_get_all_keys)

async def admin_toggle_key(key_id: int, is_active: int) -> bool:
    return await asyncio.to_thread(_sync_admin_toggle_key, key_id, is_active)

async def admin_delete_any_key(key_id: int) -> bool:
    return await asyncio.to_thread(_sync_admin_delete_any_key, key_id)

async def admin_add_quota(user_id: int, amount: int) -> bool:
    return await asyncio.to_thread(_sync_admin_add_quota, user_id, amount)

async def admin_set_quota(user_id: int, amount: int) -> bool:
    return await asyncio.to_thread(_sync_admin_set_quota, user_id, amount)

async def admin_get_all_logs(limit: int = 50, offset: int = 0) -> List[dict]:
    return await asyncio.to_thread(_sync_admin_get_all_logs, limit, offset)

async def admin_save_announcement(content: str, created_by: str = "admin") -> int:
    return await asyncio.to_thread(_sync_admin_save_announcement, content, created_by)

async def admin_get_announcements(limit: int = 20) -> List[dict]:
    return await asyncio.to_thread(_sync_admin_get_announcements, limit)

async def admin_delete_announcement(ann_id: int) -> bool:
    return await asyncio.to_thread(_sync_admin_delete_announcement, ann_id)

def validate_key_sync(full_key: str) -> dict | str:
    """Sync version for use in middleware/handlers."""
    return _sync_validate_key(full_key)

def log_usage_sync(user_id: int, key_prefix: str, model: str,
                   input_tokens: int, output_tokens: int, status: str = "success",
                   cache_read_tokens: int = 0, cache_creation_tokens: int = 0,
                   cost_usd: float = 0.0):
    _sync_log_usage(user_id, key_prefix, model, input_tokens, output_tokens, status, cache_read_tokens, cache_creation_tokens, cost_usd)


async def checkin_user(user_id: int) -> dict:
    return await asyncio.to_thread(_sync_checkin_user, user_id)


async def get_checkin_status(user_id: int, date_str: str) -> dict:
    return await asyncio.to_thread(_sync_get_checkin_status, user_id, date_str)


async def get_checkin_history(user_id: int, limit: int = 30) -> dict:
    return await asyncio.to_thread(_sync_get_checkin_history, user_id, limit)


async def get_checkin_config() -> dict:
    return await asyncio.to_thread(_sync_get_checkin_config)


async def update_checkin_config(min_tokens: int, max_tokens: int, admin: str) -> dict:
    return await asyncio.to_thread(_sync_update_checkin_config, min_tokens, max_tokens, admin)


async def get_checkin_stats(days: int = 7) -> dict:
    return await asyncio.to_thread(_sync_get_checkin_stats, days)


async def get_balance_history(user_id: int, limit: int = 200) -> dict:
    return await asyncio.to_thread(_sync_get_balance_history, user_id, limit)


async def get_image_playground_quota(user_id: int, daily_limit: int = 3) -> dict:
    return await asyncio.to_thread(_sync_get_image_playground_quota, user_id, daily_limit)


async def reserve_image_playground_usage(user_id: int, action: str, model: str, daily_limit: int = 3) -> int | None:
    return await asyncio.to_thread(_sync_reserve_image_playground_usage, user_id, action, model, daily_limit)


async def log_image_playground_usage(
    user_id: int,
    action: str,
    source_mode: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    status: str = "success",
    ) -> bool:
    return await asyncio.to_thread(
        _sync_log_image_playground_usage,
        user_id,
        action,
        source_mode,
        model,
        input_tokens,
        output_tokens,
        cost_usd,
        status,
    )


async def finalize_image_playground_usage(
    usage_id: int,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    status: str = "success",
) -> bool:
    return await asyncio.to_thread(
        _sync_finalize_image_playground_usage,
        usage_id,
        input_tokens,
        output_tokens,
        cost_usd,
        status,
    )


def _sync_get_today_checkin_leaderboard(limit: int = 50) -> dict:
    """Get today's checkin leaderboard with user info"""
    conn = _get_conn()
    try:
        today = date.today().isoformat()
        rows = conn.execute(
            """SELECT
                   u.student_id,
                   u.display_name,
                   c.tokens_awarded,
                   c.created_at
               FROM checkin_records c
               JOIN users u ON c.user_id = u.id
               WHERE c.checkin_date = ?
               ORDER BY c.tokens_awarded DESC, c.created_at ASC
               LIMIT ?""",
            (today, limit)
        ).fetchall()

        leaderboard = []
        for idx, row in enumerate(rows, 1):
            leaderboard.append({
                "rank": idx,
                "student_id": row["student_id"],
                "display_name": row["display_name"],
                "tokens_awarded": row["tokens_awarded"],
                "usd_awarded": round(row["tokens_awarded"] * LEGACY_BALANCE_USD_PER_1M / 1e6, 6),
                "checkin_time": row["created_at"]
            })

        return {
            "ok": True,
            "date": today,
            "leaderboard": leaderboard,
            "total_count": len(leaderboard)
        }
    finally:
        conn.close()


async def get_today_checkin_leaderboard(limit: int = 50) -> dict:
    return await asyncio.to_thread(_sync_get_today_checkin_leaderboard, limit)
