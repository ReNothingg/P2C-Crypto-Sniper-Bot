import logging

import aiosqlite


DB_NAME = "bot_users.db"


class Database:
    def __init__(self):
        self.conn = None

    async def connect(self):
        if self.conn:
            return
        self.conn = await aiosqlite.connect(DB_NAME, check_same_thread=False)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL;")
        await self.conn.execute("PRAGMA synchronous=NORMAL;")
        await self.create_tables()
        logging.info("Database connected (WAL mode)")

    async def close(self):
        if self.conn:
            await self.conn.close()
            self.conn = None
            logging.info("Database connection closed")

    async def create_tables(self):
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                api_key TEXT,
                proxy TEXT,
                min_amount REAL DEFAULT 500,
                max_amount REAL DEFAULT 5000,
                is_running INTEGER DEFAULT 0
            )
            """
        )
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                user_id INTEGER,
                amount REAL,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor = await self.conn.execute("PRAGMA table_info(users)")
        columns = {row[1] for row in await cursor.fetchall()}
        if "api_key" not in columns:
            await self.conn.execute("ALTER TABLE users ADD COLUMN api_key TEXT")
            if "access_token" in columns:
                await self.conn.execute(
                    "UPDATE users SET api_key = access_token WHERE api_key IS NULL"
                )
        await self.conn.commit()

    async def add_user(self, user_id, username):
        await self.conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username),
        )
        await self.conn.commit()

    async def update_api_key(self, user_id, api_key, proxy):
        cursor = await self.conn.execute(
            "UPDATE users SET api_key = ?, proxy = ? WHERE user_id = ?",
            (api_key, proxy, user_id),
        )
        if cursor.rowcount == 0:
            await self.conn.execute(
                """
                INSERT INTO users (user_id, username, api_key, proxy)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, "Trader", api_key, proxy),
            )
        await self.conn.commit()

    async def update_limits(self, user_id, min_amount, max_amount):
        await self.conn.execute(
            "UPDATE users SET min_amount = ?, max_amount = ? WHERE user_id = ?",
            (min_amount, max_amount, user_id),
        )
        await self.conn.commit()

    async def get_user(self, user_id):
        async with self.conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            return await cursor.fetchone()

    async def get_all_users(self):
        async with self.conn.execute("SELECT * FROM users") as cursor:
            return await cursor.fetchall()

    async def get_active_runners(self):
        async with self.conn.execute(
            "SELECT * FROM users WHERE is_running = 1"
        ) as cursor:
            return await cursor.fetchall()

    async def set_running_status(self, user_id, status):
        await self.conn.execute(
            "UPDATE users SET is_running = ? WHERE user_id = ?",
            (1 if status else 0, user_id),
        )
        await self.conn.commit()

    async def log_order(self, order_id, user_id, amount, status):
        await self.conn.execute(
            """
            INSERT INTO orders (order_id, user_id, amount, status)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(order_id) DO UPDATE SET status=excluded.status
            """,
            (str(order_id), user_id, float(amount), status),
        )
        await self.conn.commit()

    async def get_total_caught_volume(self, user_id):
        async with self.conn.execute(
            "SELECT SUM(amount) FROM orders WHERE user_id = ?", (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
            return float(result[0] or 0.0)

    async def get_daily_volume(self, user_id):
        async with self.conn.execute(
            """
            SELECT SUM(amount) FROM orders
            WHERE user_id = ? AND created_at >= datetime('now', '-1 day')
            """,
            (user_id,),
        ) as cursor:
            result = await cursor.fetchone()
            return float(result[0] or 0.0)


db = Database()
