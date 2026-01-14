import aiohttp
import asyncio
import ssl
import json

TOKEN = ""

async def main():
    url = "https://app.cr.bot/internal/v1/p2c/accounts"

    headers = {
        "Cookie": f"access_token={TOKEN}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
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
                    print("Список пуст. Возможно, у тебя не добавлены реквизиты в боте?")
                    print(f"Ответ сервера: {data}")

            else:
                print(f"Ошибка: {resp.status}")
                print(await resp.text())

if __name__ == "__main__":
    asyncio.run(main())