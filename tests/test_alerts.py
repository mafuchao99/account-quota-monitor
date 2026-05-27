from datetime import datetime
from zoneinfo import ZoneInfo

from cpa_monitor.application.config import TargetConfig, Thresholds
from cpa_monitor.domain.alerts import evaluate_alerts
from cpa_monitor.domain.models import MetricSnapshot
from cpa_monitor.infrastructure.storage.sqlite import SqliteSnapshotStore


def test_evaluate_alerts_detects_available_drop_and_silences_repeats(tmp_path):
    store = SqliteSnapshotStore(f"sqlite:///{tmp_path / 'monitor.db'}")
    target = TargetConfig(
        id="codex",
        name="Codex 额度",
        url="https://example.test",
        thresholds=Thresholds(available_drop=1, unauthorized=1, other_errors=1, remaining_percent=10, silence_minutes=60),
    )
    now = datetime(2026, 5, 27, 21, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    previous = MetricSnapshot(target.id, target.name, now, available=42, total=52)
    current = MetricSnapshot(target.id, target.name, now, available=40, total=52)

    alerts = evaluate_alerts(target, current, previous, store, now)
    repeated = evaluate_alerts(target, current, previous, store, now)

    assert [alert.rule_key for alert in alerts] == ["available_drop"]
    assert repeated == []
