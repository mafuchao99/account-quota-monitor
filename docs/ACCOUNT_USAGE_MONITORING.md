# 账号余量监控接口梳理

本文只基于代码静态分析，没有请求线上接口。目标是给外部监控项目（例如 `/Users/huaxi/www/personal/cpa-codex-monitor`）实现定时查询账号余量和通知。

## 结论

- 管理端接口统一在 `/api/v1/admin` 下，需要管理员鉴权。
- 外部监控不需要模拟登录，推荐创建 Admin API Key 后通过请求头 `x-api-key: <admin-api-key>` 调用。
- `GET /api/v1/admin/accounts/:id/usage` 默认是 `source=active`，可能主动请求上游账号余量接口或做探测，不适合作为高频无风险监控。
- 如果只想避免触发上游风控，应优先使用：
  - `GET /api/v1/admin/accounts/:id/usage?source=passive`：只适用于 Anthropic OAuth / SetupToken，读取本地被动采样。
  - `GET /api/v1/admin/accounts`：读取账号列表中的本地快照字段，例如 OpenAI/Codex 的 `extra.codex_*`。
  - `GET /api/v1/admin/accounts/:id/today-stats` 或 `POST /api/v1/admin/accounts/today-stats/batch`：只查本地用量日志，不查上游余量。

## 鉴权方式

Admin 鉴权中间件支持两种方式：

- `x-api-key: <admin-api-key>`
- `Authorization: Bearer <jwt-token>`，且 JWT 对应用户必须是管理员

外部监控建议用 Admin API Key。相关接口：

- `GET /api/v1/admin/settings/admin-api-key`：查看是否已配置，只返回脱敏 key。
- `POST /api/v1/admin/settings/admin-api-key/regenerate`：生成或重新生成 key，完整 key 只在生成时返回一次。
- `DELETE /api/v1/admin/settings/admin-api-key`：删除 key。

Admin API Key 前缀是 `admin-`，保存在 settings 表的 `admin_api_key` 配置项中。验证时后端会把请求上下文设置为第一个管理员用户。

## 账号余量相关接口

### `GET /api/v1/admin/accounts/:id/usage`

代码入口：

- 路由：`backend/internal/server/routes/admin.go`
- Handler：`backend/internal/handler/admin/account_handler.go`
- Service：`backend/internal/service/account_usage_service.go`

查询参数：

- `source=active|passive`，默认 `active`
- `force=true`，只在 active 路径里有意义，会强制部分探测

响应类型大致是：

```json
{
  "source": "passive",
  "updated_at": "2026-06-09T00:00:00Z",
  "five_hour": {
    "utilization": 42.5,
    "resets_at": "2026-06-09T05:00:00Z",
    "remaining_seconds": 1234,
    "window_stats": {}
  },
  "seven_day": {
    "utilization": 88.0,
    "resets_at": "2026-06-15T00:00:00Z",
    "remaining_seconds": 123456
  },
  "error_code": "",
  "error": ""
}
```

`utilization` 是已用百分比，剩余额度可以按 `100 - utilization` 计算。通知阈值建议按已用百分比判断，例如 `>= 90` 或 `>= 95`。

### active 路径风险

不要在定时监控里裸调 `/usage`，因为默认 `source=active`。

active 分支行为：

- OpenAI OAuth：优先读 `account.extra.codex_*` 快照，但如果快照缺失、过期、账号限流，可能向 `chatgpt.com` 发起 Codex 探测请求。
- Gemini：主要基于本地配额配置和 usage_logs 统计，不直接查 Google 上游余量。
- Antigravity：会通过 `AntigravityQuotaFetcher.FetchQuota` 主动查询上游。
- Anthropic OAuth：会请求 Anthropic usage API，并有 3 分钟成功缓存、1 分钟错误缓存。
- Anthropic SetupToken：没有 profile scope，使用本地 session window 推算。
- API Key 类型：通常不支持 usage 查询。

因此，如果监控目标是“低风控、只读本地状态”，不要用默认 active。

### passive 路径

`GET /api/v1/admin/accounts/:id/usage?source=passive`

特点：

- 只读取账号本地字段，不调用外部 API。
- 仅支持 Anthropic OAuth / SetupToken。
- 5 小时窗口来自 `session_window_*` 和 `extra.session_window_utilization`。
- 7 天窗口来自 `extra.passive_usage_7d_utilization`、`extra.passive_usage_7d_reset`。
- 采样时间来自 `extra.passive_usage_sampled_at`。

适合监控 Anthropic OAuth / SetupToken 账号，但要接受数据可能不是实时上游值。

### 账号列表快照

`GET /api/v1/admin/accounts`

