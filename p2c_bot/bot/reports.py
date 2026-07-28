from __future__ import annotations

from html import escape

from aiogram import Bot
from loguru import logger

from p2c_bot.core import config
from p2c_bot.infrastructure.database import db


async def send_daily_reports(bot: Bot) -> None:
    users = await db.get_all_users()
    admin_lines = ["<b>Ежедневный отчёт по системе</b>", ""]
    total_volume = 0.0
    for user in users:
        user_id = int(user["user_id"])
        stats = await db.get_statistics(user_id)
        volume = float(stats.get("daily_volume", 0))
        total_volume += volume
        try:
            await bot.send_message(
                user_id,
                "<b>Ежедневный отчёт</b>\n\n"
                f"Объём за сутки: <b>{volume:,.2f} RUB</b>\n"
                f"Поймано заявок: {stats.get('daily_orders_count', 0)}\n"
                f"Пропущено: {stats.get('daily_skipped_count', 0)}",
            )
        except Exception as exc:
            logger.warning("Не удалось отправить отчёт {}: {}", user_id, exc)
        username = escape(user.get("username") or "без имени")
        admin_lines.append(
            f"{username} (<code>{user_id}</code>): {volume:,.0f} RUB"
        )
    admin_lines.extend(["", f"<b>Общий объём: {total_volume:,.0f} RUB</b>"])
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "\n".join(admin_lines))
        except Exception as exc:
            logger.warning("Не удалось отправить отчёт администратору: {}", exc)
