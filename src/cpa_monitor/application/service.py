from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from cpa_monitor.domain.alerts import evaluate_alerts
from cpa_monitor.domain.models import MetricSnapshot
from cpa_monitor.domain.summary import format_snapshot_summary

from .config import MonitorConfig, TargetConfig
from .ports import Notifier, ReportRenderer, SnapshotCollector, SnapshotStore
from .schedule import MonitorScheduler

logger = logging.getLogger(__name__)


class MonitorService:
    def __init__(
        self,
        config: MonitorConfig,
        collector: SnapshotCollector,
        store: SnapshotStore,
        notifier: Notifier,
        reporter: ReportRenderer,
    ) -> None:
        self.config = config
        self.collector = collector
        self.store = store
        self.notifier = notifier
        self.reporter = reporter
        self.timezone = ZoneInfo(config.app.timezone)

    async def collect_once(self) -> list[MetricSnapshot]:
        snapshots = []
        for target in self.config.targets:
            snapshots.append(await self.collect_target(target))
        for snapshot in snapshots:
            await self.notifier.send_text(format_snapshot_summary(snapshot))
        return snapshots

    async def collect_target(self, target: TargetConfig) -> MetricSnapshot:
        captured_at = datetime.now(self.timezone)
        previous = self.store.latest_snapshot(target.id)
        snapshot = await self.collector.collect(target, captured_at)
        self.store.save_snapshot(snapshot)
        alerts = evaluate_alerts(target, snapshot, previous, self.store, captured_at)
        for alert in alerts:
            logger.warning("alert triggered: %s %s", alert.target_id, alert.rule_key)
            await self.notifier.send_alert(alert)
        return snapshot

    async def send_report(
        self,
        hours: int | None = None,
        detail_mode: str | None = None,
        caption: str = "Codex 额度汇总",
    ) -> None:
        now = datetime.now(self.timezone)
        hours = hours or self.config.app.report_hours
        detail_mode = detail_mode or self.config.app.report_detail_mode
        snapshots = self.store.snapshots_since(now - timedelta(hours=hours))
        history_snapshots = self.store.all_snapshots()
        if snapshots:
            await self.notifier.send_text(format_snapshot_summary(snapshots[-1], now))
        unauthorized_names = _unauthorized_names(snapshots)
        report_date = now.strftime("%Y-%m-%d")
        new_unauthorized_names = self.store.unreported_unauthorized_names(unauthorized_names, report_date)
        image_path = await self.reporter.render(
            snapshots,
            now,
            history_snapshots,
            detail_mode=detail_mode,
            unauthorized_names=new_unauthorized_names,
        )
        self.store.mark_unauthorized_reported(new_unauthorized_names, report_date, now)
        if image_path:
            await self.notifier.send_report(image_path, caption)
        else:
            await self.notifier.send_text("Codex 额度汇总已生成，但当前环境未安装 Playwright，未生成图片。")

    async def send_full_report(self) -> None:
        await self.send_report(
            hours=self.config.app.full_report_hours,
            detail_mode=self.config.app.full_report_detail_mode,
            caption="Codex 6 小时额度汇总",
        )

    async def run(self) -> None:
        scheduler = MonitorScheduler(
            timezone=self.timezone,
            targets=self.config.targets,
            report_cron=self.config.app.report_cron,
            full_report_crons=self.config.app.full_report_crons,
            collect_callback=self.collect_target,
            report_callback=self.send_report,
            full_report_callback=self.send_full_report,
        )
        scheduler.start()
        logger.info("monitor service started with %d target(s)", len(self.config.targets))
        await asyncio.Event().wait()


def _unauthorized_names(snapshots: list[MetricSnapshot]) -> set[str]:
    return {
        metric.type_name
        for snapshot in snapshots
        for metric in snapshot.type_metrics
        if metric.unauthorized > 0
    }
