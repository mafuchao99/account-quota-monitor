from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

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


def format_hourly_snapshot_summary(snapshot: MetricSnapshot, now: datetime | None = None) -> str:
    now = now or snapshot.captured_at
    available_metrics = effective_metrics(snapshot.type_metrics)
    available = len(available_metrics) if snapshot.type_metrics else snapshot.available
    lines = [
        f"{snapshot.target_name} 小时报",
        (
            f"可用账号：{available}，"
            f"5h 总额度：{average_percent(metric.remaining_5h_percent for metric in available_metrics)}，"
            f"7d 总额度：{average_percent(metric.remaining_7d_percent for metric in available_metrics)}"
        ),
        (
            f"禁用：{snapshot.disabled}，"
            f"5小时限额：{five_hour_exhausted_count(snapshot.type_metrics)}，"
            f"429 限流：{display_rate_limited_count(snapshot.type_metrics)}，"
            f"401 异常：{snapshot_unauthorized_count(snapshot)}，"
            f"其他错误：{snapshot_other_errors_count(snapshot)}"
        ),
    ]
    recovery_windows = recovery_window_summaries(snapshot.type_metrics, now)
    if recovery_windows:
        lines.append("恢复情况：" + "，".join(recovery_windows))
    if available_metrics:
        lines.append("当前可用账号：")
        for metric in sorted(available_metrics, key=lambda item: available_account_sort_key(item, now)):
            lines.append(
                f"- {mask_display_name(metric.type_name)}: 5h {_compact_percent(metric.remaining_5h_percent)}，"
                f"7d {_compact_percent(metric.remaining_7d_percent)}，{_recovery_text(metric, now)}"
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


def recovery_window_summaries(metrics: Iterable[TypeMetric], now: datetime) -> list[str]:
    items = recovery_items(metrics, now)
    result = []
    for minutes, label in ((30, "30分钟内可恢复"), (60, "1小时内可恢复")):
        end_at = now + timedelta(minutes=minutes)
        gain = sum(item[1] for item in items if now <= item[0] <= end_at)
        result.append(f"{label}：+{_compact_percent(gain)}" if gain > 0 else f"{label}：-")
    return result


def recovery_items(metrics: Iterable[TypeMetric], now: datetime) -> list[tuple[datetime, float, TypeMetric]]:
    quota_metrics = quota_pool_metrics(metrics)
    account_count = sum(1 for item in quota_metrics if item.remaining_5h_percent is not None)
    if account_count <= 0:
        return []
    items = []
    for metric in recoverable_metrics(quota_metrics):
        if metric.reset_5h_at is None or metric.remaining_5h_percent is None:
            continue
        reset_at = local_time(metric.reset_5h_at, now)
        if reset_at is None:
            continue
        gain_percent = max(0.0, 100.0 - metric.remaining_5h_percent) / account_count
        items.append((reset_at, gain_percent, metric))
    return sorted(items, key=lambda item: item[0])


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


def five_hour_exhausted_count(metrics: Iterable[TypeMetric]) -> int:
    return sum(
        1
        for metric in metrics
        if is_five_hour_exhausted(metric)
        and not is_weekly_exhausted(metric)
        and metric.unauthorized == 0
        and metric.other_errors == 0
    )


def display_rate_limited_count(metrics: Iterable[TypeMetric]) -> int:
    return sum(1 for metric in metrics if metric.rate_limited > 0 and is_weekly_exhausted(metric))


def snapshot_unauthorized_count(snapshot: MetricSnapshot) -> int:
    return snapshot.unauthorized or sum(metric.unauthorized for metric in snapshot.type_metrics)


def snapshot_other_errors_count(snapshot: MetricSnapshot) -> int:
    return snapshot.other_errors or sum(metric.other_errors for metric in snapshot.type_metrics)


def is_five_hour_exhausted(metric: TypeMetric) -> bool:
    return metric.remaining_5h_percent is not None and metric.remaining_5h_percent <= 0


def is_weekly_exhausted(metric: TypeMetric) -> bool:
    return metric.remaining_7d_percent is not None and metric.remaining_7d_percent <= 0


def local_time(value: datetime | None, reference: datetime) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(reference.tzinfo) if reference.tzinfo else value


def available_account_sort_key(metric: TypeMetric, reference: datetime) -> tuple[tuple[int, datetime], tuple[int, datetime], str]:
    return (
        _sort_time_key(local_time(metric.reset_7d_at, reference)),
        _sort_time_key(local_time(metric.reset_5h_at, reference)),
        metric.type_name.casefold(),
    )


def average_percent(values: Iterable[float | None]) -> str:
    value = average_percent_value(values)
    if value is None:
        return "-"
    return f"{value:.2f}%"


def average_percent_value(values: Iterable[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    if not known:
        return None
    return sum(known) / len(known)


def snapshot_5h_remaining_percent(snapshot: MetricSnapshot) -> float | None:
    if not snapshot.type_metrics:
        return snapshot.available_percent
    metrics = effective_metrics(snapshot.type_metrics)
    percent = average_percent_value(metric.remaining_5h_percent for metric in metrics)
    if percent is None and snapshot.available <= 0 and snapshot.total > 0:
        return 0.0
    return percent


def snapshot_7d_remaining_percent(snapshot: MetricSnapshot) -> float | None:
    if not snapshot.type_metrics:
        return None
    metrics = effective_metrics(snapshot.type_metrics)
    percent = average_percent_value(metric.remaining_7d_percent for metric in metrics)
    if percent is None and snapshot.available <= 0 and snapshot.total > 0:
        return 0.0
    return percent


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


def _compact_percent(value: float | None) -> str:
    if value is None:
        return "-"
    if value == round(value):
        return f"{value:.0f}%"
    return f"{value:.2f}%"


def _sort_time_key(value: datetime | None) -> tuple[int, datetime]:
    return (value is None, value or datetime.max)


def _total_quota_line(metrics: list[TypeMetric]) -> str:
    if not metrics:
        return "总 5h 额度：-，总 7d 额度：-"
    return f"总 5h 额度：{average_percent(metric.remaining_5h_percent for metric in metrics)}，总 7d 额度：{average_percent(metric.remaining_7d_percent for metric in metrics)}"
