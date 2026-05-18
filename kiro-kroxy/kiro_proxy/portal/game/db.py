"""Game-module persistence layer.

Uses stdlib sqlite3 + asyncio.to_thread (mirrors portal/db.py style).
Shares the same portal.db file so cross-module joins (e.g. users) remain trivial.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from .. import db as portal_db

logger = logging.getLogger(__name__)

DB_PATH: Path = portal_db.DB_PATH
STATIC_DIR = Path(__file__).resolve().parents[2] / "web" / "static"

GAME_SCHEMA = """
CREATE TABLE IF NOT EXISTS game_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    world_bible_json TEXT NOT NULL DEFAULT '{}',
    character_json TEXT NOT NULL DEFAULT '{}',
    current_state_json TEXT NOT NULL DEFAULT '{}',
    codex_json TEXT NOT NULL DEFAULT '{}',
    genre TEXT NOT NULL DEFAULT 'xianxia',
    cover_url TEXT,
    chapter_idx INTEGER DEFAULT 1,
    turn_idx INTEGER DEFAULT 0,
    total_tokens_in INTEGER DEFAULT 0,
    total_tokens_out INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    ending_slug TEXT,
    ending_text TEXT,
    score INTEGER DEFAULT 0,
    started_at TEXT DEFAULT (datetime('now', 'localtime')),
    ended_at TEXT
);
CREATE TABLE IF NOT EXISTS _game_migrations (key TEXT PRIMARY KEY);
CREATE INDEX IF NOT EXISTS idx_game_runs_user ON game_runs(user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_game_runs_active ON game_runs(user_id, status);
CREATE INDEX IF NOT EXISTS idx_game_runs_score ON game_runs(score DESC, ended_at DESC);

CREATE TABLE IF NOT EXISTS game_scenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES game_runs(id) ON DELETE CASCADE,
    turn_idx INTEGER NOT NULL,
    is_keynote INTEGER DEFAULT 0,
    narrative TEXT NOT NULL DEFAULT '',
    choices_json TEXT NOT NULL DEFAULT '[]',
    player_action TEXT,
    state_delta_json TEXT DEFAULT '{}',
    visual_tag_json TEXT DEFAULT '{}',
    image_url TEXT,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_game_scenes_run ON game_scenes(run_id, turn_idx);

CREATE TABLE IF NOT EXISTS game_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES game_runs(id) ON DELETE CASCADE,
    chapter_idx INTEGER NOT NULL,
    summary TEXT NOT NULL,
    covers_turn_from INTEGER,
    covers_turn_to INTEGER,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_game_summaries_run ON game_summaries(run_id, chapter_idx);

CREATE TABLE IF NOT EXISTS game_image_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_hash TEXT UNIQUE NOT NULL,
    image_url TEXT NOT NULL,
    cost_usd REAL DEFAULT 0,
    hit_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

-- M5: CG 收藏所有权。原作者的每张 CG 自动获得一条 source='origin' 的 ownership。
-- 交易/赠送/成就奖励再各自插一条（同 user × scene 组合用 UNIQUE 防重复）。
CREATE TABLE IF NOT EXISTS cg_ownerships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    scene_id INTEGER NOT NULL REFERENCES game_scenes(id) ON DELETE CASCADE,
    origin_user_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    rarity TEXT DEFAULT 'common',
    acquired_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(user_id, scene_id)
);
CREATE INDEX IF NOT EXISTS idx_cg_user ON cg_ownerships(user_id, acquired_at DESC);
CREATE INDEX IF NOT EXISTS idx_cg_scene ON cg_ownerships(scene_id);

-- M5: 玩家成就。slug 唯一约束保证同一成就不会反复授予。
CREATE TABLE IF NOT EXISTS achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT,
    payload_json TEXT DEFAULT '{}',
    awarded_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(user_id, slug)
);
CREATE INDEX IF NOT EXISTS idx_achv_user ON achievements(user_id, awarded_at DESC);
CREATE INDEX IF NOT EXISTS idx_achv_slug ON achievements(slug);

-- M5: "开荒"成就 — 首登 (genre + ending_slug) 组合的全局锁。
-- 每个组合只允许第一个抵达者获得 pioneer:<genre>:<ending_slug> 成就。
CREATE TABLE IF NOT EXISTS pioneer_locks (
    slug TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    run_id INTEGER NOT NULL,
    locked_at TEXT DEFAULT (datetime('now', 'localtime'))
);

