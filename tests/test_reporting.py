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
    assert "<span>总 5h 46.67%</span>" in html
    assert "<span>总 7d 81.33%</span>" in html
    assert "最近三次 5h 恢复：" in html
    assert "<li>13:20，约 14 分钟后，ea***ly@example.com 可使总 5h 额度 +33.33%</li>" in html
    assert "<li>13:36，约 30 分钟后，a***@example.com 可使总 5h 额度 +6.67%</li>" in html
    assert "<li>14:38，约 92 分钟后，b***@example.com 可使总 5h 额度 +13.33%</li>" in html
    assert "early@example.com" not in html
    assert "a@example.com" not in html
    assert "b@example.com" not in html


def test_report_detail_summary_uses_non_error_account_pool_for_total_quota():
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
    assert "<span>总 5h 46.67%</span>" in html
    assert "<span>总 7d 20.00%</span>" in html


def test_report_detail_summary_shows_unknown_recovery_time():
    tz = ZoneInfo("Asia/Shanghai")
    captured_at = datetime(2026, 5, 29, 13, 6, tzinfo=tz)
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=captured_at,
        available=1,
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
        available=1,
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


def test_report_detail_mode_latest_only_renders_latest_detail_block():
    tz = ZoneInfo("Asia/Shanghai")
    first = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=datetime(2026, 5, 29, 12, 0, tzinfo=tz),
        available=1,
        total=1,
        type_metrics=(TypeMetric(type_name="first@example.com", available=1, total=1),),
    )
    latest = MetricSnapshot(
        target_id="codex",
        target_name="Codex",
        captured_at=datetime(2026, 5, 29, 13, 0, tzinfo=tz),
        available=1,
        total=1,
        type_metrics=(TypeMetric(type_name="latest@example.com", available=1, total=1),),
    )

    html = render_report_html([first, latest], latest.captured_at, detail_mode="latest")

    assert "总览趋势" not in html
    assert "分时明细" in html
    assert "la***st@example.com" in html
    assert "latest@example.com" not in html
    assert "first@example.com" not in html


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
