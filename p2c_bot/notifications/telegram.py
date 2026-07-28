from __future__ import annotations

import asyncio
from typing import Any

from aiogram import Bot
from aiogram.types import (
    BufferedInputFile,
    InputMediaPhoto,
    InputRichMessage,
    InputRichMessageMedia,
)
from loguru import logger

from p2c_bot.notifications.rich_messages import (
    build_payment_caption,
    build_payment_rich_html,
    extract_qr_value,
    generate_qr_png,
)


class TelegramNotifier:
    def __init__(self, bot: Bot, user_id: int) -> None:
        self.bot = bot
        self.user_id = user_id

    async def send_text(self, text: str) -> None:
        try:
            await self.bot.send_message(self.user_id, text)
        except Exception as exc:
            logger.error("Не удалось отправить уведомление {}: {}", self.user_id, exc)

    async def send_payment_card(
        self,
        payment: dict[str, Any],
        source_qr: dict[str, Any],
        amount: Any,
    ) -> None:
        payment_id = payment.get("payment_id", "Не указан")
        qr_value = extract_qr_value(payment, source_qr)
        caption = build_payment_caption(amount, payment_id)

        qr_bytes = None
        if qr_value:
            try:
                qr_bytes = await asyncio.to_thread(generate_qr_png, qr_value)
            except Exception as exc:
                logger.warning("Не удалось сформировать QR-код: {}", exc)

        try:
            media = []
            if qr_bytes:
                media.append(
                    InputRichMessageMedia(
                        id="payment_qr",
                        media=InputMediaPhoto(
                            media=BufferedInputFile(
                                qr_bytes, filename="payment-qr.png"
                            )
                        ),
                    )
                )
            rich = InputRichMessage(
                html=build_payment_rich_html(
                    amount, payment_id, bool(qr_bytes)
                ),
                media=media,
            )
            await self.bot.send_rich_message(
                chat_id=self.user_id,
                rich_message=rich,
            )
            return
        except Exception as exc:
            logger.warning("Rich Message недоступно, используется резервный вид: {}", exc)

        if qr_bytes:
            try:
                await self.bot.send_photo(
                    self.user_id,
                    BufferedInputFile(qr_bytes, filename="payment-qr.png"),
                    caption=caption,
                )
                return
            except Exception as exc:
                logger.warning("Не удалось отправить QR-фото: {}", exc)
        await self.bot.send_message(self.user_id, caption)
