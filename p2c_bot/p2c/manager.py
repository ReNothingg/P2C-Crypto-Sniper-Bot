from __future__ import annotations

import asyncio
from typing import Any

from aiogram import Bot

from p2c_bot.infrastructure.database import db
from p2c_bot.notifications.telegram import TelegramNotifier
from p2c_bot.p2c.sniper import SniperBot


class SniperManager:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.snipers: dict[int, SniperBot] = {}
        self.tasks: dict[int, asyncio.Task] = {}

    def is_user_active(self, user_id: int) -> bool:
        return any(
            sniper.user_id == user_id and sniper.running
            for sniper in self.snipers.values()
        )

    def get_user_snipers(self, user_id: int) -> list[SniperBot]:
        return [
            sniper for sniper in self.snipers.values() if sniper.user_id == user_id
        ]

    async def start_account(self, account: dict[str, Any]) -> bool:
        account_id = int(account["account_id"])
        existing = self.snipers.get(account_id)
        if existing and existing.running:
            return False
        sniper = SniperBot(
            account,
            TelegramNotifier(self.bot, int(account["user_id"])),
        )
        sniper.running = True
        await db.set_running_status(account_id, True)
        self.snipers[account_id] = sniper
        self.tasks[account_id] = asyncio.create_task(sniper.start())
        return True

    async def start_for_user(self, user_id: int) -> int:
        started = 0
        for account in await db.get_accounts(user_id):
            started += int(await self.start_account(account))
        return started

    async def stop_account(self, account_id: int) -> bool:
        sniper = self.snipers.get(account_id)
        if not sniper:
            await db.set_running_status(account_id, False)
            return False
        await sniper.stop()
        task = self.tasks.pop(account_id, None)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.snipers.pop(account_id, None)
        return True

    async def stop_for_user(self, user_id: int) -> int:
        ids = [
            account_id
            for account_id, sniper in self.snipers.items()
            if sniper.user_id == user_id
        ]
        for account_id in ids:
            await self.stop_account(account_id)
        for account in await db.get_accounts(user_id):
            await db.set_running_status(int(account["account_id"]), False)
        return len(ids)

    async def stop_all(self) -> None:
        for account_id in list(self.snipers):
            await self.stop_account(account_id)
