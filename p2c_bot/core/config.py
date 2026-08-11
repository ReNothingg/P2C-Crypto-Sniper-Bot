import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))

API_KEYS_BY_ADMIN: dict[int, list[str]] = {
}

ACCESS_TOKENS_BY_ADMIN: dict[int, list[str | dict[str, str]]] = {
}

UNKNOWN_CREDENTIAL_ADMINS = (
    set(API_KEYS_BY_ADMIN) | set(ACCESS_TOKENS_BY_ADMIN)
) - set(ADMIN_IDS)
if UNKNOWN_CREDENTIAL_ADMINS:
    raise ValueError(
        "Все владельцы API_KEYS_BY_ADMIN/ACCESS_TOKENS_BY_ADMIN должны быть "
        f"перечислены в ADMIN_IDS: {sorted(UNKNOWN_CREDENTIAL_ADMINS)}"
    )
DB_PATH = str(BASE_DIR / "bot_users.db")
REQUEST_TIMEOUT = 15.0
POLL_INTERVAL = 2.0
