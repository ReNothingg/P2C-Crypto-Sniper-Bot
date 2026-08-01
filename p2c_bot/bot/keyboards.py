from aiogram.enums import ButtonStyle
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)


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
                text="Настроить лимиты",
                callback_data="configure_limits",
            ),
        ],
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="Связаться",
                url="https://t.me/daich",
                style=ButtonStyle.SUCCESS,
            ),
            InlineKeyboardButton(
                text="Поддержать проект",
                url="https://renothingg.github.io/?support",
                style=ButtonStyle.SUCCESS,
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
