from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from cpa_monitor.domain.models import MetricSnapshot, TypeMetric


class HtmlImageReporter:
    def __init__(self, report_dir: str | Path) -> None:
        self.report_dir = Path(report_dir)

    async def render(self, snapshots: list[MetricSnapshot], generated_at: datetime) -> Path | None:
        result = await write_report(snapshots, self.report_dir, generated_at)
        return result.image_path


class ReportResult:
    def __init__(self, html_path: Path, image_path: Path | None) -> None:
        self.html_path = html_path
        self.image_path = image_path


def render_report_html(snapshots: list[MetricSnapshot], generated_at: datetime) -> str:
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

    detail_blocks = "\n".join(_detail_block(item) for item in snapshots)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Codex 额度汇总</title>
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
    .card-head {{ display: flex; gap: 18px; align-items: baseline; padding: 12px 20px; background: #e8f1ff; }}
    .time {{ color: #2563eb; font-size: 28px; min-width: 92px; }}
    .card-body {{ padding: 18px 20px 26px; }}
    .footer {{ margin-top: 20px; font-size: 14px; }}
  </style>
</head>
<body>
  <h1>Codex 额度汇总</h1>
  <div class="muted">时间段：{start:%Y-%m-%d %H:%M} - {end:%Y-%m-%d %H:%M}　查询次数：{len(snapshots)}</div>
  <h2>总览趋势</h2>
  <table>
    <thead><tr><th>时间</th><th>可用/总数</th><th>可用变化</th><th>禁用</th><th>401</th><th>其他错误</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  <h2>分时明细</h2>
  {detail_blocks}
  <div class="footer muted">Generated at {generated_at:%Y-%m-%d %H:%M:%S}</div>
</body>
</html>"""


async def write_report(snapshots: list[MetricSnapshot], report_dir: str | Path, generated_at: datetime) -> ReportResult:
    directory = Path(report_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = generated_at.strftime("%Y%m%d-%H%M%S")
    html_path = directory / f"codex-quota-{stamp}.html"
    image_path = directory / f"codex-quota-{stamp}.png"
    html_path.write_text(render_report_html(snapshots, generated_at), encoding="utf-8")

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


def _detail_block(snapshot: MetricSnapshot) -> str:
    rows = "\n".join(_type_row(item) for item in snapshot.type_metrics)
    if not rows:
        rows = "<tr><td>unknown</td><td>-</td><td>-</td><td>-</td><td class='danger'>0</td><td>0</td></tr>"
    return f"""
  <section class="card">
    <div class="card-head">
      <div class="time">{snapshot.captured_at:%H:%M}</div>
      <div class="muted">总计&nbsp;&nbsp;可用 {snapshot.available}/{snapshot.total}&nbsp;&nbsp; 禁用 {snapshot.disabled}&nbsp;&nbsp; 401 {snapshot.unauthorized}&nbsp;&nbsp; 其他错误 {snapshot.other_errors}</div>
    </div>
    <div class="card-body">
      <table>
        <thead><tr><th>类型</th><th>可用/总数</th><th>5h剩余</th><th>7d剩余</th><th>401</th><th>其他错误</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </section>"""


def _type_row(metric: TypeMetric) -> str:
    remaining_5h = "-" if metric.remaining_5h_percent is None else f"{metric.remaining_5h_percent:.2f}%"
    remaining_7d = "-" if metric.remaining_7d_percent is None else f"{metric.remaining_7d_percent:.2f}%"
    return (
        "<tr>"
        f"<td class='ok'>{html.escape(metric.type_name)}</td>"
        f"<td>{metric.available}/{metric.total}</td>"
        f"<td>{remaining_5h}</td>"
        f"<td>{remaining_7d}</td>"
        f"<td class='danger'>{metric.unauthorized}</td>"
        f"<td>{metric.other_errors}</td>"
        "</tr>"
    )
