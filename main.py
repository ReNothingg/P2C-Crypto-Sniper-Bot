import asyncio
import logging
import sys
import ssl
import aiohttp
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import config
from database import db
from sniper import SniperBot

try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    logger.success("UVLoop enabled! (High Performance Mode)")
except ImportError:
    logger.warning("UVLoop not found! Install it: pip install uvloop")
    logger.warning("Running in slow mode...")


logger.add("logs/sniper.log", rotation="10 MB", compression="zip", enqueue=True)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

active_snipers = {}

class Form(StatesGroup):
    waiting_for_token = State()
    waiting_for_proxy = State()
    waiting_for_min = State()
    waiting_for_max = State()

def get_main_keyboard(user_id):
    buttons = [
        [KeyboardButton(text="🚀 Start Sniper"), KeyboardButton(text="🛑 Stop Sniper")],
        [KeyboardButton(text="➕ Update Token"), KeyboardButton(text="💰 Set Limits")],
        [KeyboardButton(text="👤 My Account"), KeyboardButton(text="📊 Daily Volume")]
    ]
    if user_id in config.ADMIN_IDS:
        buttons.append([KeyboardButton(text="👮 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_skip_keyboard():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ No Proxy (Skip)")]], resize_keyboard=True)

def clean_token_string(raw_text: str) -> str:
    text = raw_text.strip().strip('"').strip("'")
    if "access_token=" in text:
        text = text.split("access_token=")[1]
    if ";" in text:
        text = text.split(";")[0]
    return text.strip()

async def get_first_active_account(token: str, proxy: str = None):
    url = "https://app.cr.bot/internal/v1/p2c/accounts"
    headers = {
        "Cookie": f"access_token={token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    }
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, ssl=ssl_ctx, proxy=proxy, timeout=10) as resp:
                if resp.status != 200:
                    return None, f"Ошибка доступа (Code: {resp.status})."

                try:
                    data = await resp.json()
                except:
                    return None, "Ошибка парсинга JSON ответа."

                accounts = data.get('data', [])
                if not accounts and isinstance(data, list):
                    accounts = data

                if not accounts:
                    return None, "Токен рабочий, но нет реквизитов!"

                first_acc = accounts[0]
                acc_id = first_acc.get('id')
                title = first_acc.get('title', 'No Title')
                if title == 'No Title': title = first_acc.get('bank_code', 'Card')
                currency = first_acc.get('currency', 'RUB')

                return acc_id, f"{title} ({currency})"
    except Exception as e:
        return None, f"Ошибка соединения: {e}"

async def start_sniper_process(user_id, user_data):
    token = user_data[2]
    req_id = user_data[3]
    proxy = user_data[4]
    min_amt = user_data[5]
    max_amt = user_data[6]

    if not token:
        return False, "Нет токена"

    sniper = SniperBot(user_id, token, req_id, proxy, min_amt, max_amt, bot)
    task = asyncio.create_task(sniper.start())

    active_snipers[user_id] = {"task": task, "bot_obj": sniper}
    await db.set_running_status(user_id, True)
    return True, "Launched"

