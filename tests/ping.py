import asyncio
import aiohttp
import time
import statistics
import argparse
import sys
import ssl
from loguru import logger

logger.remove()
logger.add(sys.stderr, format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>", level="INFO")

HTTP_URL = "https://app.cr.bot/internal/v1/p2c/accounts"
WS_URL = "wss://app.cr.bot/internal/v1/p2c-socket/?EIO=4&transport=websocket"
ORIGIN = "https://app.cr.bot"

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

async def measure_http(session, url, count=10):
    logger.info(f"Запуск HTTP теста ({count} запросов)...")
    results = []

    for i in range(count):
        try:
            start = time.perf_counter()
            async with session.get(url) as resp:
                await resp.read()
                status = resp.status

            end = time.perf_counter()
            ms = (end - start) * 1000

            if status == 200:
                results.append(ms)
                logger.info(f"  Ping #{i+1}: {ms:.2f} ms")
            elif status == 404:
                logger.warning(f"   Ping #{i+1}: 404 Not Found (URL неверен)")
            else:
                logger.warning(f"   Ping #{i+1}: Ошибка {status}")

        except Exception as e:
            logger.error(f"   Ping #{i+1}: Ошибка {e}")

        await asyncio.sleep(0.5)

    return results

async def measure_ws(session, url):
    logger.info(f"Запуск WebSocket теста (Connect Handshake)...")
    try:
        start = time.perf_counter()
        async with session.ws_connect(url, ssl=ssl_ctx) as ws:
            pass
        end = time.perf_counter()
        ms = (end - start) * 1000
        logger.success(f"✅ WS Connect: {ms:.2f} ms")
        return ms
    except Exception as e:
        logger.error(f"❌ WS Error: {e}")
        return None

def print_stats(name, data):
    if not data:
        logger.error(f"Нет данных для {name}")
        return

    avg = statistics.mean(data)
    mn = min(data)
    mx = max(data)
    try:
        stdev = statistics.stdev(data)
    except:
        stdev = 0.0

    logger.info(f"--- {name} STATS ---")
    logger.info(f"   Средний:  {avg:.2f} ms")
    logger.info(f"   Мин:      {mn:.2f} ms")
    logger.info(f"   Макс:     {mx:.2f} ms")

    stability = "ИДЕАЛЬНО" if stdev < 5 else "⚠️ Скачет" if stdev < 20 else "❌ ПЛОХО"
    logger.info(f"Джиттер:  {stdev:.2f} ms ({stability})")
    print("-" * 30)

def clean_token_string(raw_text: str) -> str:
    text = raw_text.strip().strip('"').strip("'")
    if "access_token=" in text:
        text = text.split("access_token=")[1]
    if ";" in text:
        text = text.split(";")[0]
    return text.strip()

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", type=str, required=False, help="Access Token")
    args = parser.parse_args()

    token = args.token
    if not token:
        print("Вставь токен:")
        token = input("> ")

    token = clean_token_string(token)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Cookie": f"access_token={token}",
        "Origin": ORIGIN
    }

    async with aiohttp.ClientSession(headers=headers, connector=aiohttp.TCPConnector(ssl=ssl_ctx)) as session:
        print("\n" + "="*30)
        await measure_ws(session, WS_URL)
        print("-" * 30)
        http_results = await measure_http(session, HTTP_URL, count=10)
        print("\n")
        print_stats("HTTP API", http_results)

if __name__ == "__main__":
    asyncio.run(main())