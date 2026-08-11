from decimal import Decimal, InvalidOperation
import json
from typing import Any


def queue_items(message: dict[str, Any]) -> list[dict[str, Any]]:
    event = message.get("event")
    data = message.get("data")
    if event == "snapshot" and isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if event == "add" and isinstance(data, dict):
        return [data]
    return []


def socketio_queue_items(message: str) -> list[dict[str, Any]]:
    if not message.startswith("42"):
        return []
    try:
        packet = json.loads(message[2:])
    except (TypeError, ValueError):
        return []
    if not isinstance(packet, list) or len(packet) < 2:
        return []
    event, payload = packet[0], packet[1]
    if event not in {"list:update", "list:snapshot"}:
        return []
    if event == "list:snapshot" and isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if event == "list:update" and isinstance(payload, list):
        items: list[dict[str, Any]] = []
        for change in payload:
            if isinstance(change, dict) and change.get("op") == "add":
                data = change.get("data")
                if isinstance(data, dict):
                    items.append(data)
        return items
    return []


def parse_amount(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
