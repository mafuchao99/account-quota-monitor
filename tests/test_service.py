from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cpa_monitor.application.config import AppConfig, MonitorConfig, TargetConfig
from cpa_monitor.application.service import MonitorService
from cpa_monitor.domain.models import MetricSnapshot, TypeMetric


class FakeCollector:
    async def collect(self, target, captured_at):
        return MetricSnapshot(target_id=target.id, target_name=target.name, captured_at=captured_at)


class FakeStore:
    def __init__(self, snapshots):
        self.snapshots = snapshots
        self.marked = []

    def save_snapshot(self, snapshot):
        self.snapshots.append(snapshot)
        return len(self.snapshots)

    def latest_snapshot(self, target_id):
        return None

    def snapshots_since(self, since):
        return [snapshot for snapshot in self.snapshots if snapshot.captured_at >= since]

    def all_snapshots(self):
        return list(self.snapshots)

    def unreported_unauthorized_names(self, names, report_date):
        return {name for name in names if name != "old@example.com"}

    def mark_unauthorized_reported(self, names, report_date, now):
        self.marked.append((set(names), report_date))

    def should_send_alert(self, target_id, rule_key, now, silence_minutes):
        return True

    def mark_alert_sent(self, target_id, rule_key, now):
        pass


class FakeNotifier:
    async def send_alert(self, alert):
        pass

    async def send_report(self, image_path, caption="Codex 额度汇总"):
        pass

    async def send_text(self, text):
        pass


class FakeReporter:
    def __init__(self):
        self.calls = []

    async def render(self, snapshots, generated_at, history_snapshots=None, detail_mode="all", unauthorized_names=None):
        self.calls.append(
            {
                "snapshots": snapshots,
                "history_snapshots": history_snapshots,
                "detail_mode": detail_mode,
                "unauthorized_names": unauthorized_names,
            }
        )
        return Path("/tmp/report.png")


@pytest.mark.asyncio
async def test_send_report_uses_configured_detail_mode_and_filters_reported_401():
    tz = ZoneInfo("Asia/Shanghai")
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=datetime.now(tz),
        available=0,
        total=2,
        unauthorized=2,
        type_metrics=(
            TypeMetric(type_name="new@example.com", available=0, total=1, unauthorized=1),
            TypeMetric(type_name="old@example.com", available=0, total=1, unauthorized=1),
        ),
    )
    reporter = FakeReporter()
    store = FakeStore([snapshot])
    service = MonitorService(
        config=MonitorConfig(
            app=AppConfig(report_hours=1, report_detail_mode="latest"),
            console=None,
            onebot=None,
            qqbot=None,
            targets=(TargetConfig(id="codex", name="Codex"),),
        ),
        collector=FakeCollector(),
        store=store,
        notifier=FakeNotifier(),
        reporter=reporter,
    )

    await service.send_report()

    assert reporter.calls[0]["detail_mode"] == "latest"
    assert reporter.calls[0]["unauthorized_names"] == {"new@example.com"}
    assert store.marked == [({"new@example.com"}, snapshot.captured_at.strftime("%Y-%m-%d"))]
