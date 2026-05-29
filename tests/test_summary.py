from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from cpa_monitor.domain.models import MetricSnapshot, TypeMetric
from cpa_monitor.domain.summary import format_snapshot_summary


def test_format_snapshot_summary_lists_available_quota_and_recovery_time():
    now = datetime(2026, 5, 29, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="Codex 额度",
        captured_at=now,
        available=2,
        total=3,
        type_metrics=(
            TypeMetric(
                "gmail",
                available=1,
                total=1,
                remaining_5h_percent=63,
                remaining_7d_percent=6,
                reset_5h_at=(now + timedelta(minutes=45)).astimezone(timezone.utc),
            ),
            TypeMetric(
                "plus",
                available=1,
                total=1,
                remaining_5h_percent=83,
                remaining_7d_percent=20,
                reset_5h_at=(now + timedelta(minutes=30)).astimezone(timezone.utc),
            ),
            TypeMetric("disabled", available=0, total=1),
        ),
    )

    summary = format_snapshot_summary(snapshot, now)

    assert "可用账号：2/3" in summary
    assert "总 5h 额度：73.00%" in summary
    assert "总 7d 额度：13.00%" in summary
    assert "最近三次 5h 恢复" in summary
    assert "12:30，约 30 分钟后，plus 可使总 5h 额度 +8.50%" in summary
    assert "gmail: 5h 63.00%，7d 6.00%" in summary
    assert "约 45 分钟后" in summary
