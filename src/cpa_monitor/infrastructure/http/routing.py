from __future__ import annotations

from datetime import datetime

from cpa_monitor.application.config import TargetConfig
from cpa_monitor.domain.models import MetricSnapshot

from .cli_proxy_codex import CliProxyCodexCollector
from .collector import HttpJsonCollector
from .sub2_codex import Sub2CodexCollector


class RoutingSnapshotCollector:
    def __init__(self) -> None:
        self.http_json = HttpJsonCollector()
        self.cli_proxy_codex = CliProxyCodexCollector()
        self.sub2_codex = Sub2CodexCollector()

    async def collect(self, target: TargetConfig, captured_at: datetime) -> MetricSnapshot:
        collector = target.collector.lower()
        if collector == "http_json":
            return await self.http_json.collect(target, captured_at)
        if collector == "cli_proxy_codex":
            return await self.cli_proxy_codex.collect(target, captured_at)
        if collector == "sub2_codex":
            return await self.sub2_codex.collect(target, captured_at)
        raise ValueError(f"Unsupported collector for target {target.id}: {target.collector}")
