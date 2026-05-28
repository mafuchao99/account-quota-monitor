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
- `notifications.onebot.endpoint`：填写 NapCatQQ/OneBot HTTP 地址。
- `notifications.onebot.group_ids` 或 `private_user_ids`：填写接收通知的群号或 QQ 号。

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

常用开发命令：

```bash
python scripts/dev.py collect
python scripts/dev.py report
python scripts/dev.py test
```

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

```bash
uv run cpa-monitor --config config.yaml collect-once
uv run cpa-monitor --config config.yaml report --hours 3
uv run cpa-monitor --config config.yaml run
```

## 配置说明

`config.example.yaml` 是可运行模板，核心字段如下：

- `app.timezone`：调度和报表时区。
- `app.database_url`：SQLite 路径，当前第一版只支持 `sqlite:///...`。
- `app.report_dir`：HTML/PNG 报表输出目录。
- `app.report_cron`：汇总报表发送 Cron。
- `targets[].collector`：采集器类型。`cli_proxy_codex` 会调用 CLIProxyAPI 的 `/auth-files` 和 `/api-call`；不配置时兼容原来的 `http_json`。
- `targets[].base_url`：CLIProxyAPI 地址。示例使用环境变量 `CPA_ENDPOINT`，真实地址写到本地 `.env` 或运行环境变量。
- `targets[].headers.Authorization`：请求鉴权头，格式为 `Bearer <Management Key>`；示例使用环境变量 `CPA_MANAGEMENT_KEY`，真实 Key 写到本地 `.env` 或运行环境变量。
- `targets[].cron`：单个接口采集 Cron。
- `targets[].dynamic_schedule`：可选动态采集频率；开启后采集不再使用 `cron`，正常按 `normal_interval_minutes`，剩余比例低于 `urgent_remaining_percent` 时按 `urgent_interval_minutes`，未配置紧张阈值时沿用 `thresholds.remaining_percent`。
- `targets[].json_paths`：仅 `http_json` 采集器需要，用于从响应 JSON 中提取总量、可用量、错误数和类型明细。
- `targets[].thresholds`：可用量下降、401、其他错误、剩余比例和静默时间阈值。

## 架构职责

- `application`：读取配置、编排采集/告警/报表用例，并封装 APScheduler 调度策略。
- `domain`：保存监控快照、类型指标和告警规则，不依赖 HTTP、SQLite、QQ 或浏览器。
- `infrastructure/http`：使用 `httpx` 请求目标 HTTP JSON 接口。
- `infrastructure/storage`：使用 SQLite 保存历史快照和告警静默状态。
- `infrastructure/reporting`：先生成 HTML 报表，再用 Playwright/Chromium 截图为 PNG。
- `infrastructure/notify`：调用 OneBot HTTP API 推送文字和图片。

## QQ OneBot

推荐将 QQ 侧独立部署为 NapCatQQ/OneBot 11 网关。CPA Monitor 只调用 OneBot HTTP API：

- 群消息：`/send_group_msg`
- 私聊：`/send_private_msg`

图片以 `file://` 本地路径发送。若 OneBot 网关运行在 Docker 内，需要确保它能访问 CPA Monitor 生成的报表路径，或后续扩展为 HTTP 静态文件发送。
