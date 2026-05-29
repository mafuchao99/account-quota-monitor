from __future__ import annotations

from pathlib import Path

from cpa_monitor.domain.models import Alert


class ConsoleNotifier:
    async def send_alert(self, alert: Alert) -> None:
        await self.send_text(f"{alert.title}\n{alert.message}")

    async def send_report(self, image_path: Path, caption: str = "Codex 额度汇总") -> None:
        await self.send_text(f"{caption}\n报表已生成：{image_path.resolve()}")

    async def send_text(self, text: str) -> None:
        print(f"[CPA Monitor]\n{text}")
