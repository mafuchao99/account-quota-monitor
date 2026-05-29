from __future__ import annotations

from cpa_monitor.application.config import MonitorConfig
from cpa_monitor.application.service import MonitorService
from cpa_monitor.infrastructure.http.routing import RoutingSnapshotCollector
from cpa_monitor.infrastructure.notify.composite import CompositeNotifier
from cpa_monitor.infrastructure.notify.console import ConsoleNotifier
from cpa_monitor.infrastructure.notify.onebot import OneBotNotifier
from cpa_monitor.infrastructure.notify.qqbot import QqBotNotifier
from cpa_monitor.infrastructure.reporting.html import HtmlImageReporter
from cpa_monitor.infrastructure.storage.sqlite import SqliteSnapshotStore


def build_service(config: MonitorConfig) -> MonitorService:
    notifiers = []
    if config.console.enabled:
        notifiers.append(ConsoleNotifier())
    if config.onebot.enabled and (config.onebot.group_ids or config.onebot.private_user_ids):
        notifiers.append(OneBotNotifier(config.onebot))
    if config.qqbot.enabled:
        notifiers.append(QqBotNotifier(config.qqbot))
    return MonitorService(
        config=config,
        collector=RoutingSnapshotCollector(),
        store=SqliteSnapshotStore(config.app.database_url),
        notifier=CompositeNotifier(notifiers),
        reporter=HtmlImageReporter(config.app.report_dir),
    )
