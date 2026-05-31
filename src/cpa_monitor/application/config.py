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
    cron: str = "0 50 * * * *"
    crons: tuple[str, ...] = ()
    delay_min_seconds: float = 1
    delay_max_seconds: float = 3
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] | None = None
    json_paths: JsonPaths = field(default_factory=JsonPaths)
    thresholds: Thresholds = field(default_factory=Thresholds)
    dynamic_schedule: DynamicSchedule = field(default_factory=DynamicSchedule)


@dataclass(frozen=True)
class OneBotConfig:
    enabled: bool = False
    endpoint: str = "http://127.0.0.1:3000"
    access_token: str = ""
    retry_count: int = 2
    group_ids: tuple[str, ...] = ()
    private_user_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class QqBotConfig:
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    openid: str = ""
    token_url: str = "https://bots.qq.com/app/getAppAccessToken"
    api_base: str = "https://api.sgroup.qq.com"
    retry_count: int = 2


@dataclass(frozen=True)
class ConsoleConfig:
    enabled: bool = True


@dataclass(frozen=True)
class AppConfig:
    timezone: str = "Asia/Shanghai"
    database_url: str = "sqlite:///data/monitor.db"
    report_dir: str = "data/reports"
    report_cron: str = "0 0 * * * *"
    report_hours: int = 1
    report_detail_mode: str = "latest"
    full_report_enabled: bool = False
    full_report_crons: tuple[str, ...] = field(
        default_factory=lambda: ("0 30 7 * * *", "0 10 12 * * *", "0 10 19 * * *", "0 30 23 * * *")
    )
    full_report_hours: int = 6
    full_report_detail_mode: str = "all"


@dataclass(frozen=True)
class MonitorConfig:
    app: AppConfig
    console: ConsoleConfig
    onebot: OneBotConfig
    qqbot: QqBotConfig
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
    app = _parse_app(data.get("app", {}))
    if app.report_hours <= 0 or app.full_report_hours <= 0:
        raise ValueError("report_hours and full_report_hours must be positive.")
    if app.report_detail_mode not in {"latest", "all", "none"}:
        raise ValueError("report_detail_mode must be one of: latest, all, none.")
    if app.full_report_detail_mode not in {"latest", "all", "none"}:
        raise ValueError("full_report_detail_mode must be one of: latest, all, none.")
    notifications = data.get("notifications", {})
    onebot_data = notifications.get("onebot", {})
    onebot = OneBotConfig(
        enabled=bool(onebot_data.get("enabled", False)),
        endpoint=onebot_data.get("endpoint", "http://127.0.0.1:3000").rstrip("/"),
        access_token=onebot_data.get("access_token", ""),
        retry_count=int(onebot_data.get("retry_count", 2)),
        group_ids=tuple(str(item) for item in onebot_data.get("group_ids", [])),
        private_user_ids=tuple(str(item) for item in onebot_data.get("private_user_ids", [])),
    )
    qqbot_data = notifications.get("qqbot", {})
    qqbot = QqBotConfig(
        enabled=bool(qqbot_data.get("enabled", False)),
        app_id=str(qqbot_data.get("app_id", "")),
        app_secret=str(qqbot_data.get("app_secret", "")),
        openid=str(qqbot_data.get("openid", "")),
        token_url=str(qqbot_data.get("token_url", "https://bots.qq.com/app/getAppAccessToken")),
        api_base=str(qqbot_data.get("api_base", "https://api.sgroup.qq.com")).rstrip("/"),
        retry_count=int(qqbot_data.get("retry_count", 2)),
    )
    console_data = notifications.get("console", {})
    console = ConsoleConfig(enabled=bool(console_data.get("enabled", True)))
    targets = tuple(_parse_target(item) for item in data.get("targets", []))
    if not targets:
        raise ValueError("At least one target is required.")
    return MonitorConfig(app=app, console=console, onebot=onebot, qqbot=qqbot, targets=targets)


def _parse_app(data: dict[str, Any]) -> AppConfig:
    if not isinstance(data, dict):
        raise ValueError("app must be a mapping.")
    app_data = dict(data)
    if "full_report_crons" in app_data:
        crons = app_data["full_report_crons"]
    elif "full_report_cron" in app_data:
        crons = [app_data.pop("full_report_cron")]
    else:
        crons = None
    app_data.pop("full_report_crons", None)
    app = AppConfig(**app_data)
    if crons is not None:
        if isinstance(crons, str):
            crons = [crons]
        if not isinstance(crons, (list, tuple)) or not crons:
            raise ValueError("full_report_crons must be a non-empty list.")
        app = AppConfig(**{**app.__dict__, "full_report_crons": tuple(str(item) for item in crons)})
    return app


def _parse_target(data: dict[str, Any]) -> TargetConfig:
    paths = JsonPaths(**data.get("json_paths", {}))
    thresholds = Thresholds(**data.get("thresholds", {}))
    dynamic_schedule = _parse_dynamic_schedule(data.get("dynamic_schedule", {}))
    crons = _parse_target_crons(data)
    return TargetConfig(
        id=str(data["id"]),
        name=str(data["name"]),
        url=str(data.get("url", "")),
        collector=str(data.get("collector", "http_json")),
        base_url=str(data.get("base_url", "")),
        method=str(data.get("method", "GET")).upper(),
        cron=crons[0],
        crons=crons,
        delay_min_seconds=float(data.get("delay_min_seconds", 1)),
        delay_max_seconds=float(data.get("delay_max_seconds", 3)),
        headers={str(k): str(v) for k, v in data.get("headers", {}).items()},
        body=data.get("body"),
        json_paths=paths,
        thresholds=thresholds,
        dynamic_schedule=dynamic_schedule,
    )


def _parse_target_crons(data: dict[str, Any]) -> tuple[str, ...]:
    has_cron = "cron" in data
    has_crons = "crons" in data
    if has_cron and has_crons:
        raise ValueError("Use either target cron or crons, not both.")
    raw = data.get("crons") if has_crons else [data.get("cron", "0 50 * * * *")]
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError("target crons must be a non-empty list.")
    crons = tuple(str(item) for item in raw)
    if any(not item.strip() for item in crons):
        raise ValueError("target crons cannot contain empty values.")
    return tuple(dict.fromkeys(crons))


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
    if config.qqbot.enabled:
        if _is_placeholder(config.qqbot.app_id, {"your-qqbot-app-id"}):
            raise ValueError("QQBot notification is enabled but QQBOT_APP_ID is not configured in .env.")
        if _is_placeholder(config.qqbot.app_secret, {"your-qqbot-app-secret"}):
            raise ValueError("QQBot notification is enabled but QQBOT_APP_SECRET is not configured in .env.")
        if _is_placeholder(config.qqbot.openid, {"your-qq-openid"}):
            raise ValueError("QQBot notification is enabled but QQBOT_OPENID is not configured in .env.")

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