async def send_daily_reports():
    logger.info("🕛 Starting daily report sequence...")
    users = await db.get_all_users()
    admin_report = "📊 <b>Daily Admin Report (00:00 MSK)</b>\n\n"
    total_system_volume = 0

    for u in users:
        user_id = u[0]
        username = u[1]
        daily_vol = await db.get_daily_volume(user_id)

        if daily_vol > 0:
            total_system_volume += daily_vol
            try:
                await bot.send_message(
                    user_id,
                    f"🌙 <b>Ежедневный отчет</b>\n\n"
                    f"За прошедшие сутки вы поймали: <b>{daily_vol:,.2f} RUB</b>\n"
                    f"Продолжаем работу! 🚀",
                    parse_mode="HTML"
                )
            except Exception:
                pass
            admin_report += f"👤 {username} (ID: <code>{user_id}</code>): {daily_vol:,.0f}₽\n"

    admin_report += f"\n💰 <b>Total System: {total_system_volume:,.0f} RUB</b>"
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_report, parse_mode="HTML")
        except:
            pass

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await db.add_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "👋 <b>Привет!</b>\n\n"
        "<b>Как получить данные:</b>\n"
        "1. Зайдите на сайт <a href=\"https://app.cr.bot/\">CryptoBot</a> с ПК.\n"
        "2. Нажмите <b>F12</b> -> <b>Network</b>.\n"
        "3. Обновите страницу. Найдите запрос, где есть заголовок `Cookie`.\n"
        "4. Скопируйте значение `access_token` (без слова access_token=).\n\n"

        "<b>Управление Задачами (Tasks)</b>\n"
        "* <b>Create Task:</b> Создает новую задачу для добавленного аккаунта.\n"
        "* <b>Min/Max Amount:</b> Установка диапазона сумм (например, ловить от 500 до 5000 RUB).\n"
        "* <b>Start/Stop:</b> Запуск и остановка снайпера для конкретного аккаунта.\n"
        "* <b>Status:</b> Отображает текущее состояние.\n\n"

        "<b>Уведомления</b>\n"
        "Бот присылает уведомления в трех случаях:\n"
        "* 🔔 <b>New Payment Detected:</b> Ордер успешно взят.\n"
        "* ✅ <b>Payment Completed:</b> Ордер оплачен и закрыт.\n"
        "* ❌ <b>Error:</b> Ошибки (например, истек токен).",

        reply_markup=get_main_keyboard(message.from_user.id),
        parse_mode="HTML"
    )

@dp.message(F.text == "➕ Update Token")
async def cmd_add_account(message: types.Message, state: FSMContext):
    await message.answer("🔑 <b>Отправь Access Token:</b>", parse_mode="HTML")
    await state.set_state(Form.waiting_for_token)

@dp.message(Form.waiting_for_token)
async def process_token_step(message: types.Message, state: FSMContext):
    clean_token = clean_token_string(message.text)
    await state.update_data(token=clean_token)
    await message.answer("🌐 <b>Нужен Прокси?</b>\nФормат: <code>http://user:pass@ip:port</code>\nИли ❌ No Proxy.", reply_markup=get_skip_keyboard(), parse_mode="HTML")
    await state.set_state(Form.waiting_for_proxy)

@dp.message(Form.waiting_for_proxy)
async def process_proxy_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    token = data['token']
    proxy = None
    if message.text != "❌ No Proxy (Skip)":
        proxy = message.text.strip()
        if not proxy.startswith("http"): proxy = f"http://{proxy}"

    await message.answer("⏳ <b>Проверяю...</b>")
    acc_id, acc_info = await get_first_active_account(token, proxy)

    if not acc_id:
        await message.answer(f"❌ <b>Ошибка:</b>\n{acc_info}", reply_markup=get_main_keyboard(message.from_user.id))
        await state.clear()
        return

    await db.update_token(message.from_user.id, token, acc_id, proxy)
    await message.answer(f"✅ <b>Успешно!</b>\n💳 {acc_info}", reply_markup=get_main_keyboard(message.from_user.id), parse_mode="HTML")
    await state.clear()

@dp.message(F.text == "💰 Set Limits")
async def cmd_set_limits(message: types.Message, state: FSMContext):
    await message.answer("📉 Введите <b>Минимальную</b> сумму:", parse_mode="HTML")
    await state.set_state(Form.waiting_for_min)

@dp.message(Form.waiting_for_min)
async def process_min_limit(message: types.Message, state: FSMContext):
    try:
        min_amt = float(message.text.strip())
        if min_amt < 1:
            await message.answer("Введите число больше 0.")
            return
        await state.update_data(min_amt=min_amt)
        await message.answer(f"Минимум: {min_amt} RUB.\n📈 Введите <b>Максимальную</b> сумму:", parse_mode="HTML")
        await state.set_state(Form.waiting_for_max)
    except ValueError:
        await message.answer("Пожалуйста, введите число.")

