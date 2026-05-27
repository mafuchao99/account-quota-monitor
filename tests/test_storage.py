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
        type_metrics=(TypeMetric("plus", 42, 42, 77.4, 71.6),),
        raw={"ok": True},
    )

    store.save_snapshot(snapshot)
    latest = store.latest_snapshot("codex")

    assert latest is not None
    assert latest.available == 42
    assert latest.type_metrics[0].type_name == "plus"
    assert latest.raw == {"ok": True}
