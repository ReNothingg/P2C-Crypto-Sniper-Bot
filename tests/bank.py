import aiohttp
import asyncio
import ssl
import json

# СЮДА ВСТАВИТЬ ТОКЕН!
TOKEN = ""

def build_cookie(value):
    value = value.strip()
    if not value:
        raise ValueError("TOKEN пустой")
    if "access_token=" in value:
        return value
    return f"access_token={value}"

async def main():
    url = "https://app.send.tg/internal/v1/p2c/accounts"

    cookie = build_cookie(TOKEN)
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru",
        "Cookie": cookie,
        "Referer": "https://app.send.tg/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/27.0 Safari/605.1.15",
    }

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    print(f"Запрашиваем данные по адресу: {url} ...")

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, ssl=ssl_ctx) as resp:
            if resp.status == 200:
                data = await resp.json()
                print("\nУСПЕХ! Вот доступные реквизиты:\n")


                accounts = data.get('data', [])
                if not accounts and isinstance(data, list):
                    accounts = data

                if accounts:
                    for acc in accounts:

                        currency = acc.get('currency', '???')
                        title = acc.get('title', 'No Title')
                        if title == 'No Title':
                            title = acc.get('bank_code', 'Unknown Bank')

                        print(f"ID: {acc['id']}  |  {title} ({currency})")
                        print("-" * 30)
                else:
                    print("Список пуст. Возможно, у тебя не добавлены реквизиты в криптобота")
                    print(data)

            else:
                print(f"Ошибка: {resp.status}")
                print(f"Cookie отправлен как {'полная строка из браузера' if ';' in cookie else 'access_token'}")
                print(await resp.text())

if __name__ == "__main__":
    asyncio.run(main())
