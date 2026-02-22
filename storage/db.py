import asyncio
import sqlite3
from datetime import datetime
from urllib.parse import unquote, urlparse

import aiosqlite

from config import (
    DATABASE_URL,
    DB_BUSY_TIMEOUT_MS,
    DB_CONNECT_TIMEOUT_SECONDS,
    DB_POOL_SIZE,
    SQLITE_PATH,
)
from logger import logger


def _resolve_db_path() -> str:
    if DATABASE_URL:
        if not DATABASE_URL.startswith("sqlite://"):
            raise ValueError("Only sqlite DATABASE_URL is supported, for example sqlite:///newshive.db")
        parsed = urlparse(DATABASE_URL)
        if parsed.scheme != "sqlite":
            raise ValueError("Only sqlite DATABASE_URL is supported, for example sqlite:///newshive.db")
        if not parsed.path:
            return SQLITE_PATH

        decoded_path = unquote(parsed.path)
        if decoded_path.startswith("//"):
            return decoded_path[1:]
        if decoded_path.startswith("/"):
            return decoded_path[1:]
        return decoded_path
    return SQLITE_PATH


DB_PATH = _resolve_db_path()
_DB_SEMAPHORE = asyncio.Semaphore(max(1, DB_POOL_SIZE))


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


async def _connect() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(DB_PATH, timeout=DB_CONNECT_TIMEOUT_SECONDS)
    await conn.execute(f"PRAGMA busy_timeout = {DB_BUSY_TIMEOUT_MS}")
    return conn


