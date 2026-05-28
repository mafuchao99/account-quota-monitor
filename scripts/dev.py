from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.yaml"
EXAMPLE_CONFIG = ROOT / "config.example.yaml"
ENV_FILE = ROOT / ".env"
EXAMPLE_ENV_FILE = ROOT / ".env.example"


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command))
    return subprocess.run(command, cwd=ROOT, check=check, text=True)


def uv_command() -> str:
    executable = shutil.which("uv")
    if executable is None:
        raise RuntimeError("uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/")
    return executable


def setup(_args: argparse.Namespace) -> None:
    uv = uv_command()
    run([uv, "sync", "--extra", "dev"])
    run([uv, "run", "playwright", "install", "chromium"])
    if not CONFIG.exists():
        shutil.copyfile(EXAMPLE_CONFIG, CONFIG)
        print(f"Created {CONFIG.name} from {EXAMPLE_CONFIG.name}")
    if not ENV_FILE.exists() and EXAMPLE_ENV_FILE.exists():
        shutil.copyfile(EXAMPLE_ENV_FILE, ENV_FILE)
        print(f"Created {ENV_FILE.name} from {EXAMPLE_ENV_FILE.name}")


def cpa_monitor(args: argparse.Namespace, command: str, extra: list[str] | None = None) -> None:
    extra = extra or []
    run(
        [
            uv_command(),
            "run",
            "cpa-monitor",
            "--config",
            args.config,
            "--log-level",
            args.log_level,
            command,
            *extra,
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Development helper for CPA Monitor.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup_parser = subparsers.add_parser("setup", help="Sync uv dependencies, install Chromium, and prepare config.")
    setup_parser.set_defaults(func=setup)

    run_parser = subparsers.add_parser("run", help="Run the scheduler.")
    run_parser.add_argument("--config", default="config.yaml")
    run_parser.add_argument("--log-level", default="DEBUG")
    run_parser.set_defaults(func=lambda args: cpa_monitor(args, "run"))

    collect_parser = subparsers.add_parser("collect", help="Collect all targets once.")
    collect_parser.add_argument("--config", default="config.yaml")
    collect_parser.add_argument("--log-level", default="DEBUG")
    collect_parser.set_defaults(func=lambda args: cpa_monitor(args, "collect-once"))

    report_parser = subparsers.add_parser("report", help="Generate and send a report.")
    report_parser.add_argument("--config", default="config.yaml")
    report_parser.add_argument("--log-level", default="DEBUG")
    report_parser.add_argument("--hours", default="3")
    report_parser.set_defaults(func=lambda args: cpa_monitor(args, "report", ["--hours", args.hours]))

    test_parser = subparsers.add_parser("test", help="Run tests.")
    test_parser.set_defaults(func=lambda _args: run([uv_command(), "run", "pytest"]))

    clean_parser = subparsers.add_parser("clean", help="Remove local build and test caches.")
    clean_parser.set_defaults(func=lambda _args: clean())

    args = parser.parse_args()
    args.func(args)


def clean() -> None:
    for path in [ROOT / ".pytest_cache", ROOT / "dist"]:
        if path.exists():
            shutil.rmtree(path)
    for path in ROOT.glob("*.egg-info"):
        if path.exists():
            shutil.rmtree(path)


if __name__ == "__main__":
    main()
