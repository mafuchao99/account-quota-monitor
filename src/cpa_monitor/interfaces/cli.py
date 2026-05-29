from __future__ import annotations

import argparse
import asyncio
import logging

from cpa_monitor.application.config import MonitorConfig, load_config
from cpa_monitor.infrastructure.http.cli_proxy_codex import (
    CodexCredential,
    CodexCredentialQuota,
    collect_one_codex_quota,
    fetch_codex_credentials,
)

from .bootstrap import build_service


def main() -> None:
    parser = argparse.ArgumentParser(prog="cpa-monitor")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML/TOML config file.")
    parser.add_argument("--log-level", default="INFO", help="Python logging level.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run", help="Run scheduler forever.")
    subparsers.add_parser("collect-once", help="Collect every target once and evaluate alerts.")
    subparsers.add_parser("credentials", help="Fetch and print CLIProxyAPI Codex credential status.")
    quota_one_parser = subparsers.add_parser("quota-one", help="Collect and print quota for one Codex credential.")
    quota_one_group = quota_one_parser.add_mutually_exclusive_group(required=True)
    quota_one_group.add_argument("--auth-index", help="Full auth_index or masked form like abcd...1234.")
    quota_one_group.add_argument("--match", help="Unique substring matched against name/account/auth_index.")
    notify_parser = subparsers.add_parser("notify-test", help="Send a test notification through configured channels.")
    notify_parser.add_argument("--message", default="CPA Monitor 通知测试", help="Test message content.")
    report_parser = subparsers.add_parser("report", help="Generate and send a report from recent snapshots.")
    report_parser.add_argument("--hours", type=int, help="How many recent hours to include.")
    report_parser.add_argument("--detail-mode", choices=("latest", "all", "none"), help="Detail section mode.")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(message)s")
    config = load_config(args.config)
    service = build_service(config)

    if args.command == "run":
        asyncio.run(service.run())
    elif args.command == "collect-once":
        asyncio.run(service.collect_once())
    elif args.command == "credentials":
        raise SystemExit(asyncio.run(print_credentials(config)))
    elif args.command == "quota-one":
        raise SystemExit(asyncio.run(print_one_quota(config, auth_index=args.auth_index, match=args.match)))
    elif args.command == "notify-test":
        asyncio.run(service.notifier.send_text(args.message))
    elif args.command == "report":
        asyncio.run(service.send_report(hours=args.hours, detail_mode=args.detail_mode))


async def print_credentials(config: MonitorConfig) -> int:
    targets = [target for target in config.targets if target.collector.lower() == "cli_proxy_codex"]
    if not targets:
        print("No cli_proxy_codex target is configured.")
        return 0
    exit_code = 0
    for target in targets:
        try:
            credentials = await fetch_codex_credentials(target)
        except Exception as exc:
            exit_code = 1
            print(f"{target.name} credentials fetch failed: {type(exc).__name__}: {exc}")
            continue
        print(_credentials_report(target.name, credentials))
    return exit_code


def _credentials_report(target_name: str, credentials: list[CodexCredential]) -> str:
    total = len(credentials)
    active = sum(1 for item in credentials if not item.disabled)
    disabled = sum(1 for item in credentials if item.disabled)
    unavailable = sum(1 for item in credentials if item.unavailable)
    missing_auth_index = sum(1 for item in credentials if not item.auth_index)
    lines = [
        f"{target_name} credentials: total={total}, active={active}, disabled={disabled}, "
        f"unavailable={unavailable}, missing_auth_index={missing_auth_index}",
    ]
    for item in credentials:
        state = "disabled" if item.disabled else "active"
        if item.unavailable:
            state += "/unavailable"
        lines.append(
            f"- [{state}] {_mask_name(item.name)} auth_index={_mask_auth_index(item.auth_index)} "
            f"status={item.status} account={_mask_name(item.account)}"
        )
    return "\n".join(lines)


async def print_one_quota(config: MonitorConfig, auth_index: str | None, match: str | None) -> int:
    targets = [target for target in config.targets if target.collector.lower() == "cli_proxy_codex"]
    if not targets:
        print("No cli_proxy_codex target is configured.")
        return 1
    if len(targets) > 1:
        print("quota-one requires exactly one cli_proxy_codex target.")
        return 1
    try:
        quota = await collect_one_codex_quota(targets[0], auth_index=auth_index, match=match)
    except Exception as exc:
        print(f"quota-one failed: {type(exc).__name__}: {exc}")
        return 1
    print(_quota_one_report(targets[0].name, quota))
    return 0


def _quota_one_report(target_name: str, quota: CodexCredentialQuota) -> str:
    credential = quota.credential
    result = quota.result
    metric = result.metric
    return "\n".join(
        [
            f"{target_name} single quota",
            f"credential={_mask_name(credential.name)} auth_index={_mask_auth_index(credential.auth_index)} status={credential.status}",
            f"status_code={result.status_code}",
            f"available={metric.available}/{metric.total}",
            f"remaining_5h={_format_percent(metric.remaining_5h_percent)}",
            f"remaining_7d={_format_percent(metric.remaining_7d_percent)}",
            f"unauthorized={metric.unauthorized} other_errors={metric.other_errors}",
        ]
    )


def _mask_name(value: str) -> str:
    if "@" not in value:
        return value
    name, domain = value.split("@", 1)
    if not name:
        return f"***@{domain}"
    return f"{name[0]}***@{domain}"


def _mask_auth_index(value: str) -> str:
    if not value:
        return "-"
    if len(value) <= 8:
        return f"{value[:2]}***"
    return f"{value[:4]}...{value[-4:]}"


def _format_percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}%"