async def init_db() -> None:
    async with _DB_SEMAPHORE:
        async with await _connect() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_sources (
                    user_id TEXT,
                    source_name TEXT,
                    source_url TEXT,
                    created_at TIMESTAMP,
                    UNIQUE(user_id, source_name)
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id TEXT PRIMARY KEY,
                    delivery_mode TEXT,
                    max_items_per_push INTEGER,
                    only_top_news BOOLEAN,
                    quiet_start INTEGER,
                    quiet_end INTEGER,
                    updated_at TIMESTAMP
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_groups (
                    chat_id TEXT PRIMARY KEY,
                    added_at TIMESTAMP
                )
                """
            )
            await conn.commit()


async def _execute_write(query: str, params: tuple = ()) -> aiosqlite.Cursor:
    try:
        async with _DB_SEMAPHORE:
            async with await _connect() as conn:
                await conn.execute("BEGIN")
                cursor = await conn.execute(query, params)
                await conn.commit()
                return cursor
    except sqlite3.Error as exc:
        logger.exception("DB write failed: %s | params=%s", query, params)
        raise exc


def _log_db_error(query: str, params: tuple, exc: sqlite3.Error) -> None:
    logger.exception("DB read failed: %s | params=%s | error=%s", query, params, exc)


async def get_user_sources_for_user(user_id: str) -> dict[str, str]:
    query = "SELECT source_name, source_url FROM user_sources WHERE user_id = ? ORDER BY created_at DESC"
    params = (str(user_id),)
    try:
        async with _DB_SEMAPHORE:
            async with await _connect() as conn:
                rows = await (
                    await conn.execute(
                        "SELECT source_name, source_url FROM user_sources WHERE user_id = ? ORDER BY created_at DESC",
                        params,
                    )
                ).fetchall()
    except sqlite3.Error as exc:
        _log_db_error(query, params, exc)
        return {}
    return {name: url for name, url in rows}


async def add_user_source(user_id: str, source_name: str, source_url: str) -> bool:
    try:
        cursor = await _execute_write(
            """
            INSERT INTO user_sources (user_id, source_name, source_url, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, source_name) DO NOTHING
            """,
            (str(user_id), source_name, source_url, _utc_now()),
        )
        return cursor.rowcount > 0
    except sqlite3.IntegrityError:
        return False


async def remove_user_source(user_id: str, source_name: str) -> bool:
    cursor = await _execute_write(
        "DELETE FROM user_sources WHERE user_id = ? AND source_name = ?",
        (str(user_id), source_name),
    )
    return cursor.rowcount > 0


async def load_user_preferences() -> dict[str, dict]:
    query = """
            SELECT user_id, delivery_mode, max_items_per_push, only_top_news, quiet_start, quiet_end
            FROM user_preferences
            """
    try:
        async with _DB_SEMAPHORE:
            async with await _connect() as conn:
                rows = await (
                    await conn.execute(
                        """
                        SELECT user_id, delivery_mode, max_items_per_push, only_top_news, quiet_start, quiet_end
                        FROM user_preferences
                        """,
                    )
                ).fetchall()
    except sqlite3.Error as exc:
        _log_db_error(query, (), exc)
        return {}

    return {
        user_id: {
            "delivery_mode": delivery_mode,
            "max_items_per_push": max_items_per_push,
            "only_top_news": bool(only_top_news),
            "quiet_hours": {"start": quiet_start, "end": quiet_end},
        }
        for user_id, delivery_mode, max_items_per_push, only_top_news, quiet_start, quiet_end in rows
    }


async def get_preferences(user_id: str) -> dict | None:
    query = """
            SELECT delivery_mode, max_items_per_push, only_top_news, quiet_start, quiet_end
            FROM user_preferences
            WHERE user_id = ?
            """
    params = (str(user_id),)
    try:
        async with _DB_SEMAPHORE:
            async with await _connect() as conn:
                row = await (
                    await conn.execute(
                        """
                        SELECT delivery_mode, max_items_per_push, only_top_news, quiet_start, quiet_end
                        FROM user_preferences
                        WHERE user_id = ?
                        """,
                        params,
                    )
                ).fetchone()
    except sqlite3.Error as exc:
        _log_db_error(query, params, exc)
        return None

    if not row:
        return None

    delivery_mode, max_items_per_push, only_top_news, quiet_start, quiet_end = row
    return {
        "delivery_mode": delivery_mode,
        "max_items_per_push": max_items_per_push,
        "only_top_news": bool(only_top_news),
        "quiet_hours": {"start": quiet_start, "end": quiet_end},
    }


async def save_user_preferences(user_id: str, preferences: dict) -> None:
    await _execute_write(
        """
        INSERT INTO user_preferences (
            user_id, delivery_mode, max_items_per_push, only_top_news, quiet_start, quiet_end, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            delivery_mode = excluded.delivery_mode,
            max_items_per_push = excluded.max_items_per_push,
            only_top_news = excluded.only_top_news,
            quiet_start = excluded.quiet_start,
            quiet_end = excluded.quiet_end,
            updated_at = excluded.updated_at
        """,
        (
            str(user_id),
            preferences["delivery_mode"],
            preferences["max_items_per_push"],
            int(preferences["only_top_news"]),
            preferences["quiet_hours"]["start"],
            preferences["quiet_hours"]["end"],
            _utc_now(),
        ),
    )


async def update_preferences(user_id: str, **updates) -> dict | None:
    delivery_mode = updates.get("delivery_mode")
    max_items = updates.get("max_items_per_push")
    only_top = updates.get("only_top_news")
    quiet_start = updates.get("quiet_hours_start")
    quiet_end = updates.get("quiet_hours_end")

    await _execute_write(
        """
        INSERT INTO user_preferences (
            user_id, delivery_mode, max_items_per_push, only_top_news, quiet_start, quiet_end, updated_at
        ) VALUES (
            ?,
            COALESCE(?, 'stream'),
            COALESCE(?, 3),
            COALESCE(?, 1),
            COALESCE(?, 23),
            COALESCE(?, 7),
            ?
        )
        ON CONFLICT(user_id) DO UPDATE SET
            delivery_mode = COALESCE(excluded.delivery_mode, user_preferences.delivery_mode),
            max_items_per_push = COALESCE(excluded.max_items_per_push, user_preferences.max_items_per_push),
            only_top_news = COALESCE(excluded.only_top_news, user_preferences.only_top_news),
            quiet_start = COALESCE(excluded.quiet_start, user_preferences.quiet_start),
            quiet_end = COALESCE(excluded.quiet_end, user_preferences.quiet_end),
            updated_at = excluded.updated_at
        """,
        (
            str(user_id),
            delivery_mode,
            max_items,
            int(only_top) if only_top is not None else None,
            quiet_start,
            quiet_end,
            _utc_now(),
        ),
    )
    return await get_preferences(user_id)


async def add_bot_group(chat_id: str) -> None:
    await _execute_write(
        """
        INSERT INTO bot_groups (chat_id, added_at)
        VALUES (?, ?)
        ON CONFLICT(chat_id) DO NOTHING
        """,
        (str(chat_id), _utc_now()),
    )


async def remove_bot_group(chat_id: str) -> None:
    await _execute_write("DELETE FROM bot_groups WHERE chat_id = ?", (str(chat_id),))


async def get_bot_group_ids() -> list[str]:
    query = "SELECT chat_id FROM bot_groups"
    try:
        async with _DB_SEMAPHORE:
            async with await _connect() as conn:
                rows = await (await conn.execute(query)).fetchall()
    except sqlite3.Error as exc:
        _log_db_error(query, (), exc)
        return []
    return [row[0] for row in rows]
