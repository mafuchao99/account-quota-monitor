from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import tzinfo

from cpa_monitor.domain.models import MetricSnapshot
from cpa_monitor.domain.summary import snapshot_5h_remaining_percent

from .config import TargetConfig

logger = logging.getLogger(__name__)

CollectCallback = Callable[[TargetConfig], Awaitable[MetricSnapshot]]
ReportCallback = Callable[[], Awaitable[None]]


def cron_kwargs(expression: str) -> dict[str, str]:
    parts = expression.split()
    if len(parts) == 5:
        minute, hour, day, month, day_of_week = parts
        return {
            "minute": minute,
            "hour": hour,
            "day": day,
            "month": month,
            "day_of_week": day_of_week,
        }
    if len(parts) == 6:
        second, minute, hour, day, month, day_of_week = parts
        return {
            "second": second,
            "minute": minute,
            "hour": hour,
            "day": day,
            "month": month,
            "day_of_week": day_of_week,
        }
    raise ValueError(f"Cron expression must have 5 or 6 fields: {expression}")


def collect_crons(target: TargetConfig) -> tuple[str, ...]:
    return target.crons or (target.cron,)


def collect_job_id(target: TargetConfig, index: int | None = None) -> str:
    if index is None:
        return f"collect:{target.id}"
    return f"collect:{target.id}:{index}"


def report_job_id(index: int | None = None) -> str:
    if index is None:
        return "report"
    return f"report:{index}"


def desired_collect_interval_minutes(target: TargetConfig, snapshot: MetricSnapshot) -> int | None:
    schedule = target.dynamic_schedule
    if not schedule.enabled:
        return None
    threshold = (
        target.thresholds.remaining_percent
        if schedule.urgent_remaining_percent is None
        else schedule.urgent_remaining_percent
    )
    percent = snapshot_5h_remaining_percent(snapshot)
    if percent is not None and percent <= threshold:
        return schedule.urgent_interval_minutes
    return schedule.normal_interval_minutes


class MonitorScheduler:
    def __init__(
        self,
        timezone: tzinfo,
        targets: tuple[TargetConfig, ...],
        report_crons: tuple[str, ...],
        full_report_enabled: bool,
        full_report_crons: tuple[str, ...],
        collect_callback: CollectCallback,
        report_callback: ReportCallback,
        full_report_callback: ReportCallback,
    ) -> None:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.cron import CronTrigger
            from apscheduler.triggers.interval import IntervalTrigger
        except ImportError as exc:
            raise RuntimeError("APScheduler is required to run the scheduler.") from exc

        self.timezone = timezone
        self.collect_callback = collect_callback
        self.report_callback = report_callback
        self.full_report_callback = full_report_callback
        self.scheduler = AsyncIOScheduler(timezone=timezone)
        self.cron_trigger_cls = CronTrigger
        self.interval_trigger_cls = IntervalTrigger
        self.collect_interval_minutes: dict[str, int] = {}

        for target in targets:
            if not target.enabled:
                continue
            self._add_collect_job(target)
        for index, report_cron in enumerate(report_crons):
            self.scheduler.add_job(
                self.report_callback,
                self.cron_trigger_cls(**cron_kwargs(report_cron), timezone=self.timezone),
                id=report_job_id(index),
                replace_existing=True,
                max_instances=1,
            )
        if full_report_enabled:
            for index, full_report_cron in enumerate(full_report_crons):
                self.scheduler.add_job(
                    self.full_report_callback,
                    self.cron_trigger_cls(**cron_kwargs(full_report_cron), timezone=self.timezone),
                    id=f"full-report:{index}",
                    replace_existing=True,
                    max_instances=1,
                )

    def start(self) -> None:
        self.scheduler.start()

    def _add_collect_job(self, target: TargetConfig) -> None:
        if target.dynamic_schedule.enabled:
            minutes = target.dynamic_schedule.normal_interval_minutes
            self.collect_interval_minutes[target.id] = minutes
            self.scheduler.add_job(
                self._collect_and_reschedule,
                self.interval_trigger_cls(minutes=minutes, timezone=self.timezone),
                args=[target],
                id=collect_job_id(target),
                replace_existing=True,
                max_instances=1,
            )
            return

        for index, cron in enumerate(collect_crons(target)):
            self.scheduler.add_job(
                self._collect_and_reschedule,
                self.cron_trigger_cls(**cron_kwargs(cron), timezone=self.timezone),
                args=[target],
                id=collect_job_id(target, index),
                replace_existing=True,
                max_instances=1,
            )

    async def _collect_and_reschedule(self, target: TargetConfig) -> None:
        snapshot = await self.collect_callback(target)
        self._reschedule_collect_job(target, snapshot)

    def _reschedule_collect_job(self, target: TargetConfig, snapshot: MetricSnapshot) -> None:
        desired_minutes = desired_collect_interval_minutes(target, snapshot)
        if desired_minutes is None:
            return
        if self.collect_interval_minutes.get(target.id) == desired_minutes:
            return

        self.scheduler.reschedule_job(
            collect_job_id(target),
            trigger=self.interval_trigger_cls(minutes=desired_minutes, timezone=self.timezone),
        )
        self.collect_interval_minutes[target.id] = desired_minutes
        logger.info("rescheduled target %s collection interval to %d minute(s)", target.id, desired_minutes)
