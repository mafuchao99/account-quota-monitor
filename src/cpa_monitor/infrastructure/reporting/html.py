from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from cpa_monitor.domain.models import MetricSnapshot, TypeMetric
from cpa_monitor.domain.summary import (
    average_percent,
    effective_metrics,
    format_snapshot_summary,
    mask_display_name,
    quota_pool_metrics,
    recoverable_metrics,
    recovery_events,
)


class HtmlImageReporter:
    def __init__(self, report_dir: str | Path) -> None:
        self.report_dir = Path(report_dir)

    async def render(
        self,
        snapshots: list[MetricSnapshot],
        generated_at: datetime,
        history_snapshots: list[MetricSnapshot] | None = None,
        detail_mode: str = "all",
        unauthorized_names: set[str] | None = None,
    ) -> Path | None:
        result = await write_report(snapshots, self.report_dir, generated_at, history_snapshots, detail_mode, unauthorized_names)
        return result.image_path


class ReportResult:
    def __init__(self, html_path: Path, image_path: Path | None) -> None:
        self.html_path = html_path
        self.image_path = image_path


@dataclass(frozen=True)
class UnauthorizedAccountAnalysis:
    type_name: str
    first_success_at: datetime | None
    last_success_at: datetime | None
    unauthorized_at: datetime
    used_5h_percent: float | None
    used_7d_percent: float | None


@dataclass(frozen=True)
class RecoveryItem:
    metric: TypeMetric
    reset_at: datetime
    gain_percent: float