@dp.message(Form.waiting_for_max)
async def process_max_limit(message: types.Message, state: FSMContext):
    try:
        max_amt = float(message.text.strip())
        data = await state.get_data()
        min_amt = data.get('min_amt', 0)

        if max_amt <= min_amt:
            await message.answer(f"❌ Максимум должен быть больше минимума ({min_amt}).")
            return

        uid = message.from_user.id
        await db.update_limits(uid, min_amt, max_amt)

        status_text = ""
        if uid in active_snipers:
            active_snipers[uid]["bot_obj"].set_limits(min_amt, max_amt)
            status_text = "\n⚡️ Настройки применены на лету!"
            logger.info(f"User {uid} updated limits dynamically.")

        await message.answer(f"✅ <b>Лимиты обновлены!</b>\nДиапазон: {min_amt} - {max_amt} RUB{status_text}", reply_markup=get_main_keyboard(uid), parse_mode="HTML")
        await state.clear()
    except ValueError:
        await message.answer("Нужно число.")

@dp.message(F.text == "🚀 Start Sniper")
async def start_sniper(message: types.Message):
    uid = message.from_user.id
    if uid in active_snipers:
        await message.answer("⚠️ Уже работает!")
        return

    user_data = await db.get_user(uid)
    if not user_data or not user_data[2]:
        await message.answer("❌ Сначала добавь токен.")
        return

    success, msg = await start_sniper_process(uid, user_data)
    if success:
        p_stat = "🌐 Proxy" if user_data[4] else "⚡ Direct (Fastest)"
        await message.answer(f"🚀 <b>Снайпер запущен!</b> | {p_stat}\n<i>Limits: {user_data[5]} - {user_data[6]} RUB</i>", parse_mode="HTML")
    else:
        await message.answer(f"❌ Ошибка: {msg}")

@dp.message(F.text == "🛑 Stop Sniper")
async def stop_sniper(message: types.Message):
    uid = message.from_user.id
    if uid not in active_snipers:
        await message.answer("😴 Не работает.")
        return
    await active_snipers[uid]["bot_obj"].stop(reason="Остановлен пользователем")
    del active_snipers[uid]
    await message.answer("🛑 Стоп.")

@dp.message(F.text == "👤 My Account")
async def my_account(message: types.Message):
    user_data = await db.get_user(message.from_user.id)
    if not user_data:
        await message.answer("Нет данных.")
        return
    status = "🟢 ON" if message.from_user.id in active_snipers else "🔴 OFF"
    p_view = "YES" if user_data[4] else "NO"
    await message.answer(f"👤 <b>Account</b>\nStatus: {status}\nProxy: {p_view}\nMin: {user_data[5]} RUB\nMax: {user_data[6]} RUB", parse_mode="HTML")

@dp.message(F.text == "📊 Daily Volume")
async def show_volume(message: types.Message):
    vol = await db.get_daily_volume(message.from_user.id)
    await message.answer(f"📊 Объем за 24ч: <b>{vol:,.2f} RUB</b>", parse_mode="HTML")

@dp.message(F.text == "👮 Admin Panel")
async def admin_panel(message: types.Message):
    if message.from_user.id not in config.ADMIN_IDS: return
    users = await db.get_all_users()
    msg = f"👮 Users: {len(users)} | Active: {len(active_snipers)}\n\n"
    for u in users:
        is_active = "🟢" if u[0] in active_snipers else "🔴"
        vol = await db.get_total_caught_volume(u[0])
        msg += f"{is_active} ID: <code>{u[0]}</code> | {vol:.0f}₽\n"
    await message.answer(msg, parse_mode="HTML")

async def on_startup():
    await db.connect()
    runners = await db.get_active_runners()
    logger.info(f"🔄 Restoring {len(runners)} snipers...")
    for user_data in runners:
        asyncio.create_task(start_sniper_process(user_data[0], user_data))

async def on_shutdown():
    for uid, data in active_snipers.items():
        await data["bot_obj"].stop(reason="Restart/Shutdown")
    await db.close()

async def main():
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(send_daily_reports, "cron", hour=0, minute=0)
    scheduler.start()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")