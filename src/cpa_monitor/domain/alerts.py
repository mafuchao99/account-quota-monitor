from __future__ import annotations

from datetime import datetime
from typing import Protocol

from cpa_monitor.application.config import TargetConfig

from .models import Alert, MetricSnapshot
from .summary import mask_display_name, snapshot_5h_remaining_percent, snapshot_7d_remaining_percent


class AlertState(Protocol):
    def should_send_alert(self, target_id: str, rule_key: str, now: datetime, silence_minutes: int) -> bool: ...

    def mark_alert_sent(self, target_id: str, rule_key: str, now: datetime) -> None: ...


def evaluate_alerts(
    target: TargetConfig,
    current: MetricSnapshot,
    previous: MetricSnapshot | None,
    state: AlertState,
    now: datetime,
) -> list[Alert]:
    thresholds = target.thresholds
    candidates: list[Alert] = []

    if previous:
        drop = previous.available - current.available
        if drop >= thresholds.available_drop:
            candidates.append(
                Alert(
                    target.id,
                    "available_drop",
                    f"{target.name} 可用数量下降",
                    f"可用数量从 {previous.available}/{previous.total} 降至 {current.available}/{current.total}，下降 {drop}。",
                )
            )

    if current.unauthorized >= thresholds.unauthorized:
        candidates.append(
            Alert(
                target.id,
                "unauthorized",
                f"{target.name} 出现 401",
                f"本次发现 {current.unauthorized} 个账号 401。{_unauthorized_detail(current)}",
            )
        )

    if current.other_errors >= thresholds.other_errors:
        candidates.append(
            Alert(
                target.id,
                "other_errors",
                f"{target.name} 出现其他错误",
                f"当前其他错误数量为 {current.other_errors}，阈值为 {thresholds.other_errors}。",
            )
        )

    percent = snapshot_5h_remaining_percent(current)
    if percent is not None and percent <= thresholds.remaining_percent:
        seven_day_text = _seven_day_text(current)
        candidates.append(
            Alert(
                target.id,
                "remaining_percent",
                f"{target.name} 剩余额度偏低",
                f"当前 5h 总额度为 {percent:.2f}%{seven_day_text}，阈值为 {thresholds.remaining_percent:.2f}%。",
            )
        )

    alerts: list[Alert] = []
    for alert in candidates:
        if state.should_send_alert(target.id, alert.rule_key, now, thresholds.silence_minutes):
            alerts.append(alert)
            state.mark_alert_sent(target.id, alert.rule_key, now)
    return alerts


def _unauthorized_detail(snapshot: MetricSnapshot) -> str:
    names = [mask_display_name(metric.type_name) for metric in snapshot.type_metrics if metric.unauthorized > 0]
    if not names:
        return ""
    shown = names[:10]
    suffix = "" if len(names) <= len(shown) else f"，等 {len(names)} 个账号"
    return "\n401 账号：\n" + "\n".join(f"- {name}" for name in shown) + suffix


def _seven_day_text(snapshot: MetricSnapshot) -> str:
    percent = snapshot_7d_remaining_percent(snapshot)
    if percent is None:
        return ""
    return f"，7d 总额度为 {percent:.2f}%"
