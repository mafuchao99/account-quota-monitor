from datetime import datetime
from zoneinfo import ZoneInfo

from cpa_monitor.domain.models import MetricSnapshot, TypeMetric
from cpa_monitor.infrastructure.storage.sqlite import SqliteSnapshotStore


def test_store_round_trips_snapshot_with_type_metrics(tmp_path):
    store = SqliteSnapshotStore(f"sqlite:///{tmp_path / 'monitor.db'}")
    snapshot = MetricSnapshot(
        target_id="codex",
        target_name="Codex 额度",
        captured_at=datetime(2026, 5, 27, 18, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        available=42,
        total=52,
        disabled=10,
        type_metrics=(TypeMetric("plus", 42, 42, 77.4, 71.6, datetime(2026, 5, 27, 23, 30, tzinfo=ZoneInfo("Asia/Shanghai"))),),
        raw={"ok": True},
    )

    store.save_snapshot(snapshot)
    latest = store.latest_snapshot("codex")
    all_snapshots = store.all_snapshots()

    assert latest is not None
    assert latest.available == 42
    assert latest.type_metrics[0].type_name == "plus"
    assert latest.type_metrics[0].reset_5h_at == datetime(2026, 5, 27, 23, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert latest.raw == {"ok": True}
    assert len(all_snapshots) == 1
    assert all_snapshots[0].target_id == "codex"


def test_store_marks_unauthorized_reported_by_date(tmp_path):
    store = SqliteSnapshotStore(f"sqlite:///{tmp_path / 'monitor.db'}")
    now = datetime(2026, 5, 29, 13, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert store.unreported_unauthorized_names({"a@example.com", "b@example.com"}, "2026-05-29") == {
        "a@example.com",
        "b@example.com",
    }

    store.mark_unauthorized_reported({"a@example.com"}, "2026-05-29", now)

    assert store.unreported_unauthorized_names({"a@example.com", "b@example.com"}, "2026-05-29") == {"b@example.com"}
    assert store.unreported_unauthorized_names({"a@example.com"}, "2026-05-30") == {"a@example.com"}
