import asyncio
import ssl
import time
import random
import socket
import gc
import orjson
import aiohttp
from loguru import logger
from database import db
import config

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

WS_URL = "wss://app.cr.bot/internal/v1/p2c-socket/?EIO=4&transport=websocket"
API_TAKE_URL = "https://app.cr.bot/internal/v1/p2c/payments/take"
PAYMENTS_URL = "https://app.cr.bot/internal/v1/p2c/payments?size=20"

class SniperBot:
    def __init__(self, user_id, token, req_id, proxy, min_amt, max_amt, bot_instance):
        self.user_id = user_id
        self.token = token
        self.req_id = req_id
        self.proxy = proxy
        self.min = min_amt
        self.max = max_amt
        self.bot = bot_instance

        self.running = False
        self.session = None
        self.known_orders = set()

        self.payload_bytes = orjson.dumps({"payment_method_id": self.req_id})
        self.ua = random.choice(config.USER_AGENTS)

    def set_limits(self, min_amt, max_amt):
        self.min = min_amt
        self.max = max_amt
        logger.info(f"User {self.user_id} limits updated: {self.min} - {self.max}")

    async def send_notification(self, message):
        async def _safe_send():
            try:
                await self.bot.send_message(self.user_id, message, parse_mode="HTML")
            except Exception as e:
                logger.error(f"⚠️ Failed to send TG message to {self.user_id}: {e}")
        asyncio.create_task(_safe_send())

    async def stop(self, reason=None):
        self.running = False
        if self.session:
            await self.session.close()

        gc.enable()
        gc.collect()

        await db.set_running_status(self.user_id, False)

        if reason:
            logger.warning(f"Sniper stopped for {self.user_id}: {reason}")
            await self.send_notification(f"🛑 <b>Снайпер остановлен!</b>\nПричина: {reason}")

    def get_safe_amount(self, order_data):
        amt = order_data.get('in_amount') or order_data.get('amount')
        try:
            return (float(amt) / 10**18) if amt else 0.0
        except:
            return 0.0

    async def monitor_payments(self):
        logger.info(f"Started monitoring (and warmer) for {self.user_id}")
        iteration_count = 0

        while self.running:
            try:
                if not self.session or self.session.closed:
                    break

                start_time = time.perf_counter()

                async with self.session.get(PAYMENTS_URL, proxy=self.proxy, timeout=10) as resp:
                    ping = (time.perf_counter() - start_time) * 1000
                    logger.info(f"📶 Ping {self.user_id}: {ping:.2f}ms") # ЛОГИ БЛЯДЬ

                    if resp.status == 401:
                        await self.stop("Токен истек (Ошибка 401). Обновите токен!")
                        return

                    if resp.status == 200:
                        data = await resp.json()
                        orders = data.get('data', [])

                        for order in orders:
                            oid = order.get('id')
                            status = order.get('status')
                            status_key = f"{oid}_{status}"

                            if status == "completed" and status_key not in self.known_orders:
                                self.known_orders.add(status_key)
                                amount = self.get_safe_amount(order)
                                await self.send_notification(
                                    f"✅ <b>Payment Completed!</b>\n\n"
                                    f"💰 Amount: {amount} RUB\n"
                                    f"🆔 ID: <code>{oid}</code>"
                                )
                            elif status == "canceled":
                                 self.known_orders.add(status_key)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"⚠️ Ping/Monitor error: {e}") # ЛОГИ БЛЯДЬ
                pass

            iteration_count += 1
            if iteration_count >= 12:
                gc.collect()
                iteration_count = 0

            await asyncio.sleep(5)

    async def send_single_shot(self, url, payload_bytes):
        try:
            start = time.perf_counter()
            async with self.session.post(url, data=payload_bytes, proxy=self.proxy, timeout=5) as response:
                latency = (time.perf_counter() - start) * 1000
                text = await response.text()
                return response.status, latency, text
        except Exception:
            return 0, 0, ""

    async def try_take_order(self, order_id, amount):
        url = f"{API_TAKE_URL}/{order_id}"

        count = config.CONCURRENT_REQUESTS
        tasks = [asyncio.create_task(self.send_single_shot(url, self.payload_bytes)) for _ in range(count)]

        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for p in pending: p.cancel()

        for task in done:
            try:
                status, latency, response_text = task.result()

                if status == 200:
                    try:
                        await db.log_order(order_id, self.user_id, amount, "sniped")
                        logger.success(f"✅ User {self.user_id} TOOK: {amount} RUB | {latency:.2f}ms")
                        await self.send_notification(
                            f"🔔 <b>New Payment Detected!</b>\n\n"
                            f"💰 Amount: {amount} RUB\n"
                            f"🆔 ID: <code>{order_id}</code>\n"
                            f"⚡ Speed: {latency:.2f}ms"
                        )
                        return
                    except Exception as e:
                        logger.error(f"DB Log Error: {e}")

                elif status == 401:
                    await self.stop("Токен истек во время захвата!")
                    return
                elif status != 0:
                    res_str = response_text[:50] if response_text else "Empty"
                    logger.warning(f"❌ User {self.user_id} MISSED: {amount} RUB | {status} | {res_str}")

            except Exception as e:
                logger.error(f"Task result error: {e}")

    async def start(self):
        self.running = True
        gc.disable()

        headers = {
            "User-Agent": self.ua,
            "Cookie": f"access_token={self.token}",
            "Origin": "https://app.cr.bot",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*"
        }

        conn = aiohttp.TCPConnector(
            ssl=ssl_ctx,
            limit=0,
            ttl_dns_cache=3000,
            keepalive_timeout=60,
            family=socket.AF_INET
        )

        try:
            async with aiohttp.ClientSession(headers=headers, connector=conn) as session:
                self.session = session
                monitor_task = asyncio.create_task(self.monitor_payments())

                while self.running:
                    try:
                        async with session.ws_connect(WS_URL, headers=headers, heartbeat=15, proxy=self.proxy, timeout=10) as ws:
                            logger.info(f"Socket connected for {self.user_id}")

                            async for msg in ws:
                                if not self.running: break

                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    payload = msg.data

                                    if payload.startswith("42"):
                                        if '"op":"add"' in payload:
                                            try:
                                                idx = payload.find('[')
                                                if idx != -1:
                                                    data = orjson.loads(payload[idx:])
                                                    if len(data) > 1:
                                                        items = data[1]
                                                        for item in items:
                                                            if item["op"] == "add":
                                                                d = item["data"]
                                                                try:
                                                                    amt = float(d.get("in_amount", 0))
                                                                    logger.info(f"👀 Ордер: {d.get('id')} | Сумма: {amt:.2f} RUB")

                                                                    if self.min <= amt <= self.max:
                                                                        asyncio.create_task(self.try_take_order(d.get("id"), amt))
                                                                except Exception as e:
                                                                    logger.error(f"Error parsing order: {e}")
                                            except Exception:
                                                pass

                                    elif payload.startswith("0"):
                                        await ws.send_str("40")
                                    elif payload == "2":
                                        await ws.send_str("3")
                                    elif payload.startswith("40"):
                                        await ws.send_str('42["list:initialize"]')

                    except Exception as e:
                        logger.error(f"Socket died for {self.user_id}: {e}")
                        await asyncio.sleep(5)

                monitor_task.cancel()
        except Exception as e:
            logger.critical(f"Critical sniper error {self.user_id}: {e}")
        finally:
            gc.enable()