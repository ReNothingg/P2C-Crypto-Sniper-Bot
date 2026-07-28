from __future__ import annotations

import asyncio
from html import escape

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from p2c_bot.bot.access import AdminOnlyMiddleware
from p2c_bot.bot.dashboard import build_dashboard_html, build_dashboard_rich
from p2c_bot.bot.keyboards import dashboard_keyboard
from p2c_bot.bot.reports import send_daily_reports
from p2c_bot.bot.states import ConfigureLimits, ConnectAccount
from p2c_bot.core import config
from p2c_bot.infrastructure.database import db
from p2c_bot.p2c.api_keys import clean_api_key, fetch_merchant_config
from p2c_bot.p2c.manager import SniperManager

try:
    import uvloop

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

logger.add(
    "logs/sniper.log",
    rotation="10 MB",
    compression="zip",
    enqueue=True,
)

bot = Bot(
    token=config.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
dp.message.outer_middleware(AdminOnlyMiddleware())
dp.callback_query.outer_middleware(AdminOnlyMiddleware())
manager = SniperManager(bot)
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")


async def _merchant_views(
    accounts: list[dict],
) -> list[dict]:
    async def load(account: dict) -> dict:
        try:
            return await fetch_merchant_config(account["api_key"])
        except Exception:
            return {}

    return await asyncio.gather(*(load(account) for account in accounts))


async def send_dashboard(chat_id: int, user_id: int) -> None:
    accounts = await db.get_accounts(user_id)
    stats = await db.get_statistics(user_id)
    views = await _merchant_views(accounts)
    running = manager.is_user_active(user_id)
    keyboard = dashboard_keyboard(running=running)
    try:
        await bot.send_rich_message(
            chat_id=chat_id,
            rich_message=build_dashboard_rich(accounts, views, stats, running),
            reply_markup=keyboard,
        )
    except Exception as exc:
        logger.warning("Панель Rich Message недоступна: {}", exc)
        await bot.send_message(
            chat_id,
            build_dashboard_html(accounts, views, stats, running),
            reply_markup=keyboard,
        )


@dp.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await db.add_user(
        message.from_user.id,
        message.from_user.username,
    )
    await send_dashboard(message.chat.id, message.from_user.id)


@dp.callback_query(F.data == "connect_api")
async def connect_api(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ConnectAccount.api_key)
    await callback.message.answer(
        "<b>Отправьте API-ключ мерчанта</b>\n\n"
        "Для ключа нужны права на чтение и получение P2C-платежей."
    )
    await callback.answer()


@dp.message(ConnectAccount.api_key)
async def receive_api_key(message: types.Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Отправьте API-ключ обычным текстом.")
        return
    api_key = clean_api_key(message.text)
    try:
        merchant = await fetch_merchant_config(api_key)
    except Exception as exc:
        await state.clear()
        await message.answer(
            f"<b>Не удалось подключить API-ключ</b>\n{escape(str(exc))}"
        )
        await send_dashboard(message.chat.id, message.from_user.id)
        return
    await db.add_account(message.from_user.id, api_key)
    await state.clear()
    name = (
        merchant.get("brand_name")
        or merchant.get("merchant_name")
        or merchant.get("name")
        or "мерчант"
    )
    await message.answer(
        f"<b>API-ключ подключён</b>\nМерчант: {escape(str(name))}"
    )
    await send_dashboard(message.chat.id, message.from_user.id)


@dp.callback_query(F.data == "configure_limits")
async def configure_limits(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    await state.set_state(ConfigureLimits.values)
    await callback.message.answer(
        "<b>Введите минимальную и максимальную сумму</b>\n\n"
        "Например: <code>500 5000</code>"
    )
    await callback.answer()


@dp.message(ConfigureLimits.values)
async def receive_limits(message: types.Message, state: FSMContext) -> None:
    try:
        values = (message.text or "").replace(",", ".").split()
        if len(values) != 2:
            raise ValueError
        minimum, maximum = map(float, values)
        if minimum < 0 or maximum <= minimum:
            raise ValueError
    except ValueError:
        await message.answer(
            "Нужны два числа. Максимальная сумма должна быть больше минимальной."
        )
        return
    user_id = message.from_user.id
    await db.update_limits(user_id, minimum, maximum)
    for sniper in manager.get_user_snipers(user_id):
        sniper.set_limits(minimum, maximum)
    await state.clear()
    await message.answer(
        "<b>Лимиты обновлены</b>\n"
        f"Диапазон: {minimum:,.0f}–{maximum:,.0f} RUB".replace(",", " ")
    )
    await send_dashboard(message.chat.id, user_id)


@dp.callback_query(F.data == "toggle_sniper")
async def toggle_sniper(callback: types.CallbackQuery) -> None:
    user_id = callback.from_user.id
    accounts = await db.get_accounts(user_id)
    if not accounts:
        await callback.answer(
            "Сначала подключите хотя бы один API-ключ.",
            show_alert=True,
        )
        return
    if manager.is_user_active(user_id):
        await manager.stop_for_user(user_id)
        await callback.answer("Снайпер остановлен")
    else:
        await manager.start_for_user(user_id)
        await callback.answer("Снайпер запущен")
    try:
        await callback.message.delete()
    except Exception:
        pass
    await send_dashboard(callback.message.chat.id, user_id)


async def on_startup() -> None:
    await db.connect()
    await db.reset_running_statuses()
    if not scheduler.running:
        scheduler.add_job(
            send_daily_reports,
            "cron",
            hour=0,
            minute=0,
            args=[bot],
        )
        scheduler.start()


async def on_shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
    await manager.stop_all()
    await db.close()


async def run() -> None:
    if not config.BOT_TOKEN:
        raise RuntimeError("Переменная BOT_TOKEN не задана")
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await dp.start_polling(bot)
