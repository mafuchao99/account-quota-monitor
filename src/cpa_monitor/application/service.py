from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from cpa_monitor.domain.alerts import evaluate_alerts

from .config import MonitorConfig, TargetConfig
from .ports import Notifier, ReportRenderer, SnapshotCollector, SnapshotStore
from .schedule import cron_kwargs

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

    async def collect_once(self) -> None:
        for target in self.config.targets:
            await self.collect_target(target)

    async def collect_target(self, target: TargetConfig) -> None:
        captured_at = datetime.now(self.timezone)
        previous = self.store.latest_snapshot(target.id)
        snapshot = await self.collector.collect(target, captured_at)
        self.store.save_snapshot(snapshot)
        alerts = evaluate_alerts(target, snapshot, previous, self.store, captured_at)
        for alert in alerts:
            logger.warning("alert triggered: %s %s", alert.target_id, alert.rule_key)
            await self.notifier.send_alert(alert)

    async def send_report(self, hours: int = 3) -> None:
        now = datetime.now(self.timezone)
        snapshots = self.store.snapshots_since(now - timedelta(hours=hours))
        image_path = await self.reporter.render(snapshots, now)
        if image_path:
            await self.notifier.send_report(image_path)
        else:
            await self.notifier.send_text("Codex 额度汇总已生成，但当前环境未安装 Playwright，未生成图片。")

    async def run(self) -> None:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.cron import CronTrigger
        except ImportError as exc:
            raise RuntimeError("APScheduler is required to run the scheduler.") from exc

        scheduler = AsyncIOScheduler(timezone=self.timezone)
        for target in self.config.targets:
            scheduler.add_job(
                self.collect_target,
                CronTrigger(**cron_kwargs(target.cron), timezone=self.timezone),
                args=[target],
                id=f"collect:{target.id}",
                replace_existing=True,
                max_instances=1,
            )
        scheduler.add_job(
            self.send_report,
            CronTrigger(**cron_kwargs(self.config.app.report_cron), timezone=self.timezone),
            id="report",
            replace_existing=True,
            max_instances=1,
        )
        scheduler.start()
        logger.info("monitor service started with %d target(s)", len(self.config.targets))
        await asyncio.Event().wait()
