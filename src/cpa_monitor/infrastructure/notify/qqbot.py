from __future__ import annotations

import asyncio
import random
import time
from pathlib import Path
from typing import Any

from cpa_monitor.application.config import QqBotConfig
from cpa_monitor.domain.models import Alert


class QqBotNotifier:
    def __init__(self, config: QqBotConfig) -> None:
        self.config = config
        self._access_token = ""
        self._expires_at = 0.0

    async def send_alert(self, alert: Alert) -> None:
        await self.send_text(f"{alert.title}\n{alert.message}")

    async def send_report(self, image_path: Path, caption: str = "Codex 额度汇总") -> None:
        # Official QQ Bot image upload/send has a different flow. Keep v1 private notification text-only.
        async with _http_client() as client:
            await self._send_report_with_client(client, image_path, caption)

    async def send_text(self, text: str) -> None:
        await self._post_message({"msg_type": 0, "content": text, "msg_seq": _message_sequence()})

    async def _send_report_with_client(self, client: Any, image_path: Path, caption: str) -> None:
        await self._post_message_with_client(
            client,
            {"msg_type": 0, "content": f"{caption}\n报表已生成：{image_path.resolve()}", "msg_seq": _message_sequence()},
        )

    async def _post_message(self, payload: dict[str, Any]) -> None:
        async with _http_client() as client:
            await self._post_message_with_client(client, payload)

    async def _post_message_with_client(self, client: Any, payload: dict[str, Any]) -> None:
        last_error: Exception | None = None
        for _ in range(self.config.retry_count + 1):
            try:
                token = await self._token(client)
                response = await client.post(
                    f"{self.config.api_base}/v2/users/{self.config.openid}/messages",
                    json=payload,
                    headers={"Authorization": f"QQBot {token}"},
                )
                response.raise_for_status()
                return
            except Exception as exc:  # noqa: BLE001 - retry boundary should preserve original error.
                last_error = exc
                await asyncio.sleep(1)
        if last_error:
            raise last_error

    async def _token(self, client: Any) -> str:
        now = time.time()
        if self._access_token and now < self._expires_at:
            return self._access_token

        response = await client.post(
            self.config.token_url,
            json={"appId": self.config.app_id, "clientSecret": self.config.app_secret},
        )
        response.raise_for_status()
        data = response.json()
        token = str(data.get("access_token") or data.get("accessToken") or "")
        if not token:
            raise RuntimeError("QQBot token response does not contain access_token.")
        expires_in = int(data.get("expires_in") or data.get("expiresIn") or 7200)
        self._access_token = token
        self._expires_at = now + max(60, expires_in - 60)
        return token


def _http_client() -> Any:
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("httpx is required to send QQBot notifications.") from exc
    return httpx.AsyncClient(timeout=20)


def _message_sequence() -> int:
    return random.randint(1, 2_147_483_647)
