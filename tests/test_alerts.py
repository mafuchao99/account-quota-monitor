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


def test_remaining_percent_alert_uses_hourly_report_quota_pool(tmp_path):
    store = SqliteSnapshotStore(f"sqlite:///{tmp_path / 'monitor.db'}")
    target = TargetConfig(
        id="codex",
        name="Codex 额度",
        thresholds=Thresholds(available_drop=1, unauthorized=1, other_errors=1, remaining_percent=20, silence_minutes=60),
    )
    now = datetime(2026, 5, 27, 21, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    current = MetricSnapshot(
        target.id,
        target.name,
        now,
        available=1,
        total=12,
        type_metrics=(
            TypeMetric("ok@example.com", available=1, total=1, remaining_5h_percent=80, remaining_7d_percent=90),
            TypeMetric("empty@example.com", available=0, total=1, remaining_5h_percent=0, remaining_7d_percent=90),
            TypeMetric("unauthorized@example.com", available=0, total=1, remaining_5h_percent=0, remaining_7d_percent=90, unauthorized=1),
        ),
    )

    alerts = evaluate_alerts(target, current, None, store, now)

    assert [alert.rule_key for alert in alerts] == []


def test_remaining_percent_alert_reports_total_quota_when_low(tmp_path):
    store = SqliteSnapshotStore(f"sqlite:///{tmp_path / 'monitor.db'}")
    target = TargetConfig(
        id="codex",
        name="Codex 额度",
        thresholds=Thresholds(available_drop=1, unauthorized=1, other_errors=1, remaining_percent=20, silence_minutes=60),
    )
    now = datetime(2026, 5, 27, 21, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    current = MetricSnapshot(
        target.id,
        target.name,
        now,
        available=1,
        total=12,
        type_metrics=(
            TypeMetric("ok@example.com", available=1, total=1, remaining_5h_percent=8.33, remaining_7d_percent=70),
        ),
    )

    alerts = evaluate_alerts(target, current, None, store, now)

    assert [alert.rule_key for alert in alerts] == ["remaining_percent"]
    assert alerts[0].title == "Codex 额度 剩余额度偏低"
    assert alerts[0].message == "当前 5h 总额度为 8.33%，7d 总额度为 70.00%，阈值为 20.00%。"
