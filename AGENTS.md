# AGENTS.md

这个项目是为了开源准备的 CPA / Codex 额度监控工具。后续继续开发时，请优先遵守这里的约定。

## 语言和风格

- 面向用户的说明、文档、提交信息优先使用中文。
- 改动尽量小，跟随现有架构，不要为了一个小需求大范围重构。
- 只在不明显的地方加简短注释，重点包括隐私边界、风控限速、调度规则、数据库迁移。

## 隐私边界

真实运行数据和密钥绝不能提交。

- 不要提交 `.env`、`config.yaml`、`data/`、`data/monitor.db`、`data/reports/`、生成的报告 HTML/PNG。
- 不要把真实 CPA 地址、Management Key、QQBot 密钥、OpenID、邮箱、额度数据写进已跟踪文件。
- 仓库只提交模板，例如 `.env.example` 和 `config.example.yaml`。
- 数据库表结构由程序运行时自动创建和迁移，不要提交空 SQLite 数据库。

暂存前一定检查：

```bash
git status --short
git check-ignore -v .env config.yaml data/monitor.db data/reports/example.html
```

## CPA 请求安全

CPA 查询要非常保守，过于频繁或并发查询可能触发风控。

- 不要在用户没明确要求时运行全量采集。
- 优先跑测试和报表生成，因为它们只读本地数据。
- `report` 只读取 SQLite 并生成本地 HTML/PNG，不请求 CPA。
- `quota-one` 只查一个凭证，比全量采集安全。
- 全量采集必须顺序查询账号，并在账号之间随机等待；当前默认 1 到 3 秒。
- 不要重新引入并发额度查询。

会请求 CPA 的命令：

```bash
python scripts/dev.py collect
python scripts/dev.py run
python scripts/dev.py credentials
python scripts/dev.py quota-one --match gmail
```

只读本地数据的命令：

```bash
python scripts/dev.py report
python scripts/dev.py report --hours 6 --detail-mode all
python scripts/dev.py test
```

## 报表规则

- 小时报是简版：最近 1 小时，`detail_mode=latest`，不显示“总览趋势”表。
- 总结报由 `app.full_report_crons` 控制，默认每天 07:30、12:10、19:10、23:30 发送。
- 总结报只读本地数据库做数据总结，绝不能触发采集。
- `401 账号分析` 只基于已经采集过的快照估算。因为 401 当次通常拿不到额度，所以消耗量取最后一次成功采集值。
- 401 去重按“账号名 + 日期”记录；当天已经报告过的账号，后续小时报和总结报都不重复展示，第二天重新统计新的 401。

## 架构边界

- `application`：配置、业务编排、调度。
- `domain`：模型、告警规则、汇总文本。
- `infrastructure/http`：CPA / CLIProxyAPI 采集器。
- `infrastructure/storage`：SQLite 存储和轻量迁移。
- `infrastructure/reporting`：HTML 报表渲染和 Playwright 截图。
- `infrastructure/notify`：控制台、OneBot、QQBot 通知适配器。
- `interfaces`：CLI 和依赖组装。

保持这些边界清楚。比如报表渲染不能请求 CPA，采集器也不应该关心报表布局。

## 测试

改动后跑完整测试：

```bash
python scripts/dev.py test
```

如果沙箱挡住 `uv` 缓存访问，可以用同一个测试命令申请权限后重跑。测试是本地行为，不应该请求 CPA。

## Git 注意事项

- 只暂存当前任务相关文件。
- 不要暂存 `.env`、`config.yaml`、`data/`、`.DS_Store`、缓存文件或无关改动。
- 如果用户要求 commit，提交信息用简洁中文，例如：

```text
feat: 优化报表展示和401分析
```
