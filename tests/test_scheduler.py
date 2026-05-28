from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from cpa_monitor.application.config import DynamicSchedule, TargetConfig, load_config
from cpa_monitor.application.schedule import cron_kwargs, desired_collect_interval_minutes
from cpa_monitor.domain.models import MetricSnapshot


def test_cron_kwargs_accepts_six_field_cron():
    assert cron_kwargs("0 */30 * * * *") == {
        "second": "0",
        "minute": "*/30",
        "hour": "*",
        "day": "*",
        "month": "*",
        "day_of_week": "*",
    }


def test_load_config_accepts_dynamic_schedule(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[[targets]]
id = "codex"
name = "Codex"
url = "https://example.test"

[targets.dynamic_schedule]
enabled = true
normal_interval_minutes = 30
urgent_interval_minutes = 10
urgent_remaining_percent = 15
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.targets[0].dynamic_schedule == DynamicSchedule(
        enabled=True,
        normal_interval_minutes=30,
        urgent_interval_minutes=10,
        urgent_remaining_percent=15,
    )


def test_load_config_rejects_empty_targets(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="At least one target"):
        load_config(config_path)


def test_load_config_rejects_non_positive_dynamic_schedule_intervals(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[[targets]]
id = "codex"
name = "Codex"
url = "https://example.test"

[targets.dynamic_schedule]
enabled = true
normal_interval_minutes = 0
urgent_interval_minutes = 10
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="dynamic_schedule intervals"):
        load_config(config_path)


def test_dynamic_schedule_uses_urgent_interval_when_remaining_percent_is_low():
    target = TargetConfig(
        id="codex",
        name="Codex",
        url="https://example.test",
        dynamic_schedule=DynamicSchedule(enabled=True, normal_interval_minutes=30, urgent_interval_minutes=10),
    )
    snapshot = MetricSnapshot(
        target_id=target.id,
        target_name=target.name,
        captured_at=datetime(2026, 5, 28, tzinfo=ZoneInfo("Asia/Shanghai")),
        available=10,
        total=100,
    )

    assert desired_collect_interval_minutes(target, snapshot) == 10


def test_dynamic_schedule_uses_normal_interval_when_remaining_percent_recovers():
    target = TargetConfig(
        id="codex",
        name="Codex",
        url="https://example.test",
        dynamic_schedule=DynamicSchedule(enabled=True, normal_interval_minutes=30, urgent_interval_minutes=10),
    )
    snapshot = MetricSnapshot(
        target_id=target.id,
        target_name=target.name,
        captured_at=datetime(2026, 5, 28, tzinfo=ZoneInfo("Asia/Shanghai")),
        available=80,
        total=100,
    )

    assert desired_collect_interval_minutes(target, snapshot) == 30


def test_fixed_schedule_does_not_request_interval_reschedule():
    target = TargetConfig(id="codex", name="Codex", url="https://example.test")
    snapshot = MetricSnapshot(
        target_id=target.id,
        target_name=target.name,
        captured_at=datetime(2026, 5, 28, tzinfo=ZoneInfo("Asia/Shanghai")),
        available=10,
        total=100,
    )

    assert desired_collect_interval_minutes(target, snapshot) is None