这个接口返回账号基础信息和 `extra`，适合一次拉取多账号做监控。它会查并发数、部分 Redis 计数、本地 usage_logs 聚合，但不会像 `/usage?source=active` 那样为每个账号主动查上游余量。

OpenAI/Codex 余量快照字段在 `account.extra`：

- `codex_5h_used_percent`
- `codex_5h_reset_after_seconds`
- `codex_5h_reset_at`
- `codex_5h_window_minutes`
- `codex_7d_used_percent`
- `codex_7d_reset_after_seconds`
- `codex_7d_reset_at`
- `codex_7d_window_minutes`
- `codex_usage_updated_at`

这些字段来自实际网关请求或探测响应头中的 Codex rate-limit header。字段是已用百分比，不是剩余百分比。

账号列表也带 Anthropic session window 字段：

- `session_window_start`
- `session_window_end`
- `session_window_status`
- `extra.session_window_utilization`
- `extra.passive_usage_7d_utilization`
- `extra.passive_usage_7d_reset`
- `extra.passive_usage_sampled_at`

如果新监控项目想一次处理多个平台，建议先拉账号列表，然后按平台解析本地快照字段。

## Codex-only 快照监控流程

如果当前只监控 OpenAI/Codex 账号，`GET /api/v1/admin/accounts` 这一类账号列表接口基本就够用。它不会为了刷新 Codex 余量而逐账号主动探测上游，只读取 sub2api 本地保存的账号信息和 `extra.codex_*` 快照字段。

推荐请求：

```http
GET /api/v1/admin/accounts?page=1&page_size=100&platform=openai
x-api-key: <admin-api-key>
```

如果账号数量可能超过 100，需要按分页拉完整列表：

```text
page=1&page_size=100
page=2&page_size=100
...
直到响应里的 items 数量为空，或已经达到 total。
```

后续实现可以按这个流程写：

1. 定时触发任务，例如每 5 分钟或每 10 分钟一次。
2. 调用 `GET /api/v1/admin/accounts?page=1&page_size=100&platform=openai`。
3. 如果返回分页数据，遍历所有页，拿到完整 OpenAI 账号列表。
4. 遍历账号，只处理 `platform=openai` 的账号。
5. 优先处理 `type=oauth` 且启用了 Codex/WebSocket v2 能力的账号；如果不想判断能力，也可以先判断是否存在 `extra.codex_5h_used_percent` 或 `extra.codex_7d_used_percent`。
6. 跳过明显不可用的账号，例如 `status=error` 可单独发账号异常通知，`schedulable=false` 可按你的策略决定是否忽略。
7. 从 `account.extra` 读取 Codex 快照字段。
8. 检查 `extra.codex_usage_updated_at` 是否存在、是否过旧。
9. 根据 `codex_5h_used_percent` 和 `codex_7d_used_percent` 判断是否需要通知。
10. 做通知去重，避免每次定时任务都重复推送同一条预警。

需要读取的核心字段：

```text
account.id
account.name
account.platform
account.type
account.status
account.schedulable
account.error_message
account.rate_limited_at
account.rate_limit_reset_at
account.temp_unschedulable_until
account.overload_until

account.extra.codex_5h_used_percent
account.extra.codex_5h_reset_at
account.extra.codex_7d_used_percent
account.extra.codex_7d_reset_at
account.extra.codex_usage_updated_at
```

字段含义：

```text
codex_5h_used_percent     Codex 5 小时窗口已用百分比
codex_5h_reset_at         Codex 5 小时窗口预计重置时间
codex_7d_used_percent     Codex 7 天窗口已用百分比
codex_7d_reset_at         Codex 7 天窗口预计重置时间
codex_usage_updated_at    这份 Codex 余量快照的更新时间
```

注意：`used_percent` 是已用百分比，不是剩余百分比。剩余百分比可以这样计算：

```text
remaining_percent = 100 - used_percent
```

示例判断：

```text
5h used >= 90 且 < 98：5 小时窗口预警
5h used >= 98：5 小时窗口严重
7d used >= 90 且 < 98：7 天窗口预警
7d used >= 98：7 天窗口严重
```

快照新鲜度建议：

```text
codex_usage_updated_at 不存在：
  不当作实时余量，标记为“无 Codex 快照”

距当前时间 <= 30 分钟：
  快照较新，可以正常按阈值通知

距当前时间 30 分钟 ~ 2 小时：
  可以通知，但消息里标注“快照可能偏旧”

距当前时间 > 2 小时：
  不建议发满额/余量不足告警，只发“Codex 快照过旧”或降低通知优先级
```

`codex_usage_updated_at` 会在用户真实使用 Codex/OpenAI 路径，并且上游响应带 Codex rate-limit header 时更新。也就是说，账号有人持续使用时，快照通常会跟着刷新；账号长时间没人用时，快照自然会变旧。监控系统需要把“余量高”和“快照旧”分开判断。

