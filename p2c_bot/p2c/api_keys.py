from __future__ import annotations

from typing import Any

import aiohttp

from p2c_bot.core import config


def access_token_cookie(value: str) -> str:
    value = value.strip()
    return value if "access_token=" in value else f"access_token={value}"


async def fetch_merchant_config(
    credential: str, credential_type: str = "api_key"
) -> dict[str, Any]:
    if credential_type == "access_token":
        headers = {
            "Cookie": access_token_cookie(credential),
            "Accept": "application/json",
            "Origin": "https://app.send.tg",
        }
        url = "https://app.send.tg/internal/v1/user/settings"
    else:
        headers = {"X-API-Key": credential, "Accept": "application/json"}
        url = "https://api.send.tg/v1/p2cMerchant/getConfig"
    timeout = aiohttp.ClientTimeout(total=config.REQUEST_TIMEOUT)
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        async with session.get(url) as response:
            try:
                payload = await response.json()
            except (aiohttp.ContentTypeError, ValueError):
                payload = {"ok": False, "description": (await response.text())[:200]}
            if response.status in {401, 403}:
                raise ValueError("Учетные данные недействительны")
            if credential_type == "access_token":
                if not 200 <= response.status < 300:
                    raise ValueError(
                        payload.get("description")
                        or payload.get("error")
                        or f"Ошибка API: HTTP {response.status}"
                    )
                result = payload.get("result") or payload.get("data")
                return result if isinstance(result, dict) else payload
            if not payload.get("ok"):
                raise ValueError(
                    payload.get("description")
                    or payload.get("error")
                    or f"Ошибка API: HTTP {response.status}"
                )
            result = payload.get("result")
            return result if isinstance(result, dict) else {}
