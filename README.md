# CPA Monitor

CPA Monitor 是一个服务器常驻的接口额度监控服务。它按 Cron 定时请求 HTTP JSON 接口，将采集结果写入 SQLite，按阈值触发告警，生成图片报表，并通过 QQ OneBot 网关推送。

English documentation: [README.en.md](README.en.md)

## 项目结构

```text
src/cpa_monitor/
  domain/          # 纯业务模型与告警规则
  application/     # 用例编排、配置、端口协议、调度表达式
  infrastructure/  # HTTP、SQLite、OneBot、HTML/PNG 报表适配器
  interfaces/      # CLI 入口与依赖装配
```

这种分层让核心业务不绑定具体外部实现：后续加飞书、企业微信、PostgreSQL、Web 管理台或新的采集方式时，优先新增 infrastructure 适配器，而不是改业务规则。

## Docker 部署

1. 复制配置：

```bash
cp config.example.yaml config.yaml
```

2. 修改 `config.yaml`：

- `targets`：填写要监控的 HTTP JSON 接口、请求头、Cron 和 JSON 路径。
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

## 本地开发

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/playwright install chromium
cp config.example.yaml config.yaml
.venv/bin/cpa-monitor --config config.yaml run
```

Windows PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\playwright install chromium
copy config.example.yaml config.yaml
.venv\Scripts\cpa-monitor --config config.yaml run
```

## 常用命令

```bash
cpa-monitor --config config.yaml collect-once
cpa-monitor --config config.yaml report --hours 3
cpa-monitor --config config.yaml run
```

## 配置说明

`config.example.yaml` 是可运行模板，核心字段如下：

- `app.timezone`：调度和报表时区。
- `app.database_url`：SQLite 路径，当前第一版只支持 `sqlite:///...`。
- `app.report_dir`：HTML/PNG 报表输出目录。
- `app.report_cron`：汇总报表发送 Cron。
- `targets[].cron`：单个接口采集 Cron。
- `targets[].json_paths`：从响应 JSON 中提取总量、可用量、错误数和类型明细。
- `targets[].thresholds`：可用量下降、401、其他错误、剩余比例和静默时间阈值。

## QQ OneBot

推荐将 QQ 侧独立部署为 NapCatQQ/OneBot 11 网关。CPA Monitor 只调用 OneBot HTTP API：

- 群消息：`/send_group_msg`
- 私聊：`/send_private_msg`

图片以 `file://` 本地路径发送。若 OneBot 网关运行在 Docker 内，需要确保它能访问 CPA Monitor 生成的报表路径，或后续扩展为 HTTP 静态文件发送。
