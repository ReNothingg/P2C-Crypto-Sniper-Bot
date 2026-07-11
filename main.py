import asyncio
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
    waiting_for_api_key = State()
    waiting_for_proxy = State()
    waiting_for_min = State()
    waiting_for_max = State()

def get_main_keyboard(user_id):
    buttons = [
        [KeyboardButton(text="🚀 Start Sniper"), KeyboardButton(text="🛑 Stop Sniper")],
        [KeyboardButton(text="➕ Update API Key"), KeyboardButton(text="💰 Set Limits")],
        [KeyboardButton(text="👤 My Account"), KeyboardButton(text="📊 Daily Volume")]
    ]
    if user_id in config.ADMIN_IDS:
        buttons.append([KeyboardButton(text="👮 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_skip_keyboard():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ No Proxy (Skip)")]], resize_keyboard=True)

def clean_api_key(raw_text: str) -> str:
    return raw_text.strip().strip('"').strip("'")


async def validate_api_key(api_key: str, proxy: str = None):
    headers = {"X-API-Key": api_key, "Accept": "application/json"}
    url = f"{config.API_BASE_URL}/p2cMerchant/getConfig"
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                url, proxy=proxy, timeout=config.REQUEST_TIMEOUT
            ) as response:
                data = await response.json()
                if response.status != 200 or not data.get("ok"):
                    error = data.get("error", f"HTTP {response.status}")
                    description = data.get("description", "")
                    return False, f"{error}: {description}".strip(": ")
                result = data.get("result", {})
                return True, (
                    f"лимит до {result.get('max_payment_amount', '—')} RUB, "
                    f"награда {result.get('reward_percent', '—')}%"
                )
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        return False, f"Ошибка соединения: {exc}"

async def start_sniper_process(user_id, user_data):
    api_key = user_data["api_key"]
    proxy = user_data["proxy"]
    min_amt = user_data["min_amount"]
    max_amt = user_data["max_amount"]

    if not api_key:
        return False, "Нет API-ключа"

    sniper = SniperBot(user_id, api_key, proxy, min_amt, max_amt, bot)
    task = asyncio.create_task(sniper.start())

    active_snipers[user_id] = {"task": task, "bot_obj": sniper}
    task.add_done_callback(
        lambda finished: active_snipers.pop(user_id, None)
        if active_snipers.get(user_id, {}).get("task") is finished
        else None
    )
    await db.set_running_status(user_id, True)
    return True, "Launched"

async def send_daily_reports():
    logger.info("🕛 Starting daily report sequence...")
    users = await db.get_all_users()
    admin_report = "📊 <b>Daily Admin Report (00:00 MSK)</b>\n\n"
    total_system_volume = 0

    for u in users:
        user_id = u["user_id"]
        username = u["username"]
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
        except Exception:
            pass

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await db.add_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "👋 <b>Привет!</b>\n\n"
        "<b>Как получить данные:</b>\n"
        "1. Станьте P2C-мерчантом Crypto Bot.\n"
        "2. Создайте ключ в <a href=\"https://app.send.tg/dev\">API-разделе</a>.\n"
        "3. Выдайте scopes <code>p2cMerchant:payments:read</code> и "
        "<code>p2cMerchant:payments:take</code>.\n"
        "4. Добавьте IP сервера в whitelist и отправьте ключ боту.\n\n"

        "<b>Управление Задачами (Tasks)</b>\n"
        "* <b>Create Task:</b> Создает новую задачу для добавленного аккаунта.\n"
        "* <b>Min/Max Amount:</b> Установка диапазона сумм (например, ловить от 500 до 5000 RUB).\n"
        "* <b>Start/Stop:</b> Запуск и остановка снайпера для конкретного аккаунта.\n"
        "* <b>Status:</b> Отображает текущее состояние.\n\n"

        "<b>Уведомления</b>\n"
        "Бот присылает уведомления в трех случаях:\n"
        "* 🔔 <b>New Payment Detected:</b> Ордер успешно взят.\n"
        "* ✅ <b>Payment Completed:</b> Ордер оплачен и закрыт.\n"
        "* ❌ <b>Error:</b> Ошибки API, scopes или IP whitelist.",

        reply_markup=get_main_keyboard(message.from_user.id),
        parse_mode="HTML"
    )

@dp.message(F.text == "➕ Update API Key")
async def cmd_add_account(message: types.Message, state: FSMContext):
    await message.answer("🔑 <b>Отправь Send.tg API-ключ:</b>", parse_mode="HTML")
    await state.set_state(Form.waiting_for_api_key)

@dp.message(Form.waiting_for_api_key)
async def process_token_step(message: types.Message, state: FSMContext):
    api_key = clean_api_key(message.text)
    await state.update_data(api_key=api_key)
    await message.answer("🌐 <b>Нужен прокси?</b>\nЕго IP должен быть в whitelist ключа.\nФормат: <code>http://user:pass@ip:port</code>\nИли ❌ No Proxy.", reply_markup=get_skip_keyboard(), parse_mode="HTML")
    await state.set_state(Form.waiting_for_proxy)

@dp.message(Form.waiting_for_proxy)
async def process_proxy_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    api_key = data['api_key']
    proxy = None
    if message.text != "❌ No Proxy (Skip)":
        proxy = message.text.strip()
        if not proxy.startswith("http"): proxy = f"http://{proxy}"

    await message.answer("⏳ <b>Проверяю...</b>")
    is_valid, key_info = await validate_api_key(api_key, proxy)

    if not is_valid:
        await message.answer(f"❌ <b>Ошибка:</b>\n{key_info}", reply_markup=get_main_keyboard(message.from_user.id))
        await state.clear()
        return

    await db.update_api_key(message.from_user.id, api_key, proxy)
    await message.answer(f"✅ <b>API-ключ подключён!</b>\n{key_info}", reply_markup=get_main_keyboard(message.from_user.id), parse_mode="HTML")
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
    if not user_data or not user_data["api_key"]:
        await message.answer("❌ Сначала добавь API-ключ.")
        return

    success, msg = await start_sniper_process(uid, user_data)
    if success:
        p_stat = "🌐 Proxy" if user_data["proxy"] else "🔌 Direct"
        await message.answer(f"🚀 <b>Снайпер запущен!</b> | {p_stat}\n<i>Limits: {user_data['min_amount']} - {user_data['max_amount']} RUB</i>", parse_mode="HTML")
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
    p_view = "YES" if user_data["proxy"] else "NO"
    await message.answer(f"👤 <b>Account</b>\nStatus: {status}\nProxy: {p_view}\nMin: {user_data['min_amount']} RUB\nMax: {user_data['max_amount']} RUB", parse_mode="HTML")

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
        is_active = "🟢" if u["user_id"] in active_snipers else "🔴"
        vol = await db.get_total_caught_volume(u["user_id"])
        msg += f"{is_active} ID: <code>{u['user_id']}</code> | {vol:.0f}₽\n"
    await message.answer(msg, parse_mode="HTML")

async def on_startup():
    await db.connect()
    runners = await db.get_active_runners()
    logger.info(f"🔄 Restoring {len(runners)} snipers...")
    for user_data in runners:
        asyncio.create_task(start_sniper_process(user_data["user_id"], user_data))

async def on_shutdown():
    for uid, data in list(active_snipers.items()):
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
