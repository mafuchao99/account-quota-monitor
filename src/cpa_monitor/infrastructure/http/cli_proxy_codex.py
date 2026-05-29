from __future__ import annotations

import asyncio
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from cpa_monitor.application.config import TargetConfig
from cpa_monitor.domain.models import MetricSnapshot, TypeMetric


USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
USER_AGENT = "codex_cli_rs/0.76.0 (Debian 13.0.0; x86_64) WindowsTerminal"


@dataclass(frozen=True)
class CodexCredential:
    name: str
    auth_index: str
    status: str
    disabled: bool
    unavailable: bool
    account: str


@dataclass(frozen=True)
class CodexQuotaResult:
    metric: TypeMetric
    status_code: int | None
    quota: dict[str, Any] | None
    error: str | None = None

    @property
    def available(self) -> int:
        return self.metric.available

    @property
    def unauthorized(self) -> int:
        return self.metric.unauthorized

    @property
    def other_errors(self) -> int:
        return self.metric.other_errors


@dataclass(frozen=True)
class CodexCredentialQuota:
    credential: CodexCredential
    result: CodexQuotaResult


class CliProxyCodexCollector:
    def __init__(self, timeout: float = 60) -> None:
        self.timeout = timeout

    async def collect(self, target: TargetConfig, captured_at: datetime) -> MetricSnapshot:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required to collect CLIProxyAPI Codex quota.") from exc

        base_url = management_base_url(target)
        headers = management_headers(target)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(f"{base_url}/auth-files", headers=headers)
                response.raise_for_status()
                files = response.json().get("files", [])
                disabled = sum(1 for item in files if _is_codex_file(item) and item.get("disabled") is True)
                active_files = [item for item in files if _is_active_codex_file(item)]
                results = await self._collect_all(client, base_url, headers, active_files, target)
            except Exception as exc:
                return _error_snapshot(target, captured_at, str(exc))

        type_metrics = tuple(item.metric for item in results)
        total = len(active_files)
        return MetricSnapshot(
            target_id=target.id,
            target_name=target.name,
            captured_at=captured_at,
            available=sum(item.available for item in results),
            total=total,
            disabled=disabled,
            unauthorized=sum(item.unauthorized for item in results),
            other_errors=sum(item.other_errors for item in results),
            type_metrics=type_metrics,
            raw={"files": files, "quota_results": [_raw_result(item) for item in results]},
        )

    async def _collect_all(
        self,
        client: Any,
        base_url: str,
        headers: dict[str, str],
        files: list[dict[str, Any]],
        target: TargetConfig,
    ) -> list[CodexQuotaResult]:
        results = []
        for index, item in enumerate(files):
            if index > 0:
                await asyncio.sleep(random.uniform(target.delay_min_seconds, target.delay_max_seconds))
            results.append(await collect_codex_quota(client, base_url, headers, item))
        return results


async def fetch_codex_credentials(target: TargetConfig) -> list[CodexCredential]:
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("httpx is required to fetch CLIProxyAPI credentials.") from exc

    base_url = management_base_url(target)
    headers = management_headers(target)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{base_url}/auth-files", headers=headers)
        response.raise_for_status()
        files = response.json().get("files", [])
    return [credential_summary(item) for item in files if _is_codex_file(item)]


async def collect_one_codex_quota(target: TargetConfig, auth_index: str | None = None, match: str | None = None) -> CodexCredentialQuota:
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("httpx is required to collect CLIProxyAPI Codex quota.") from exc

    base_url = management_base_url(target)
    headers = management_headers(target)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{base_url}/auth-files", headers=headers)
        response.raise_for_status()
        files = [item for item in response.json().get("files", []) if _is_codex_file(item)]
        raw = select_credential(files, auth_index=auth_index, match=match)
        result = await collect_codex_quota(client, base_url, headers, raw)
    return CodexCredentialQuota(credential=credential_summary(raw), result=result)


def credential_summary(item: dict[str, Any]) -> CodexCredential:
    return CodexCredential(
        name=_display_name(item),
        auth_index=str(item.get("auth_index") or ""),
        status=str(item.get("status") or "-"),
        disabled=bool(item.get("disabled")),
        unavailable=bool(item.get("unavailable")),
        account=str(item.get("account") or item.get("account_type") or "-"),
    )


def select_credential(
    credentials: list[dict[str, Any]],
    auth_index: str | None = None,
    match: str | None = None,
) -> dict[str, Any]:
    if bool(auth_index) == bool(match):
        raise ValueError("Provide exactly one of auth_index or match.")

    if auth_index:
        matches = [item for item in credentials if _auth_index_matches(str(item.get("auth_index") or ""), auth_index)]
    else:
        pattern = str(match or "").lower()
        matches = [
            item
            for item in credentials
            if pattern in _display_name(item).lower()
            or pattern in str(item.get("account") or "").lower()
            or pattern in str(item.get("auth_index") or "").lower()
        ]

    if len(matches) != 1:
        raise ValueError(f"Expected exactly one credential match, got {len(matches)}.")
    return matches[0]


