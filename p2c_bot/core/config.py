import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))

API_KEYS_BY_ADMIN: dict[int, list[str]] = {
    
}

UNKNOWN_API_KEY_ADMINS = set(API_KEYS_BY_ADMIN) - set(ADMIN_IDS)
if UNKNOWN_API_KEY_ADMINS:
    raise ValueError(
        "Все владельцы API_KEYS_BY_ADMIN должны быть перечислены в ADMIN_IDS: "
        f"{sorted(UNKNOWN_API_KEY_ADMINS)}"
    )
DB_PATH = str(BASE_DIR / "bot_users.db")
REQUEST_TIMEOUT = 15.0
POLL_INTERVAL = 2.0