-- M6 预备：奖励池 + 用户灵玉额度。M5 期间只读出 0 即可。
CREATE TABLE IF NOT EXISTS reward_pool (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    balance_usd REAL NOT NULL DEFAULT 0,
    total_paid_out_usd REAL NOT NULL DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
INSERT OR IGNORE INTO reward_pool (id, balance_usd) VALUES (1, 0);

-- M6: CG 赠送流水。source='gift' 的 ownership 指向这张 scene 后，这里记录来龙去脉。
-- trade offer 体系以后再加 (kind='trade' 用另一条路径)，暂只支持单张 gift。
CREATE TABLE IF NOT EXISTS cg_transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,                     -- 'gift' (PR1) | 'trade' (PR2)
    from_user_id INTEGER NOT NULL,
    to_user_id INTEGER NOT NULL,
    scene_id INTEGER NOT NULL REFERENCES game_scenes(id) ON DELETE CASCADE,
    message TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_cg_transfers_from ON cg_transfers(from_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cg_transfers_to   ON cg_transfers(to_user_id, created_at DESC);

-- M6: 成就兑换流水 + 金额审计。achievement_id UNIQUE 保证一次性。
-- 我们还在 achievements 表本身追加 redeemed_at / reward_usd 两列（通过迁移）。
CREATE TABLE IF NOT EXISTS achievement_redemptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    achievement_id INTEGER NOT NULL UNIQUE,
    reward_usd REAL NOT NULL,
    redeemed_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_ach_redeem_user ON achievement_redemptions(user_id, redeemed_at DESC);

-- M6 · PR2: 交易挂单。offered/wanted 以 JSON array 存 scene_id；accept 成功
-- 后 status 翻成 'accepted' 并在 cg_transfers 里写多条 offer_id 关联的 trade
-- 流水。from != to 由 route 层强制。
CREATE TABLE IF NOT EXISTS cg_trade_offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_user_id INTEGER NOT NULL,
    to_user_id INTEGER NOT NULL,
    offered_scene_ids TEXT NOT NULL,
    wanted_scene_ids TEXT NOT NULL,
    message TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    responded_at TEXT,
    expires_at TEXT NOT NULL DEFAULT (datetime('now', '+7 days', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_trade_from ON cg_trade_offers(from_user_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trade_to   ON cg_trade_offers(to_user_id, status, created_at DESC);

-- M7: 跳蚤市场。任何人可挂牌自己的 CG，定价格；其他人直接购买。
CREATE TABLE IF NOT EXISTS marketplace_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id INTEGER NOT NULL,
    scene_id INTEGER NOT NULL REFERENCES game_scenes(id) ON DELETE CASCADE,
    price_usd REAL NOT NULL,
    message TEXT,
    status TEXT NOT NULL DEFAULT 'active',   -- active | sold | cancelled
    buyer_id INTEGER,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    sold_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_market_seller ON marketplace_listings(seller_id, status);
CREATE INDEX IF NOT EXISTS idx_market_active ON marketplace_listings(status, created_at DESC);

-- M7: 联机基础 — 共享会话。两个玩家同时进入同一个故事世界时创建。
CREATE TABLE IF NOT EXISTS shared_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    genre TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting',  -- waiting | active | ended
    world_bible_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS shared_session_players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES shared_sessions(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    run_id INTEGER REFERENCES game_runs(id),
    joined_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(session_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_ssp_session ON shared_session_players(session_id);
CREATE INDEX IF NOT EXISTS idx_ssp_user    ON shared_session_players(user_id);
"""


def _get_conn() -> sqlite3.Connection:
    """Open a fresh connection. Schema/migrations are NOT run here — they're
    executed once at startup via ``init_tables``. Per-request connects stay
    cheap (just connect + PRAGMAs)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Keep foreign-key enforcement on for ON DELETE CASCADE on cg_ownerships etc.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _sync_init_tables() -> None:
    """Run CREATE TABLE IF NOT EXISTS + idempotent ALTER migrations once.

    Called from ``init_tables`` during portal lifespan startup. After this
    returns, ``_get_conn`` is a cheap connect.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    try:
        conn.executescript(GAME_SCHEMA)
        # Idempotent ALTER for DBs created before current_state_json existed.
        already = conn.execute(
            "SELECT 1 FROM _game_migrations WHERE key='add_current_state_json'"
        ).fetchone()
        if not already:
            try:
                conn.execute(
                    "ALTER TABLE game_runs ADD COLUMN current_state_json TEXT NOT NULL DEFAULT '{}'"
                )
            except sqlite3.OperationalError:
                pass
            conn.execute(
                "INSERT OR IGNORE INTO _game_migrations (key) VALUES ('add_current_state_json')"
            )
        # M4c: add codex_json + ending_text.
        if not conn.execute(
            "SELECT 1 FROM _game_migrations WHERE key='add_codex_and_ending_text'"
        ).fetchone():
            for ddl in (
                "ALTER TABLE game_runs ADD COLUMN codex_json TEXT NOT NULL DEFAULT '{}'",
                "ALTER TABLE game_runs ADD COLUMN ending_text TEXT",
            ):
                try:
                    conn.execute(ddl)
                except sqlite3.OperationalError:
                    pass
            conn.execute(
                "INSERT OR IGNORE INTO _game_migrations (key) VALUES ('add_codex_and_ending_text')"
            )
        # M4b: add genre column.
        if not conn.execute(
            "SELECT 1 FROM _game_migrations WHERE key='add_genre'"
        ).fetchone():
            try:
                conn.execute(
                    "ALTER TABLE game_runs ADD COLUMN genre TEXT NOT NULL DEFAULT 'xianxia'"
                )
            except sqlite3.OperationalError:
                pass
            conn.execute(
                "INSERT OR IGNORE INTO _game_migrations (key) VALUES ('add_genre')"
            )
        # M6: achievements 加 redeemed_at + reward_usd；reward_pool 加 total_paid_out_usd。
        if not conn.execute(
            "SELECT 1 FROM _game_migrations WHERE key='add_redemption_cols'"
        ).fetchone():
            for ddl in (
                "ALTER TABLE achievements ADD COLUMN redeemed_at TEXT",
                "ALTER TABLE achievements ADD COLUMN reward_usd REAL NOT NULL DEFAULT 0",
                "ALTER TABLE reward_pool  ADD COLUMN total_paid_out_usd REAL NOT NULL DEFAULT 0",
            ):
                try:
                    conn.execute(ddl)
                except sqlite3.OperationalError:
                    pass
            conn.execute(
                "INSERT OR IGNORE INTO _game_migrations (key) VALUES ('add_redemption_cols')"
            )
        # M6 · PR2: cg_transfers 关联 trade offer
        if not conn.execute(
            "SELECT 1 FROM _game_migrations WHERE key='add_trade_offer_link'"
        ).fetchone():
            try:
                conn.execute("ALTER TABLE cg_transfers ADD COLUMN offer_id INTEGER")
            except sqlite3.OperationalError:
                pass
            conn.execute(
                "INSERT OR IGNORE INTO _game_migrations (key) VALUES ('add_trade_offer_link')"
            )
        conn.commit()
    finally:
        conn.close()


async def init_tables() -> None:
    await asyncio.to_thread(_sync_init_tables)


# ─── Runs ─────────────────────────────────────────────────────────────────────


def _row_to_run(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for key in ("world_bible_json", "character_json", "current_state_json", "codex_json"):
        raw = data.get(key) or "{}"
        try:
            data[key[:-5]] = json.loads(raw)
        except json.JSONDecodeError:
            data[key[:-5]] = {}
    return data


def _sync_get_active_run(user_id: int) -> dict[str, Any] | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM game_runs WHERE user_id=? AND status IN ('generating','running') "
            "ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        return _row_to_run(row)
    finally:
        conn.close()


async def get_active_run(user_id: int) -> dict[str, Any] | None:
    return await asyncio.to_thread(_sync_get_active_run, user_id)


def _sync_get_run(run_id: int, user_id: int | None = None) -> dict[str, Any] | None:
    conn = _get_conn()
    try:
        if user_id is None:
            row = conn.execute("SELECT * FROM game_runs WHERE id=?", (run_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM game_runs WHERE id=? AND user_id=?", (run_id, user_id)
            ).fetchone()
        return _row_to_run(row)
    finally:
        conn.close()


async def get_run(run_id: int, user_id: int | None = None) -> dict[str, Any] | None:
    return await asyncio.to_thread(_sync_get_run, run_id, user_id)


def _sync_create_run(user_id: int) -> int:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO game_runs (user_id, status) VALUES (?, 'generating')",
            (user_id,),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


async def create_run(user_id: int) -> int:
    return await asyncio.to_thread(_sync_create_run, user_id)


def _sync_update_run(run_id: int, **fields: Any) -> None:
    if not fields:
        return
    cols = []
    vals: list[Any] = []
    for key, value in fields.items():
        if key in {"world_bible", "character", "current_state", "codex"}:
            cols.append(f"{key}_json=?")
            vals.append(json.dumps(value, ensure_ascii=False))
        else:
            cols.append(f"{key}=?")
            vals.append(value)
    vals.append(run_id)
    conn = _get_conn()
    try:
        conn.execute(f"UPDATE game_runs SET {', '.join(cols)} WHERE id=?", vals)
        conn.commit()
    finally:
        conn.close()


async def update_run(run_id: int, **fields: Any) -> None:
    await asyncio.to_thread(lambda: _sync_update_run(run_id, **fields))


def _sync_list_history(user_id: int, limit: int = 30) -> list[dict[str, Any]]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, status, cover_url, chapter_idx, turn_idx, ending_slug, score, "
            "started_at, ended_at FROM game_runs WHERE user_id=? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


async def list_history(user_id: int, limit: int = 30) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_sync_list_history, user_id, limit)


def _sync_recent_genres(user_id: int, limit: int = 5) -> list[str]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT genre FROM game_runs WHERE user_id=? AND genre IS NOT NULL "
            "ORDER BY id DESC LIMIT ?",
            (user_id, max(1, int(limit or 5))),
        ).fetchall()
        return [str(r["genre"]) for r in rows if r["genre"]]
    finally:
        conn.close()


async def recent_genres(user_id: int, limit: int = 5) -> list[str]:
    return await asyncio.to_thread(_sync_recent_genres, user_id, limit)


def _sync_leaderboard(scope: str = "all", limit: int = 50) -> list[dict[str, Any]]:
    conn = _get_conn()
    try:
        if scope == "weekly":
            where = (
                "r.status='ended' AND r.ended_at >= datetime('now', '-7 days', 'localtime')"
            )
        else:
            where = "r.status='ended'"
        rows = conn.execute(
            f"SELECT r.id, r.user_id, r.score, r.ending_slug, r.cover_url, r.turn_idx, "
            f"r.ended_at, u.display_name, u.student_id "
            f"FROM game_runs r LEFT JOIN users u ON r.user_id=u.id "
            f"WHERE {where} ORDER BY r.score DESC, r.ended_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


async def leaderboard(scope: str = "all", limit: int = 50) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_sync_leaderboard, scope, limit)


# ─── Composite writes (transactional) ─────────────────────────────────────────


def _sync_commit_turn(
    run_id: int,
    *,
    scene: dict[str, Any],
    run_updates: dict[str, Any],
) -> int:
    """Insert a new scene and update the run row atomically.

    Returns the new scene id. Rolls back on any failure so the run never ends
    up with a persisted scene but a stale turn_idx.

    ``scene`` keys:
      turn_idx, is_keynote, narrative, choices, player_action,
      state_delta, visual_tag, image_url, tokens_in, tokens_out

    ``run_updates``: same keys as _sync_update_run (world_bible/character/
    current_state/codex are serialized, the rest stored as-is).
    """
    conn = _get_conn()
    try:
        # Explicit BEGIN to batch the INSERT + UPDATE in one write.
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "INSERT INTO game_scenes "
            "(run_id, turn_idx, is_keynote, narrative, choices_json, player_action, "
            " state_delta_json, visual_tag_json, image_url, tokens_in, tokens_out) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                int(scene["turn_idx"]),
                1 if scene.get("is_keynote") else 0,
                scene.get("narrative") or "",
                json.dumps(scene.get("choices") or [], ensure_ascii=False),
                scene.get("player_action"),
                json.dumps(scene.get("state_delta") or {}, ensure_ascii=False),
                json.dumps(scene.get("visual_tag") or {}, ensure_ascii=False),
                scene.get("image_url"),
                int(scene.get("tokens_in") or 0),
                int(scene.get("tokens_out") or 0),
            ),
        )
        scene_id = int(cur.lastrowid)

        if run_updates:
            cols: list[str] = []
            vals: list[Any] = []
            for key, value in run_updates.items():
                if key in {"world_bible", "character", "current_state", "codex"}:
                    cols.append(f"{key}_json=?")
                    vals.append(json.dumps(value, ensure_ascii=False))
                else:
                    cols.append(f"{key}=?")
                    vals.append(value)
            vals.append(run_id)
            conn.execute(
                f"UPDATE game_runs SET {', '.join(cols)} WHERE id=?", vals
            )

        conn.commit()
        return scene_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def commit_turn(
    run_id: int,
    *,
    scene: dict[str, Any],
    run_updates: dict[str, Any],
) -> int:
    """Async wrapper — see ``_sync_commit_turn``."""
    return await asyncio.to_thread(
        _sync_commit_turn, run_id, scene=scene, run_updates=run_updates
    )


# ─── Scenes ───────────────────────────────────────────────────────────────────


def _sync_insert_scene(
    run_id: int,
    turn_idx: int,
    *,
    is_keynote: bool,
    narrative: str,
    choices: list[dict[str, Any]],
    player_action: str | None,
    state_delta: dict[str, Any],
    visual_tag: dict[str, Any],
    image_url: str | None,
    tokens_in: int,
    tokens_out: int,
) -> int:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO game_scenes "
            "(run_id, turn_idx, is_keynote, narrative, choices_json, player_action, "
            " state_delta_json, visual_tag_json, image_url, tokens_in, tokens_out) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                turn_idx,
                1 if is_keynote else 0,
                narrative,
                json.dumps(choices, ensure_ascii=False),
                player_action,
                json.dumps(state_delta, ensure_ascii=False),
                json.dumps(visual_tag, ensure_ascii=False),
                image_url,
                tokens_in,
                tokens_out,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


async def insert_scene(
    run_id: int,
    turn_idx: int,
    *,
    is_keynote: bool,
    narrative: str,
    choices: list[dict[str, Any]],
    player_action: str | None,
    state_delta: dict[str, Any],
    visual_tag: dict[str, Any],
    image_url: str | None,
    tokens_in: int,
    tokens_out: int,
) -> int:
    return await asyncio.to_thread(
        _sync_insert_scene,
        run_id,
        turn_idx,
        is_keynote=is_keynote,
        narrative=narrative,
        choices=choices,
        player_action=player_action,
        state_delta=state_delta,
        visual_tag=visual_tag,
        image_url=image_url,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )


def _sync_list_scenes(run_id: int, from_turn: int = 0, limit: int = 200) -> list[dict[str, Any]]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM game_scenes WHERE run_id=? AND turn_idx>=? "
            "ORDER BY turn_idx ASC LIMIT ?",
            (run_id, from_turn, limit),
        ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            for key in ("choices_json", "state_delta_json", "visual_tag_json"):
                raw = item.pop(key, None) or ("[]" if key == "choices_json" else "{}")
                try:
                    item[key[:-5]] = json.loads(raw)
                except json.JSONDecodeError:
                    item[key[:-5]] = [] if key == "choices_json" else {}
            out.append(item)
        return out
    finally:
        conn.close()


async def list_scenes(run_id: int, from_turn: int = 0, limit: int = 200) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_sync_list_scenes, run_id, from_turn, limit)


def _sync_update_scene_image(scene_id: int, image_url: str) -> None:
    conn = _get_conn()
    try:
        conn.execute("UPDATE game_scenes SET image_url=? WHERE id=?", (image_url, scene_id))
        conn.commit()
    finally:
        conn.close()


async def update_scene_image(scene_id: int, image_url: str) -> None:
    await asyncio.to_thread(_sync_update_scene_image, scene_id, image_url)


# ─── Summaries (long-term memory) ─────────────────────────────────────────────


def _sync_insert_summary(
    run_id: int, chapter_idx: int, summary: str, turn_from: int, turn_to: int
) -> int:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO game_summaries (run_id, chapter_idx, summary, covers_turn_from, covers_turn_to) "
            "VALUES (?,?,?,?,?)",
            (run_id, chapter_idx, summary, turn_from, turn_to),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


async def insert_summary(
    run_id: int, chapter_idx: int, summary: str, turn_from: int, turn_to: int
) -> int:
    return await asyncio.to_thread(
        _sync_insert_summary, run_id, chapter_idx, summary, turn_from, turn_to
    )


def _sync_list_summaries(run_id: int) -> list[dict[str, Any]]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT chapter_idx, summary, covers_turn_from, covers_turn_to "
            "FROM game_summaries WHERE run_id=? ORDER BY chapter_idx ASC",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


async def list_summaries(run_id: int) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_sync_list_summaries, run_id)


# ─── Image cache ──────────────────────────────────────────────────────────────


def _sync_get_cached_image(tag_hash: str) -> str | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT image_url FROM game_image_cache WHERE tag_hash=?", (tag_hash,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE game_image_cache SET hit_count=hit_count+1 WHERE tag_hash=?",
                (tag_hash,),
            )
            conn.commit()
            return row["image_url"]
        return None
    finally:
        conn.close()


async def get_cached_image(tag_hash: str) -> str | None:
    return await asyncio.to_thread(_sync_get_cached_image, tag_hash)


def _sync_cache_image(tag_hash: str, image_url: str, cost_usd: float) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO game_image_cache (tag_hash, image_url, cost_usd) VALUES (?,?,?)",
            (tag_hash, image_url, cost_usd),
        )
        conn.commit()
    finally:
        conn.close()


async def cache_image(tag_hash: str, image_url: str, cost_usd: float) -> None:
    await asyncio.to_thread(_sync_cache_image, tag_hash, image_url, cost_usd)


# ─── M5: CG ownership ─────────────────────────────────────────────────────────


def _is_valid_gallery_image_url(image_url: Any) -> bool:
    """Gallery CGs must point to a real rendered image.

    Local generated images are served from /static; if the file is gone or the
    URL is blank, the old ownership row is treated as invalid and hidden.
    External URLs are allowed for forward compatibility.
    """
    url = str(image_url or "").strip()
    if not url:
        return False
    if url.startswith(("http://", "https://")):
        return True
    if not url.startswith("/static/"):
        return False
    rel = url.split("?", 1)[0].split("#", 1)[0][len("/static/") :]
    try:
        path = (STATIC_DIR / rel).resolve()
        path.relative_to(STATIC_DIR.resolve())
    except Exception:
        return False
    return path.is_file() and path.stat().st_size > 0


def _sync_grant_ownership(
    user_id: int,
    scene_id: int,
    origin_user_id: int,
    source: str,
    rarity: str = "common",
) -> bool:
    """Insert a CG ownership row. Returns True if a new row was created
    (False on UNIQUE conflict — user already owned this scene)."""
    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO cg_ownerships "
            "(user_id, scene_id, origin_user_id, source, rarity) VALUES (?,?,?,?,?)",
            (user_id, scene_id, origin_user_id, source, rarity),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


async def grant_ownership(
    user_id: int,
    scene_id: int,
    origin_user_id: int,
    source: str = "origin",
    rarity: str = "common",
) -> bool:
    return await asyncio.to_thread(
        _sync_grant_ownership, user_id, scene_id, origin_user_id, source, rarity
    )


def _sync_list_user_gallery(
    user_id: int,
    *,
    genre: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return CG ownerships for a user joined with scene + run metadata.

    Used by both /gallery/me and /gallery/{user_id} (public view).
    """
    conn = _get_conn()
    try:
        params: list[Any] = [user_id]
        where = "o.user_id = ? AND s.image_url IS NOT NULL AND trim(s.image_url) != ''"
        if genre:
            where += " AND r.genre = ?"
            params.append(genre)
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT
              o.id            AS ownership_id,
              o.scene_id      AS scene_id,
              o.source        AS source,
              o.rarity        AS rarity,
              o.acquired_at   AS acquired_at,
              o.origin_user_id AS origin_user_id,
              uo.display_name AS origin_display_name,
              uo.student_id   AS origin_student_id,
              s.image_url     AS image_url,
              s.turn_idx      AS turn_idx,
              s.is_keynote    AS is_keynote,
              r.id            AS run_id,
              r.genre         AS genre,
              r.ending_slug   AS ending_slug
            FROM cg_ownerships o
            LEFT JOIN game_scenes s ON s.id = o.scene_id
            LEFT JOIN game_runs r   ON r.id = s.run_id
            LEFT JOIN users uo      ON uo.id = o.origin_user_id
            WHERE {where}
            ORDER BY o.acquired_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows if _is_valid_gallery_image_url(r["image_url"])]
    finally:
        conn.close()


async def list_user_gallery(
    user_id: int, *, genre: str | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(
        _sync_list_user_gallery, user_id, genre=genre, limit=limit
    )


def _sync_gallery_summary(user_id: int) -> dict[str, Any]:
    """Return per-genre CG counts + totals for a user — small, cacheable."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT r.genre AS genre, s.image_url AS image_url
            FROM cg_ownerships o
            LEFT JOIN game_scenes s ON s.id = o.scene_id
            LEFT JOIN game_runs r   ON r.id = s.run_id
            WHERE o.user_id = ? AND s.image_url IS NOT NULL AND trim(s.image_url) != ''
            """,
            (user_id,),
        ).fetchall()
        per_genre: dict[str, int] = {}
        for r in rows:
            if not _is_valid_gallery_image_url(r["image_url"]):
                continue
            key = r["genre"] or "unknown"
            per_genre[key] = per_genre.get(key, 0) + 1
        return {"total": sum(per_genre.values()), "per_genre": per_genre}
    finally:
        conn.close()


async def gallery_summary(user_id: int) -> dict[str, Any]:
    return await asyncio.to_thread(_sync_gallery_summary, user_id)


def _sync_get_scene_run_owner(scene_id: int) -> dict[str, Any] | None:
    """Look up (scene_id → run user/genre/ending) for ownership grants."""
    conn = _get_conn()
    try:
        row = conn.execute(
            """
            SELECT s.id, s.run_id, s.is_keynote, s.image_url, s.turn_idx,
                   r.user_id AS owner_id, r.genre AS genre,
                   r.ending_slug AS ending_slug
            FROM game_scenes s
            LEFT JOIN game_runs r ON r.id = s.run_id
            WHERE s.id = ?
            """,
            (scene_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


async def get_scene_run_owner(scene_id: int) -> dict[str, Any] | None:
    return await asyncio.to_thread(_sync_get_scene_run_owner, scene_id)


# ─── M5: Achievements ─────────────────────────────────────────────────────────


def _sync_award_achievement(
    user_id: int,
    kind: str,
    slug: str,
    title: str,
    detail: str | None,
    payload: dict[str, Any] | None,
) -> bool:
    """INSERT OR IGNORE — returns True only when a new achievement landed."""
    from . import rewards as game_rewards  # local import avoids cycle risk

    reward_usd = float(game_rewards.reward_for(slug, kind))
    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO achievements "
            "(user_id, kind, slug, title, detail, payload_json, reward_usd) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                user_id,
                kind,
                slug,
                title,
                detail or "",
                json.dumps(payload or {}, ensure_ascii=False),
                reward_usd,
            ),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


async def award_achievement(
    user_id: int,
    *,
    kind: str,
    slug: str,
    title: str,
    detail: str | None = None,
    payload: dict[str, Any] | None = None,
) -> bool:
    return await asyncio.to_thread(
        _sync_award_achievement, user_id, kind, slug, title, detail, payload
    )


def _sync_list_achievements(user_id: int, limit: int = 100) -> list[dict[str, Any]]:
    from . import rewards as game_rewards  # local import — keeps DB module free of circular risk

    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, kind, slug, title, detail, payload_json, awarded_at, "
            "       redeemed_at, reward_usd "
            "FROM achievements WHERE user_id=? ORDER BY awarded_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d.pop("payload_json") or "{}")
            except json.JSONDecodeError:
                d["payload"] = {}
            # Persisted reward_usd may be 0 for pre-migration rows; fall back
            # to the live catalogue so the UI always has something to show.
            live_reward = float(game_rewards.reward_for(d["slug"], d.get("kind")))
            stored = float(d.get("reward_usd") or 0.0)
            d["reward_usd"] = round(stored if stored > 0 else live_reward, 4)
            d["redeemable"] = bool(d["reward_usd"] > 0 and not d.get("redeemed_at"))
            out.append(d)
        return out
    finally:
        conn.close()


async def list_achievements(user_id: int, limit: int = 100) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_sync_list_achievements, user_id, limit)


# ─── M6: Redemption + pool accounting ─────────────────────────────────────────


def _sync_redeem_achievement(
    achievement_id: int, user_id: int
) -> dict[str, Any]:
    """Atomic redemption: charge reward_pool, credit users.balance_usd, mark
    achievements.redeemed_at, insert audit rows.

    Returns ``{"ok": True, "reward_usd": ..., "balance_after": ...}`` on
    success. Raises ``ValueError`` with a ``code`` payload on any rule
    failure so the route layer can map to a 4xx cleanly:

        not_found          — achievement doesn't belong to this user
        already_redeemed   — redeemed_at already set
        not_redeemable     — reward_usd <= 0 (unknown slug)
        pool_empty         — reward_pool.balance_usd < reward_usd
    """
    from . import rewards as game_rewards

    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id, user_id, slug, kind, redeemed_at, reward_usd "
            "FROM achievements WHERE id=? AND user_id=?",
            (achievement_id, user_id),
        ).fetchone()
        if row is None:
            raise ValueError({"code": "not_found"})
        if row["redeemed_at"]:
            raise ValueError({"code": "already_redeemed"})
        stored = float(row["reward_usd"] or 0.0)
        live = float(game_rewards.reward_for(row["slug"], row["kind"]))
        reward_usd = round(stored if stored > 0 else live, 4)
        if reward_usd <= 0:
            raise ValueError({"code": "not_redeemable"})

        pool_row = conn.execute(
            "SELECT balance_usd FROM reward_pool WHERE id=1"
        ).fetchone()
        pool_balance = float((pool_row and pool_row["balance_usd"]) or 0.0)
        if pool_balance < reward_usd:
            raise ValueError({"code": "pool_empty", "pool": pool_balance, "need": reward_usd})

        now = "datetime('now','localtime')"
        conn.execute(
            f"UPDATE achievements SET redeemed_at={now}, reward_usd=? WHERE id=?",
            (reward_usd, achievement_id),
        )
        conn.execute(
            "INSERT INTO achievement_redemptions (user_id, achievement_id, reward_usd) "
            "VALUES (?,?,?)",
            (user_id, achievement_id, reward_usd),
        )
        conn.execute(
            f"UPDATE reward_pool SET balance_usd = balance_usd - ?, "
            f"total_paid_out_usd = total_paid_out_usd + ?, updated_at={now} WHERE id=1",
            (reward_usd, reward_usd),
        )
        conn.execute(
            "UPDATE users SET balance_usd = balance_usd + ? WHERE id=?",
            (reward_usd, user_id),
        )
        balance_after_row = conn.execute(
            "SELECT balance_usd FROM users WHERE id=?", (user_id,)
        ).fetchone()
        balance_after = float((balance_after_row and balance_after_row[0]) or 0.0)
        # Mirror into the portal balance_events audit so admins have a single
        # place to see every credit/debit across the system.
        conn.execute(
            "INSERT INTO balance_events "
            "(user_id, event_type, delta_usd, balance_after_usd, description) "
            "VALUES (?,?,?,?,?)",
            (
                user_id,
                "achievement_redeem",
                round(reward_usd, 8),
                round(balance_after, 6),
                f"redeem achievement #{achievement_id} slug={row['slug']}",
            ),
        )
        conn.commit()
        return {
            "ok": True,
            "reward_usd": reward_usd,
            "balance_after": round(balance_after, 6),
        }
    except ValueError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def redeem_achievement(achievement_id: int, user_id: int) -> dict[str, Any]:
    return await asyncio.to_thread(_sync_redeem_achievement, achievement_id, user_id)


def _sync_get_reward_pool() -> dict[str, float]:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT balance_usd, total_paid_out_usd FROM reward_pool WHERE id=1"
        ).fetchone()
        return {
            "balance_usd": float((row and row["balance_usd"]) or 0.0),
            "total_paid_out_usd": float((row and row["total_paid_out_usd"]) or 0.0),
        }
    finally:
        conn.close()


async def get_reward_pool() -> dict[str, float]:
    return await asyncio.to_thread(_sync_get_reward_pool)


def _sync_topup_reward_pool(
    amount_usd: float, from_user_id: int | None = None
) -> dict[str, float]:
    """Grow the reward pool.

    If ``from_user_id`` is provided, debit that user's balance_usd atomically
    and log a ``balance_events`` row on each side of the transfer. Raises
    ``ValueError`` with ``code='insufficient_balance'`` when the user
    doesn't have enough — we never pull a balance negative.

    When ``from_user_id`` is None this behaves as a plain (signed) top-up,
    used during local testing / admin scripting where funds come from
    nowhere. Negative ``amount_usd`` drains the pool back down; we clamp at
    zero there too.
    """
    amount = float(amount_usd)
    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if from_user_id is not None and amount > 0:
            user_row = conn.execute(
                "SELECT balance_usd FROM users WHERE id=?", (from_user_id,)
            ).fetchone()
            if user_row is None:
                raise ValueError({"code": "user_not_found"})
            current = float(user_row[0] or 0.0)
            if current < amount:
                raise ValueError(
                    {"code": "insufficient_balance", "balance": current, "need": amount}
                )
            conn.execute(
                "UPDATE users SET balance_usd = balance_usd - ? WHERE id=?",
                (amount, from_user_id),
            )
            balance_after_row = conn.execute(
                "SELECT balance_usd FROM users WHERE id=?", (from_user_id,)
            ).fetchone()
            balance_after = float(balance_after_row[0] or 0.0)
            conn.execute(
                "INSERT INTO balance_events "
                "(user_id, event_type, delta_usd, balance_after_usd, description) "
                "VALUES (?,?,?,?,?)",
                (
                    from_user_id,
                    "reward_pool_topup",
                    -round(amount, 8),
                    round(balance_after, 6),
                    f"topup reward_pool by ${amount:.4f}",
                ),
            )
        conn.execute(
            "UPDATE reward_pool SET balance_usd = MAX(0, balance_usd + ?), "
            "updated_at = datetime('now','localtime') WHERE id=1",
            (amount,),
        )
        row = conn.execute(
            "SELECT balance_usd, total_paid_out_usd FROM reward_pool WHERE id=1"
        ).fetchone()
        conn.commit()
        return {
            "balance_usd": float(row["balance_usd"]),
            "total_paid_out_usd": float(row["total_paid_out_usd"]),
        }
    except ValueError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def topup_reward_pool(
    amount_usd: float, from_user_id: int | None = None
) -> dict[str, float]:
    return await asyncio.to_thread(_sync_topup_reward_pool, amount_usd, from_user_id)


# ─── M6: CG gifts ─────────────────────────────────────────────────────────────


def _sync_transfer_cg_gift(
    *,
    from_user_id: int,
    to_user_id: int,
    scene_id: int,
    message: str | None,
) -> dict[str, Any]:
    """Atomically: delete sender's ownership → insert recipient's (kind='gift')
    → log cg_transfers row. Raises ``ValueError`` with a ``code`` payload on
    rule failure.

    Rules enforced here (route layer also pre-checks for nicer errors):
      self_gift          — from == to
      not_owned          — sender doesn't own the scene
      not_transferable   — pioneer CG (is_keynote=1 AND source='origin')
      already_owned      — recipient already has this scene (prevent dupes)
    """
    if from_user_id == to_user_id:
        raise ValueError({"code": "self_gift"})

    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")

        own_row = conn.execute(
            "SELECT o.id, o.origin_user_id, o.source, s.is_keynote "
            "FROM cg_ownerships o LEFT JOIN game_scenes s ON s.id = o.scene_id "
            "WHERE o.user_id=? AND o.scene_id=?",
            (from_user_id, scene_id),
        ).fetchone()
        if own_row is None:
            raise ValueError({"code": "not_owned"})

        # Pioneer lock: an "origin + keynote" CG is the sender's proof of
        # first-landing. Trading or gifting it away would make the scarcity
        # semantics fuzzy, so we hard-block. Non-keynote origin CGs are fine
        # to move around.
        if bool(own_row["is_keynote"]) and own_row["source"] == "origin":
            raise ValueError({"code": "not_transferable"})

        dup = conn.execute(
            "SELECT 1 FROM cg_ownerships WHERE user_id=? AND scene_id=?",
            (to_user_id, scene_id),
        ).fetchone()
        if dup is not None:
            raise ValueError({"code": "already_owned"})

        origin_uid = int(own_row["origin_user_id"])
        conn.execute(
            "DELETE FROM cg_ownerships WHERE id=?", (int(own_row["id"]),)
        )
        conn.execute(
            "INSERT INTO cg_ownerships "
            "(user_id, scene_id, origin_user_id, source, rarity) "
            "VALUES (?,?,?,?,?)",
            (to_user_id, scene_id, origin_uid, "gift", "common"),
        )
        cur = conn.execute(
            "INSERT INTO cg_transfers (kind, from_user_id, to_user_id, scene_id, message) "
            "VALUES ('gift', ?, ?, ?, ?)",
            (from_user_id, to_user_id, scene_id, (message or "").strip() or None),
        )
        transfer_id = int(cur.lastrowid)
        conn.commit()
        return {"ok": True, "transfer_id": transfer_id}
    except ValueError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def transfer_cg_gift(
    *,
    from_user_id: int,
    to_user_id: int,
    scene_id: int,
    message: str | None = None,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _sync_transfer_cg_gift,
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        scene_id=scene_id,
        message=message,
    )


def _sync_count_gifts_sent_today(user_id: int) -> int:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM cg_transfers "
            "WHERE from_user_id=? AND kind='gift' "
            "AND created_at >= datetime('now','start of day','localtime')",
            (user_id,),
        ).fetchone()
        return int((row and row["n"]) or 0)
    finally:
        conn.close()


async def count_gifts_sent_today(user_id: int) -> int:
    return await asyncio.to_thread(_sync_count_gifts_sent_today, user_id)


def _sync_list_transfers(user_id: int, direction: str, limit: int = 50) -> list[dict[str, Any]]:
    """direction: 'sent' | 'received'."""
    field = "from_user_id" if direction == "sent" else "to_user_id"
    conn = _get_conn()
    try:
        rows = conn.execute(
            f"""
            SELECT t.id, t.kind, t.from_user_id, t.to_user_id, t.scene_id,
                   t.message, t.created_at,
                   s.image_url AS image_url, s.turn_idx AS turn_idx,
                   s.is_keynote AS is_keynote,
                   r.genre AS genre,
                   uf.display_name AS from_display_name,
                   ut.display_name AS to_display_name
            FROM cg_transfers t
            LEFT JOIN game_scenes s ON s.id = t.scene_id
            LEFT JOIN game_runs r   ON r.id = s.run_id
            LEFT JOIN users uf      ON uf.id = t.from_user_id
            LEFT JOIN users ut      ON ut.id = t.to_user_id
            WHERE t.{field} = ?
            ORDER BY t.created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


async def list_transfers(user_id: int, direction: str, limit: int = 50) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_sync_list_transfers, user_id, direction, limit)


def _sync_find_user_by_student_id(student_id: str) -> dict[str, Any] | None:
    """Looking up a recipient by student_id is the path the gift UI uses —
    we never expose integer user_ids to the other side of the gift form."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, student_id, display_name FROM users WHERE student_id=? AND is_active=1",
            (student_id.strip(),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


async def find_user_by_student_id(student_id: str) -> dict[str, Any] | None:
    return await asyncio.to_thread(_sync_find_user_by_student_id, student_id)


def _sync_find_user_by_display_name(name: str) -> list[dict[str, Any]]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, student_id, display_name FROM users "
            "WHERE display_name LIKE ? AND is_active=1 LIMIT 10",
            (f"%{name.strip()}%",),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


async def find_user_by_display_name(name: str) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_sync_find_user_by_display_name, name)


# ─── M6 · PR2: trade offers ───────────────────────────────────────────────────

TRADE_MAX_ITEMS = 5
TRADE_MAX_ACTIVE_OUTGOING = 20
TRADE_EXPIRY_SQL = "datetime('now', '+7 days', 'localtime')"


def _pioneer_locked_scene_ids(conn: sqlite3.Connection, scene_ids: list[int]) -> set[int]:
    """Return the subset of ``scene_ids`` that are pioneer-locked (origin+keynote).
    Used before creating an offer so we can reject early with the exact ids.
    """
    if not scene_ids:
        return set()
    placeholders = ",".join(["?"] * len(scene_ids))
    rows = conn.execute(
        f"SELECT id FROM game_scenes WHERE id IN ({placeholders}) AND is_keynote=1",
        tuple(scene_ids),
    ).fetchall()
    keynote_ids = {int(r["id"]) for r in rows}
    if not keynote_ids:
        return set()
    # Origin-ownership check — only the run's original author "earned" the
    # keynote, so only they're locked out of trading it. A keynote that was
    # gifted/acquired later is tradable by the holder.
    placeholders2 = ",".join(["?"] * len(keynote_ids))
    rows2 = conn.execute(
        f"SELECT scene_id FROM cg_ownerships "
        f"WHERE scene_id IN ({placeholders2}) AND source='origin'",
        tuple(keynote_ids),
    ).fetchall()
    return {int(r["scene_id"]) for r in rows2}


def _sync_create_trade_offer(
    *,
    from_user_id: int,
    to_user_id: int,
    offered_ids: list[int],
    wanted_ids: list[int],
    message: str | None,
) -> dict[str, Any]:
    """Create a pending offer. Validates ownership + pioneer locks + caps.

    Raises ``ValueError`` with ``{"code": ...}`` on rule failure:
      self_trade          — from==to
      empty_offer         — both sides empty
      too_many_items      — > TRADE_MAX_ITEMS on a side
      duplicate_items     — same scene_id more than once
      too_many_active     — sender already has >= TRADE_MAX_ACTIVE_OUTGOING pending
      not_owned           — sender doesn't own one of offered_ids
      not_owned_by_target — target doesn't own one of wanted_ids
      not_transferable    — offered contains a pioneer-locked CG
    """
    if from_user_id == to_user_id:
        raise ValueError({"code": "self_trade"})
    if not offered_ids and not wanted_ids:
        raise ValueError({"code": "empty_offer"})
    if len(offered_ids) > TRADE_MAX_ITEMS or len(wanted_ids) > TRADE_MAX_ITEMS:
        raise ValueError(
            {"code": "too_many_items", "max": TRADE_MAX_ITEMS}
        )
    if len(set(offered_ids)) != len(offered_ids) or len(set(wanted_ids)) != len(wanted_ids):
        raise ValueError({"code": "duplicate_items"})

    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")

        active = conn.execute(
            "SELECT COUNT(*) AS n FROM cg_trade_offers "
            "WHERE from_user_id=? AND status='pending'",
            (from_user_id,),
        ).fetchone()
        if int(active["n"]) >= TRADE_MAX_ACTIVE_OUTGOING:
            raise ValueError(
                {"code": "too_many_active", "limit": TRADE_MAX_ACTIVE_OUTGOING}
            )

        # Sender owns offered.
        for sid in offered_ids:
            row = conn.execute(
                "SELECT 1 FROM cg_ownerships WHERE user_id=? AND scene_id=?",
                (from_user_id, sid),
            ).fetchone()
            if row is None:
                raise ValueError({"code": "not_owned", "scene_id": sid})

        # Target owns wanted.
        for sid in wanted_ids:
            row = conn.execute(
                "SELECT 1 FROM cg_ownerships WHERE user_id=? AND scene_id=?",
                (to_user_id, sid),
            ).fetchone()
            if row is None:
                raise ValueError({"code": "not_owned_by_target", "scene_id": sid})

        # Pioneer-lock: sender's origin+keynote CGs can't leave the sender.
        # (We don't check the target's side here — if they accept, their own
        # keynote origins would fail the same check symmetrically.)
        all_ids = list(set(offered_ids) | set(wanted_ids))
        locked = _pioneer_locked_scene_ids(conn, all_ids)
        # For offered: only block if the sender is the origin owner.
        bad: list[int] = []
        for sid in offered_ids:
            if sid in locked:
                row = conn.execute(
                    "SELECT source FROM cg_ownerships WHERE user_id=? AND scene_id=?",
                    (from_user_id, sid),
                ).fetchone()
                if row and row["source"] == "origin":
                    bad.append(sid)
        for sid in wanted_ids:
            if sid in locked:
                row = conn.execute(
                    "SELECT source FROM cg_ownerships WHERE user_id=? AND scene_id=?",
                    (to_user_id, sid),
                ).fetchone()
                if row and row["source"] == "origin":
                    bad.append(sid)
        if bad:
            raise ValueError({"code": "not_transferable", "scene_ids": sorted(set(bad))})

        cur = conn.execute(
            f"""
            INSERT INTO cg_trade_offers
              (from_user_id, to_user_id, offered_scene_ids, wanted_scene_ids,
               message, status, expires_at)
            VALUES (?,?,?,?,?,'pending',{TRADE_EXPIRY_SQL})
            """,
            (
                from_user_id,
                to_user_id,
                json.dumps(list(offered_ids), ensure_ascii=False),
                json.dumps(list(wanted_ids), ensure_ascii=False),
                (message or "").strip() or None,
            ),
        )
        conn.commit()
        return {"ok": True, "offer_id": int(cur.lastrowid)}
    except ValueError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def create_trade_offer(
    *,
    from_user_id: int,
    to_user_id: int,
    offered_ids: list[int],
    wanted_ids: list[int],
    message: str | None = None,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _sync_create_trade_offer,
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        offered_ids=offered_ids,
        wanted_ids=wanted_ids,
        message=message,
    )


def _sync_expire_stale(conn: sqlite3.Connection) -> None:
    """Cheap lazy-expiry: call inside a read path to auto-flip pending offers
    past their ``expires_at``. Runs in a short write transaction; keep calls
    scoped to list / get paths where a few tens of ms is fine."""
    conn.execute(
        "UPDATE cg_trade_offers SET status='expired', responded_at=datetime('now','localtime') "
        "WHERE status='pending' AND expires_at < datetime('now','localtime')"
    )


def _row_to_offer(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    for k in ("offered_scene_ids", "wanted_scene_ids"):
        raw = d.get(k) or "[]"
        try:
            d[k[:-4]] = json.loads(raw)  # offered_scene_ids -> offered_scenes
        except json.JSONDecodeError:
            d[k[:-4]] = []
        d.pop(k, None)
    return d


def _enrich_scene_previews(
    conn: sqlite3.Connection, scene_ids: list[int]
) -> dict[int, dict[str, Any]]:
    if not scene_ids:
        return {}
    placeholders = ",".join(["?"] * len(scene_ids))
    rows = conn.execute(
        f"""
        SELECT s.id, s.turn_idx, s.is_keynote, s.image_url, r.genre, r.id AS run_id
        FROM game_scenes s LEFT JOIN game_runs r ON r.id = s.run_id
        WHERE s.id IN ({placeholders})
        """,
        tuple(scene_ids),
    ).fetchall()
    return {int(r["id"]): dict(r) for r in rows}


def _sync_list_trade_offers(
    user_id: int,
    *,
    scope: str,  # 'incoming' | 'outgoing' | 'history'
    limit: int = 50,
) -> list[dict[str, Any]]:
    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        _sync_expire_stale(conn)
        conn.commit()

        if scope == "incoming":
            where = "to_user_id=? AND status='pending'"
        elif scope == "outgoing":
            where = "from_user_id=? AND status='pending'"
        else:
            where = "(from_user_id=? OR to_user_id=?) AND status != 'pending'"
        params: tuple[Any, ...] = (
            (user_id, user_id) if scope == "history" else (user_id,)
        )
        rows = conn.execute(
            f"""
            SELECT o.*, uf.display_name AS from_display_name, ut.display_name AS to_display_name
            FROM cg_trade_offers o
            LEFT JOIN users uf ON uf.id = o.from_user_id
            LEFT JOIN users ut ON ut.id = o.to_user_id
            WHERE {where}
            ORDER BY
              CASE WHEN o.status='pending' THEN 0 ELSE 1 END,
              o.created_at DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        offers = [_row_to_offer(r) for r in rows]

        all_scene_ids: set[int] = set()
        for o in offers:
            all_scene_ids.update(o.get("offered_scenes", []) or [])
            all_scene_ids.update(o.get("wanted_scenes", []) or [])
        previews = _enrich_scene_previews(conn, sorted(all_scene_ids))

        for o in offers:
            o["offered_preview"] = [
                previews[i] for i in (o.get("offered_scenes") or []) if i in previews
            ]
            o["wanted_preview"] = [
                previews[i] for i in (o.get("wanted_scenes") or []) if i in previews
            ]
        return offers
    finally:
        conn.close()


async def list_trade_offers(
    user_id: int, *, scope: str, limit: int = 50
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_sync_list_trade_offers, user_id, scope=scope, limit=limit)


def _sync_get_trade_offer(offer_id: int, user_id: int) -> dict[str, Any] | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT o.*, uf.display_name AS from_display_name, ut.display_name AS to_display_name "
            "FROM cg_trade_offers o "
            "LEFT JOIN users uf ON uf.id = o.from_user_id "
            "LEFT JOIN users ut ON ut.id = o.to_user_id "
            "WHERE o.id=? AND (o.from_user_id=? OR o.to_user_id=?)",
            (offer_id, user_id, user_id),
        ).fetchone()
        if row is None:
            return None
        o = _row_to_offer(row)
        all_ids = (o.get("offered_scenes") or []) + (o.get("wanted_scenes") or [])
        previews = _enrich_scene_previews(conn, list(set(all_ids)))
        o["offered_preview"] = [previews[i] for i in (o.get("offered_scenes") or []) if i in previews]
        o["wanted_preview"] = [previews[i] for i in (o.get("wanted_scenes") or []) if i in previews]
        return o
    finally:
        conn.close()


async def get_trade_offer(offer_id: int, user_id: int) -> dict[str, Any] | None:
    return await asyncio.to_thread(_sync_get_trade_offer, offer_id, user_id)


def _sync_respond_offer(
    *,
    offer_id: int,
    user_id: int,
    action: str,  # 'accept' | 'reject' | 'cancel'
) -> dict[str, Any]:
    """Atomic trade resolution.

    accept: sender must be to_user_id; move offered_ids from from→to and
            wanted_ids from to→from; log a cg_transfers row per moved scene
            with kind='trade' and offer_id; flip status='accepted'.
    reject: to_user_id only.
    cancel: from_user_id only.

    Raises ``ValueError`` with a ``code`` on any mismatch: not_found,
    wrong_role, already_responded, expired, not_owned_anymore, already_owned.
    """
    if action not in {"accept", "reject", "cancel"}:
        raise ValueError({"code": "bad_action"})

    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM cg_trade_offers WHERE id=?", (offer_id,)
        ).fetchone()
        if row is None:
            raise ValueError({"code": "not_found"})
        if row["status"] != "pending":
            raise ValueError({"code": "already_responded", "status": row["status"]})
        # Expiry — treat as expired if past the window, even if we didn't
        # run the lazy sweeper recently.
        exp_row = conn.execute(
            "SELECT CASE WHEN expires_at < datetime('now','localtime') THEN 1 ELSE 0 END AS past "
            "FROM cg_trade_offers WHERE id=?",
            (offer_id,),
        ).fetchone()
        if exp_row and int(exp_row["past"]):
            conn.execute(
                "UPDATE cg_trade_offers SET status='expired', responded_at=datetime('now','localtime') "
                "WHERE id=?",
                (offer_id,),
            )
            conn.commit()
            raise ValueError({"code": "expired"})

        if action == "reject":
            if int(row["to_user_id"]) != int(user_id):
                raise ValueError({"code": "wrong_role"})
            conn.execute(
                "UPDATE cg_trade_offers SET status='rejected', "
                "responded_at=datetime('now','localtime') WHERE id=?",
                (offer_id,),
            )
            conn.commit()
            return {"ok": True, "status": "rejected"}

        if action == "cancel":
            if int(row["from_user_id"]) != int(user_id):
                raise ValueError({"code": "wrong_role"})
            conn.execute(
                "UPDATE cg_trade_offers SET status='cancelled', "
                "responded_at=datetime('now','localtime') WHERE id=?",
                (offer_id,),
            )
            conn.commit()
            return {"ok": True, "status": "cancelled"}

        # accept path — recipient confirms.
        if int(row["to_user_id"]) != int(user_id):
            raise ValueError({"code": "wrong_role"})

        offered_ids = json.loads(row["offered_scene_ids"] or "[]")
        wanted_ids = json.loads(row["wanted_scene_ids"] or "[]")
        from_uid = int(row["from_user_id"])
        to_uid = int(row["to_user_id"])

        # Re-verify ownership under the transaction — someone may have
        # moved a CG since the offer was created.
        for sid in offered_ids:
            r = conn.execute(
                "SELECT 1 FROM cg_ownerships WHERE user_id=? AND scene_id=?",
                (from_uid, sid),
            ).fetchone()
            if r is None:
                raise ValueError({"code": "not_owned_anymore", "scene_id": sid, "side": "offered"})
        for sid in wanted_ids:
            r = conn.execute(
                "SELECT 1 FROM cg_ownerships WHERE user_id=? AND scene_id=?",
                (to_uid, sid),
            ).fetchone()
            if r is None:
                raise ValueError({"code": "not_owned_anymore", "scene_id": sid, "side": "wanted"})

        # No side may end up with a duplicate row (UNIQUE(user_id, scene_id)).
        # We only care about "recipient of a transfer". Delete sender rows
        # first so the destination rows don't collide in mid-swap when the
        # same scene appears on both sides (impossible here because from!=to
        # and each side owns their own IDs, but guarded anyway).
        def _move(scene_id: int, src_uid: int, dst_uid: int) -> None:
            # Preserve origin_user_id across trades.
            src = conn.execute(
                "SELECT origin_user_id FROM cg_ownerships WHERE user_id=? AND scene_id=?",
                (src_uid, scene_id),
            ).fetchone()
            origin_uid = int(src["origin_user_id"]) if src else src_uid
            conn.execute(
                "DELETE FROM cg_ownerships WHERE user_id=? AND scene_id=?",
                (src_uid, scene_id),
            )
            # If dst already owns (shouldn't, but guard): flag.
            dup = conn.execute(
                "SELECT 1 FROM cg_ownerships WHERE user_id=? AND scene_id=?",
                (dst_uid, scene_id),
            ).fetchone()
            if dup is not None:
                raise ValueError({"code": "already_owned", "scene_id": scene_id})
            conn.execute(
                "INSERT INTO cg_ownerships "
                "(user_id, scene_id, origin_user_id, source, rarity) "
                "VALUES (?,?,?,?,?)",
                (dst_uid, scene_id, origin_uid, "trade", "common"),
            )
            conn.execute(
                "INSERT INTO cg_transfers (kind, from_user_id, to_user_id, scene_id, offer_id) "
                "VALUES ('trade', ?, ?, ?, ?)",
                (src_uid, dst_uid, scene_id, offer_id),
            )

        for sid in offered_ids:
            _move(sid, from_uid, to_uid)
        for sid in wanted_ids:
            _move(sid, to_uid, from_uid)

        conn.execute(
            "UPDATE cg_trade_offers SET status='accepted', "
            "responded_at=datetime('now','localtime') WHERE id=?",
            (offer_id,),
        )
        conn.commit()
        return {"ok": True, "status": "accepted"}
    except ValueError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def respond_trade_offer(
    *, offer_id: int, user_id: int, action: str
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _sync_respond_offer, offer_id=offer_id, user_id=user_id, action=action
    )


def _sync_try_claim_pioneer(slug: str, user_id: int, run_id: int) -> bool:
    """Atomically claim a pioneer slot for a (genre, ending) combo.

    Returns True if THIS user is the first; subsequent callers get False.
    """
    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO pioneer_locks (slug, user_id, run_id) VALUES (?,?,?)",
            (slug, user_id, run_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


async def try_claim_pioneer(slug: str, user_id: int, run_id: int) -> bool:
    return await asyncio.to_thread(_sync_try_claim_pioneer, slug, user_id, run_id)


def _sync_count_user_endings(user_id: int) -> dict[str, set[str]]:
    """For each genre, the set of ending_slugs this user has finished."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT genre, ending_slug FROM game_runs
            WHERE user_id=? AND status='ended'
              AND ending_slug IS NOT NULL AND ending_slug <> ''
            """,
            (user_id,),
        ).fetchall()
        out: dict[str, set[str]] = {}
        for r in rows:
            out.setdefault(r["genre"] or "unknown", set()).add(r["ending_slug"])
        return out
    finally:
        conn.close()


async def count_user_endings(user_id: int) -> dict[str, set[str]]:
    return await asyncio.to_thread(_sync_count_user_endings, user_id)


def _sync_leaderboard_v2(scope: str = "all", limit: int = 50) -> list[dict[str, Any]]:
    """Score + cg_count two-dimensional leaderboard.

    cg_count counts owned scenes (incl. originals) — a proxy for活跃 + 收藏.
    """
    conn = _get_conn()
    try:
        if scope == "weekly":
            where = (
                "r.status='ended' AND r.ended_at >= datetime('now', '-7 days', 'localtime')"
            )
        else:
            where = "r.status='ended'"
        rows = conn.execute(
            f"""
            SELECT r.id, r.user_id, r.score, r.ending_slug, r.cover_url,
                   r.turn_idx, r.ended_at, r.genre,
                   u.display_name, u.student_id,
                   COALESCE(g.cg_count, 0) AS cg_count
            FROM game_runs r
            LEFT JOIN users u ON r.user_id = u.id
            LEFT JOIN (
              SELECT user_id, COUNT(*) AS cg_count
              FROM cg_ownerships GROUP BY user_id
            ) g ON g.user_id = r.user_id
            WHERE {where}
            ORDER BY r.score DESC, r.ended_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


async def leaderboard_v2(scope: str = "all", limit: int = 50) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_sync_leaderboard_v2, scope, limit)


def _sync_leaderboard_users(sort: str = "achievements", limit: int = 50) -> list[dict[str, Any]]:
    """User-centric leaderboard.

    sort:
      'achievements' — count of distinct achievements (any kind)
      'redeemed'     — total redeemed_usd across achievement_redemptions
      'gifts_sent'   — count of gift transfers initiated
      'gifts_got'    — count of gift transfers received

    Rows are shaped consistently regardless of sort, so the frontend can
    render with one card template. All metrics are shown even when sorted
    by a different one, so users can compare at a glance.
    """
    sort_clean = sort if sort in {"achievements", "redeemed", "gifts_sent", "gifts_got"} else "achievements"
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT
              u.id          AS user_id,
              u.display_name AS display_name,
              u.student_id  AS student_id,
              COALESCE(a.achievement_count, 0)   AS achievement_count,
              COALESCE(r.redeemed_usd, 0)        AS redeemed_usd,
              COALESCE(gs.gifts_sent, 0)         AS gifts_sent,
              COALESCE(gr.gifts_got, 0)          AS gifts_got,
              COALESCE(cg.cg_count, 0)           AS cg_count
            FROM users u
            LEFT JOIN (
              SELECT user_id, COUNT(*) AS achievement_count
              FROM achievements GROUP BY user_id
            ) a ON a.user_id = u.id
            LEFT JOIN (
              SELECT user_id, COALESCE(SUM(reward_usd), 0) AS redeemed_usd
              FROM achievement_redemptions GROUP BY user_id
            ) r ON r.user_id = u.id
            LEFT JOIN (
              SELECT from_user_id AS user_id, COUNT(*) AS gifts_sent
              FROM cg_transfers WHERE kind='gift' GROUP BY from_user_id
            ) gs ON gs.user_id = u.id
            LEFT JOIN (
              SELECT to_user_id AS user_id, COUNT(*) AS gifts_got
              FROM cg_transfers WHERE kind='gift' GROUP BY to_user_id
            ) gr ON gr.user_id = u.id
            LEFT JOIN (
              SELECT user_id, COUNT(*) AS cg_count
              FROM cg_ownerships GROUP BY user_id
            ) cg ON cg.user_id = u.id
            WHERE u.is_active = 1
            """,
        ).fetchall()
        out = [dict(r) for r in rows]
        key_fn = {
            "achievements": lambda r: (r["achievement_count"], r["redeemed_usd"]),
            "redeemed":     lambda r: (r["redeemed_usd"], r["achievement_count"]),
            "gifts_sent":   lambda r: (r["gifts_sent"], r["cg_count"]),
            "gifts_got":    lambda r: (r["gifts_got"], r["cg_count"]),
        }[sort_clean]
        out.sort(key=key_fn, reverse=True)
        # Only return users who actually have something to show on the
        # primary metric — a board full of zeros looks broken.
        primary = {
            "achievements": "achievement_count",
            "redeemed":     "redeemed_usd",
            "gifts_sent":   "gifts_sent",
            "gifts_got":    "gifts_got",
        }[sort_clean]
        out = [r for r in out if float(r.get(primary) or 0) > 0]
        return out[:limit]
    finally:
        conn.close()


async def leaderboard_users(sort: str = "achievements", limit: int = 50) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_sync_leaderboard_users, sort, limit)


# ─── M7 · Marketplace ────────────────────────────────────────────────────────

def _sync_create_listing(
    seller_id: int, scene_id: int, price_usd: float, message: str | None
) -> dict[str, Any]:
    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        # Must own the CG
        own = conn.execute(
            "SELECT id FROM cg_ownerships WHERE user_id=? AND scene_id=?",
            (seller_id, scene_id),
        ).fetchone()
        if own is None:
            raise ValueError({"code": "not_owned"})
        # Check it's not a pioneer CG
        scene = conn.execute(
            "SELECT is_keynote FROM game_scenes WHERE id=?", (scene_id,)
        ).fetchone()
        run = conn.execute(
            "SELECT r.genre FROM game_scenes s JOIN game_runs r ON r.id=s.run_id WHERE s.id=?",
            (scene_id,),
        ).fetchone()
        # Pioneer check: first scene of a run (turn_idx=0) + keynote
        if scene and scene["is_keynote"]:
            first = conn.execute(
                "SELECT id FROM game_scenes WHERE run_id=(SELECT run_id FROM game_scenes WHERE id=?) ORDER BY turn_idx LIMIT 1",
                (scene_id,),
            ).fetchone()
            if first and first["id"] == scene_id:
                raise ValueError({"code": "pioneer_locked"})
        if price_usd <= 0:
            raise ValueError({"code": "bad_price"})
        cur = conn.execute(
            "INSERT INTO marketplace_listings (seller_id, scene_id, price_usd, message) VALUES (?,?,?,?)",
            (seller_id, scene_id, price_usd, message),
        )
        conn.commit()
        return {"listing_id": cur.lastrowid, "price_usd": price_usd}
    finally:
        conn.close()


async def create_listing(
    seller_id: int, scene_id: int, price_usd: float, message: str | None = None
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _sync_create_listing, seller_id, scene_id, price_usd, message
    )


def _sync_cancel_listing(user_id: int, listing_id: int) -> dict[str, Any]:
    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM marketplace_listings WHERE id=?", (listing_id,)
        ).fetchone()
        if row is None:
            raise ValueError({"code": "not_found"})
        if row["seller_id"] != user_id:
            raise ValueError({"code": "not_seller"})
        if row["status"] != "active":
            raise ValueError({"code": "already_resolved"})
        conn.execute(
            "UPDATE marketplace_listings SET status='cancelled' WHERE id=?",
            (listing_id,),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


async def cancel_listing(user_id: int, listing_id: int) -> dict[str, Any]:
    return await asyncio.to_thread(_sync_cancel_listing, user_id, listing_id)


def _sync_buy_listing(buyer_id: int, listing_id: int) -> dict[str, Any]:
    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM marketplace_listings WHERE id=?", (listing_id,)
        ).fetchone()
        if row is None:
            raise ValueError({"code": "not_found"})
        if row["status"] != "active":
            raise ValueError({"code": "already_sold"})
        if row["seller_id"] == buyer_id:
            raise ValueError({"code": "self_buy"})
        seller_id = row["seller_id"]
        scene_id = row["scene_id"]
        price = row["price_usd"]

        # Buyer must have enough balance
        buyer = conn.execute("SELECT balance_usd FROM users WHERE id=?", (buyer_id,)).fetchone()
        if not buyer or float(buyer["balance_usd"]) < price:
            raise ValueError({"code": "insufficient_balance"})

        # Transfer: deduct buyer, credit seller, move CG ownership
        conn.execute(
            "UPDATE users SET balance_usd = balance_usd - ? WHERE id=?",
            (price, buyer_id),
        )
        conn.execute(
            "UPDATE users SET balance_usd = balance_usd + ? WHERE id=?",
            (price, seller_id),
        )
        # Remove seller's ownership, add buyer's
        conn.execute(
            "DELETE FROM cg_ownerships WHERE user_id=? AND scene_id=?",
            (seller_id, scene_id),
        )
        conn.execute(
            "INSERT OR IGNORE INTO cg_ownerships (user_id, scene_id, origin_user_id, source) "
            "SELECT ?, s.id, o.origin_user_id, 'marketplace' "
            "FROM game_scenes s JOIN cg_ownerships o ON o.scene_id=s.id AND o.user_id=? "
            "WHERE s.id=?",
            (buyer_id, seller_id, scene_id),
        )
        # Log transfer
        conn.execute(
            "INSERT INTO cg_transfers (kind, from_user_id, to_user_id, scene_id, message) VALUES ('marketplace',?,?,?,?)",
            (seller_id, buyer_id, scene_id, f"市场交易 ${price:.2f}"),
        )
        # Mark listing sold
        conn.execute(
            "UPDATE marketplace_listings SET status='sold', buyer_id=?, sold_at=datetime('now','localtime') WHERE id=?",
            (buyer_id, listing_id),
        )
        conn.commit()
        return {"ok": True, "price_usd": price}
    finally:
        conn.close()


async def buy_listing(buyer_id: int, listing_id: int) -> dict[str, Any]:
    return await asyncio.to_thread(_sync_buy_listing, buyer_id, listing_id)


def _sync_list_marketplace(
    user_id: int | None, scope: str, limit: int
) -> list[dict[str, Any]]:
    conn = _get_conn()
    try:
        if scope == "my":
            where = "l.seller_id=? AND l.status='active'"
            params: tuple[Any, ...] = (user_id,)
        elif scope == "bought":
            where = "l.buyer_id=? AND l.status='sold'"
            params = (user_id,)
        else:  # 'all'
            where = "l.status='active'"
            params = ()

        rows = conn.execute(
            f"""
            SELECT l.*, u.display_name AS seller_name,
                   s.image_url, s.turn_idx, s.is_keynote,
                   r.genre
            FROM marketplace_listings l
            JOIN users u ON u.id = l.seller_id
            JOIN game_scenes s ON s.id = l.scene_id
            LEFT JOIN game_runs r ON r.id = s.run_id
            WHERE {where}
            ORDER BY l.created_at DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


async def list_marketplace(
    user_id: int | None = None, scope: str = "all", limit: int = 50
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_sync_list_marketplace, user_id, scope, limit)


def _sync_admin_set_reward(slug: str, reward_usd: float) -> dict[str, Any]:
    """Override reward for a specific achievement slug in a DB table."""
    conn = _get_conn()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS reward_overrides (slug TEXT PRIMARY KEY, reward_usd REAL NOT NULL)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO reward_overrides (slug, reward_usd) VALUES (?,?)",
            (slug, reward_usd),
        )
        conn.commit()
        return {"slug": slug, "reward_usd": reward_usd}
    finally:
        conn.close()


async def admin_set_reward(slug: str, reward_usd: float) -> dict[str, Any]:
    return await asyncio.to_thread(_sync_admin_set_reward, slug, reward_usd)


def _sync_get_reward_overrides() -> dict[str, float]:
    conn = _get_conn()
    try:
        try:
            rows = conn.execute("SELECT slug, reward_usd FROM reward_overrides").fetchall()
        except sqlite3.OperationalError:
            return {}
        return {r["slug"]: float(r["reward_usd"]) for r in rows}
    finally:
        conn.close()


async def get_reward_overrides() -> dict[str, float]:
    return await asyncio.to_thread(_sync_get_reward_overrides)
