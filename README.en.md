# Account Quota Monitor

Account Quota Monitor is a long-running account quota monitor. It polls CPA / sub2 management APIs on Cron schedules, stores snapshots in SQLite, evaluates alert thresholds, renders image reports, and sends notifications through a QQ OneBot gateway.

Repository: [mafuchao99/account-quota-monitor](https://github.com/mafuchao99/account-quota-monitor)

Chinese documentation: [README.md](README.md)

Maintainer notes:

- [Project overview (Chinese)](docs/project-overview_CN.md)

## Showcase

Hourly reports are rendered as local images, making it easy to review the current account pool, recovery estimates, and available-account details.

![Codex hourly report showcase](docs/assets/hourly-report-showcase.png)

After OneBot/NapCatQQ is configured, quota summaries can be sent automatically to QQ groups or private chats.

![Codex quota summary sent to QQ](docs/assets/qq-message-showcase.png)

## Architecture

```text
src/cpa_monitor/
  domain/          # Pure business models and alert rules
  application/     # Use cases, config, ports, and schedule helpers
  infrastructure/  # HTTP, SQLite, OneBot, and HTML/PNG report adapters
  interfaces/      # CLI entry points and dependency wiring
```

The core business logic is isolated from external tools. Future channels such as Feishu, WeCom, PostgreSQL, Web UI, or new collectors should be added as infrastructure adapters first.

## 3-Minute Quick Start

```bash
python scripts/dev.py setup
```

For CLIProxyAPI / CPA, replace the placeholders in `.env` with your endpoint and Management Key:

```env
CPA_ENDPOINT=https://your-domain.example
CPA_MANAGEMENT_KEY=your-management-key
```

For sub2 monitoring, enable `sub2-codex-quota` in `config.yaml` and configure:

```env
SUB2_ENDPOINT=https://your-sub2-domain.example
SUB2_ADMIN_API_KEY=admin-api-key
```

Run one collection pass. `collect` only collects enabled targets; if only sub2 is enabled, it only reads the sub2 account list:

```bash
python scripts/dev.py collect
```

`credentials` and `quota-one` are for `cli_proxy_codex` targets only. sub2 monitoring uses `collect` / `run`.

## Docker Deployment

1. Copy the example config:

```bash
cp .env.example .env
cp config.example.yaml config.yaml
```

2. Edit `.env` and `config.yaml`:

- For CPA: set `CPA_ENDPOINT` to your CLIProxyAPI endpoint and `CPA_MANAGEMENT_KEY` to your Management Key.
- For sub2: set `SUB2_ENDPOINT` to your sub2 endpoint and `SUB2_ADMIN_API_KEY` to your Admin API Key.
- `targets[].collector`: use `cli_proxy_codex` for CPA; use `sub2_codex` for sub2. The sub2 collector reads local Codex snapshots from the account list.
- `targets[].enabled`: target-level toggle. To switch from CPA to sub2, disable the CPA target and enable `sub2-codex-quota`.
- `targets[].base_url`: reads from environment variables by default. Never commit your real endpoint.
- `targets[].headers.Authorization` / `targets[].headers.x-api-key`: keep real keys in local `.env` or runtime environment variables. Never commit them.
- `targets[].delay_min_seconds` / `delay_max_seconds`: Full collection queries credentials sequentially and waits a random delay between credentials. The default is 5 to 10 seconds to avoid concurrent quota checks.
- `notifications.console.enabled`: Enabled by default. Alerts and report notices are printed to the console.
- `notifications.onebot.enabled`: Set it to `true` when using NapCatQQ/OneBot, then fill endpoint and recipients. At the moment, only the OneBot/NapCatQQ channel can send QQ notifications.
- `notifications.qqbot.enabled`: Reserved for the official QQ Bot channel. It is not adapted yet, so keep it `false`.

3. Start the service:

```bash
docker compose up -d --build
```

4. Follow logs:

```bash
docker compose logs -f cpa-monitor
```

The container reads `/app/config/config.yaml` and writes SQLite data plus generated reports to the host `./data` directory.
The image uses `uv` with `uv.lock` so local and container dependency resolution stay consistent.

Rebuild on a remote server:

```bash
cd /path/to/account-quota-monitor
git pull
docker compose down
docker compose up -d --build
docker compose logs -f cpa-monitor
```

If the remote still points at the old repository name, update it first:

```bash
git remote set-url origin https://github.com/mafuchao99/account-quota-monitor.git
```

## Local Development

First-time setup:

```bash
python scripts/dev.py setup
```

This runs `uv sync`, `uv run playwright install chromium`, and creates `config.yaml` or `.env` from the examples when they are missing.

Daily run:

```bash
python scripts/dev.py run
```

Common development commands:

```bash
python scripts/dev.py credentials
python scripts/dev.py notify --message "Account Quota Monitor notification test"
python scripts/dev.py onebot-login
python scripts/dev.py onebot-groups
python scripts/dev.py collect
python scripts/dev.py report
python scripts/dev.py test
```

On macOS/Linux, if `make` is installed, you can also use shortcuts:

```bash
make setup
make run
```

Windows PowerShell uses the same Python helper:

```powershell
python scripts/dev.py setup
python scripts/dev.py run
```

## Commands

```bash
uv run cpa-monitor --config config.yaml collect-once
uv run cpa-monitor --config config.yaml credentials
uv run cpa-monitor --config config.yaml notify-test --message "Account Quota Monitor notification test"
uv run cpa-monitor --config config.yaml report
uv run cpa-monitor --config config.yaml report --hours 6 --detail-mode all
uv run cpa-monitor --config config.yaml run
```

## Configuration

`config.example.yaml` is the reference template:

- `app.timezone`: Time zone for schedules and reports.
- `app.database_url`: SQLite database URL. The first version supports `sqlite:///...` only.
- `app.report_dir`: Output directory for HTML/PNG reports.
- `app.report_cron` / `app.report_crons` / `app.report_hours` / `app.report_detail_mode`: hourly report schedule, window, and detail mode. `report_crons` supports multiple custom send times, while the legacy `report_cron` field remains compatible. Defaults to a short hourly report with only the latest detail block.
- `app.full_report_enabled` / `app.full_report_crons` / `app.full_report_hours` / `app.full_report_detail_mode`: full report toggle, schedules, window, and detail mode. Disabled by default; when enabled, it sends the last 6-hour full detail report at 07:30, 12:10, 19:10, and 23:30 without triggering collection.
- 401 account analysis is deduplicated by account name and date. An account reported once today will not be repeated in later hourly/full reports until the next day.
- `targets[].enabled`: target-level toggle. Disabled targets are not scheduled and are skipped by `collect-once`.
- `targets[].collector`: Collector type. `cli_proxy_codex` calls CLIProxyAPI `/auth-files` and `/api-call`; `sub2_codex` calls sub2 `/api/v1/admin/accounts` and reads local `extra.codex_*` snapshots; omitting it keeps the original `http_json` behavior.
- `targets[].base_url`: CLIProxyAPI endpoint. The example reads it from `CPA_ENDPOINT`; put the real endpoint only in your local `.env` or runtime environment.
- `targets[].headers.Authorization`: Authentication header in the `Bearer <Management Key>` format. The example reads it from `CPA_MANAGEMENT_KEY`; put the real key only in your local `.env` or runtime environment.
- `sub2_codex` uses `headers.x-api-key` for the Admin API Key. It does not call `/usage` or actively probe upstream quota; it only paginates the account list and reads local Codex snapshot fields.
- sub2 hourly reports recognize `rate_limit_reset_at`, `temp_unschedulable_until`, and `overload_until` as 429 / temporary-unschedulable signals. 429 accounts are shown in the abnormal-account section sorted by expected recovery time.
- sub2 hourly reports show `extra.codex_usage_updated_at` so users can judge whether the quota snapshot is fresh enough.
- The hourly report header calculates total 5h / 7d quota from currently available accounts only. 429, 401, error, exhausted, and unavailable accounts are excluded from that average.
- `targets[].delay_min_seconds` / `delay_max_seconds`: Random delay for full quota collection. It affects `collect` and scheduled collection only; `quota-one` does not wait.
- `targets[].cron` / `targets[].crons`: Polling Cron for each target. Use `cron` for a single schedule and `crons` for multiple custom windows. Collection should run before report schedules; the default example collects at minute 50 to leave a window before the top-of-hour report.
- `targets[].dynamic_schedule`: Optional dynamic polling interval. Disabled by default. When enabled, collection no longer uses `cron`; the target uses `normal_interval_minutes`, switches to `urgent_interval_minutes` when total 5h quota is at or below `urgent_remaining_percent`, and falls back to `thresholds.remaining_percent` when the urgent threshold is omitted.
- `targets[].json_paths`: Required only by the `http_json` collector. It maps response JSON into total, available, error counts, and type details.
- `targets[].thresholds`: Available drop, 401, other error, total 5h quota, and silence window thresholds.
- `notifications.console`: Console notification settings. Enabled by default for local debugging and non-bot deployments.
- `notifications.onebot`: NapCatQQ/OneBot notification settings. It supports group messages, private messages, login checks, and group-list checks. Report images are sent as local `file://` paths first and automatically fall back to `base64://` when the gateway cannot read the local path.
- `notifications.qqbot`: Reserved official QQ Bot settings. Sending through the official QQ Bot channel is not adapted yet, so keep it disabled.

## Open Source Data Boundary

The repository should only commit source code, docs, tests, `.env.example`, and `config.example.yaml`. Real runtime data stays local and must not be committed:

- `.env`: real CPA endpoint, Management Key, and bot secrets.
- `config.yaml`: local runtime config that may contain private switches or paths.
- `data/monitor.db`: SQLite database with account status, quota snapshots, and 401 records.
- `data/reports/`: generated HTML/PNG reports that may include emails and quota data.

The database schema is created and migrated by the application at runtime, so there is no need to commit an empty database. New users can copy the example config and generate their own local data.

## Architecture Responsibilities

- `application`: loads config, orchestrates collection/alerts/reports, and wraps APScheduler scheduling policy.
- `domain`: stores snapshots, type metrics, and alert rules without depending on HTTP, SQLite, QQ, or browsers.
- `infrastructure/http`: calls target HTTP JSON APIs with `httpx`.
- `infrastructure/storage`: stores snapshots and alert silence state in SQLite.
- `infrastructure/reporting`: renders HTML reports, then uses Playwright/Chromium to capture PNG images.
- `infrastructure/notify`: sends notifications through the OneBot HTTP API. The official QQ Bot channel is not adapted yet.

## QQ Notifications

Console notification is enabled by default, so the monitor works without any bot configuration. QQ delivery currently supports only a NapCatQQ/OneBot 11 gateway. The official QQ Bot channel is not adapted yet, so do not enable `notifications.qqbot.enabled`.

If you use a NapCatQQ/OneBot 11 gateway, enable OneBot in `config.yaml` and fill the endpoint, token, and recipients:

```yaml
notifications:
  onebot:
    enabled: true
    endpoint: http://127.0.0.1:3000
    access_token: your-onebot-token
    group_ids:
      - 123456789
```

After configuration, send a test notification:

```bash
python scripts/dev.py notify --message "Account Quota Monitor notification test"
```

Account Quota Monitor uses these OneBot HTTP APIs:

- Connectivity check: `/get_login_info`
- Group list: `/get_group_list`
- Group messages: `/send_group_msg`
- Private messages: `/send_private_msg`
- Common sending: `/send_msg`

You can test the configured endpoint/token first:

```bash
python scripts/dev.py onebot-login
python scripts/dev.py onebot-groups
```

Text and images use OneBot array message segments. Report images are sent as local `file://` paths first. If the OneBot gateway runs outside the container or on another machine and cannot read that path, the notifier automatically retries with a `base64://` image. For additional NapCat/OneBot actions, add a small wrapper on top of `OneBotClient.call()`.
