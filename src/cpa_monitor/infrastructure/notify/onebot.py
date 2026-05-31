from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from cpa_monitor.application.config import OneBotConfig
from cpa_monitor.domain.models import Alert


MessageSegment = dict[str, Any]
Message = list[MessageSegment]


class OneBotClient:
    """Small OneBot HTTP action client; add new NapCat actions here as needed."""

    def __init__(self, config: OneBotConfig) -> None:
        self.config = config

    async def get_login_info(self) -> dict[str, Any]:
        return await self.call("get_login_info")

    async def get_group_list(self) -> list[dict[str, Any]]:
        result = await self.call("get_group_list")
        if isinstance(result, list):
            return result
        return []

    async def send_group_msg(self, group_id: str, message: Message) -> dict[str, Any]:
        return await self.call("send_group_msg", {"group_id": group_id, "message": message})

    async def send_private_msg(self, user_id: str, message: Message) -> dict[str, Any]:
        return await self.call("send_private_msg", {"user_id": user_id, "message": message})

    async def send_msg(self, message_type: str, target_id: str, message: Message) -> dict[str, Any]:
        payload: dict[str, Any] = {"message_type": message_type, "message": message}
        if message_type == "group":
            payload["group_id"] = target_id
        elif message_type == "private":
            payload["user_id"] = target_id
        else:
            raise ValueError("message_type must be group or private.")
        return await self.call("send_msg", payload)

    async def call(self, action: str, payload: dict[str, Any] | None = None) -> Any:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required to send OneBot notifications.") from exc

        headers = self._headers()
        last_error: Exception | None = None
        url = f"{self.config.endpoint}/{action.lstrip('/')}"
        for _ in range(self.config.retry_count + 1):
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    if payload is None:
                        response = await client.get(url, headers=headers)
                    else:
                        response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    return self._response_data(response)
            except Exception as exc:  # noqa: BLE001 - retry boundary should preserve original error.
                last_error = exc
                await asyncio.sleep(1)
        if last_error:
            raise last_error
        return None

    def _headers(self) -> dict[str, str]:
        if not self.config.access_token:
            return {}
        return {"Authorization": f"Bearer {self.config.access_token}"}

    def _response_data(self, response: Any) -> Any:
        try:
            body = response.json()
        except ValueError:
            return None
        if not isinstance(body, dict):
            return body
        retcode = body.get("retcode")
        if retcode not in (None, 0):
            raise RuntimeError(f"OneBot action failed: retcode={retcode}, message={body.get('message') or body}")
        if "data" in body:
            return body["data"]
        return body


class OneBotNotifier:
    def __init__(self, config: OneBotConfig, client: OneBotClient | None = None) -> None:
        self.config = config
        self.client = client or OneBotClient(config)

    async def send_alert(self, alert: Alert) -> None:
        text = f"{alert.title}\n{alert.message}"
        await self.send_text(text)

    async def send_report(self, image_path: Path, caption: str = "Codex 额度汇总") -> None:
        message = [
            text_segment(caption + "\n"),
            image_segment(image_path.resolve().as_uri()),
        ]
        await self._broadcast(message)

    async def send_text(self, text: str) -> None:
        await self._broadcast([text_segment(text)])

    async def _broadcast(self, message: Message) -> None:
        tasks = []
        for group_id in self.config.group_ids:
            tasks.append(self.client.send_group_msg(group_id, message))
        for user_id in self.config.private_user_ids:
            tasks.append(self.client.send_private_msg(user_id, message))
        if tasks:
            await asyncio.gather(*tasks)


def text_segment(text: str) -> MessageSegment:
    return {"type": "text", "data": {"text": text}}


def image_segment(file_uri: str) -> MessageSegment:
    return {"type": "image", "data": {"file": file_uri}}
