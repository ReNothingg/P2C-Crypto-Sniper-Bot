from __future__ import annotations

from typing import Any

import aiohttp

from p2c_bot.core import config


async def fetch_merchant_config(api_key: str) -> dict[str, Any]:
    headers = {"X-API-Key": api_key, "Accept": "application/json"}
    timeout = aiohttp.ClientTimeout(total=config.REQUEST_TIMEOUT)
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        async with session.get(
            f"{config.API_BASE_URL}/p2cMerchant/getConfig"
        ) as response:
            try:
                payload = await response.json()
            except (aiohttp.ContentTypeError, ValueError):
                payload = {"ok": False, "description": (await response.text())[:200]}
            if response.status == 401:
                raise ValueError("API-ключ недействителен")
            if not payload.get("ok"):
                raise ValueError(
                    payload.get("description")
                    or payload.get("error")
                    or f"Ошибка API: HTTP {response.status}"
                )
            result = payload.get("result")
            return result if isinstance(result, dict) else {}
