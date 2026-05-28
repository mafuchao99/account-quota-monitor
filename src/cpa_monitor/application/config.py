from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class JsonPaths:
    total: str = "$.total"
    available: str = "$.available"
    disabled: str = "$.disabled"
    unauthorized: str = "$.unauthorized"
    other_errors: str = "$.other_errors"
    types: str | None = "$.types"


@dataclass(frozen=True)
class Thresholds:
    available_drop: int = 1
    unauthorized: int = 1
    other_errors: int = 1
    remaining_percent: float = 20
    silence_minutes: int = 60


@dataclass(frozen=True)
class DynamicSchedule:
    enabled: bool = False
    normal_interval_minutes: int = 30
    urgent_interval_minutes: int = 10
    urgent_remaining_percent: float | None = None


@dataclass(frozen=True)
class TargetConfig:
    id: str
    name: str
    url: str = ""
    collector: str = "http_json"
    base_url: str = ""
    method: str = "GET"
    cron: str = "0 */30 * * * *"
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] | None = None
    json_paths: JsonPaths = field(default_factory=JsonPaths)
    thresholds: Thresholds = field(default_factory=Thresholds)
    dynamic_schedule: DynamicSchedule = field(default_factory=DynamicSchedule)


@dataclass(frozen=True)
class OneBotConfig:
    endpoint: str = "http://127.0.0.1:3000"
    access_token: str = ""
    retry_count: int = 2
    group_ids: tuple[str, ...] = ()
    private_user_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AppConfig:
    timezone: str = "Asia/Shanghai"
    database_url: str = "sqlite:///data/monitor.db"
    report_dir: str = "data/reports"
    report_cron: str = "0 */30 * * * *"


@dataclass(frozen=True)
class MonitorConfig:
    app: AppConfig
    onebot: OneBotConfig
    targets: tuple[TargetConfig, ...]


_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::-(.*?))?\}")


def load_config(path: str | Path) -> MonitorConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    _load_env_file(path.parent / ".env")
    data = _load_mapping(path)
    expanded = _expand_env(data)
    config = _parse_config(expanded)
    _validate_config(config)
    return config


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if not item or item.startswith("#") or "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _clean_env_value(value.strip())


def _clean_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".toml":
        return tomllib.loads(text)
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to read YAML config files.") from exc
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ValueError("Config root must be a mapping.")
    return loaded


def _expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        return os.getenv(name, default or "")

    return _ENV_PATTERN.sub(replace, value)


def _parse_config(data: dict[str, Any]) -> MonitorConfig:
    app = AppConfig(**data.get("app", {}))
    notifications = data.get("notifications", {})
    onebot_data = notifications.get("onebot", {})
    onebot = OneBotConfig(
        endpoint=onebot_data.get("endpoint", "http://127.0.0.1:3000").rstrip("/"),
        access_token=onebot_data.get("access_token", ""),
        retry_count=int(onebot_data.get("retry_count", 2)),
        group_ids=tuple(str(item) for item in onebot_data.get("group_ids", [])),
        private_user_ids=tuple(str(item) for item in onebot_data.get("private_user_ids", [])),
    )
    targets = tuple(_parse_target(item) for item in data.get("targets", []))
    if not targets:
        raise ValueError("At least one target is required.")
    return MonitorConfig(app=app, onebot=onebot, targets=targets)


def _parse_target(data: dict[str, Any]) -> TargetConfig:
    paths = JsonPaths(**data.get("json_paths", {}))
    thresholds = Thresholds(**data.get("thresholds", {}))
    dynamic_schedule = _parse_dynamic_schedule(data.get("dynamic_schedule", {}))
    return TargetConfig(
        id=str(data["id"]),
        name=str(data["name"]),
        url=str(data.get("url", "")),
        collector=str(data.get("collector", "http_json")),
        base_url=str(data.get("base_url", "")),
        method=str(data.get("method", "GET")).upper(),
        cron=str(data.get("cron", "0 */30 * * * *")),
        headers={str(k): str(v) for k, v in data.get("headers", {}).items()},
        body=data.get("body"),
        json_paths=paths,
        thresholds=thresholds,
        dynamic_schedule=dynamic_schedule,
    )


def _parse_dynamic_schedule(data: dict[str, Any]) -> DynamicSchedule:
    if not isinstance(data, dict):
        raise ValueError("dynamic_schedule must be a mapping.")
    schedule = DynamicSchedule(
        enabled=bool(data.get("enabled", False)),
        normal_interval_minutes=int(data.get("normal_interval_minutes", 30)),
        urgent_interval_minutes=int(data.get("urgent_interval_minutes", 10)),
        urgent_remaining_percent=(
            None if data.get("urgent_remaining_percent") is None else float(data["urgent_remaining_percent"])
        ),
    )
    if schedule.normal_interval_minutes <= 0 or schedule.urgent_interval_minutes <= 0:
        raise ValueError("dynamic_schedule intervals must be positive minutes.")
    return schedule


def _validate_config(config: MonitorConfig) -> None:
    for target in config.targets:
        if target.collector.lower() != "cli_proxy_codex":
            continue
        if _is_placeholder(target.base_url or target.url, {"https://your-cpa-endpoint.example.com"}):
            raise ValueError(
                f"Target {target.id} is still using the example CPA endpoint. "
                "Set CPA_ENDPOINT in .env to your CLIProxyAPI address."
            )
        authorization = target.headers.get("Authorization", "")
        if _is_placeholder(authorization.removeprefix("Bearer").strip(), {"your-management-key"}):
            raise ValueError(
                f"Target {target.id} is still using the example Management Key. "
                "Set CPA_MANAGEMENT_KEY in .env to your real Management Key."
            )


def _is_placeholder(value: str, placeholders: set[str]) -> bool:
    normalized = value.strip()
    return not normalized or normalized in placeholders
