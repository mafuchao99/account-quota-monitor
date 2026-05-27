from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class TypeMetric:
    type_name: str
    available: int
    total: int
    remaining_5h_percent: float | None = None
    remaining_7d_percent: float | None = None
    unauthorized: int = 0
    other_errors: int = 0


@dataclass(frozen=True)
class MetricSnapshot:
    target_id: str
    target_name: str
    captured_at: datetime
    available: int
    total: int
    disabled: int = 0
    unauthorized: int = 0
    other_errors: int = 0
    type_metrics: tuple[TypeMetric, ...] = field(default_factory=tuple)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def available_percent(self) -> float | None:
        if self.total <= 0:
            return None
        return self.available / self.total * 100


@dataclass(frozen=True)
class Alert:
    target_id: str
    rule_key: str
    title: str
    message: str
