#!/usr/bin/env python3
"""Миграция файлового хранилища в SQLite.

Загружает данные из:
- user_sources.json
- user_preferences.json
- groups.txt

Повторный запуск идемпотентен благодаря UPSERT/DO NOTHING.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path("newshive.db")
DEFAULT_USER_SOURCES_PATH = Path("user_sources.json")
DEFAULT_USER_PREFERENCES_PATH = Path("user_preferences.json")
DEFAULT_GROUPS_PATH = Path("groups.txt")


@dataclass
class MigrationStats:
    inserted: int = 0
    updated: int = 0
    skipped: list[str] = field(default_factory=list)


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s | %(levelname)s | %(message)s")


def ensure_tables(conn: sqlite3.Connection) -> None:
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
    conn.commit()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        logging.warning("Файл %s не найден, пропускаю.", path)
        return {}

    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, dict):
        raise ValueError(f"Ожидался JSON-объект в {path}, получено: {type(payload).__name__}")

    return payload


def migrate_user_sources(conn: sqlite3.Connection, user_sources_path: Path) -> MigrationStats:
    stats = MigrationStats()
    payload = load_json(user_sources_path)

    for user_id, sources in payload.items():
        if not isinstance(user_id, str) or not user_id.strip():
            stats.skipped.append(f"user_sources: invalid user_id={user_id!r}")
            continue
        if not isinstance(sources, dict):
            stats.skipped.append(f"user_sources[{user_id}]: expected object, got {type(sources).__name__}")
            continue

        for source_name, source_url in sources.items():
            if not isinstance(source_name, str) or not source_name.strip():
                stats.skipped.append(f"user_sources[{user_id}]: invalid source_name={source_name!r}")
                continue
            if not isinstance(source_url, str) or not source_url.strip():
                stats.skipped.append(
                    f"user_sources[{user_id}][{source_name}]: invalid source_url={source_url!r}"
                )
                continue

            normalized_user_id = user_id.strip()
            normalized_source_name = source_name.strip()
            normalized_source_url = source_url.strip()

            existing = conn.execute(
                "SELECT source_url FROM user_sources WHERE user_id = ? AND source_name = ?",
                (normalized_user_id, normalized_source_name),
            ).fetchone()

            conn.execute(
                """
                INSERT INTO user_sources (user_id, source_name, source_url, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, source_name) DO UPDATE SET
                    source_url = excluded.source_url
                WHERE user_sources.source_url IS NOT excluded.source_url
                """,
                (normalized_user_id, normalized_source_name, normalized_source_url, utc_now()),
            )

            if existing is None:
                stats.inserted += 1
            elif existing[0] != normalized_source_url:
                stats.updated += 1

    conn.commit()
    return stats


def _validate_preferences(user_id: str, prefs: Any, stats: MigrationStats) -> tuple | None:
    if not isinstance(prefs, dict):
        stats.skipped.append(f"user_preferences[{user_id}]: expected object, got {type(prefs).__name__}")
        return None

    delivery_mode = prefs.get("delivery_mode", "stream")
    if delivery_mode not in {"stream", "digest"}:
        stats.skipped.append(f"user_preferences[{user_id}]: invalid delivery_mode={delivery_mode!r}")
        return None

    max_items = prefs.get("max_items_per_push", 3)
    if not isinstance(max_items, int) or max_items <= 0:
        stats.skipped.append(f"user_preferences[{user_id}]: invalid max_items_per_push={max_items!r}")
        return None

    only_top_news = prefs.get("only_top_news", True)
    if not isinstance(only_top_news, bool):
        stats.skipped.append(f"user_preferences[{user_id}]: invalid only_top_news={only_top_news!r}")
        return None

    quiet_hours = prefs.get("quiet_hours", {"start": 23, "end": 7})
    if not isinstance(quiet_hours, dict):
        stats.skipped.append(f"user_preferences[{user_id}]: invalid quiet_hours={quiet_hours!r}")
        return None

    quiet_start = quiet_hours.get("start", 23)
    quiet_end = quiet_hours.get("end", 7)
    if not isinstance(quiet_start, int) or not 0 <= quiet_start <= 23:
        stats.skipped.append(f"user_preferences[{user_id}]: invalid quiet_hours.start={quiet_start!r}")
        return None
    if not isinstance(quiet_end, int) or not 0 <= quiet_end <= 23:
        stats.skipped.append(f"user_preferences[{user_id}]: invalid quiet_hours.end={quiet_end!r}")
        return None

    return (
        user_id.strip(),
        delivery_mode,
        max_items,
        int(only_top_news),
        quiet_start,
        quiet_end,
        utc_now(),
    )


def migrate_user_preferences(conn: sqlite3.Connection, user_preferences_path: Path) -> MigrationStats:
    stats = MigrationStats()
    payload = load_json(user_preferences_path)

    for user_id, prefs in payload.items():
        if not isinstance(user_id, str) or not user_id.strip():
            stats.skipped.append(f"user_preferences: invalid user_id={user_id!r}")
            continue

        params = _validate_preferences(user_id, prefs, stats)
        if params is None:
            continue

        existing = conn.execute(
            "SELECT delivery_mode, max_items_per_push, only_top_news, quiet_start, quiet_end FROM user_preferences WHERE user_id = ?",
            (user_id.strip(),),
        ).fetchone()

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
            params,
        )

        if existing is None:
            stats.inserted += 1
        elif existing != params[1:6]:
            stats.updated += 1

    conn.commit()
    return stats


def migrate_groups(conn: sqlite3.Connection, groups_path: Path) -> MigrationStats:
    stats = MigrationStats()

    if not groups_path.exists():
        logging.warning("Файл %s не найден, пропускаю.", groups_path)
        return stats

    with groups_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    for idx, raw_line in enumerate(lines, start=1):
        chat_id = raw_line.strip()
        if not chat_id:
            continue
        if not (chat_id.lstrip("-").isdigit()):
            stats.skipped.append(f"groups.txt:{idx}: invalid chat_id={chat_id!r}")
            continue

        cursor = conn.execute(
            """
            INSERT INTO bot_groups (chat_id, added_at)
            VALUES (?, ?)
            ON CONFLICT(chat_id) DO NOTHING
            """,
            (chat_id, utc_now()),
        )
        if cursor.rowcount > 0:
            stats.inserted += 1

    conn.commit()
    return stats


def report(entity_name: str, stats: MigrationStats) -> None:
    logging.info(
        "%s: migrated=%d updated=%d skipped=%d",
        entity_name,
        stats.inserted,
        stats.updated,
        len(stats.skipped),
    )
    for item in stats.skipped:
        logging.warning("%s | skipped: %s", entity_name, item)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Миграция JSON/TXT хранилища в SQLite")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--user-sources", type=Path, default=DEFAULT_USER_SOURCES_PATH)
    parser.add_argument("--user-preferences", type=Path, default=DEFAULT_USER_PREFERENCES_PATH)
    parser.add_argument("--groups", type=Path, default=DEFAULT_GROUPS_PATH)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.verbose)

    conn = sqlite3.connect(args.db_path)
    try:
        ensure_tables(conn)
        user_sources_stats = migrate_user_sources(conn, args.user_sources)
        user_preferences_stats = migrate_user_preferences(conn, args.user_preferences)
        groups_stats = migrate_groups(conn, args.groups)

        report("user_sources", user_sources_stats)
        report("user_preferences", user_preferences_stats)
        report("bot_groups", groups_stats)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
