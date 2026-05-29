from __future__ import annotations

from datetime import datetime

from .models import MetricSnapshot, TypeMetric


def format_snapshot_summary(snapshot: MetricSnapshot, now: datetime | None = None) -> str:
    now = now or snapshot.captured_at
    available_metrics = [item for item in snapshot.type_metrics if item.available > 0]
    lines = [
        f"{snapshot.target_name} 本次汇总",
        f"可用账号：{snapshot.available}/{snapshot.total}，禁用：{snapshot.disabled}，401：{snapshot.unauthorized}，其他错误：{snapshot.other_errors}",
        _total_quota_line(available_metrics),
    ]
    if available_metrics:
        recoveries = recovery_events(available_metrics, now)
        if recoveries:
            lines.append("最近三次 5h 恢复：")
            lines.extend(f"- {item}" for item in recoveries[:3])
        lines.append("可用额度：")
        for metric in available_metrics:
            lines.append(
                f"- {metric.type_name}: 5h {_percent(metric.remaining_5h_percent)}，"
                f"7d {_percent(metric.remaining_7d_percent)}，{_recovery_text(metric, now)}"
            )
    else:
        lines.append("当前没有可用账号。")
    return "\n".join(lines)


def recovery_events(metrics: list[TypeMetric], now: datetime) -> list[str]:
    events = []
    available_count = max(1, len(metrics))
    for metric in metrics:
        if metric.reset_5h_at is None:
            continue
        reset_at = metric.reset_5h_at.astimezone(now.tzinfo) if now.tzinfo else metric.reset_5h_at
        remaining_minutes = max(0, round((reset_at - now).total_seconds() / 60))
        gain_percent = (
            None if metric.remaining_5h_percent is None else max(0.0, 100.0 - metric.remaining_5h_percent) / available_count
        )
        gain_text = "-" if gain_percent is None else f"+{gain_percent:.2f}%"
        events.append((reset_at, f"{reset_at:%H:%M}，约 {remaining_minutes} 分钟后，{metric.type_name} 可使总 5h 额度 {gain_text}"))
    return [text for _, text in sorted(events, key=lambda item: item[0])]


def _recovery_text(metric: TypeMetric, now: datetime) -> str:
    if metric.reset_5h_at is None:
        return "5h 恢复时间未知"
    reset_at = metric.reset_5h_at.astimezone(now.tzinfo) if now.tzinfo else metric.reset_5h_at
    remaining_minutes = max(0, round((reset_at - now).total_seconds() / 60))
    return f"5h 预计 {reset_at:%H:%M} 恢复至 100%，约 {remaining_minutes} 分钟后"


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}%"


def _total_quota_line(metrics: list[TypeMetric]) -> str:
    if not metrics:
        return "总 5h 额度：-，总 7d 额度：-"
    return f"总 5h 额度：{_average_percent(metric.remaining_5h_percent for metric in metrics)}，总 7d 额度：{_average_percent(metric.remaining_7d_percent for metric in metrics)}"


def _average_percent(values) -> str:
    known = [value for value in values if value is not None]
    if not known:
        return "-"
    return f"{sum(known) / len(known):.2f}%"
