import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = "newshive.db"


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
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
        conn.execute(
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_groups (
                chat_id TEXT PRIMARY KEY,
                added_at TIMESTAMP
            )
            """
        )


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_user_sources_for_user(user_id: str) -> dict[str, str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT source_name, source_url FROM user_sources WHERE user_id = ? ORDER BY created_at DESC",
            (str(user_id),),
        ).fetchall()
    return {name: url for name, url in rows}


def add_user_source(user_id: str, source_name: str, source_url: str) -> bool:
    try:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_sources (user_id, source_name, source_url, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (str(user_id), source_name, source_url, _utc_now()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def remove_user_source(user_id: str, source_name: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM user_sources WHERE user_id = ? AND source_name = ?",
            (str(user_id), source_name),
        )
    return cursor.rowcount > 0


def load_user_preferences() -> dict[str, dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT user_id, delivery_mode, max_items_per_push, only_top_news, quiet_start, quiet_end
            FROM user_preferences
            """
        ).fetchall()

    return {
        user_id: {
            "delivery_mode": delivery_mode,
            "max_items_per_push": max_items_per_push,
            "only_top_news": bool(only_top_news),
            "quiet_hours": {"start": quiet_start, "end": quiet_end},
        }
        for user_id, delivery_mode, max_items_per_push, only_top_news, quiet_start, quiet_end in rows
    }


def get_preferences(user_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT delivery_mode, max_items_per_push, only_top_news, quiet_start, quiet_end
            FROM user_preferences
            WHERE user_id = ?
            """,
            (str(user_id),),
        ).fetchone()

    if not row:
        return None

    delivery_mode, max_items_per_push, only_top_news, quiet_start, quiet_end = row
    return {
        "delivery_mode": delivery_mode,
        "max_items_per_push": max_items_per_push,
        "only_top_news": bool(only_top_news),
        "quiet_hours": {"start": quiet_start, "end": quiet_end},
    }


def save_user_preferences(user_id: str, preferences: dict) -> None:
    with get_connection() as conn:
        conn.execute(
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


def update_preferences(user_id: str, **updates) -> dict | None:
    current = get_preferences(user_id)
    if current is None:
        return None

    if "quiet_hours_start" in updates:
        current["quiet_hours"]["start"] = updates["quiet_hours_start"]
    if "quiet_hours_end" in updates:
        current["quiet_hours"]["end"] = updates["quiet_hours_end"]

    for key in {"delivery_mode", "max_items_per_push", "only_top_news"}:
        if key in updates:
            current[key] = updates[key]

    save_user_preferences(user_id, current)
    return current


def add_bot_group(chat_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO bot_groups (chat_id, added_at)
            VALUES (?, ?)
            ON CONFLICT(chat_id) DO NOTHING
            """,
            (str(chat_id), _utc_now()),
        )


def remove_bot_group(chat_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM bot_groups WHERE chat_id = ?", (str(chat_id),))


def get_bot_group_ids() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT chat_id FROM bot_groups").fetchall()
    return [row[0] for row in rows]
