import asyncio
from decimal import Decimal

import aiohttp
from loguru import logger

import config
from database import db
from send_api import parse_amount, queue_items


TAKE_PAYMENT_URL = f"{config.API_BASE_URL}/p2cMerchant/takePayment"
GET_PAYMENTS_URL = f"{config.API_BASE_URL}/p2cMerchant/getPayments"
GET_WS_TOKEN_URL = f"{config.API_BASE_URL}/p2cMerchant/getWsToken"


class SniperBot:
    def __init__(self, user_id, api_key, proxy, min_amt, max_amt, bot_instance):
        self.user_id = user_id
        self.api_key = api_key
        self.proxy = proxy
        self.min = Decimal(str(min_amt))
        self.max = Decimal(str(max_amt))
        self.bot = bot_instance
        self.running = False
        self.session = None
        self.attempted_qrs = set()
        self.taken_payments = {}
        self.payment_statuses = {}

    def set_limits(self, min_amt, max_amt):
        self.min = Decimal(str(min_amt))
        self.max = Decimal(str(max_amt))
        logger.info(f"User {self.user_id} limits updated: {self.min} - {self.max}")

    async def send_notification(self, message):
        try:
            await self.bot.send_message(self.user_id, message, parse_mode="HTML")
        except Exception as exc:
            logger.error(f"Failed to send Telegram message to {self.user_id}: {exc}")

    async def stop(self, reason=None):
        self.running = False
        if self.session and not self.session.closed:
            await self.session.close()
        await db.set_running_status(self.user_id, False)
        if reason:
            logger.warning(f"Sniper stopped for {self.user_id}: {reason}")
            await self.send_notification(
                f"🛑 <b>Снайпер остановлен</b>\nПричина: {reason}"
            )

    async def api_request(self, method, url, **kwargs):
        try:
            async with self.session.request(
                method,
                url,
                proxy=self.proxy,
                timeout=config.REQUEST_TIMEOUT,
                **kwargs,
            ) as response:
                try:
                    payload = await response.json()
                except (aiohttp.ContentTypeError, ValueError):
                    payload = {
                        "ok": False,
                        "error": "InvalidResponse",
                        "description": (await response.text())[:200],
                    }
                return response.status, payload
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.warning(f"Send.tg request failed for {self.user_id}: {exc}")
            return 0, {"ok": False, "error": "ConnectionError"}

    async def monitor_payments(self):
        while self.running:
            try:
                payment_ids = list(self.taken_payments)
                if payment_ids:
                    status, payload = await self.api_request(
                        "POST", GET_PAYMENTS_URL, json={"payment_ids": payment_ids}
                    )
                    if status == 401:
                        await self.stop("API-ключ недействителен или отключён")
                        return
                    if payload.get("ok"):
                        for payment in payload.get("result", {}).get("payments", []):
                            await self.handle_payment_status(payment)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning(f"Payment monitor error for {self.user_id}: {exc}")
            await asyncio.sleep(config.POLL_INTERVAL)

    async def handle_payment_status(self, payment):
        payment_id = payment.get("payment_id")
        status = payment.get("status")
        if payment_id is None or not status:
            return
        previous = self.payment_statuses.get(payment_id)
        self.payment_statuses[payment_id] = status
        if previous == status or status == "processing":
            return

        amount = payment.get("in_amount", self.taken_payments.get(payment_id, "0"))
        await db.log_order(payment_id, self.user_id, amount, status)
        labels = {
            "completed": "✅ <b>Payment completed</b>",
            "canceled": "❌ <b>Payment canceled</b>",
            "disputed": "⚠️ <b>Payment disputed</b>",
            "refunded": "↩️ <b>Payment refunded</b>",
        }
        label = labels.get(status)
        if label:
            await self.send_notification(
                f"{label}\n\n💰 Amount: {amount} RUB\n"
                f"🆔 ID: <code>{payment_id}</code>"
            )

    async def try_take_order(self, qr):
        qr_id = qr.get("qr_id")
        amount = parse_amount(qr.get("in_amount"))
        if not qr_id or qr_id in self.attempted_qrs:
            return
        if not self.min <= amount <= self.max:
            return
        self.attempted_qrs.add(qr_id)

        status, payload = await self.api_request(
            "POST", TAKE_PAYMENT_URL, json={"qr_id": qr_id}
        )
        if status == 401:
            await self.stop("API-ключ недействителен или отключён")
            return
        if payload.get("ok"):
            payment = payload.get("result", {})
            payment_id = payment.get("payment_id")
            if payment_id is None:
                logger.warning(f"takePayment returned no payment_id: {payload}")
                return
            self.taken_payments[payment_id] = str(amount)
            self.payment_statuses[payment_id] = payment.get("status", "processing")
            await db.log_order(payment_id, self.user_id, amount, "processing")
            logger.success(
                f"User {self.user_id} took payment {payment_id}: {amount} RUB"
            )
            await self.send_notification(
                f"🔔 <b>New payment taken</b>\n\n"
                f"💰 Amount: {amount} RUB\n"
                f"🏪 Merchant: {payment.get('brand_name') or qr.get('brand_name') or '—'}\n"
                f"🆔 ID: <code>{payment_id}</code>"
            )
            return

        error = payload.get("error", "UnknownError")
        description = payload.get("description", "")
        logger.info(f"Payment {qr_id} was not taken: {error} {description}")
        if error in {"IpWhitelistRequired", "AccessDenied", "NoPermissions"}:
            await self.stop(f"Send.tg API: {error}. Проверьте scopes и IP whitelist")

    async def consume_websocket(self):
        status, token_payload = await self.api_request("GET", GET_WS_TOKEN_URL)
        if not token_payload.get("ok"):
            error = token_payload.get("error", f"HTTP {status}")
            if error in {
                "Unauthorized",
                "ApiKeyExpired",
                "AccessDenied",
                "IpWhitelistRequired",
                "NoPermissions",
            }:
                await self.stop(f"getWsToken: {error}")
                return
            raise RuntimeError(error)

        ws_token = token_payload.get("result", {}).get("ws_token")
        if not ws_token:
            raise RuntimeError("getWsToken returned no ws_token")

        async with self.session.ws_connect(
            config.API_WS_URL,
            params={"ws_token": ws_token},
            proxy=self.proxy,
            heartbeat=45,
            timeout=config.REQUEST_TIMEOUT,
        ) as ws:
            logger.info(f"Send.tg WebSocket connected for {self.user_id}")
            async for message in ws:
                if not self.running:
                    return
                if message.type != aiohttp.WSMsgType.TEXT:
                    continue
                try:
                    payload = message.json()
                except ValueError:
                    continue
                if not isinstance(payload, dict):
                    continue

                if payload.get("error"):
                    error = payload["error"]
                    retry_after = payload.get("retry_after")
                    if error in {"AccessDenied", "IpWhitelistRequired"}:
                        await self.stop(f"WebSocket: {error}")
                        return
                    if retry_after:
                        await asyncio.sleep(min(float(retry_after), 60))
                    raise RuntimeError(error)
                if payload.get("event") == "ping":
                    await ws.send_json({"event": "pong"})
                    continue

                for qr in queue_items(payload):
                    logger.info(
                        f"QR {qr.get('qr_id')} | {qr.get('in_amount')} RUB | "
                        f"{qr.get('brand_name', '—')}"
                    )
                    asyncio.create_task(self.try_take_order(qr))

    async def start(self):
        self.running = True
        headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        monitor_task = None
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                self.session = session
                monitor_task = asyncio.create_task(self.monitor_payments())
                while self.running:
                    try:
                        await self.consume_websocket()
                    except asyncio.CancelledError:
                        return
                    except Exception as exc:
                        if self.running:
                            logger.warning(
                                f"Send.tg WebSocket disconnected for {self.user_id}: {exc}"
                            )
                            await asyncio.sleep(5)
        finally:
            if monitor_task:
                monitor_task.cancel()
                await asyncio.gather(monitor_task, return_exceptions=True)
            self.session = None
            if self.running:
                self.running = False
                await db.set_running_status(self.user_id, False)
