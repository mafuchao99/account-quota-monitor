# CPA Monitor

CPA Monitor 是一个服务器常驻的接口额度监控服务。它按 Cron 定时请求 HTTP JSON 接口，将采集结果写入 SQLite，按阈值触发告警，生成图片报表，并通过 QQ OneBot 网关推送。

English documentation: [README.en.md](README.en.md)

开发维护说明：[CLIProxyAPI Codex 额度采集器开发说明](docs/cli-proxy-codex-collector_CN.md)

## 项目结构

```text
src/cpa_monitor/
  domain/          # 纯业务模型与告警规则
  application/     # 用例编排、配置、端口协议、调度表达式
  infrastructure/  # HTTP、SQLite、OneBot、HTML/PNG 报表适配器
  interfaces/      # CLI 入口与依赖装配
```

这种分层让核心业务不绑定具体外部实现：后续加飞书、企业微信、PostgreSQL、Web 管理台或新的采集方式时，优先新增 infrastructure 适配器，而不是改业务规则。

## 3 分钟快速启动

```bash
python scripts/dev.py setup
```

把 `.env` 里的占位值换成你的 CLIProxyAPI 地址和 Management Key：

```env
CPA_ENDPOINT=https://your-domain.example
CPA_MANAGEMENT_KEY=your-management-key
```

运行一次采集验证：

```bash
python scripts/dev.py credentials
python scripts/dev.py collect
```

如果 `.env` 还保持示例占位，程序会在启动时直接提示需要修改 `CPA_ENDPOINT` 或 `CPA_MANAGEMENT_KEY`。

## Docker 部署

1. 复制配置：

```bash
cp .env.example .env
cp config.example.yaml config.yaml
```

2. 修改 `.env` 和 `config.yaml`：

- `.env` 里的 `CPA_ENDPOINT`：填写你的 CLIProxyAPI 地址，可以是裸域名，也可以是带 `/v0/management` 的管理端地址。
- `.env` 里的 `CPA_MANAGEMENT_KEY`：填写你的 Management Key。
- `targets[].collector`：默认使用 `cli_proxy_codex`，会按 CLIProxyAPI 管理端文档自动读取凭证并查询 Codex 额度。
- `targets[].base_url`：默认使用 `${CPA_ENDPOINT}`，不要把真实接口地址提交到仓库。
- `targets[].headers.Authorization`：默认使用 `Bearer ${CPA_MANAGEMENT_KEY}`，程序会自动读取同目录 `.env`，也支持系统环境变量。不要把真实 Key 提交到仓库。
- `targets[].delay_min_seconds` / `delay_max_seconds`：全量采集时每个凭证顺序查询，两个凭证之间随机等待，默认 1 到 3 秒，避免并发触发风控。
- `notifications.console.enabled`：默认开启，告警和报表提醒会直接打印到控制台。
- `notifications.qqbot.enabled`：如果使用 QQ 官方机器人私聊通知，改为 `true`，并在 `.env` 填写 `QQBOT_APP_ID`、`QQBOT_APP_SECRET`、`QQBOT_OPENID`。
- `notifications.onebot.enabled`：如果使用 NapCatQQ/OneBot，改为 `true`，再填写 endpoint 和接收人。

3. 启动：

```bash
docker compose up -d --build
```

4. 查看日志：

```bash
docker compose logs -f cpa-monitor
```

默认容器会把配置挂载到 `/app/config/config.yaml`，数据和报表写入宿主机 `./data`。
镜像内部使用 `uv` 按 `uv.lock` 安装依赖，保证本地和容器里的依赖解析一致。

## 本地开发

首次初始化：

```bash
python scripts/dev.py setup
```

这个命令内部会执行 `uv sync`、`uv run playwright install chromium`，并在缺少 `config.yaml` 或 `.env` 时从示例配置复制一份。

日常运行：

```bash
python scripts/dev.py run
```

更多本地命令见下方“常用命令”。

macOS/Linux 如果安装了 `make`，也可以使用快捷命令：

```bash
make setup
make run
```

Windows PowerShell 同样使用 Python 脚本：

```powershell
python scripts/dev.py setup
python scripts/dev.py run
```

