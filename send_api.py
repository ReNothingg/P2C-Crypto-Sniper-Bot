from decimal import Decimal, InvalidOperation


def queue_items(message):
    event = message.get("event")
    data = message.get("data")
    if event == "snapshot" and isinstance(data, list):
        return data
    if event == "add" and isinstance(data, dict):
        return [data]
    return []


def parse_amount(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
