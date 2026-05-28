from __future__ import annotations

from cpa_monitor.application.config import MonitorConfig
from cpa_monitor.application.service import MonitorService
from cpa_monitor.infrastructure.http.routing import RoutingSnapshotCollector
from cpa_monitor.infrastructure.notify.onebot import OneBotNotifier
from cpa_monitor.infrastructure.reporting.html import HtmlImageReporter
from cpa_monitor.infrastructure.storage.sqlite import SqliteSnapshotStore


def build_service(config: MonitorConfig) -> MonitorService:
    return MonitorService(
        config=config,
        collector=RoutingSnapshotCollector(),
        store=SqliteSnapshotStore(config.app.database_url),
        notifier=OneBotNotifier(config.onebot),
        reporter=HtmlImageReporter(config.app.report_dir),
    )