通知内容建议包含：

```text
账号名称 / ID
5h 已用百分比和剩余百分比
5h 重置时间
7d 已用百分比和剩余百分比
7d 重置时间
快照更新时间
账号状态 status / error_message
```

通知去重建议：

```text
去重 key = account_id + window + severity + reset_at
```

例如同一个账号的 5h 窗口已经达到严重阈值，只要 `codex_5h_reset_at` 没变，就不要每 5 分钟重复发同一条严重告警。等窗口重置时间变化，或严重程度从 warning 升级到 critical，再发新通知。

伪代码：

```ts
for (const account of accounts) {
  if (account.platform !== 'openai') continue

  const extra = account.extra ?? {}
  const updatedAt = parseTime(extra.codex_usage_updated_at)
  const stale = !updatedAt || now - updatedAt > 2 hours
  const maybeStale = updatedAt && now - updatedAt > 30 minutes

  const fiveHourUsed = numberOrNull(extra.codex_5h_used_percent)
  const sevenDayUsed = numberOrNull(extra.codex_7d_used_percent)

  if (!updatedAt || (fiveHourUsed == null && sevenDayUsed == null)) {
    notifySnapshotMissingOrSkip(account)
    continue
  }

  if (stale) {
    notifySnapshotStale(account, updatedAt)
    continue
  }

  checkWindow({
    account,
    window: '5h',
    usedPercent: fiveHourUsed,
    resetAt: extra.codex_5h_reset_at,
    snapshotMaybeStale: maybeStale,
  })

  checkWindow({
    account,
    window: '7d',
    usedPercent: sevenDayUsed,
    resetAt: extra.codex_7d_reset_at,
    snapshotMaybeStale: maybeStale,
  })
}
```

### 今日用量统计

`GET /api/v1/admin/accounts/:id/today-stats`

`POST /api/v1/admin/accounts/today-stats/batch`

批量请求体：

```json
{
  "account_ids": [18, 19, 20]
}
```

这两个接口只查本地 usage_logs，用来监控今天已经消耗的 tokens/cost/request 数，不代表上游账号剩余额度。批量接口有 30 秒进程内缓存和 ETag。

## 推荐监控方案

### 推荐默认策略

1. 使用 Admin API Key：请求头带 `x-api-key`。
2. 定时拉 `GET /api/v1/admin/accounts?page=1&page_size=...`。
3. 对 OpenAI/Codex 账号读取 `extra.codex_5h_used_percent`、`extra.codex_7d_used_percent`。
4. 对 Anthropic OAuth / SetupToken 账号优先调用 `/usage?source=passive`，或者直接解析列表中的 `session_window_*` / `passive_usage_*` 字段。
5. 对 Gemini 账号，如果只关心本地消耗，使用 `/usage` active 风险较低；如果严格避免任何非本地行为，先只用 today-stats 和账号列表。
6. 对 Antigravity 账号，不建议定时调 `/usage` active；可先只看账号状态、错误和本地日志统计。

### 通知规则建议

- 5 小时窗口：`used_percent >= 90` 预警，`>= 98` 严重。
- 7 天窗口：`used_percent >= 90` 预警，`>= 98` 严重。
- 如果 `resets_at` 已过期但 used 仍高，标记为“快照可能过期”，避免误报成真实满额。
- 如果 `updated_at` 或 `codex_usage_updated_at` 太旧，例如超过 1 小时，通知里标注“数据较旧”。
- 对 `status=error`、`rate_limit_reset_at`、`temp_unschedulable_until`、`overload_until` 单独做状态通知。

### 外部项目调用示例

不要直接复制真实 key 到代码仓库，建议用环境变量：

```bash
SUB2API_BASE_URL=https://sub.juaihub.cn/api/v1
SUB2API_ADMIN_KEY=admin-xxxxxxxx
```

OpenAI/Codex 本地快照优先：

```http
GET /api/v1/admin/accounts?page=1&page_size=100&platform=openai
x-api-key: <admin-api-key>
```

Anthropic 被动余量：

```http
GET /api/v1/admin/accounts/18/usage?source=passive
x-api-key: <admin-api-key>
```

本地今日统计批量：

```http
POST /api/v1/admin/accounts/today-stats/batch
x-api-key: <admin-api-key>
content-type: application/json

{"account_ids":[18]}
```

## 不建议

- 不建议监控任务定时请求 `GET /api/v1/admin/accounts/:id/usage` 且不带 `source=passive`。
- 不建议使用 `force=true`，它会绕过部分缓存/探测保护。
- 不建议用管理员账号密码登录后长期保存 JWT；Admin API Key 更适合外部集成。
- 不建议高频逐账号调用 active usage。若必须 active，至少要做低频、错峰、缓存和失败退避。
