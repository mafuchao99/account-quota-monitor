from __future__ import annotations

import asyncio
from pathlib import Path

from cpa_monitor.application.ports import Notifier
from cpa_monitor.domain.models import Alert


class CompositeNotifier:
    def __init__(self, notifiers: list[Notifier]) -> None:
        self.notifiers = notifiers

    async def send_alert(self, alert: Alert) -> None:
        await self._broadcast("send_alert", alert)

    async def send_report(self, image_path: Path, caption: str = "Codex 额度汇总") -> None:
        await self._broadcast("send_report", image_path, caption)

    async def send_text(self, text: str) -> None:
        await self._broadcast("send_text", text)

    async def _broadcast(self, method: str, *args) -> None:
        if not self.notifiers:
            return
        await asyncio.gather(*(getattr(notifier, method)(*args) for notifier in self.notifiers))
