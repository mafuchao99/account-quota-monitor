from datetime import datetime
from zoneinfo import ZoneInfo

from cpa_monitor.application.config import TargetConfig, Thresholds
from cpa_monitor.domain.alerts import evaluate_alerts
from cpa_monitor.domain.models import MetricSnapshot, TypeMetric
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


def test_evaluate_alerts_includes_unauthorized_account_names(tmp_path):
    store = SqliteSnapshotStore(f"sqlite:///{tmp_path / 'monitor.db'}")
    target = TargetConfig(
        id="codex",
        name="Codex 额度",
        thresholds=Thresholds(available_drop=1, unauthorized=1, other_errors=1, remaining_percent=10, silence_minutes=60),
    )
    now = datetime(2026, 5, 27, 21, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    current = MetricSnapshot(
        target.id,
        target.name,
        now,
        available=1,
        total=2,
        unauthorized=1,
        type_metrics=(TypeMetric("account-user@example.com", available=0, total=1, unauthorized=1),),
    )

    alerts = evaluate_alerts(target, current, None, store, now)

    assert alerts[0].rule_key == "unauthorized"
    assert "阈值" not in alerts[0].message
    assert "本次发现 1 个账号 401。" in alerts[0].message
    assert "401 账号：\n- ac***er@example.com" in alerts[0].message