def _auth_index_matches(value: str, pattern: str) -> bool:
    if "..." not in pattern:
        return value == pattern
    prefix, suffix = pattern.split("...", 1)
    return value.startswith(prefix) and value.endswith(suffix)


async def collect_codex_quota(
    client: Any,
    base_url: str,
    management_headers: dict[str, str],
    credential: dict[str, Any],
) -> CodexQuotaResult:
    auth_index = credential.get("auth_index")
    if not auth_index:
        return _error_result(credential, "missing auth_index")

    account_id = _account_id(credential)
    api_headers = {
        "Authorization": "Bearer $TOKEN$",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    if account_id:
        api_headers["Chatgpt-Account-Id"] = account_id

    try:
        response = await client.post(
            f"{base_url}/api-call",
            headers={**management_headers, "Content-Type": "application/json"},
            json={"authIndex": auth_index, "method": "GET", "url": USAGE_URL, "header": api_headers},
        )
        response.raise_for_status()
        api_call = response.json()
        status_code = int(api_call.get("status_code", 0) or 0)
        quota = _parse_api_call_body(api_call.get("body"))
    except Exception as exc:
        return _error_result(credential, str(exc))
    return quota_result(credential, status_code, quota)


def quota_result(credential: dict[str, Any], status_code: int, quota: dict[str, Any] | None) -> CodexQuotaResult:
    unauthorized = 1 if status_code in {401, 403} else 0
    other_errors = 1 if (status_code == 0 or status_code >= 400) and not unauthorized else 0
    allowed = bool(_get(quota, "rate_limit", "allowed"))
    limit_reached = bool(_get(quota, "rate_limit", "limit_reached"))
    available = 1 if status_code == 200 and allowed and not limit_reached else 0
    metric = TypeMetric(
        type_name=_display_name(credential),
        available=available,
        total=1,
        remaining_5h_percent=_remaining_percent(_get(quota, "rate_limit", "primary_window", "used_percent")),
        remaining_7d_percent=_remaining_percent(_get(quota, "rate_limit", "secondary_window", "used_percent")),
        reset_5h_at=_reset_at(_get(quota, "rate_limit", "primary_window", "reset_at")),
        reset_7d_at=_reset_at(_get(quota, "rate_limit", "secondary_window", "reset_at")),
        unauthorized=unauthorized,
        other_errors=other_errors,
    )
    return CodexQuotaResult(metric=metric, status_code=status_code, quota=quota)


def management_base_url(target: TargetConfig) -> str:
    base_url = (target.base_url or target.url).rstrip("/")
    if not base_url:
        raise ValueError(f"Target {target.id} requires base_url or url for cli_proxy_codex collector.")
    if base_url.endswith("/v0/management"):
        return base_url
    return f"{base_url}/v0/management"


def management_headers(target: TargetConfig) -> dict[str, str]:
    return dict(target.headers)


def _parse_api_call_body(body: Any) -> dict[str, Any] | None:
    if body is None or body == "":
        return None
    if isinstance(body, dict):
        return body
    if isinstance(body, str):
        parsed = json.loads(body)
        return parsed if isinstance(parsed, dict) else None
    return None


def _is_codex_file(item: dict[str, Any]) -> bool:
    provider = str(item.get("provider") or item.get("type") or "").lower()
    return provider == "codex"


def _is_active_codex_file(item: dict[str, Any]) -> bool:
    return _is_codex_file(item) and item.get("disabled") is not True


def _error_result(credential: dict[str, Any], error: str) -> CodexQuotaResult:
    metric = TypeMetric(type_name=_display_name(credential), available=0, total=1, other_errors=1)
    return CodexQuotaResult(metric=metric, status_code=None, quota=None, error=error)


def _error_snapshot(target: TargetConfig, captured_at: datetime, error: str) -> MetricSnapshot:
    return MetricSnapshot(
        target_id=target.id,
        target_name=target.name,
        captured_at=captured_at,
        available=0,
        total=0,
        other_errors=1,
        raw={"error": error},
    )


def _display_name(credential: dict[str, Any]) -> str:
    return str(
        credential.get("label")
        or credential.get("email")
        or credential.get("name")
        or credential.get("auth_index")
        or credential.get("id")
        or "unknown"
    )


def _account_id(credential: dict[str, Any]) -> str | None:
    id_token = credential.get("id_token")
    if not isinstance(id_token, dict):
        return None
    value = id_token.get("chatgpt_account_id")
    return str(value) if value else None


def _remaining_percent(used_percent: Any) -> float | None:
    if used_percent is None:
        return None
    try:
        return max(0.0, 100.0 - float(used_percent))
    except (TypeError, ValueError):
        return None


def _reset_at(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _get(value: dict[str, Any] | None, *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _raw_result(item: CodexQuotaResult) -> dict[str, Any]:
    return {
        "name": item.metric.type_name,
        "status_code": item.status_code,
        "quota": item.quota,
        "error": item.error,
    }
