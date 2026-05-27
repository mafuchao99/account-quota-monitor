from __future__ import annotations

from datetime import datetime
from typing import Any

from cpa_monitor.application.config import TargetConfig
from cpa_monitor.domain.models import MetricSnapshot, TypeMetric
from cpa_monitor.infrastructure.jsonpath import get_path, to_float_or_none, to_int


class HttpJsonCollector:
    async def collect(self, target: TargetConfig, captured_at: datetime) -> MetricSnapshot:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required to collect HTTP targets.") from exc

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                target.method,
                target.url,
                headers=target.headers,
                json=target.body,
            )
            response.raise_for_status()
            payload = response.json()
        return parse_snapshot(target, payload, captured_at)


def parse_snapshot(target: TargetConfig, payload: dict[str, Any], captured_at: datetime) -> MetricSnapshot:
    paths = target.json_paths
    type_payloads = get_path(payload, paths.types, []) if paths.types else []
    type_metrics = tuple(_parse_type_metric(item) for item in _as_list(type_payloads))
    return MetricSnapshot(
        target_id=target.id,
        target_name=target.name,
        captured_at=captured_at,
        total=to_int(get_path(payload, paths.total, 0)),
        available=to_int(get_path(payload, paths.available, 0)),
        disabled=to_int(get_path(payload, paths.disabled, 0)),
        unauthorized=to_int(get_path(payload, paths.unauthorized, 0)),
        other_errors=to_int(get_path(payload, paths.other_errors, 0)),
        type_metrics=type_metrics,
        raw=payload,
    )


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [{"type": key, **item} if isinstance(item, dict) else {"type": key, "value": item} for key, item in value.items()]
    if isinstance(value, list):
        return value
    raise ValueError("Type metrics path must resolve to a list or mapping.")


def _parse_type_metric(item: dict[str, Any]) -> TypeMetric:
    return TypeMetric(
        type_name=str(item.get("type") or item.get("name") or item.get("type_name") or "unknown"),
        available=to_int(item.get("available", 0)),
        total=to_int(item.get("total", 0)),
        remaining_5h_percent=to_float_or_none(item.get("remaining_5h_percent", item.get("5h_remaining"))),
        remaining_7d_percent=to_float_or_none(item.get("remaining_7d_percent", item.get("7d_remaining"))),
        unauthorized=to_int(item.get("unauthorized", item.get("401", 0))),
        other_errors=to_int(item.get("other_errors", 0)),
    )
