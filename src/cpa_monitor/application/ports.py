from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol

from cpa_monitor.domain.models import Alert, MetricSnapshot

from .config import TargetConfig


class SnapshotCollector(Protocol):
    async def collect(self, target: TargetConfig, captured_at: datetime) -> MetricSnapshot: ...


class SnapshotStore(Protocol):
    def save_snapshot(self, snapshot: MetricSnapshot) -> int: ...

    def latest_snapshot(self, target_id: str) -> MetricSnapshot | None: ...

    def snapshots_since(self, since: datetime) -> list[MetricSnapshot]: ...

    def all_snapshots(self) -> list[MetricSnapshot]: ...

    def unreported_unauthorized_names(self, names: set[str], report_date: str) -> set[str]: ...

    def mark_unauthorized_reported(self, names: set[str], report_date: str, now: datetime) -> None: ...

    def should_send_alert(self, target_id: str, rule_key: str, now: datetime, silence_minutes: int) -> bool: ...

    def mark_alert_sent(self, target_id: str, rule_key: str, now: datetime) -> None: ...


class Notifier(Protocol):
    async def send_alert(self, alert: Alert) -> None: ...

    async def send_report(self, image_path: Path, caption: str = "Codex 额度汇总") -> None: ...

    async def send_text(self, text: str) -> None: ...


class ReportRenderer(Protocol):
    async def render(
        self,
        snapshots: list[MetricSnapshot],
        generated_at: datetime,
        history_snapshots: list[MetricSnapshot] | None = None,
        detail_mode: str = "all",
        unauthorized_names: set[str] | None = None,
    ) -> Path | None: ...
