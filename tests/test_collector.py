from datetime import datetime
from zoneinfo import ZoneInfo

from cpa_monitor.application.config import JsonPaths, TargetConfig
from cpa_monitor.infrastructure.http.collector import parse_snapshot


def test_parse_snapshot_maps_summary_and_type_metrics():
    target = TargetConfig(
        id="codex",
        name="Codex 额度",
        url="https://example.test/quota",
        json_paths=JsonPaths(
            total="$.summary.total",
            available="$.summary.available",
            disabled="$.summary.disabled",
            unauthorized="$.summary.unauthorized",
            other_errors="$.summary.other_errors",
            types="$.types",
        ),
    )

    snapshot = parse_snapshot(
        target,
        {
            "summary": {"total": 52, "available": 42, "disabled": 10, "unauthorized": 0, "other_errors": 2},
            "types": [{"type": "plus", "available": 42, "total": 42, "5h_remaining": 77.4, "7d_remaining": 71.6}],
        },
        datetime(2026, 5, 27, 18, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert snapshot.available == 42
    assert snapshot.total == 52
    assert snapshot.other_errors == 2
    assert snapshot.type_metrics[0].type_name == "plus"
    assert snapshot.type_metrics[0].remaining_5h_percent == 77.4
