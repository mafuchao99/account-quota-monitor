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


def test_load_config_accepts_report_modes(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[app]
report_cron = "0 0 * * * *"
report_hours = 1
report_detail_mode = "latest"
full_report_enabled = true
full_report_crons = ["0 30 7 * * *", "0 10 12 * * *", "0 10 19 * * *", "0 30 23 * * *"]
full_report_hours = 6
full_report_detail_mode = "all"

[[targets]]
id = "codex"
name = "Codex"
url = "https://example.test"
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.app.report_hours == 1
    assert config.app.report_detail_mode == "latest"
    assert config.app.full_report_enabled is True
    assert config.app.full_report_crons == ("0 30 7 * * *", "0 10 12 * * *", "0 10 19 * * *", "0 30 23 * * *")
    assert config.app.full_report_hours == 6
    assert config.app.full_report_detail_mode == "all"


def test_full_report_schedule_is_disabled_by_default(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[[targets]]
id = "codex"
name = "Codex"
url = "https://example.test"
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.app.full_report_enabled is False


def test_target_collection_defaults_to_hourly_minute_50(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[[targets]]
id = "codex"
name = "Codex"
url = "https://example.test"
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.targets[0].cron == "0 50 * * * *"
    assert config.targets[0].dynamic_schedule.enabled is False


def test_load_config_accepts_legacy_single_full_report_cron(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[app]
full_report_cron = "0 0 */6 * * *"

[[targets]]
id = "codex"
name = "Codex"
url = "https://example.test"
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.app.full_report_crons == ("0 0 */6 * * *",)


def test_load_config_reads_sibling_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("CPA_MANAGEMENT_KEY", raising=False)
    monkeypatch.delenv("CPA_ENDPOINT", raising=False)
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[[targets]]
id = "codex"
name = "Codex"
collector = "cli_proxy_codex"
base_url = "${CPA_ENDPOINT}"

[targets.headers]
Authorization = "Bearer ${CPA_MANAGEMENT_KEY}"
""",
        encoding="utf-8",
    )

    (tmp_path / ".env").write_text(
        "CPA_ENDPOINT=https://example.test\nCPA_MANAGEMENT_KEY=secret-from-env-file\n",
        encoding="utf-8",
    )
    config = load_config(config_path)

    assert config.targets[0].collector == "cli_proxy_codex"
    assert config.targets[0].base_url == "https://example.test"
    assert config.targets[0].headers["Authorization"] == "Bearer secret-from-env-file"


def test_load_config_rejects_cli_proxy_example_endpoint(tmp_path, monkeypatch):
    monkeypatch.delenv("CPA_ENDPOINT", raising=False)
    monkeypatch.delenv("CPA_MANAGEMENT_KEY", raising=False)
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[[targets]]
id = "codex"
name = "Codex"
collector = "cli_proxy_codex"
base_url = "${CPA_ENDPOINT}"

[targets.headers]
Authorization = "Bearer ${CPA_MANAGEMENT_KEY}"
""",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "CPA_ENDPOINT=https://your-cpa-endpoint.example.com\nCPA_MANAGEMENT_KEY=secret\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="CPA_ENDPOINT"):
        load_config(config_path)


def test_load_config_rejects_cli_proxy_example_management_key(tmp_path, monkeypatch):
    monkeypatch.delenv("CPA_ENDPOINT", raising=False)
    monkeypatch.delenv("CPA_MANAGEMENT_KEY", raising=False)
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[[targets]]
id = "codex"
name = "Codex"
collector = "cli_proxy_codex"
base_url = "${CPA_ENDPOINT}"

[targets.headers]
Authorization = "Bearer ${CPA_MANAGEMENT_KEY}"
""",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "CPA_ENDPOINT=https://example.test\nCPA_MANAGEMENT_KEY=your-management-key\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="CPA_MANAGEMENT_KEY"):
        load_config(config_path)


def test_load_config_rejects_enabled_qqbot_placeholder_secret(tmp_path, monkeypatch):
    monkeypatch.delenv("QQBOT_APP_ID", raising=False)
    monkeypatch.delenv("QQBOT_APP_SECRET", raising=False)
    monkeypatch.delenv("QQBOT_OPENID", raising=False)
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[notifications.qqbot]
enabled = true
app_id = "${QQBOT_APP_ID}"
app_secret = "${QQBOT_APP_SECRET}"
openid = "${QQBOT_OPENID}"

[[targets]]
id = "codex"
name = "Codex"
url = "https://example.test"
""",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        """
QQBOT_APP_ID=app-id
QQBOT_APP_SECRET=your-qqbot-app-secret
QQBOT_OPENID=openid
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="QQBOT_APP_SECRET"):
        load_config(config_path)


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
