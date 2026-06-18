from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from .models import MetricSnapshot, TypeMetric


def format_snapshot_summary(snapshot: MetricSnapshot, now: datetime | None = None) -> str:
    now = now or snapshot.captured_at
    available_metrics = effective_metrics(snapshot.type_metrics)
    quota_metrics = available_metrics
    recoveries = recovery_events(snapshot.type_metrics, now)
    lines = [
        f"{snapshot.target_name} 本次汇总",
        f"可用账号：{snapshot.available}/{snapshot.total}，禁用：{snapshot.disabled}，429：{snapshot.rate_limited}，401：{snapshot.unauthorized}，其他错误：{snapshot.other_errors}",
        _total_quota_line(quota_metrics),
    ]
    if recoveries:
        lines.append("最近三次 5h 恢复：")
        lines.extend(f"- {item}" for item in recoveries[:3])
    if available_metrics:
        lines.append("可用额度：")
        for metric in available_metrics:
            lines.append(
                f"- {mask_display_name(metric.type_name)}: 5h {_percent(metric.remaining_5h_percent)}，"
                f"7d {_percent(metric.remaining_7d_percent)}，{_recovery_text(metric, now)}"
            )
    else:
        lines.append("当前没有可用账号。")
    return "\n".join(lines)


def recovery_events(metrics: Iterable[TypeMetric], now: datetime) -> list[str]:
    quota_metrics = quota_pool_metrics(metrics)
    if not quota_metrics:
        return []
    metrics = recoverable_metrics(quota_metrics)
    events = []
    account_count = sum(1 for item in quota_metrics if item.remaining_5h_percent is not None)
    if account_count <= 0:
        return []
    for metric in metrics:
        if metric.reset_5h_at is None:
            continue
        reset_at = metric.reset_5h_at.astimezone(now.tzinfo) if now.tzinfo else metric.reset_5h_at
        remaining_minutes = max(0, round((reset_at - now).total_seconds() / 60))
        gain_percent = max(0.0, 100.0 - metric.remaining_5h_percent) / account_count
        gain_text = f"+{gain_percent:.2f}%"
        events.append(
            (
                reset_at,
                f"{reset_at:%H:%M}，约 {remaining_minutes} 分钟后，{mask_display_name(metric.type_name)} 可使总 5h 额度 {gain_text}",
            )
        )
    return [text for _, text in sorted(events, key=lambda item: item[0])]


def effective_metrics(metrics: Iterable[TypeMetric]) -> list[TypeMetric]:
    return [
        item
        for item in metrics
        if item.available > 0
        and item.rate_limited == 0
        and item.unauthorized == 0
        and item.other_errors == 0
    ]


def quota_pool_metrics(metrics: Iterable[TypeMetric]) -> list[TypeMetric]:
    return [item for item in metrics if item.total > 0 and item.unauthorized == 0 and item.other_errors == 0]


def recoverable_metrics(metrics: Iterable[TypeMetric]) -> list[TypeMetric]:
    return [
        item
        for item in metrics
        if item.unauthorized == 0
        and item.other_errors == 0
        and item.reset_5h_at is not None
        and item.remaining_5h_percent is not None
        and item.remaining_7d_percent is not None
        and item.remaining_7d_percent > 0
    ]


def average_percent(values: Iterable[float | None]) -> str:
    known = [value for value in values if value is not None]
    if not known:
        return "-"
    return f"{sum(known) / len(known):.2f}%"


def mask_display_name(value: str) -> str:
    if "@" not in value:
        if len(value) <= 4:
            return value
        if len(value) <= 8:
            return f"{value[:2]}***"
        return f"{value[:2]}***{value[-2:]}"
    name, domain = value.split("@", 1)
    if not name:
        return f"***@{domain}"
    if len(name) <= 2:
        return f"{name[0]}***@{domain}"
    if len(name) <= 4:
        return f"{name[:2]}***@{domain}"
    return f"{name[:2]}***{name[-2:]}@{domain}"


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
    return f"总 5h 额度：{average_percent(metric.remaining_5h_percent for metric in metrics)}，总 7d 额度：{average_percent(metric.remaining_7d_percent for metric in metrics)}"
