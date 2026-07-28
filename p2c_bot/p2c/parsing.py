from decimal import Decimal, InvalidOperation
from typing import Any


def queue_items(message: dict[str, Any]) -> list[dict[str, Any]]:
    event = message.get("event")
    data = message.get("data")
    if event == "snapshot" and isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if event == "add" and isinstance(data, dict):
        return [data]
    return []


def parse_amount(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
