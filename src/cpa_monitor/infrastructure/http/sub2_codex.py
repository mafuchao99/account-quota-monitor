from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from cpa_monitor.application.config import TargetConfig
from cpa_monitor.domain.models import MetricSnapshot, TypeMetric


class Sub2CodexCollector:
    def __init__(self, timeout: float = 30, page_size: int = 100) -> None:
        self.timeout = timeout
        self.page_size = page_size

    async def collect(self, target: TargetConfig, captured_at: datetime) -> MetricSnapshot:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required to collect sub2 Codex snapshots.") from exc

        base_url = admin_base_url(target)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                accounts = await fetch_accounts(client, base_url, target.headers, self.page_size)
            except Exception as exc:
                return error_snapshot(target, captured_at, str(exc))

        metrics = tuple(account_metric(item, captured_at) for item in accounts if is_codex_account(item))
        return MetricSnapshot(
            target_id=target.id,
            target_name=target.name,
            captured_at=captured_at,
            available=sum(metric.available for metric in metrics),
            total=len(metrics),
            disabled=sum(1 for item in accounts if is_codex_account(item) and is_disabled_account(item)),
            rate_limited=sum(metric.rate_limited for metric in metrics),
            unauthorized=sum(metric.unauthorized for metric in metrics),
            other_errors=sum(metric.other_errors for metric in metrics),
            type_metrics=metrics,
            raw={"accounts": accounts},
        )


async def fetch_accounts(
    client: Any,
    base_url: str,
    headers: dict[str, str],
    page_size: int = 100,
) -> list[dict[str, Any]]:
    accounts: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = await fetch_accounts_page(client, base_url, headers, page, page_size)
        items, total = parse_accounts_page(payload)
        accounts.extend(items)
        if not items or (total is not None and len(accounts) >= total) or len(items) < page_size:
            return accounts
        await asyncio.sleep(random.uniform(0, 2))
        page += 1


async def fetch_accounts_page(
    client: Any,
    base_url: str,
    headers: dict[str, str],
    page: int,
    page_size: int,
) -> dict[str, Any]:
    query = urlencode({"page": page, "page_size": page_size, "platform": "openai"})
    response = await client.get(f"{base_url}/accounts?{query}", headers=headers)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("sub2 accounts response must be a JSON object.")
    return payload


def parse_accounts_page(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int | None]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    raw_items = (
        data.get("items")
        or data.get("accounts")
        or data.get("list")
        or payload.get("items")
        or payload.get("accounts")
        or payload.get("list")
        or []
    )
    if not isinstance(raw_items, list):
        raise ValueError("sub2 accounts items must be a list.")
    total = to_int_or_none(data.get("total") if isinstance(data, dict) else None)
    return [item for item in raw_items if isinstance(item, dict)], total


def account_metric(account: dict[str, Any], captured_at: datetime | None = None) -> TypeMetric:
    extra = account.get("extra") if isinstance(account.get("extra"), dict) else {}
    used_5h = to_float_or_none(extra.get("codex_5h_used_percent"))
    used_7d = to_float_or_none(extra.get("codex_7d_used_percent"))
    schedulable = bool(account.get("schedulable", True))
    has_snapshot = used_5h is not None or used_7d is not None
    remaining_5h = remaining_percent(used_5h)
    remaining_7d = remaining_percent(used_7d)
    unauthorized = 1 if is_unauthorized_account(account) else 0
    other_errors = 1 if is_error_account(account) and not unauthorized else 0
    quota_available = _positive_or_unknown(remaining_5h) and _positive_or_unknown(remaining_7d)
    rate_limited = is_rate_limited_account(account, captured_at)
    rate_limited_until = rate_limited_reset_at(account, captured_at)
    available = 1 if schedulable and has_snapshot and quota_available and not rate_limited and not unauthorized and not other_errors else 0
    return TypeMetric(
        type_name=display_name(account),
        available=available,
        total=1,
        remaining_5h_percent=remaining_5h,
        remaining_7d_percent=remaining_7d,
        reset_5h_at=parse_datetime(extra.get("codex_5h_reset_at")),
        reset_7d_at=parse_datetime(extra.get("codex_7d_reset_at")),
        usage_updated_at=parse_datetime(extra.get("codex_usage_updated_at")),
        rate_limited=1 if rate_limited else 0,
        rate_limited_until=rate_limited_until,
        unauthorized=unauthorized,
        other_errors=other_errors,
    )


def is_codex_account(account: dict[str, Any]) -> bool:
    platform = str(account.get("platform") or "").lower()
    extra = account.get("extra") if isinstance(account.get("extra"), dict) else {}
    return platform == "openai" and any(str(key).startswith("codex_") for key in extra)


def is_error_account(account: dict[str, Any]) -> bool:
    status = str(account.get("status") or "").lower()
    return status == "error" or bool(account.get("error_message"))


def is_unauthorized_account(account: dict[str, Any]) -> bool:
    status = str(account.get("status") or "").lower()
    error_message = str(account.get("error_message") or "").lower()
    return status in {"unauthorized", "401", "403"} or "401" in error_message or "unauthorized" in error_message


def is_disabled_account(account: dict[str, Any]) -> bool:
    status = str(account.get("status") or "").lower()
    return status == "disabled" or account.get("schedulable") is False


def is_rate_limited_account(account: dict[str, Any], captured_at: datetime | None = None) -> bool:
    status = str(account.get("status") or "").lower()
    if status in {"rate_limited", "429"}:
        return True
    now = captured_at or datetime.now(timezone.utc)
    reset_at = parse_datetime(account.get("rate_limit_reset_at"))
    temp_until = parse_datetime(account.get("temp_unschedulable_until"))
    overload_until = parse_datetime(account.get("overload_until"))
    return any(_is_future_time(value, now) for value in (reset_at, temp_until, overload_until))


def rate_limited_reset_at(account: dict[str, Any], captured_at: datetime | None = None) -> datetime | None:
    now = captured_at or datetime.now(timezone.utc)
    candidates = [
        parse_datetime(account.get("rate_limit_reset_at")),
        parse_datetime(account.get("temp_unschedulable_until")),
        parse_datetime(account.get("overload_until")),
    ]
    future = [value for value in candidates if _is_future_time(value, now)]
    return min(future) if future else None


def admin_base_url(target: TargetConfig) -> str:
    base_url = (target.base_url or target.url).rstrip("/")
    if not base_url:
        raise ValueError(f"Target {target.id} requires base_url or url for sub2_codex collector.")
    if base_url.endswith("/api/v1/admin"):
        return base_url
    return f"{base_url}/api/v1/admin"


def error_snapshot(target: TargetConfig, captured_at: datetime, error: str) -> MetricSnapshot:
    return MetricSnapshot(
        target_id=target.id,
        target_name=target.name,
        captured_at=captured_at,
        available=0,
        total=0,
        other_errors=1,
        raw={"error": error},
    )


def display_name(account: dict[str, Any]) -> str:
    return str(account.get("name") or account.get("email") or account.get("id") or "unknown")


def remaining_percent(used_percent: float | None) -> float | None:
    if used_percent is None:
        return None
    return max(0.0, 100.0 - used_percent)


def _positive_or_unknown(value: float | None) -> bool:
    return value is None or value > 0


def _is_future_time(value: datetime | None, now: datetime) -> bool:
    if value is None:
        return False
    comparable_now = now.astimezone(value.tzinfo) if value.tzinfo and now.tzinfo else now
    return value > comparable_now


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None


def to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
