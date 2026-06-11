from datetime import datetime
from zoneinfo import ZoneInfo

from cpa_monitor.domain.models import MetricSnapshot, TypeMetric
from cpa_monitor.infrastructure.reporting.html import render_report_html
from cpa_monitor.infrastructure.reporting.html import _report_directory


def test_report_directory_uses_generated_date(tmp_path):
    generated_at = datetime(2026, 5, 29, 13, 6, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert _report_directory(tmp_path, generated_at) == tmp_path / "2026-05-29"


def test_report_detail_summary_splits_total_quota_and_recoveries():
    tz = ZoneInfo("Asia/Shanghai")
    captured_at = datetime(2026, 5, 29, 13, 6, tzinfo=tz)
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=captured_at,
        available=2,
        total=3,
        disabled=3,
        unauthorized=0,
        other_errors=0,
        type_metrics=(
            TypeMetric(
                type_name="early@example.com",
                available=0,
                total=1,
                remaining_5h_percent=0,
                remaining_7d_percent=84,
                reset_5h_at=datetime(2026, 5, 29, 13, 20, tzinfo=tz),
            ),
            TypeMetric(
                type_name="a@example.com",
                available=1,
                total=1,
                remaining_5h_percent=80,
                remaining_7d_percent=90,
                reset_5h_at=datetime(2026, 5, 29, 13, 36, tzinfo=tz),
            ),
            TypeMetric(
                type_name="b@example.com",
                available=1,
                total=1,
                remaining_5h_percent=60,
                remaining_7d_percent=70,
                reset_5h_at=datetime(2026, 5, 29, 14, 38, tzinfo=tz),
            ),
        ),
    )

    html = render_report_html([snapshot], captured_at)

    assert '<div class="quota-line">' in html
    assert "<span>总 5h 70.00%</span>" in html
    assert "<span>总 7d 80.00%</span>" in html
    assert "最近三次 5h 恢复：" in html
    assert "<li>13:20，约 14 分钟后，ea***ly@example.com 可使总 5h 额度 +33.33%</li>" in html
    assert "<li>13:36，约 30 分钟后，a***@example.com 可使总 5h 额度 +6.67%</li>" in html
    assert "<li>14:38，约 92 分钟后，b***@example.com 可使总 5h 额度 +13.33%</li>" in html
    assert "early@example.com" not in html
    assert "a@example.com" not in html
    assert "b@example.com" not in html


def test_report_detail_summary_uses_available_account_pool_for_total_quota():
    tz = ZoneInfo("Asia/Shanghai")
    captured_at = datetime(2026, 5, 29, 13, 6, tzinfo=tz)
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=captured_at,
        available=2,
        total=5,
        disabled=1,
        unauthorized=1,
        other_errors=1,
        type_metrics=(
            TypeMetric(type_name="ok-a@example.com", available=1, total=1, remaining_5h_percent=80, remaining_7d_percent=40),
            TypeMetric(type_name="ok-b@example.com", available=1, total=1, remaining_5h_percent=60),
            TypeMetric(type_name="disabled@example.com", available=0, total=1, remaining_5h_percent=0, remaining_7d_percent=0),
            TypeMetric(type_name="401@example.com", available=0, total=1, remaining_5h_percent=10, remaining_7d_percent=10, unauthorized=1),
            TypeMetric(type_name="error@example.com", available=0, total=1, remaining_5h_percent=30, remaining_7d_percent=30, other_errors=1),
        ),
    )

    html = render_report_html([snapshot], captured_at)

    assert "<span>可用 2/5</span>" in html
    assert "<span>禁用 1</span>" in html
    assert "<span>401 1</span>" in html
    assert "<span>其他错误 1</span>" in html
    assert "<span>总 5h 70.00%</span>" in html
    assert "<span>总 7d 40.00%</span>" in html


def test_report_detail_summary_shows_unknown_recovery_time():
    tz = ZoneInfo("Asia/Shanghai")
    captured_at = datetime(2026, 5, 29, 13, 6, tzinfo=tz)
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=captured_at,
        available=2,
        total=1,
        disabled=0,
        unauthorized=0,
        other_errors=0,
        type_metrics=(
            TypeMetric(
                type_name="a@example.com",
                available=1,
                total=1,
                remaining_5h_percent=80,
                remaining_7d_percent=90,
            ),
        ),
    )

    html = render_report_html([snapshot], captured_at)

    assert "<li>恢复时间未知</li>" in html


