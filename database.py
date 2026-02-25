import aiosqlite
import logging

DB_NAME = "bot_users.db"

class Database:
    def __init__(self):
        self.conn = None

    async def connect(self):
        if not self.conn:
            self.conn = await aiosqlite.connect(DB_NAME, check_same_thread=False)
            await self.conn.execute("PRAGMA journal_mode=WAL;")
            await self.conn.execute("PRAGMA synchronous=NORMAL;")
            await self.create_tables()
            logging.info("Database connected (WAL mode)")

    async def close(self):
        if self.conn:
            await self.conn.close()
            logging.info("Database connection closed")

    async def create_tables(self):
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                access_token TEXT,
                req_id TEXT,
                proxy TEXT,
                min_amount REAL DEFAULT 500,
                max_amount REAL DEFAULT 5000,
                is_running INTEGER DEFAULT 0
            )
        """)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                user_id INTEGER,
                amount REAL,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.conn.commit()

    async def add_user(self, user_id, username):
        await self.conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username)
        )
        await self.conn.commit()

    async def update_token(self, user_id, token, req_id, proxy):
        cursor = await self.conn.execute("""
            UPDATE users
            SET access_token = ?, req_id = ?, proxy = ?
            WHERE user_id = ?
        """, (token, req_id, proxy, user_id))

        if cursor.rowcount == 0:
            await self.conn.execute("""
                INSERT INTO users (user_id, username, access_token, req_id, proxy)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, "Trader", token, req_id, proxy))
        await self.conn.commit()

    async def update_limits(self, user_id, min_amount, max_amount):
        await self.conn.execute(
            "UPDATE users SET min_amount = ?, max_amount = ? WHERE user_id = ?",
            (min_amount, max_amount, user_id)
        )
        await self.conn.commit()

    async def get_user(self, user_id):
        async with self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

    async def get_all_users(self):
        async with self.conn.execute("SELECT * FROM users") as cursor:
            return await cursor.fetchall()

    async def get_active_runners(self):
        async with self.conn.execute("SELECT * FROM users WHERE is_running = 1") as cursor:
            return await cursor.fetchall()

    async def set_running_status(self, user_id, status):
        await self.conn.execute(
            "UPDATE users SET is_running = ? WHERE user_id = ?",
            (1 if status else 0, user_id)
        )
        await self.conn.commit()

    async def log_order(self, order_id, user_id, amount, status):
        await self.conn.execute("""
            INSERT INTO orders (order_id, user_id, amount, status)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(order_id) DO UPDATE SET status=excluded.status
        """, (order_id, user_id, amount, status))
        await self.conn.commit()

    async def get_total_caught_volume(self, user_id):
        query = "SELECT SUM(amount) FROM orders WHERE user_id = ?"
        async with self.conn.execute(query, (user_id,)) as cursor:
            result = await cursor.fetchone()
            val = result[0] if result and result[0] else 0.0
            return float(val)

    async def get_daily_volume(self, user_id):
        query = """
            SELECT SUM(amount) FROM orders
            WHERE user_id = ?
            AND created_at >= datetime('now', '-1 day')
        """
        async with self.conn.execute(query, (user_id,)) as cursor:
            result = await cursor.fetchone()
            val = result[0] if result and result[0] else 0.0
            return float(val)

db = Database()