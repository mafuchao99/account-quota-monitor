from __future__ import annotations

import argparse
import asyncio
import logging

from cpa_monitor.application.config import load_config

from .bootstrap import build_service


def main() -> None:
    parser = argparse.ArgumentParser(prog="cpa-monitor")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML/TOML config file.")
    parser.add_argument("--log-level", default="INFO", help="Python logging level.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run", help="Run scheduler forever.")
    subparsers.add_parser("collect-once", help="Collect every target once and evaluate alerts.")
    report_parser = subparsers.add_parser("report", help="Generate and send a report from recent snapshots.")
    report_parser.add_argument("--hours", type=int, default=3, help="How many recent hours to include.")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(message)s")
    config = load_config(args.config)
    service = build_service(config)

    if args.command == "run":
        asyncio.run(service.run())
    elif args.command == "collect-once":
        asyncio.run(service.collect_once())
    elif args.command == "report":
        asyncio.run(service.send_report(hours=args.hours))
