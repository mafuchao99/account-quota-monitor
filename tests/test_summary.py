from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from cpa_monitor.domain.models import MetricSnapshot, TypeMetric
from cpa_monitor.domain.summary import format_hourly_snapshot_summary, format_snapshot_summary, mask_display_name


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
    assert "gm***: 5h 63.00%，7d 6.00%" in summary
    assert "约 45 分钟后" in summary


def test_mask_display_name_keeps_email_identifiable_without_full_address():
    assert mask_display_name("84106712349@qq.com") == "84***49@qq.com"
    assert mask_display_name("a@example.com") == "a***@example.com"
    assert mask_display_name("plus") == "plus"
    assert mask_display_name("mafuhcao") == "ma***"
    assert mask_display_name("Sana Leng Arti+oeewybc") == "Sa***bc"


def test_format_snapshot_summary_lists_exhausted_5h_account_when_weekly_quota_remains():
    now = datetime(2026, 5, 29, 15, 56, tzinfo=ZoneInfo("Asia/Shanghai"))
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="Codex 额度",
        captured_at=now,
        available=1,
        total=3,
        unauthorized=1,
        type_metrics=(
            TypeMetric(
                "early@example.com",
                available=0,
                total=1,
                remaining_5h_percent=0,
                remaining_7d_percent=84,
                reset_5h_at=now + timedelta(minutes=97),
            ),
            TypeMetric(
                "available@example.com",
                available=1,
                total=1,
                remaining_5h_percent=50,
                remaining_7d_percent=75,
                reset_5h_at=now + timedelta(minutes=161),
            ),
            TypeMetric(
                "weekly-empty@example.com",
                available=0,
                total=1,
                remaining_5h_percent=99,
                remaining_7d_percent=0,
                reset_5h_at=now + timedelta(minutes=60),
            ),
            TypeMetric("unauthorized@example.com", available=0, total=1, unauthorized=1),
        ),
    )

    summary = format_snapshot_summary(snapshot, now)

    assert "总 5h 额度：50.00%" in summary
    assert "总 7d 额度：75.00%" in summary
    assert "17:33，约 97 分钟后，ea***ly@example.com 可使总 5h 额度 +33.33%" in summary
    assert "18:37，约 161 分钟后，av***le@example.com 可使总 5h 额度 +16.67%" in summary
    assert "early@example.com" not in summary
    assert "available@example.com" not in summary
    assert "weekly-empty@example.com" not in summary
    assert "unauthorized@example.com" not in summary


def test_format_snapshot_summary_uses_available_account_pool_for_total_quota():
    now = datetime(2026, 5, 29, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="Codex 额度",
        captured_at=now,
        available=2,
        total=5,
        disabled=1,
        unauthorized=1,
        other_errors=1,
        type_metrics=(
            TypeMetric("ok-a", available=1, total=1, remaining_5h_percent=80, remaining_7d_percent=40),
            TypeMetric("ok-b", available=1, total=1, remaining_5h_percent=60, remaining_7d_percent=20),
            TypeMetric("disabled", available=0, total=1, remaining_5h_percent=0, remaining_7d_percent=0),
            TypeMetric("unauthorized", available=0, total=1, remaining_5h_percent=10, remaining_7d_percent=10, unauthorized=1),
            TypeMetric("error", available=0, total=1, remaining_5h_percent=30, remaining_7d_percent=30, other_errors=1),
        ),
    )

    summary = format_snapshot_summary(snapshot, now)

    assert "可用账号：2/5，禁用：1，429：0，401：1，其他错误：1" in summary
    assert "总 5h 额度：70.00%" in summary
    assert "总 7d 额度：30.00%" in summary


def test_format_snapshot_summary_skips_missing_quota_field_per_window():
    now = datetime(2026, 5, 29, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="Codex 额度",
        captured_at=now,
        available=2,
        total=2,
        type_metrics=(
            TypeMetric("five-only", available=1, total=1, remaining_5h_percent=80),
            TypeMetric("seven-only", available=1, total=1, remaining_7d_percent=40),
        ),
    )

    summary = format_snapshot_summary(snapshot, now)

    assert "总 5h 额度：80.00%" in summary
    assert "总 7d 额度：40.00%" in summary


def test_recovery_gain_uses_recoverable_accounts_with_5h_quota():
    now = datetime(2026, 5, 29, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="Codex 额度",
        captured_at=now,
        available=3,
        total=5,
        type_metrics=(
            TypeMetric(
                "ok-a",
                available=1,
                total=1,
                remaining_5h_percent=80,
                remaining_7d_percent=80,
                reset_5h_at=now + timedelta(minutes=30),
            ),
            TypeMetric(
                "ok-b",
                available=1,
                total=1,
                remaining_5h_percent=60,
                remaining_7d_percent=60,
                reset_5h_at=now + timedelta(minutes=45),
            ),
            TypeMetric("no-5h", available=1, total=1, remaining_7d_percent=10, reset_5h_at=now + timedelta(minutes=60)),
            TypeMetric("unauthorized", available=0, total=1, unauthorized=1, reset_5h_at=now + timedelta(minutes=15)),
            TypeMetric("error", available=0, total=1, other_errors=1, reset_5h_at=now + timedelta(minutes=20)),
        ),
    )

    summary = format_snapshot_summary(snapshot, now)

    assert "ok-a 可使总 5h 额度 +10.00%" in summary
    assert "ok-b 可使总 5h 额度 +20.00%" in summary
    assert "no-5h 可使总 5h 额度" not in summary
    assert "unauthorized 可使总 5h 额度" not in summary
    assert "error 可使总 5h 额度" not in summary


def test_format_hourly_snapshot_summary_matches_hourly_report_counts():
    now = datetime(2026, 5, 29, 13, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="sub2 Codex 额度",
        captured_at=now,
        available=1,
        total=5,
        rate_limited=2,
        type_metrics=(
            TypeMetric(
                "ok@example.com",
                available=1,
                total=1,
                remaining_5h_percent=84,
                remaining_7d_percent=90,
                reset_5h_at=now + timedelta(hours=2),
            ),
            TypeMetric(
                "recover@example.com",
                available=0,
                total=1,
                remaining_5h_percent=0,
                remaining_7d_percent=80,
                reset_5h_at=now + timedelta(minutes=30),
            ),
            TypeMetric(
                "temporary-429@example.com",
                available=0,
                total=1,
                remaining_5h_percent=50,
                remaining_7d_percent=80,
                rate_limited=1,
                rate_limited_until=now + timedelta(minutes=30),
            ),
            TypeMetric(
                "weekly-429@example.com",
                available=0,
                total=1,
                remaining_5h_percent=0,
                remaining_7d_percent=0,
                rate_limited=1,
                rate_limited_until=now + timedelta(hours=3),
            ),
            TypeMetric("bad@example.com", available=0, total=1, unauthorized=1),
        ),
    )

    summary = format_hourly_snapshot_summary(snapshot, now)

    assert "sub2 Codex 额度 小时报" in summary
    assert "可用账号：1，5h 总额度：84.00%，7d 总额度：90.00%" in summary
    assert "5小时限额：1，429 限流：1，401 异常：1，其他错误：0" in summary
    assert "30分钟内可恢复：+25%" in summary
    assert "ok@example.com" not in summary
    assert "o***@example.com: 5h 84%，7d 90%" in summary
