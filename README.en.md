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
- `notifications.onebot.endpoint`: NapCatQQ/OneBot HTTP endpoint.
- `notifications.onebot.group_ids` or `private_user_ids`: QQ recipients.

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
uv run cpa-monitor --config config.yaml report --hours 3
uv run cpa-monitor --config config.yaml run
```

## Configuration

`config.example.yaml` is the reference template:

- `app.timezone`: Time zone for schedules and reports.
- `app.database_url`: SQLite database URL. The first version supports `sqlite:///...` only.
- `app.report_dir`: Output directory for HTML/PNG reports.
- `app.report_cron`: Cron schedule for summary reports.
- `targets[].collector`: Collector type. `cli_proxy_codex` calls CLIProxyAPI `/auth-files` and `/api-call`; omitting it keeps the original `http_json` behavior.
- `targets[].base_url`: CLIProxyAPI endpoint. The example reads it from `CPA_ENDPOINT`; put the real endpoint only in your local `.env` or runtime environment.
- `targets[].headers.Authorization`: Authentication header in the `Bearer <Management Key>` format. The example reads it from `CPA_MANAGEMENT_KEY`; put the real key only in your local `.env` or runtime environment.
- `targets[].cron`: Polling Cron for each target.
- `targets[].dynamic_schedule`: Optional dynamic polling interval. When enabled, collection no longer uses `cron`; the target uses `normal_interval_minutes`, switches to `urgent_interval_minutes` when the remaining percent is at or below `urgent_remaining_percent`, and falls back to `thresholds.remaining_percent` when the urgent threshold is omitted.
- `targets[].json_paths`: Required only by the `http_json` collector. It maps response JSON into total, available, error counts, and type details.
- `targets[].thresholds`: Available drop, 401, other error, remaining percent, and silence window thresholds.

## Architecture Responsibilities

- `application`: loads config, orchestrates collection/alerts/reports, and wraps APScheduler scheduling policy.
- `domain`: stores snapshots, type metrics, and alert rules without depending on HTTP, SQLite, QQ, or browsers.
- `infrastructure/http`: calls target HTTP JSON APIs with `httpx`.
- `infrastructure/storage`: stores snapshots and alert silence state in SQLite.
- `infrastructure/reporting`: renders HTML reports, then uses Playwright/Chromium to capture PNG images.
- `infrastructure/notify`: sends text and image messages through the OneBot HTTP API.

## QQ OneBot

Run QQ integration as a separate NapCatQQ/OneBot 11 gateway. CPA Monitor only calls the OneBot HTTP API:

- Group messages: `/send_group_msg`
- Private messages: `/send_private_msg`

Images are sent as local `file://` paths. If your OneBot gateway runs in Docker, make sure it can read the generated report path, or extend the notifier to send HTTP-accessible image URLs.
