# CPA Monitor

CPA Monitor is a long-running HTTP quota monitor. It polls HTTP JSON APIs on Cron schedules, stores snapshots in SQLite, evaluates alert thresholds, renders image reports, and sends notifications through a QQ OneBot gateway.

Chinese documentation: [README.md](README.md)

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

Replace the placeholders in `.env` with your CLIProxyAPI endpoint and Management Key:

```env
CPA_ENDPOINT=https://your-domain.example
CPA_MANAGEMENT_KEY=your-management-key
```

Run one collection pass:

```bash
python scripts/dev.py credentials
python scripts/dev.py collect
```

If `.env` still contains example placeholders, startup fails fast with a message pointing to `CPA_ENDPOINT` or `CPA_MANAGEMENT_KEY`.

## Docker Deployment

1. Copy the example config:

```bash
cp .env.example .env
cp config.example.yaml config.yaml
```

2. Edit `.env` and `config.yaml`:

- `CPA_ENDPOINT` in `.env`: Your CLIProxyAPI endpoint. It can be either the bare domain or the full `/v0/management` management URL.
- `CPA_MANAGEMENT_KEY` in `.env`: Your Management Key.
- `targets[].collector`: The default template uses `cli_proxy_codex`, which reads credentials and collects Codex quota through the CLIProxyAPI management APIs.
- `targets[].base_url`: The default template uses `${CPA_ENDPOINT}`. Never commit your real endpoint.
- `targets[].headers.Authorization`: The default template uses `Bearer ${CPA_MANAGEMENT_KEY}`. The app automatically loads a sibling `.env` file and also supports system environment variables. Never commit the real key.
- `targets[].delay_min_seconds` / `delay_max_seconds`: Full collection queries credentials sequentially and waits a random delay between credentials. The default is 1 to 3 seconds to avoid concurrent quota checks.
- `notifications.console.enabled`: Enabled by default. Alerts and report notices are printed to the console.
- `notifications.qqbot.enabled`: Set it to `true` for official QQ Bot private notifications, then fill `QQBOT_APP_ID`, `QQBOT_APP_SECRET`, and `QQBOT_OPENID` in `.env`.
- `notifications.onebot.enabled`: Set it to `true` only when using NapCatQQ/OneBot, then fill endpoint and recipients.

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
python scripts/dev.py notify --message "CPA Monitor notification test"
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
uv run cpa-monitor --config config.yaml notify-test --message "CPA Monitor notification test"
uv run cpa-monitor --config config.yaml report
uv run cpa-monitor --config config.yaml report --hours 6 --detail-mode all
uv run cpa-monitor --config config.yaml run
```

## Configuration

`config.example.yaml` is the reference template:

- `app.timezone`: Time zone for schedules and reports.
- `app.database_url`: SQLite database URL. The first version supports `sqlite:///...` only.
- `app.report_dir`: Output directory for HTML/PNG reports.
- `app.report_cron` / `app.report_hours` / `app.report_detail_mode`: hourly report schedule, window, and detail mode. Defaults to a short hourly report with only the latest detail block.
- `app.full_report_enabled` / `app.full_report_crons` / `app.full_report_hours` / `app.full_report_detail_mode`: full report toggle, schedules, window, and detail mode. Disabled by default; when enabled, it sends the last 6-hour full detail report at 07:30, 12:10, 19:10, and 23:30 without triggering collection.
- 401 account analysis is deduplicated by account name and date. An account reported once today will not be repeated in later hourly/full reports until the next day.
- `targets[].collector`: Collector type. `cli_proxy_codex` calls CLIProxyAPI `/auth-files` and `/api-call`; omitting it keeps the original `http_json` behavior.
- `targets[].base_url`: CLIProxyAPI endpoint. The example reads it from `CPA_ENDPOINT`; put the real endpoint only in your local `.env` or runtime environment.
- `targets[].headers.Authorization`: Authentication header in the `Bearer <Management Key>` format. The example reads it from `CPA_MANAGEMENT_KEY`; put the real key only in your local `.env` or runtime environment.
- `targets[].delay_min_seconds` / `delay_max_seconds`: Random delay for full quota collection. It affects `collect` and scheduled collection only; `quota-one` does not wait.
- `targets[].cron`: Polling Cron for each target. The default collects at minute 50 every hour, leaving a collection window before the top-of-hour report.
- `targets[].dynamic_schedule`: Optional dynamic polling interval. Disabled by default. When enabled, collection no longer uses `cron`; the target uses `normal_interval_minutes`, switches to `urgent_interval_minutes` when the remaining percent is at or below `urgent_remaining_percent`, and falls back to `thresholds.remaining_percent` when the urgent threshold is omitted.
- `targets[].json_paths`: Required only by the `http_json` collector. It maps response JSON into total, available, error counts, and type details.
- `targets[].thresholds`: Available drop, 401, other error, remaining percent, and silence window thresholds.
- `notifications.console`: Console notification settings. Enabled by default for local debugging and non-bot deployments.
- `notifications.qqbot`: Official QQ Bot notification settings. The first version sends text-only private messages to one OpenID, with AppID, AppSecret, and OpenID read from `.env`.

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
- `infrastructure/notify`: sends notifications through the official QQ Bot API or OneBot HTTP API.

## QQ Notifications

Console notification is enabled by default, so the monitor works without any bot configuration. To additionally use official QQ Bot private notification, put `AppID`, `AppSecret`, and your `OpenID` in local `.env`:

```env
QQBOT_APP_ID=your-qqbot-app-id
QQBOT_APP_SECRET=your-qqbot-app-secret
QQBOT_OPENID=your-qq-openid
```

Then enable it in `config.yaml`:

```yaml
notifications:
  qqbot:
    enabled: true
```

The QQBot channel currently supports text alerts and report-ready notices. Image sending and group notifications can be added later.

After configuration, send a test private message:

```bash
python scripts/dev.py notify --message "CPA Monitor notification test"
```

If you use a NapCatQQ/OneBot 11 gateway, CPA Monitor still supports OneBot HTTP APIs:

- Group messages: `/send_group_msg`
- Private messages: `/send_private_msg`

Images are sent as local `file://` paths. If your OneBot gateway runs in Docker, make sure it can read the generated report path, or extend the notifier to send HTTP-accessible image URLs.
