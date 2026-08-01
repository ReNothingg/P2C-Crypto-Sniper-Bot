from __future__ import annotations

import asyncio
from decimal import Decimal
from html import escape
from typing import Any

import aiohttp
from loguru import logger

from p2c_bot.core import config
from p2c_bot.infrastructure.database import db
from p2c_bot.notifications.telegram import TelegramNotifier
from p2c_bot.p2c.parsing import parse_amount, queue_items


class SniperBot:
    def __init__(
        self,
        account: dict[str, Any],
        notifier: TelegramNotifier,
    ) -> None:
        self.account_id = int(account["account_id"])
        self.user_id = int(account["user_id"])
        self.api_key = account["api_key"]
        self.min = Decimal(str(account.get("min_amount") or 0))
        self.max = Decimal(str(account.get("max_amount") or 1_000_000_000))
        self.notifier = notifier
        self.running = False
        self.session: aiohttp.ClientSession | None = None
        self.attempted_qrs: set[str] = set()
        self.taken_payments: dict[str, str] = {}
        self.payment_statuses: dict[str, str] = {}

    def set_limits(self, min_amount: float, max_amount: float) -> None:
        self.min = Decimal(str(min_amount))
        self.max = Decimal(str(max_amount))

    async def stop(self, reason: str | None = None) -> None:
        was_running = self.running
        self.running = False
        await db.set_running_status(self.account_id, False)
        if reason and was_running:
            await self.notifier.send_text(
                "<b>Снайпер остановлен</b>\n"
                f"Причина: {escape(reason)}"
            )

    async def api_request(
        self, method: str, url: str, **kwargs: Any
    ) -> tuple[int, dict[str, Any]]:
        if not self.session:
            return 0, {"ok": False, "error": "Нет активной сессии"}
        try:
            async with self.session.request(
                method,
                url,
                timeout=config.REQUEST_TIMEOUT,
                **kwargs,
            ) as response:
                try:
                    payload = await response.json()
                except (aiohttp.ContentTypeError, ValueError):
                    payload = {
                        "ok": False,
                        "error": "Некорректный ответ API",
                        "description": (await response.text())[:200],
                    }
                return response.status, payload
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.warning("Ошибка API для аккаунта {}: {}", self.account_id, exc)
            return 0, {"ok": False, "error": "Ошибка соединения"}

    async def monitor_payments(self) -> None:
        while self.running:
            try:
                payment_ids = list(self.taken_payments)
                if payment_ids:
                    status, payload = await self.api_request(
                        "POST",
                        "https://api.send.tg/v1/p2cMerchant/getPayments",
                        json={"payment_ids": payment_ids},
                    )
                    if status == 401:
                        await self.stop("API-ключ недействителен или отключён")
                        return
                    if payload.get("ok"):
                        payments = payload.get("result", {}).get("payments", [])
                        for payment in payments:
                            if isinstance(payment, dict):
                                await self.handle_payment_status(payment)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning(
                    "Ошибка проверки платежей аккаунта {}: {}",
                    self.account_id,
                    exc,
                )
            await asyncio.sleep(config.POLL_INTERVAL)

    async def handle_payment_status(self, payment: dict[str, Any]) -> None:
        payment_id = payment.get("payment_id")
        status = payment.get("status")
        if payment_id is None or not status:
            return
        payment_id = str(payment_id)
        previous = self.payment_statuses.get(payment_id)
        self.payment_statuses[payment_id] = status
        if previous == status or status == "processing":
            return

        amount = payment.get("in_amount", self.taken_payments.get(payment_id, "0"))
        await db.log_order(
            payment_id, self.user_id, float(parse_amount(amount)), status, self.account_id
        )
        labels = {
            "completed": "Платёж завершён",
            "canceled": "Платёж отменён",
            "disputed": "По платежу открыт спор",
            "refunded": "Платёж возвращён",
        }
        if status in labels:
            await self.notifier.send_text(
                f"<b>{labels[status]}</b>\n\n"
                f"<b>Сумма:</b> {escape(str(amount))} RUB\n"
                f"<b>ID:</b> <code>{escape(payment_id)}</code>"
            )

    async def try_take_order(self, qr: dict[str, Any]) -> None:
        qr_id = qr.get("qr_id")
        amount = parse_amount(qr.get("in_amount"))
        if not qr_id or str(qr_id) in self.attempted_qrs:
            return
        if not self.min <= amount <= self.max:
            return
        qr_id = str(qr_id)
        self.attempted_qrs.add(qr_id)

        status, payload = await self.api_request(
            "POST",
            "https://api.send.tg/v1/p2cMerchant/takePayment",
            json={"qr_id": qr_id},
        )
        if status == 401:
            await self.stop("API-ключ недействителен или отключён")
            return
        if payload.get("ok"):
            payment = payload.get("result", {})
            if not isinstance(payment, dict):
                payment = {}
            payment_id = payment.get("payment_id")
            if payment_id is None:
                logger.warning("В ответе takePayment отсутствует payment_id: {}", payload)
                return
            payment_id = str(payment_id)
            self.taken_payments[payment_id] = str(amount)
            self.payment_statuses[payment_id] = payment.get("status", "processing")
            await db.log_order(
                payment_id,
                self.user_id,
                float(amount),
                "processing",
                self.account_id,
            )
            await self.notifier.send_payment_card(payment, qr, amount)
            return

        await db.log_order(
            f"missed:{qr_id}",
            self.user_id,
            float(amount),
            "missed",
            self.account_id,
        )
        error = payload.get("error", "Неизвестная ошибка")
        description = payload.get("description", "")
        logger.info("Заявка {} пропущена: {} {}", qr_id, error, description)
        if error in {"IpWhitelistRequired", "AccessDenied", "NoPermissions"}:
            await self.stop(f"Ошибка API: {error}. Проверьте права и список IP")

    async def consume_websocket(self) -> None:
        status, payload = await self.api_request(
            "GET", "https://api.send.tg/v1/p2cMerchant/getWsToken"
        )
        if not payload.get("ok"):
            error = payload.get("error", f"HTTP {status}")
            if error in {
                "Unauthorized",
                "ApiKeyExpired",
                "AccessDenied",
                "IpWhitelistRequired",
                "NoPermissions",
            }:
                await self.stop(f"Не удалось подключиться: {error}")
                return
            raise RuntimeError(str(error))

        ws_token = payload.get("result", {}).get("ws_token")
        if not ws_token:
            raise RuntimeError("API не вернул токен WebSocket")
        assert self.session
        async with self.session.ws_connect(
            "wss://api.send.tg/v1/p2cMerchant/ws",
            params={"ws_token": ws_token},
            heartbeat=45,
            timeout=config.REQUEST_TIMEOUT,
        ) as websocket:
            async for message in websocket:
                if not self.running:
                    return
                if message.type != aiohttp.WSMsgType.TEXT:
                    continue
                try:
                    event = message.json()
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("error"):
                    error = str(event["error"])
                    if error in {"AccessDenied", "IpWhitelistRequired"}:
                        await self.stop(f"Ошибка WebSocket: {error}")
                        return
                    if event.get("retry_after"):
                        await asyncio.sleep(
                            min(float(event["retry_after"]), 60)
                        )
                    raise RuntimeError(error)
                if event.get("event") == "ping":
                    await websocket.send_json({"event": "pong"})
                    continue
                for qr in queue_items(event):
                    asyncio.create_task(self.try_take_order(qr))

    async def start(self) -> None:
        self.running = True
        await db.set_running_status(self.account_id, True)
        headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        monitor_task: asyncio.Task | None = None
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
                                "WebSocket аккаунта {} отключён: {}",
                                self.account_id,
                                exc,
                            )
                            await asyncio.sleep(5)
        finally:
            if monitor_task:
                monitor_task.cancel()
                await asyncio.gather(monitor_task, return_exceptions=True)
            self.session = None
            if self.running:
                self.running = False
                await db.set_running_status(self.account_id, False)
