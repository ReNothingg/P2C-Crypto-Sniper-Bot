from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from p2c_bot.core import config


class Database:
    def __init__(self, path: str | Path = config.DB_PATH) -> None:
        self.path = str(path)
        self.connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.connection = await aiosqlite.connect(self.path)
        self.connection.row_factory = aiosqlite.Row
        await self.connection.execute("PRAGMA journal_mode=WAL")
        await self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                api_key TEXT,
                min_amount REAL DEFAULT 0,
                max_amount REAL DEFAULT 1000000000,
                is_running INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS merchant_accounts (
                account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                api_key TEXT NOT NULL UNIQUE,
                min_amount REAL DEFAULT 0,
                max_amount REAL DEFAULT 1000000000,
                is_running INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                account_id INTEGER,
                amount REAL DEFAULT 0,
                status TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await self._ensure_column("orders", "account_id", "INTEGER")
        await self.connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id)"
        )
        await self._migrate_legacy_accounts()
        await self.connection.commit()

    async def _ensure_column(self, table: str, column: str, sql_type: str) -> None:
        assert self.connection
        cursor = await self.connection.execute(f"PRAGMA table_info({table})")
        columns = {row["name"] for row in await cursor.fetchall()}
        if column not in columns:
            await self.connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"
            )

    async def _migrate_legacy_accounts(self) -> None:
        assert self.connection
        await self.connection.execute(
            """
            INSERT OR IGNORE INTO merchant_accounts
                (user_id, api_key, min_amount, max_amount, is_running)
            SELECT user_id, api_key, min_amount, max_amount, 0
            FROM users
            WHERE api_key IS NOT NULL AND TRIM(api_key) != ''
            """
        )

    async def close(self) -> None:
        if self.connection:
            await self.connection.close()
            self.connection = None

    async def add_user(self, user_id: int, username: str | None) -> None:
        assert self.connection
        await self.connection.execute(
            """
            INSERT INTO users (user_id, username)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
            """,
            (user_id, username),
        )
        await self.connection.commit()

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        assert self.connection
        cursor = await self.connection.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_all_users(self) -> list[dict[str, Any]]:
        assert self.connection
        cursor = await self.connection.execute("SELECT * FROM users")
        return [dict(row) for row in await cursor.fetchall()]

    async def add_account(self, user_id: int, api_key: str) -> int:
        assert self.connection
        user = await self.get_user(user_id)
        limits = (
            float(user["min_amount"] or 0),
            float(user["max_amount"] or 1_000_000_000),
        ) if user else (0.0, 1_000_000_000.0)
        await self.connection.execute(
            """
            INSERT INTO merchant_accounts
                (user_id, api_key, min_amount, max_amount)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(api_key) DO NOTHING
            """,
            (user_id, api_key, *limits),
        )
        await self.connection.commit()
        cursor = await self.connection.execute(
            """
            SELECT account_id FROM merchant_accounts
            WHERE api_key = ? AND user_id = ?
            """,
            (api_key, user_id),
        )
        row = await cursor.fetchone()
        if not row:
            raise ValueError("Этот API-ключ уже подключён к другому пользователю")
        return int(row["account_id"])

    async def get_accounts(self, user_id: int) -> list[dict[str, Any]]:
        assert self.connection
        cursor = await self.connection.execute(
            """
            SELECT * FROM merchant_accounts
            WHERE user_id = ?
            ORDER BY account_id
            """,
            (user_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def update_limits(
        self, user_id: int, min_amount: float, max_amount: float
    ) -> None:
        assert self.connection
        await self.connection.execute(
            "UPDATE users SET min_amount = ?, max_amount = ? WHERE user_id = ?",
            (min_amount, max_amount, user_id),
        )
        await self.connection.execute(
            """
            UPDATE merchant_accounts
            SET min_amount = ?, max_amount = ?
            WHERE user_id = ?
            """,
            (min_amount, max_amount, user_id),
        )
        await self.connection.commit()

    async def set_running_status(self, account_id: int, running: bool) -> None:
        assert self.connection
        await self.connection.execute(
            "UPDATE merchant_accounts SET is_running = ? WHERE account_id = ?",
            (int(running), account_id),
        )
        await self.connection.commit()

    async def reset_running_statuses(self) -> None:
        assert self.connection
        await self.connection.execute(
            "UPDATE merchant_accounts SET is_running = 0"
        )
        await self.connection.execute("UPDATE users SET is_running = 0")
        await self.connection.commit()

    async def log_order(
        self,
        order_id: str,
        user_id: int,
        amount: float,
        status: str,
        account_id: int | None = None,
    ) -> None:
        assert self.connection
        await self.connection.execute(
            """
            INSERT INTO orders (order_id, user_id, account_id, amount, status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(order_id) DO UPDATE SET
                account_id = excluded.account_id,
                amount = excluded.amount,
                status = excluded.status
            """,
            (order_id, user_id, account_id, amount, status),
        )
        await self.connection.commit()

    async def get_statistics(self, user_id: int) -> dict[str, float | int]:
        assert self.connection
        cursor = await self.connection.execute(
            """
            SELECT
                COUNT(CASE WHEN status != 'missed' THEN 1 END) AS orders_count,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) AS completed_count,
                COUNT(CASE WHEN status = 'missed' THEN 1 END) AS skipped_count,
                COALESCE(SUM(CASE WHEN status != 'missed' THEN amount END), 0)
                    AS total_volume,
                COUNT(CASE WHEN status != 'missed'
                    AND datetime(created_at) >= datetime('now', '-1 day')
                    THEN 1 END) AS daily_orders_count,
                COUNT(CASE WHEN status = 'completed'
                    AND datetime(created_at) >= datetime('now', '-1 day')
                    THEN 1 END) AS daily_completed_count,
                COUNT(CASE WHEN status = 'missed'
                    AND datetime(created_at) >= datetime('now', '-1 day')
                    THEN 1 END) AS daily_skipped_count,
                COALESCE(SUM(CASE WHEN status != 'missed'
                    AND datetime(created_at) >= datetime('now', '-1 day')
                    THEN amount END), 0) AS daily_volume
            FROM orders
            WHERE user_id = ?
            """,
            (user_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else {}

    async def get_daily_volume(self, user_id: int) -> float:
        return float((await self.get_statistics(user_id)).get("daily_volume", 0))


db = Database()
