from __future__ import annotations

from html import escape
from typing import Any

from aiogram.types import (
    InputRichBlockDivider,
    InputRichBlockParagraph,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichMessage,
    RichBlockTableCell,
    RichTextBold,
    RichTextCode,
    RichTextUrl,
)

from p2c_bot.core import config


def mask_api_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "•" * len(api_key)
    return f"{api_key[:4]}…{api_key[-4:]}"


def format_limits(minimum: Any, maximum: Any) -> str:
    return f"{float(minimum or 0):,.0f}–{float(maximum or 0):,.0f} RUB".replace(
        ",", " "
    )


def _cell(text: Any, header: bool = False, center: bool = False) -> RichBlockTableCell:
    rich_text = RichTextBold(text=str(text)) if header else str(text)
    return RichBlockTableCell(
        align="center" if center else "left",
        valign="middle",
        text=rich_text,
        is_header=header or None,
    )


def _stats_table(stats: dict[str, Any], limits: str) -> InputRichBlockTable:
    return InputRichBlockTable(
        is_bordered=True,
        is_striped=True,
        caption=RichTextBold(text="Статистика за всё время"),
        cells=[
            [_cell("Параметр", True), _cell("Значение", True)],
            [_cell("Объём"), _cell(f"{float(stats.get('total_volume', 0)):,.0f} RUB".replace(",", " "))],
            [_cell("Поймано заявок"), _cell(stats.get("orders_count", 0))],
            [_cell("Пропущено"), _cell(stats.get("skipped_count", 0))],
            [_cell("Лимиты"), _cell(limits)],
        ],
    )


def build_dashboard_rich(
    accounts: list[dict[str, Any]],
    merchant_views: list[dict[str, Any]],
    stats: dict[str, Any],
    running: bool,
) -> InputRichMessage:
    if accounts:
        limits = format_limits(
            accounts[0].get("min_amount"), accounts[0].get("max_amount")
        )
    else:
        limits = "Не настроены"
    status = "Снайпер запущен" if running else "Снайпер остановлен"
    contact_text = (
        "Контакт: @daich\n"
        f"Поддержать проект: {config.DONATION_URL}"
    )
    blocks: list[Any] = [
        InputRichBlockTable(
            is_bordered=True,
            cells=[[_cell(contact_text, center=True)]],
        ),
        InputRichBlockParagraph(
            text=RichTextBold(
                text=RichTextUrl(
                    text="Как ловить большие чеки?",
                    url=config.BIG_CHECKS_GUIDE_URL,
                )
            )
        ),
        InputRichBlockParagraph(text=RichTextBold(text=status)),
        InputRichBlockDivider(),
        _stats_table(stats, limits),
        InputRichBlockDivider(),
        InputRichBlockSectionHeading(text="Подключённые мерчанты", size=3),
    ]
    if not accounts:
        blocks.append(
            InputRichBlockParagraph(
                text="API-ключи не заданы в config.py"
            )
        )
    for index, account in enumerate(accounts, 1):
        view = merchant_views[index - 1] if index <= len(merchant_views) else {}
        merchant_name = (
            view.get("brand_name")
            or view.get("merchant_name")
            or view.get("name")
            or f"Мерчант {index}"
        )
        blocks.append(
            InputRichBlockParagraph(
                text=RichTextBold(text=f"{index}. {merchant_name}")
            )
        )
        blocks.append(
            InputRichBlockParagraph(
                text=RichTextCode(
                    text=(
                        f"Ключ: {mask_api_key(account['api_key'])}\n"
                        f"Лимиты: {format_limits(account.get('min_amount'), account.get('max_amount'))}\n"
                        f"Состояние: {'запущен' if account.get('is_running') else 'остановлен'}"
                    )
                )
            )
        )
    return InputRichMessage(blocks=blocks)


def build_dashboard_html(
    accounts: list[dict[str, Any]],
    merchant_views: list[dict[str, Any]],
    stats: dict[str, Any],
    running: bool,
) -> str:
    limits = (
        format_limits(accounts[0].get("min_amount"), accounts[0].get("max_amount"))
        if accounts
        else "Не настроены"
    )
    status = "Снайпер запущен" if running else "Снайпер остановлен"
    lines = [
        "<b>Контакт:</b> @daich",
        f"<b>Поддержать проект:</b> {escape(config.DONATION_URL)}",
        (
            f'<b><a href="{escape(config.BIG_CHECKS_GUIDE_URL)}">'
            "Как ловить большие чеки?</a></b>"
        ),
        "",
        f"<b>Состояние:</b> {status}",
        "",
        "<b>Статистика за всё время</b>",
        f"Объём: {float(stats.get('total_volume', 0)):,.0f} RUB".replace(",", " "),
        f"Поймано заявок: {stats.get('orders_count', 0)}",
        f"Пропущено: {stats.get('skipped_count', 0)}",
        f"Лимиты: {limits}",
        "",
        "<b>Подключённые мерчанты</b>",
    ]
    if not accounts:
        lines.append("API-ключи не заданы в config.py")
    for index, account in enumerate(accounts, 1):
        view = merchant_views[index - 1] if index <= len(merchant_views) else {}
        merchant = (
            view.get("brand_name")
            or view.get("merchant_name")
            or view.get("name")
            or f"Мерчант {index}"
        )
        lines.extend(
            [
                "",
                f"<b>{index}. {escape(str(merchant))}</b>",
                f"Ключ: <code>{escape(mask_api_key(account['api_key']))}</code>",
                (
                    "Лимиты: "
                    + format_limits(
                        account.get("min_amount"), account.get("max_amount")
                    )
                ),
                (
                    "Состояние: "
                    + ("запущен" if account.get("is_running") else "остановлен")
                ),
            ]
        )
    return "\n".join(lines)