def render_report_html(
    snapshots: list[MetricSnapshot],
    generated_at: datetime,
    history_snapshots: list[MetricSnapshot] | None = None,
    detail_mode: str = "all",
    unauthorized_names: set[str] | None = None,
) -> str:
    if not snapshots:
        title = "Codex 额度汇总"
        return f"<!doctype html><meta charset='utf-8'><title>{title}</title><h1>{title}</h1><p>暂无数据</p>"

    start = snapshots[0].captured_at
    end = snapshots[-1].captured_at
    rows = []
    previous_available: int | None = None
    for item in snapshots:
        change = "-" if previous_available is None else str(item.available - previous_available)
        previous_available = item.available
        rows.append(
            "<tr>"
            f"<td>{item.captured_at:%H:%M}</td>"
            f"<td>{item.available}/{item.total}</td>"
            f"<td>{change}</td>"
            f"<td>{item.disabled}</td>"
            f"<td class='danger'>{item.unauthorized}</td>"
            f"<td>{item.other_errors}</td>"
            "</tr>"
        )

    if detail_mode == "latest":
        title = "Codex 小时报表"
        report_body = _hourly_report_block(snapshots)
        subtitle = f"时间：{generated_at:%Y-%m-%d %H:%M}"
    else:
        title = "Codex 额度汇总"
        latest_summary = _summary_block(snapshots[-1])
        unauthorized_analysis = _unauthorized_analysis_block(snapshots, history_snapshots or snapshots, unauthorized_names)
        trend_block = _trend_block(rows, detail_mode)
        detail_blocks = _detail_blocks(snapshots, detail_mode)
        report_body = f"""
  <div class="muted">时间段：{start:%Y-%m-%d %H:%M} - {end:%Y-%m-%d %H:%M}　查询次数：{len(snapshots)}</div>
  {latest_summary}
  {unauthorized_analysis}
  {trend_block}
  {detail_blocks}"""
        subtitle = ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{
      margin: 0;
      padding: 36px;
      background: #f5f7fb;
      color: #253047;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      font-size: 18px;
    }}
    h1 {{ margin: 0 0 4px; font-size: 34px; font-weight: 650; }}
    h2 {{ margin: 28px 0 10px; font-size: 24px; }}
    .muted {{ color: #69758b; }}
    table {{ border-collapse: collapse; background: white; min-width: 820px; }}
    th, td {{ border: 1px solid #dbe3f2; padding: 8px 18px; text-align: center; }}
    th {{ background: #e9eef7; font-weight: 650; }}
    tr:nth-child(even) td {{ background: #fafcff; }}
    .danger {{ color: #ef4444; }}
    .ok {{ color: #22c55e; }}
    .card {{ margin: 20px 0; background: white; border: 1px solid #cbd7ea; border-radius: 8px; overflow: hidden; }}
    .card-head {{ display: flex; gap: 18px; align-items: flex-start; padding: 12px 20px; background: #e8f1ff; }}
    .time {{ color: #2563eb; font-size: 28px; min-width: 92px; }}
    .quota-summary {{ display: grid; gap: 6px; line-height: 1.55; }}
    .quota-line {{ display: flex; flex-wrap: wrap; gap: 8px 18px; }}
    .quota-recovery-title {{ margin-top: 2px; color: #253047; font-weight: 650; }}
    .quota-recovery-list {{ margin: 0; padding-left: 20px; }}
    .quota-recovery-list li {{ margin: 2px 0; }}
    .card-body {{ padding: 18px 20px 26px; }}
    .hourly {{ margin-top: 22px; display: grid; gap: 18px; }}
    .hourly-section {{ padding: 18px 20px; background: white; border: 1px solid #cbd7ea; border-radius: 8px; }}
    .hourly-title {{ margin-bottom: 10px; font-weight: 700; }}
    .hourly-line {{ display: flex; flex-wrap: wrap; gap: 8px 22px; line-height: 1.6; }}
    .hourly-list {{ margin: 0; padding-left: 20px; line-height: 1.65; }}
    .footer {{ margin-top: 20px; font-size: 14px; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  {f'<div class="muted">{subtitle}</div>' if subtitle else ''}
  {report_body}
  <div class="footer muted">Generated at {generated_at:%Y-%m-%d %H:%M:%S}</div>
</body>
</html>"""


def _hourly_report_block(snapshots: list[MetricSnapshot]) -> str:
    latest = snapshots[-1]
    quota_metrics = quota_pool_metrics(latest.type_metrics)
    status_items = [
        f"可用账号：{latest.available}/{latest.total}",
        f"5h 总额度：{average_percent(metric.remaining_5h_percent for metric in quota_metrics)}",
        f"7d 总额度：{average_percent(metric.remaining_7d_percent for metric in quota_metrics)}",
    ]
    if latest.disabled:
        status_items.append(f"禁用：{latest.disabled}")
    if latest.unauthorized:
        status_items.append(f"401 异常：{latest.unauthorized}")
    if latest.other_errors:
        status_items.append(f"其他错误：{latest.other_errors}")

    recovery_items = _recovery_items(latest)
    upcoming_recoveries = [item for item in recovery_items if item.metric.available <= 0][:3]
    nearest_recovery = _nearest_recovery_text(upcoming_recoveries or recovery_items[:3])
    recovery_gain = _recovery_gain_text(upcoming_recoveries or recovery_items[:3])
    available = _available_account_block(latest)
    upcoming = _upcoming_recovery_block(upcoming_recoveries)
    exhausted = _exhausted_account_block(latest, {item.metric.type_name for item in upcoming_recoveries})
    errors = _error_account_block(latest)

    sections = [
        _hourly_section("当前状态", "<div class='hourly-line'>" + "".join(f"<span>{html.escape(item)}</span>" for item in status_items) + "</div>"),
        _hourly_section(
            "恢复情况",
            "<div class='hourly-line'>"
            f"<span>最近恢复：{html.escape(nearest_recovery)}</span>"
            f"<span>预计恢复增量：{html.escape(recovery_gain)}</span>"
            "</div>",
        ),
        available,
        upcoming,
        exhausted,
        errors,
    ]
    return "<div class='hourly'>\n" + "\n".join(section for section in sections if section) + "\n</div>"


def _hourly_section(title: str, body: str) -> str:
    return f"""
  <section class="hourly-section">
    <div class="hourly-title">【{html.escape(title)}】</div>
    {body}
  </section>"""


def _available_account_block(snapshot: MetricSnapshot) -> str:
    metrics = sorted(
        effective_metrics(snapshot.type_metrics),
        key=lambda metric: (_local_time(metric.reset_5h_at, snapshot.captured_at) is None, _local_time(metric.reset_5h_at, snapshot.captured_at) or datetime.max),
    )
    if not metrics:
        return _hourly_section("当前可用账号", "<div class='muted'>当前没有可用账号。</div>")
    items = []
    for metric in metrics:
        reset_5h_at = _local_time(metric.reset_5h_at, snapshot.captured_at)
        reset_text = "恢复时间未知" if reset_5h_at is None else f"预计 {reset_5h_at:%H:%M} 恢复"
        items.append(
            f"{mask_display_name(metric.type_name)}："
            f"5h {_compact_percent(metric.remaining_5h_percent)}，"
            f"7d {_compact_percent(metric.remaining_7d_percent)}，{reset_text}"
        )
    return _list_section("当前可用账号", items)


def _upcoming_recovery_block(recovery_items: list[RecoveryItem]) -> str:
    if not recovery_items:
        return ""
    items = [
        f"{mask_display_name(item.metric.type_name)}：{item.reset_at:%H:%M}，恢复后 +{_compact_percent(item.gain_percent)}"
        for item in recovery_items
    ]
    return _list_section("即将恢复", items)


def _exhausted_account_block(snapshot: MetricSnapshot, recovery_names: set[str]) -> str:
    items = []
    for metric in snapshot.type_metrics:
        if metric.available > 0 or metric.unauthorized > 0 or metric.other_errors > 0 or metric.type_name in recovery_names:
            continue
        reason = _exhausted_reason(metric)
        if reason:
            items.append(f"{mask_display_name(metric.type_name)}：{reason}")
    return _list_section("额度耗尽", items)


def _error_account_block(snapshot: MetricSnapshot) -> str:
    items = []
    for metric in snapshot.type_metrics:
        if metric.unauthorized > 0:
            items.append(f"{mask_display_name(metric.type_name)}：401 未授权")
        if metric.other_errors > 0:
            items.append(f"{mask_display_name(metric.type_name)}：其他错误 {metric.other_errors}")
    return _list_section("异常账号", items)


def _list_section(title: str, items: list[str]) -> str:
    if not items:
        return ""
    body = "<ul class='hourly-list'>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>"
    return _hourly_section(title, body)


def _recovery_items(snapshot: MetricSnapshot) -> list[RecoveryItem]:
    quota_metrics = quota_pool_metrics(snapshot.type_metrics)
    account_count = sum(1 for item in quota_metrics if item.remaining_5h_percent is not None)
    if account_count <= 0:
        return []
    items = []
    for metric in recoverable_metrics(quota_metrics):
        if metric.reset_5h_at is None or metric.remaining_5h_percent is None:
            continue
        reset_at = _local_time(metric.reset_5h_at, snapshot.captured_at)
        if reset_at is None:
            continue
        gain_percent = max(0.0, 100.0 - metric.remaining_5h_percent) / account_count
        items.append(RecoveryItem(metric=metric, reset_at=reset_at, gain_percent=gain_percent))
    return sorted(items, key=lambda item: item.reset_at)


def _nearest_recovery_text(recovery_items: list[RecoveryItem]) -> str:
    if not recovery_items:
        return "暂无明确恢复时间"
    first = recovery_items[0].reset_at
    last = recovery_items[-1].reset_at
    if first == last:
        return f"{first:%H:%M}"
    return f"{first:%H:%M} ~ {last:%H:%M}"


def _recovery_gain_text(recovery_items: list[RecoveryItem]) -> str:
    if not recovery_items:
        return "-"
    return f"+{_compact_percent(sum(item.gain_percent for item in recovery_items))}"


def _exhausted_reason(metric: TypeMetric) -> str:
    if metric.remaining_7d_percent is not None and metric.remaining_7d_percent <= 0:
        return "7d 已耗尽"
    if metric.remaining_5h_percent is not None and metric.remaining_5h_percent <= 0:
        return "5h 已耗尽"
    if metric.total > 0 and metric.available <= 0:
        return "不可用"
    return ""


def _compact_percent(value: float | None) -> str:
    if value is None:
        return "-"
    if value == round(value):
        return f"{value:.0f}%"
    return f"{value:.2f}%"


def _local_time(value: datetime | None, reference: datetime) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(reference.tzinfo) if reference.tzinfo else value


async def write_report(
    snapshots: list[MetricSnapshot],
    report_dir: str | Path,
    generated_at: datetime,
    history_snapshots: list[MetricSnapshot] | None = None,
    detail_mode: str = "all",
    unauthorized_names: set[str] | None = None,
) -> ReportResult:
    directory = _report_directory(report_dir, generated_at)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = generated_at.strftime("%Y%m%d-%H%M%S")
    html_path = directory / f"codex-quota-{stamp}.html"
    image_path = directory / f"codex-quota-{stamp}.png"
    html_path.write_text(
        render_report_html(snapshots, generated_at, history_snapshots, detail_mode, unauthorized_names),
        encoding="utf-8",
    )

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return ReportResult(html_path=html_path, image_path=None)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 1800}, device_scale_factor=1)
        await page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
        await page.screenshot(path=str(image_path), full_page=True)
        await browser.close()
    return ReportResult(html_path=html_path, image_path=image_path)


def _report_directory(report_dir: str | Path, generated_at: datetime) -> Path:
    return Path(report_dir) / generated_at.strftime("%Y-%m-%d")


def _trend_block(rows: list[str], detail_mode: str) -> str:
    if detail_mode != "all":
        return ""
    return f"""
  <h2>总览趋势</h2>
  <table>
    <thead><tr><th>时间</th><th>可用/总数</th><th>可用变化</th><th>禁用</th><th>401</th><th>其他错误</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>"""


def _detail_blocks(snapshots: list[MetricSnapshot], detail_mode: str) -> str:
    if detail_mode == "none":
        return ""
    if detail_mode == "latest":
        snapshots = snapshots[-1:]
    elif detail_mode != "all":
        raise ValueError("detail_mode must be one of: latest, all, none.")
    detail_blocks = "\n".join(_detail_block(item) for item in snapshots)
    return f"""
  <h2>分时明细</h2>
  {detail_blocks}"""


def _detail_block(snapshot: MetricSnapshot) -> str:
    rows = "\n".join(_type_row(item, snapshot.captured_at) for item in snapshot.type_metrics)
    if not rows:
        rows = "<tr><td>unknown</td><td>-</td><td>-</td><td>-</td><td>-</td><td class='danger'>0</td><td>0</td></tr>"
    return f"""
  <section class="card">
    <div class="card-head">
      <div class="time">{snapshot.captured_at:%H:%M}</div>
      {_html_total_quota(snapshot)}
    </div>
    <div class="card-body">
      <table>
        <thead><tr><th>类型</th><th>可用/总数</th><th>5h剩余</th><th>7d剩余</th><th>5h恢复</th><th>401</th><th>其他错误</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </section>"""


def _type_row(metric: TypeMetric, captured_at: datetime) -> str:
    remaining_5h = "-" if metric.remaining_5h_percent is None else f"{metric.remaining_5h_percent:.2f}%"
    remaining_7d = "-" if metric.remaining_7d_percent is None else f"{metric.remaining_7d_percent:.2f}%"
    reset_5h_at = metric.reset_5h_at.astimezone(captured_at.tzinfo) if metric.reset_5h_at and captured_at.tzinfo else metric.reset_5h_at
    reset_5h = "-" if reset_5h_at is None else f"{reset_5h_at:%H:%M}"
    return (
        "<tr>"
        f"<td class='ok'>{html.escape(mask_display_name(metric.type_name))}</td>"
        f"<td>{metric.available}/{metric.total}</td>"
        f"<td>{remaining_5h}</td>"
        f"<td>{remaining_7d}</td>"
        f"<td>{reset_5h}</td>"
        f"<td class='danger'>{metric.unauthorized}</td>"
        f"<td>{metric.other_errors}</td>"
        "</tr>"
    )


def _summary_block(snapshot: MetricSnapshot) -> str:
    summary = html.escape(format_snapshot_summary(snapshot)).replace("\n", "<br>")
    return f"""
  <section class="card">
    <div class="card-head"><strong>最新汇总</strong></div>
    <div class="card-body">{summary}</div>
  </section>"""


def _unauthorized_analysis_block(
    snapshots: list[MetricSnapshot],
    history_snapshots: list[MetricSnapshot],
    unauthorized_names: set[str] | None,
) -> str:
    analyses = _unauthorized_account_analyses(snapshots, history_snapshots, unauthorized_names)
    if not analyses:
        return ""
    rows = "\n".join(_unauthorized_analysis_row(item) for item in analyses)
    return f"""
  <section class="card">
    <div class="card-head"><strong>401 账号分析</strong></div>
    <div class="card-body">
      <table>
        <thead><tr><th>账号</th><th>存活时长</th><th>首次成功</th><th>最后成功</th><th>401 时间</th><th>5h 消耗</th><th>周额度消耗</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
      <div class="footer muted">基于本地已采集快照估算；401 当次通常拿不到额度，所以消耗量取最后一次成功采集值。</div>
    </div>
  </section>"""


def _unauthorized_analysis_row(item: UnauthorizedAccountAnalysis) -> str:
    return (
        "<tr>"
        f"<td class='danger'>{html.escape(mask_display_name(item.type_name))}</td>"
        f"<td>{_duration_text(item.first_success_at, item.unauthorized_at)}</td>"
        f"<td>{_time_text(item.first_success_at)}</td>"
        f"<td>{_time_text(item.last_success_at)}</td>"
        f"<td>{_time_text(item.unauthorized_at)}</td>"
        f"<td>{_used_percent_text(item.used_5h_percent)}</td>"
        f"<td>{_used_percent_text(item.used_7d_percent)}</td>"
        "</tr>"
    )


def _unauthorized_account_analyses(
    snapshots: list[MetricSnapshot],
    history_snapshots: list[MetricSnapshot],
    unauthorized_names: set[str] | None,
) -> list[UnauthorizedAccountAnalysis]:
    unauthorized_items = {}
    for snapshot in snapshots:
        for metric in snapshot.type_metrics:
            if metric.unauthorized > 0:
                unauthorized_items[metric.type_name] = (snapshot.captured_at, metric)
    if unauthorized_names is not None:
        unauthorized_items = {name: item for name, item in unauthorized_items.items() if name in unauthorized_names}

    analyses = []
    for type_name, (unauthorized_at, _metric) in sorted(unauthorized_items.items(), key=lambda item: item[1][0]):
        successful_history = [
            (snapshot.captured_at, metric)
            for snapshot in history_snapshots
            for metric in snapshot.type_metrics
            if metric.type_name == type_name
            and snapshot.captured_at < unauthorized_at
            and metric.unauthorized == 0
            and metric.other_errors == 0
            and (metric.remaining_5h_percent is not None or metric.remaining_7d_percent is not None)
        ]
        successful_history.sort(key=lambda item: item[0])
        first_success_at = successful_history[0][0] if successful_history else None
        last_success_at = successful_history[-1][0] if successful_history else None
        last_metric = successful_history[-1][1] if successful_history else None
        analyses.append(
            UnauthorizedAccountAnalysis(
                type_name=type_name,
                first_success_at=first_success_at,
                last_success_at=last_success_at,
                unauthorized_at=unauthorized_at,
                used_5h_percent=_used_percent(last_metric.remaining_5h_percent) if last_metric else None,
                used_7d_percent=_used_percent(last_metric.remaining_7d_percent) if last_metric else None,
            )
        )
    return analyses


def _html_total_quota(snapshot: MetricSnapshot) -> str:
    metrics = quota_pool_metrics(snapshot.type_metrics)
    five = average_percent(item.remaining_5h_percent for item in metrics)
    seven = average_percent(item.remaining_7d_percent for item in metrics)
    recoveries = recovery_events(snapshot.type_metrics, snapshot.captured_at)[:3]
    if recoveries:
        recovery_html = "\n".join(f"<li>{html.escape(item)}</li>" for item in recoveries)
    else:
        recovery_html = "<li>恢复时间未知</li>"
    return f"""
      <div class="quota-summary muted">
        <div class="quota-line">
          <span>总计</span>
          <span>可用 {snapshot.available}/{snapshot.total}</span>
          <span>禁用 {snapshot.disabled}</span>
          <span>401 {snapshot.unauthorized}</span>
          <span>其他错误 {snapshot.other_errors}</span>
        </div>
        <div class="quota-line">
          <span>总 5h {five}</span>
          <span>总 7d {seven}</span>
        </div>
        <div class="quota-recovery-title">最近三次 5h 恢复：</div>
        <ul class="quota-recovery-list">
          {recovery_html}
        </ul>
      </div>"""

def _used_percent(remaining_percent: float | None) -> float | None:
    return None if remaining_percent is None else max(0.0, 100.0 - remaining_percent)


def _used_percent_text(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}%"


def _time_text(value: datetime | None) -> str:
    return "-" if value is None else f"{value:%Y-%m-%d %H:%M}"


def _duration_text(start: datetime | None, end: datetime) -> str:
    if start is None:
        return "历史成功记录不足"
    minutes = max(0, round((end - start).total_seconds() / 60))
    days, remainder = divmod(minutes, 1440)
    hours, mins = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days} 天")
    if hours:
        parts.append(f"{hours} 小时")
    if mins or not parts:
        parts.append(f"{mins} 分钟")
    return "约 " + " ".join(parts)
