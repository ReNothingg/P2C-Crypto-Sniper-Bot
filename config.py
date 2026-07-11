import os

from dotenv import load_dotenv


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [7878539493]

API_BASE_URL = os.getenv("SEND_API_BASE_URL", "https://api.send.tg/v1").rstrip("/")
API_WS_URL = os.getenv(
    "SEND_API_WS_URL", "wss://api.send.tg/v1/p2cMerchant/ws"
)
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "10"))
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "5"))
