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

## Docker Deployment

1. Copy the example config:

```bash
cp config.example.yaml config.yaml
```

2. Edit `config.yaml`:

- `targets`: HTTP JSON endpoints, headers, Cron expressions, and JSON paths.
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

## Local Development

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/playwright install chromium
cp config.example.yaml config.yaml
.venv/bin/cpa-monitor --config config.yaml run
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\playwright install chromium
copy config.example.yaml config.yaml
.venv\Scripts\cpa-monitor --config config.yaml run
```

## Commands

```bash
cpa-monitor --config config.yaml collect-once
cpa-monitor --config config.yaml report --hours 3
cpa-monitor --config config.yaml run
```

## Configuration

`config.example.yaml` is the reference template:

- `app.timezone`: Time zone for schedules and reports.
- `app.database_url`: SQLite database URL. The first version supports `sqlite:///...` only.
- `app.report_dir`: Output directory for HTML/PNG reports.
- `app.report_cron`: Cron schedule for summary reports.
- `targets[].cron`: Polling Cron for each target.
- `targets[].json_paths`: JSON paths for total, available, error counts, and type details.
- `targets[].thresholds`: Available drop, 401, other error, remaining percent, and silence window thresholds.

## QQ OneBot

Run QQ integration as a separate NapCatQQ/OneBot 11 gateway. CPA Monitor only calls the OneBot HTTP API:

- Group messages: `/send_group_msg`
- Private messages: `/send_private_msg`

Images are sent as local `file://` paths. If your OneBot gateway runs in Docker, make sure it can read the generated report path, or extend the notifier to send HTTP-accessible image URLs.
