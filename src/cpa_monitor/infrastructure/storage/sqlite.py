from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from cpa_monitor.domain.models import MetricSnapshot, TypeMetric


class SqliteSnapshotStore:
    def __init__(self, database_url: str) -> None:
        self.path = _sqlite_path(database_url)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            create table if not exists snapshots (
              id integer primary key autoincrement,
              target_id text not null,
              target_name text not null,
              captured_at text not null,
              available integer not null,
              total integer not null,
              disabled integer not null,
              unauthorized integer not null,
              other_errors integer not null,
              raw_json text not null
            );
            create index if not exists idx_snapshots_target_time on snapshots(target_id, captured_at);

            create table if not exists type_metrics (
              id integer primary key autoincrement,
              snapshot_id integer not null references snapshots(id) on delete cascade,
              type_name text not null,
              available integer not null,
              total integer not null,
              remaining_5h_percent real,
              remaining_7d_percent real,
              unauthorized integer not null,
              other_errors integer not null
            );

            create table if not exists alert_state (
              target_id text not null,
              rule_key text not null,
              last_sent_at text not null,
              primary key (target_id, rule_key)
            );
            """
        )
        self.conn.commit()

    def save_snapshot(self, snapshot: MetricSnapshot) -> int:
        cursor = self.conn.execute(
            """
            insert into snapshots
              (target_id, target_name, captured_at, available, total, disabled, unauthorized, other_errors, raw_json)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.target_id,
                snapshot.target_name,
                snapshot.captured_at.isoformat(),
                snapshot.available,
                snapshot.total,
                snapshot.disabled,
                snapshot.unauthorized,
                snapshot.other_errors,
                json.dumps(snapshot.raw, ensure_ascii=False),
            ),
        )
        snapshot_id = int(cursor.lastrowid)
        self.conn.executemany(
            """
            insert into type_metrics
              (snapshot_id, type_name, available, total, remaining_5h_percent, remaining_7d_percent, unauthorized, other_errors)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    snapshot_id,
                    metric.type_name,
                    metric.available,
                    metric.total,
                    metric.remaining_5h_percent,
                    metric.remaining_7d_percent,
                    metric.unauthorized,
                    metric.other_errors,
                )
                for metric in snapshot.type_metrics
            ],
        )
        self.conn.commit()
        return snapshot_id

    def latest_snapshot(self, target_id: str) -> MetricSnapshot | None:
        row = self.conn.execute(
            "select * from snapshots where target_id = ? order by captured_at desc limit 1",
            (target_id,),
        ).fetchone()
        return self._row_to_snapshot(row) if row else None

    def snapshots_since(self, since: datetime) -> list[MetricSnapshot]:
        rows = self.conn.execute(
            "select * from snapshots where captured_at >= ? order by captured_at asc",
            (since.isoformat(),),
        ).fetchall()
        return [self._row_to_snapshot(row) for row in rows]

    def should_send_alert(self, target_id: str, rule_key: str, now: datetime, silence_minutes: int) -> bool:
        row = self.conn.execute(
            "select last_sent_at from alert_state where target_id = ? and rule_key = ?",
            (target_id, rule_key),
        ).fetchone()
        if not row:
            return True
        last_sent_at = datetime.fromisoformat(row["last_sent_at"])
        return now - last_sent_at >= timedelta(minutes=silence_minutes)

    def mark_alert_sent(self, target_id: str, rule_key: str, now: datetime) -> None:
        self.conn.execute(
            """
            insert into alert_state (target_id, rule_key, last_sent_at)
            values (?, ?, ?)
            on conflict(target_id, rule_key) do update set last_sent_at = excluded.last_sent_at
            """,
            (target_id, rule_key, now.isoformat()),
        )
        self.conn.commit()

    def _row_to_snapshot(self, row: sqlite3.Row) -> MetricSnapshot:
        type_rows = self.conn.execute(
            "select * from type_metrics where snapshot_id = ? order by id asc",
            (row["id"],),
        ).fetchall()
        return MetricSnapshot(
            target_id=row["target_id"],
            target_name=row["target_name"],
            captured_at=datetime.fromisoformat(row["captured_at"]),
            available=row["available"],
            total=row["total"],
            disabled=row["disabled"],
            unauthorized=row["unauthorized"],
            other_errors=row["other_errors"],
            type_metrics=tuple(
                TypeMetric(
                    type_name=item["type_name"],
                    available=item["available"],
                    total=item["total"],
                    remaining_5h_percent=item["remaining_5h_percent"],
                    remaining_7d_percent=item["remaining_7d_percent"],
                    unauthorized=item["unauthorized"],
                    other_errors=item["other_errors"],
                )
                for item in type_rows
            ),
            raw=json.loads(row["raw_json"]),
        )


def _sqlite_path(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("Only sqlite:/// database URLs are supported in v1.")
    return Path(database_url.removeprefix("sqlite:///"))