def test_report_includes_unauthorized_account_analysis_from_history():
    tz = ZoneInfo("Asia/Shanghai")
    first_success = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=datetime(2026, 5, 29, 9, 0, tzinfo=tz),
        available=2,
        total=1,
        type_metrics=(
            TypeMetric(
                type_name="a@example.com",
                available=1,
                total=1,
                remaining_5h_percent=90,
                remaining_7d_percent=80,
            ),
        ),
    )
    last_success = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=datetime(2026, 5, 29, 12, 30, tzinfo=tz),
        available=1,
        total=1,
        type_metrics=(
            TypeMetric(
                type_name="a@example.com",
                available=1,
                total=1,
                remaining_5h_percent=65,
                remaining_7d_percent=18,
            ),
        ),
    )
    unauthorized = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=datetime(2026, 5, 29, 13, 0, tzinfo=tz),
        available=0,
        total=1,
        unauthorized=1,
        type_metrics=(
            TypeMetric(
                type_name="a@example.com",
                available=0,
                total=1,
                unauthorized=1,
            ),
        ),
    )

    html = render_report_html([unauthorized], unauthorized.captured_at, [first_success, last_success, unauthorized])

    assert "401 账号分析" in html
    assert "a***@example.com" in html
    assert "a@example.com" not in html
    assert "约 4 小时" in html
    assert "2026-05-29 09:00" in html
    assert "2026-05-29 12:30" in html
    assert "2026-05-29 13:00" in html
    assert "<td>35.00%</td>" in html
    assert "<td>82.00%</td>" in html
    assert "基于本地已采集快照估算" in html


def test_report_omits_unauthorized_account_analysis_without_401():
    tz = ZoneInfo("Asia/Shanghai")
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=datetime(2026, 5, 29, 13, 0, tzinfo=tz),
        available=1,
        total=1,
        type_metrics=(TypeMetric(type_name="a@example.com", available=1, total=1, remaining_7d_percent=80),),
    )

    html = render_report_html([snapshot], snapshot.captured_at, [snapshot])

    assert "401 账号分析" not in html


def test_report_detail_mode_latest_renders_compact_hourly_report():
    tz = ZoneInfo("Asia/Shanghai")
    first = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=datetime(2026, 5, 29, 12, 0, tzinfo=tz),
        available=2,
        total=5,
        type_metrics=(
            TypeMetric(type_name="latest@example.com", available=1, total=1, remaining_5h_percent=90, remaining_7d_percent=90),
            TypeMetric(type_name="recover@example.com", available=0, total=1, remaining_5h_percent=30, remaining_7d_percent=80),
            TypeMetric(type_name="weekly-empty@example.com", available=0, total=1, remaining_5h_percent=99, remaining_7d_percent=0),
            TypeMetric(type_name="bad@example.com", available=1, total=1, remaining_5h_percent=65, remaining_7d_percent=18),
        ),
    )
    latest = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=datetime(2026, 5, 29, 13, 0, tzinfo=tz),
        available=2,
        total=5,
        unauthorized=1,
        type_metrics=(
            TypeMetric(
                type_name="latest@example.com",
                available=1,
                total=1,
                remaining_5h_percent=45,
                remaining_7d_percent=91,
                reset_5h_at=datetime(2026, 5, 29, 17, 0, tzinfo=tz),
                reset_7d_at=datetime(2026, 6, 1, 17, 0, tzinfo=tz),
                usage_updated_at=datetime(2026, 5, 29, 12, 45, tzinfo=tz),
            ),
            TypeMetric(
                type_name="soon@example.com",
                available=1,
                total=1,
                remaining_5h_percent=50,
                remaining_7d_percent=92,
                reset_5h_at=datetime(2026, 5, 29, 14, 0, tzinfo=tz),
            ),
            TypeMetric(
                type_name="recover@example.com",
                available=0,
                total=1,
                remaining_5h_percent=0,
                remaining_7d_percent=80,
                reset_5h_at=datetime(2026, 5, 29, 13, 30, tzinfo=tz),
            ),
            TypeMetric(type_name="weekly-empty@example.com", available=0, total=1, remaining_5h_percent=99, remaining_7d_percent=0),
            TypeMetric(type_name="bad@example.com", available=0, total=1, unauthorized=1),
        ),
    )

    html = render_report_html([first, latest], latest.captured_at, detail_mode="latest")

    assert "Codex 小时报表" in html
    assert "总览趋势" not in html
    assert "分时明细" not in html
    assert "【当前状态】" in html
    assert "可用账号：2/5" in html
    assert "5h 总额度：47.50%" in html
    assert "7d 总额度：91.50%" in html
    assert "禁用：0" in html
    assert "5小时限额：1" in html
    assert "429 限流：0" in html
    assert "401 异常：1" in html
    assert "其他错误：0" in html
    assert "30分钟内可恢复：+25%" in html
    assert "1小时内可恢复：+37.50%" in html
    assert "最近恢复：" not in html
    assert "预计耗尽" not in html
    assert "【当前可用账号（2）】" in html
    assert "la***st@example.com" in html
    assert "5h 45%" in html
    assert "预计 17:00 恢复" in html
    assert "7d 预计 06-01 17:00 刷新" in html
    assert "快照 12:45，约 15 分钟前" in html
    assert html.index("la***st@example.com") < html.index("so***@example.com")
    assert "account-grid quota-account-grid" in html
    assert "【即将恢复】" not in html
    assert "【额度耗尽】" not in html
    assert "【五小时额度耗尽（1）】" in html
    assert "re***er@example.com" in html
    assert "5h 0%" in html
    assert "【异常账号（2）】" in html
    assert "account-grid error-account-grid" in html
    assert "we***ty@example.com" in html
    assert "周额度耗尽" in html
    assert "ba***@example.com" in html
    assert "401 未授权" in html
    assert "5h 已用 35.00%，7d 已用 82.00%" in html
    assert "latest@example.com" not in html