## 常用命令

本地开发优先使用 `scripts/dev.py`，它会自动带上 `--config config.yaml`：

| 命令 | 用途 | 是否请求 CPA |
| --- | --- | --- |
| `python scripts/dev.py setup` | 安装依赖、安装 Playwright Chromium，并在缺少本地配置时复制示例文件。 | 否 |
| `python scripts/dev.py run` | 启动常驻监控调度；会按配置定时采集、生成小时报、发送通知。 | 是，按采集调度请求 |
| `python scripts/dev.py collect` | 立即执行一次全量采集，按凭证顺序查询额度并写入 SQLite。 | 是 |
| `python scripts/dev.py credentials` | 读取 CLIProxyAPI 管理端凭证列表，查看 active、disabled、unavailable、auth_index 等状态。 | 是，只请求管理端凭证列表 |
| `python scripts/dev.py quota-one --match gmail` | 只查询一个匹配的凭证，适合排查单个账号额度或 401。 | 是，只查一个凭证 |
| `python scripts/dev.py report` | 生成并发送小时报；只读取本地 SQLite 最近 `app.report_hours` 的快照。 | 否 |
| `python scripts/dev.py report --hours 6 --detail-mode all` | 手动查看 6 小时额度汇总/完整报；不受 `full_report_enabled` 影响。 | 否 |
| `python scripts/dev.py notify --message "CPA Monitor 通知测试"` | 发送一条测试通知，用于验证控制台、OneBot 或 QQBot 配置。 | 否 |
| `python scripts/dev.py test` | 运行测试。 | 否 |
| `python scripts/dev.py clean` | 删除本地测试和构建缓存。 | 否 |

也可以直接调用 CLI，适合部署脚本或临时调试：

```bash
uv run cpa-monitor --config config.yaml run
uv run cpa-monitor --config config.yaml collect-once
uv run cpa-monitor --config config.yaml credentials
uv run cpa-monitor --config config.yaml quota-one --match gmail
uv run cpa-monitor --config config.yaml report
uv run cpa-monitor --config config.yaml report --hours 6 --detail-mode all
uv run cpa-monitor --config config.yaml notify-test --message "CPA Monitor 通知测试"
```

注意：`report` 只读本地数据库并生成报表，不会请求 CPA；`collect`、`run`、`credentials`、`quota-one` 会访问 CPA/CLIProxyAPI。

## 配置说明

`config.example.yaml` 是可运行模板，核心字段如下：

- `app.timezone`：调度和报表时区。
- `app.database_url`：SQLite 路径，当前第一版只支持 `sqlite:///...`。
- `app.report_dir`：HTML/PNG 报表输出目录。
- `app.report_cron` / `app.report_crons` / `app.report_hours` / `app.report_detail_mode`：小时报 Cron、统计窗口和分时明细模式；`report_crons` 支持多个定制发送时间，旧字段 `report_cron` 仍兼容。默认每小时发送最近 1 小时，只展示最新一次明细。
- `app.full_report_enabled` / `app.full_report_crons` / `app.full_report_hours` / `app.full_report_detail_mode`：完整报开关、Cron 列表、统计窗口和分时明细模式；默认关闭，开启后按 07:30、12:10、19:10、23:30 发送最近 6 小时完整明细，只做数据总结，不触发采集。
- 401 账号分析会按邮箱和日期去重；同一天已报告过的 401 账号，后续小时报/完整报不再重复展示，第二天重新统计新的 401。
- `targets[].collector`：采集器类型。`cli_proxy_codex` 会调用 CLIProxyAPI 的 `/auth-files` 和 `/api-call`；不配置时兼容原来的 `http_json`。
- `targets[].base_url`：CLIProxyAPI 地址。示例使用环境变量 `CPA_ENDPOINT`，真实地址写到本地 `.env` 或运行环境变量。
- `targets[].headers.Authorization`：请求鉴权头，格式为 `Bearer <Management Key>`；示例使用环境变量 `CPA_MANAGEMENT_KEY`，真实 Key 写到本地 `.env` 或运行环境变量。
- `targets[].delay_min_seconds` / `delay_max_seconds`：全量额度采集的随机间隔。只影响 `collect` / 常驻采集，`quota-one` 单查不会等待。
- `targets[].cron` / `targets[].crons`：单个接口采集 Cron；简单场景用 `cron`，复杂时段用 `crons` 列表。建议采集时间早于报告时间，默认示例在第 50 分钟采集，给整点小时报留出采集窗口。
- `targets[].dynamic_schedule`：可选动态采集频率，默认关闭；开启后采集不再使用 `cron`，正常按 `normal_interval_minutes`，剩余比例低于 `urgent_remaining_percent` 时按 `urgent_interval_minutes`，未配置紧张阈值时沿用 `thresholds.remaining_percent`。
- `targets[].json_paths`：仅 `http_json` 采集器需要，用于从响应 JSON 中提取总量、可用量、错误数和类型明细。
- `targets[].thresholds`：可用量下降、401、其他错误、剩余比例和静默时间阈值。
- `notifications.console`：控制台通知配置，默认开启，适合本地调试和不接机器人时使用。
- `notifications.qqbot`：QQ 官方机器人通知配置。当前先支持给单个 OpenID 发送文本私聊，AppID、AppSecret、OpenID 都从 `.env` 读取。

