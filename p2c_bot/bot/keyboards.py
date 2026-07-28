from aiogram.enums import ButtonStyle
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from p2c_bot.core import config


def dashboard_keyboard(running: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=(
                    "Остановить снайпер"
                    if running
                    else "Запустить снайпер"
                ),
                callback_data="toggle_sniper",
                style=(
                    ButtonStyle.DANGER
                    if running
                    else ButtonStyle.SUCCESS
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="Подключить API-ключ",
                callback_data="connect_api",
            ),
            InlineKeyboardButton(
                text="Настроить лимиты",
                callback_data="configure_limits",
            ),
        ],
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="Связаться",
                url=config.CONTACT_URL,
                style=ButtonStyle.SUCCESS,
            ),
            InlineKeyboardButton(
                text="Поддержать проект",
                url=config.DONATION_URL,
                style=ButtonStyle.SUCCESS,
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