def test_hourly_report_sorts_available_accounts_by_7d_reset_time():
    tz = ZoneInfo("Asia/Shanghai")
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=datetime(2026, 5, 29, 13, 0, tzinfo=tz),
        available=2,
        total=2,
        type_metrics=(
            TypeMetric(
                type_name="late-5h@example.com",
                available=1,
                total=1,
                remaining_5h_percent=10,
                remaining_7d_percent=90,
                reset_5h_at=datetime(2026, 5, 29, 14, 0, tzinfo=tz),
                reset_7d_at=datetime(2026, 5, 30, 16, 0, tzinfo=tz),
            ),
            TypeMetric(
                type_name="early-5h@example.com",
                available=1,
                total=1,
                remaining_5h_percent=90,
                remaining_7d_percent=80,
                reset_5h_at=datetime(2026, 5, 29, 18, 0, tzinfo=tz),
                reset_7d_at=datetime(2026, 5, 29, 14, 30, tzinfo=tz),
            ),
        ),
    )

    html = render_report_html([snapshot], snapshot.captured_at, detail_mode="latest")

    assert html.index("ea***5h@example.com") < html.index("la***5h@example.com")


def test_hourly_report_filters_five_hour_exhausted_and_weekly_429_accounts():
    tz = ZoneInfo("Asia/Shanghai")
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=datetime(2026, 5, 29, 13, 0, tzinfo=tz),
        available=0,
        total=4,
        rate_limited=2,
        type_metrics=(
            TypeMetric(
                type_name="later@example.com",
                available=0,
                total=1,
                remaining_5h_percent=0,
                remaining_7d_percent=90,
                reset_5h_at=datetime(2026, 5, 29, 15, 0, tzinfo=tz),
            ),
            TypeMetric(
                type_name="early@example.com",
                available=0,
                total=1,
                remaining_5h_percent=0,
                remaining_7d_percent=80,
                reset_5h_at=datetime(2026, 5, 29, 14, 0, tzinfo=tz),
            ),
            TypeMetric(
                type_name="weekly-429@example.com",
                available=0,
                total=1,
                remaining_5h_percent=0,
                remaining_7d_percent=0,
                rate_limited=1,
                rate_limited_until=datetime(2026, 5, 29, 16, 0, tzinfo=tz),
            ),
            TypeMetric(
                type_name="limited-5h@example.com",
                available=0,
                total=1,
                remaining_5h_percent=0,
                remaining_7d_percent=50,
                reset_5h_at=datetime(2026, 5, 29, 14, 30, tzinfo=tz),
                rate_limited=1,
                rate_limited_until=datetime(2026, 5, 29, 14, 30, tzinfo=tz),
            ),
            TypeMetric(
                type_name="only-429@example.com",
                available=0,
                total=1,
                remaining_5h_percent=50,
                remaining_7d_percent=50,
                rate_limited=1,
                rate_limited_until=datetime(2026, 5, 29, 14, 30, tzinfo=tz),
            ),
        ),
    )

    html = render_report_html([snapshot], snapshot.captured_at, detail_mode="latest")

    assert "5小时限额：3" in html
    assert "429 限流：1" in html
    assert "【五小时额度耗尽（3）】" in html
    assert "【异常账号（1）】" in html
    assert html.index("ea***ly@example.com") < html.index("la***er@example.com")
    assert "li***5h@example.com" in html
    assert "预计 14:00 恢复" in html
    assert "预计 14:30 恢复" in html
    assert "预计 15:00 恢复" in html
    assert "we***29@example.com" in html
    assert "429 限流" in html
    assert "周额度耗尽，预计 05-29 16:00 恢复，快照时间未知" in html
    assert "on***29@example.com" not in html


