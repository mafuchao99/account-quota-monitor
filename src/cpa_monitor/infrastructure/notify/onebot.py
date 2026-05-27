from __future__ import annotations

import asyncio
from pathlib import Path

from cpa_monitor.application.config import OneBotConfig
from cpa_monitor.domain.models import Alert


class OneBotNotifier:
    def __init__(self, config: OneBotConfig) -> None:
        self.config = config

    async def send_alert(self, alert: Alert) -> None:
        text = f"{alert.title}\n{alert.message}"
        await self.send_text(text)

    async def send_report(self, image_path: Path, caption: str = "Codex 额度汇总") -> None:
        message = [
            {"type": "text", "data": {"text": caption + "\n"}},
            {"type": "image", "data": {"file": image_path.resolve().as_uri()}},
        ]
        await self._broadcast(message)

    async def send_text(self, text: str) -> None:
        await self._broadcast([{"type": "text", "data": {"text": text}}])

    async def _broadcast(self, message: list[dict]) -> None:
        tasks = []
        for group_id in self.config.group_ids:
            tasks.append(self._post("/send_group_msg", {"group_id": group_id, "message": message}))
        for user_id in self.config.private_user_ids:
            tasks.append(self._post("/send_private_msg", {"user_id": user_id, "message": message}))
        if tasks:
            await asyncio.gather(*tasks)

    async def _post(self, path: str, payload: dict) -> None:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required to send OneBot notifications.") from exc

        headers = {}
        if self.config.access_token:
            headers["Authorization"] = f"Bearer {self.config.access_token}"

        last_error: Exception | None = None
        for _ in range(self.config.retry_count + 1):
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post(self.config.endpoint + path, json=payload, headers=headers)
                    response.raise_for_status()
                    return
            except Exception as exc:  # noqa: BLE001 - retry boundary should preserve original error.
                last_error = exc
                await asyncio.sleep(1)
        if last_error:
            raise last_error
