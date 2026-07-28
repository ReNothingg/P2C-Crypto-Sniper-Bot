from __future__ import annotations

from html import escape
from io import BytesIO
from typing import Any


QR_VALUE_KEYS = (
    "qr_payload",
    "qr_data",
    "qr_string",
    "raw_qr",
    "qr_content",
    "qr_text",
    "qr_code",
    "payment_url",
    "pay_url",
    "direct_url",
    "deep_link",
    "deeplink",
    "qr_url",
    "url",
    "payload",
)
NESTED_KEYS = ("qr", "payment", "details", "result")


def _walk_values(data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for nested_key in NESTED_KEYS:
        nested = data.get(nested_key)
        if isinstance(nested, dict):
            found = _walk_values(nested, keys)
            if found:
                return found
    return None


def extract_qr_value(*sources: dict[str, Any] | None) -> str | None:
    for source in sources:
        if source:
            value = _walk_values(source, QR_VALUE_KEYS)
            if value:
                return value
    return None


def generate_qr_png(value: str) -> bytes:
    import qrcode

    image = qrcode.make(value)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def build_payment_caption(amount: Any, payment_id: Any) -> str:
    return (
        "<b>Новая заявка поймана</b>\n\n"
        f"<b>Сумма:</b> {escape(str(amount))} RUB\n"
        f"<b>ID:</b> <code>{escape(str(payment_id))}</code>"
    )


def build_payment_rich_html(
    amount: Any, payment_id: Any, has_qr: bool
) -> str:
    qr = '<img src="tg://photo?id=payment_qr">' if has_qr else ""
    return (
        "<h2>Новая заявка поймана</h2>"
        f"{qr}"
        '<table border="1" striped="true">'
        f"<tr><td>Сумма</td><td>{escape(str(amount))} RUB</td></tr>"
        f"<tr><td>ID</td><td><code>{escape(str(payment_id))}</code></td></tr>"
        "</table>"
    )