## 开源数据边界

仓库只提交代码、文档、测试、`.env.example` 和 `config.example.yaml`。真实运行数据全部保留在本地，不应提交：

- `.env`：真实 CPA 地址、Management Key、机器人密钥。
- `config.yaml`：本机运行配置，可能包含私有开关或路径。
- `data/monitor.db`：SQLite 数据库，包含账号状态、额度快照、401 记录。
- `data/reports/`：生成的 HTML/PNG 报告，可能包含邮箱和额度数据。

数据库表结构由程序启动时自动创建和迁移，不需要提交空数据库；其他人拉取项目后复制示例配置并运行即可生成自己的本地数据。

## 架构职责

- `application`：读取配置、编排采集/告警/报表用例，并封装 APScheduler 调度策略。
- `domain`：保存监控快照、类型指标和告警规则，不依赖 HTTP、SQLite、QQ 或浏览器。
- `infrastructure/http`：使用 `httpx` 请求目标 HTTP JSON 接口。
- `infrastructure/storage`：使用 SQLite 保存历史快照和告警静默状态。
- `infrastructure/reporting`：先生成 HTML 报表，再用 Playwright/Chromium 截图为 PNG。
- `infrastructure/notify`：调用 QQ 官方 Bot API 或 OneBot HTTP API 推送通知。

## QQ 通知

项目默认开启控制台通知，不配置机器人也可以看到监控输出。如果要额外使用 QQ 官方机器人私聊通知，创建机器人后，把 `AppID`、`AppSecret` 和你的 `OpenID` 写入本地 `.env`：

```env
QQBOT_APP_ID=your-qqbot-app-id
QQBOT_APP_SECRET=your-qqbot-app-secret
QQBOT_OPENID=your-qq-openid
```

然后在 `config.yaml` 中启用：

```yaml
notifications:
  qqbot:
    enabled: true
```

当前 QQBot 通道先支持文本告警和报表生成提醒。图片直发、群通知可以后续扩展。

配置完成后可以先发一条测试私聊：

```bash
python scripts/dev.py notify --message "CPA Monitor 通知测试"
```

如果你使用 NapCatQQ/OneBot 11 网关，CPA Monitor 也保留 OneBot HTTP API：

- 连通性测试：`/get_login_info`
- 获取群列表：`/get_group_list`
- 群消息：`/send_group_msg`
- 私聊：`/send_private_msg`
- 通用发送：`/send_msg`

可以先用配置里的 endpoint/token 测 NapCat 是否可访问：

```bash
python scripts/dev.py onebot-login
python scripts/dev.py onebot-groups
```

文本和图片都使用 OneBot Array 消息段格式；报表图片以 `file://` 本地路径发送。若 OneBot 网关运行在 Docker 内，需要确保它能访问 CPA Monitor 生成的报表路径，或后续扩展为 HTTP 静态文件发送。后续要接入更多 NapCat/OneBot 动作时，优先在 `OneBotClient.call()` 上薄封装一个方法。
