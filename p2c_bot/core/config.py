import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [
    int(value)
    for value in os.getenv("ADMIN_IDS", "7878539493").split(",")
    if value.strip().isdigit()
]
CONTACT_URL = "https://t.me/daich"
DONATION_URL = "https://renothingg.github.io/?support"
BIG_CHECKS_GUIDE_URL = (
    "https://github.com/ReNothingg/P2C-Crypto-Sniper-Bot"
    "#%D0%BA%D0%B0%D0%BA-%D0%BB%D0%BE%D0%B2%D0%B8%D1%82%D1%8C-"
    "%D0%B1%D0%BE%D0%BB%D1%8C%D1%88%D0%B8%D0%B5-%D1%87%D0%B5%D0%BA%D0%B8"
)
DB_PATH = str(BASE_DIR / "bot_users.db")
API_BASE_URL = "https://api.send.tg/v1"
API_WS_URL = "wss://api.send.tg/v1/p2cMerchant/ws"
REQUEST_TIMEOUT = 15.0
POLL_INTERVAL = 2.0