def test_hourly_report_shows_zero_error_counts_and_type_metric_401_fallback():
    tz = ZoneInfo("Asia/Shanghai")
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=datetime(2026, 5, 29, 13, 0, tzinfo=tz),
        available=13,
        total=13,
        disabled=1,
        unauthorized=0,
        other_errors=0,
        type_metrics=(
            TypeMetric(type_name="ok@example.com", available=1, total=1, remaining_5h_percent=80, remaining_7d_percent=90),
            TypeMetric(type_name="bad@example.com", available=0, total=1, unauthorized=1),
        ),
    )

    html = render_report_html([snapshot], snapshot.captured_at, detail_mode="latest")

    assert "禁用：1" in html
    assert "401 异常：1" in html
    assert "其他错误：0" in html


def test_hourly_report_always_lists_current_401_account():
    tz = ZoneInfo("Asia/Shanghai")
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=datetime(2026, 5, 29, 13, 0, tzinfo=tz),
        available=0,
        total=1,
        unauthorized=1,
        type_metrics=(TypeMetric(type_name="bad@example.com", available=0, total=1, unauthorized=1),),
    )

    html = render_report_html([snapshot], snapshot.captured_at, detail_mode="latest", unauthorized_names=set())

    assert "401 异常：1" in html
    assert "【当前可用账号（0）】" in html
    assert "【异常账号（1）】" in html
    assert "ba***@example.com" in html
    assert "401 未授权" in html
    assert "历史额度不足" in html
    assert "bad@example.com" not in html


def test_report_detail_mode_none_omits_detail_section():
    tz = ZoneInfo("Asia/Shanghai")
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=datetime(2026, 5, 29, 13, 0, tzinfo=tz),
        available=1,
        total=1,
        type_metrics=(TypeMetric(type_name="a@example.com", available=1, total=1),),
    )

    html = render_report_html([snapshot], snapshot.captured_at, detail_mode="none")

    assert "总览趋势" not in html
    assert "分时明细" not in html


def test_report_detail_mode_all_keeps_trend_section():
    tz = ZoneInfo("Asia/Shanghai")
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=datetime(2026, 5, 29, 13, 0, tzinfo=tz),
        available=1,
        total=1,
        type_metrics=(TypeMetric(type_name="a@example.com", available=1, total=1),),
    )

    html = render_report_html([snapshot], snapshot.captured_at, detail_mode="all")

    assert "总览趋势" in html


def test_report_filters_already_reported_unauthorized_accounts():
    tz = ZoneInfo("Asia/Shanghai")
    unauthorized = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=datetime(2026, 5, 29, 13, 0, tzinfo=tz),
        available=0,
        total=1,
        unauthorized=1,
        type_metrics=(TypeMetric(type_name="a@example.com", available=0, total=1, unauthorized=1),),
    )

    html = render_report_html(
        [unauthorized],
        unauthorized.captured_at,
        [unauthorized],
        unauthorized_names=set(),
    )

    assert "401 账号分析" not in html
