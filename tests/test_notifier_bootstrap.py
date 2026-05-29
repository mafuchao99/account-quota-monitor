from cpa_monitor.application.config import (
    AppConfig,
    ConsoleConfig,
    MonitorConfig,
    OneBotConfig,
    QqBotConfig,
    TargetConfig,
)
from cpa_monitor.infrastructure.notify.console import ConsoleNotifier
from cpa_monitor.infrastructure.notify.onebot import OneBotNotifier
from cpa_monitor.infrastructure.notify.qqbot import QqBotNotifier
from cpa_monitor.interfaces.bootstrap import build_service


def test_build_service_uses_console_notifier_by_default(tmp_path):
    config = MonitorConfig(
        app=AppConfig(database_url=f"sqlite:///{tmp_path / 'monitor.db'}"),
        console=ConsoleConfig(enabled=True),
        onebot=OneBotConfig(enabled=False),
        qqbot=QqBotConfig(enabled=False),
        targets=(TargetConfig(id="codex", name="Codex", url="https://example.test"),),
    )

    service = build_service(config)

    assert any(isinstance(item, ConsoleNotifier) for item in service.notifier.notifiers)
    assert not any(isinstance(item, OneBotNotifier) for item in service.notifier.notifiers)
    assert not any(isinstance(item, QqBotNotifier) for item in service.notifier.notifiers)


def test_build_service_respects_notification_enabled_flags(tmp_path):
    config = MonitorConfig(
        app=AppConfig(database_url=f"sqlite:///{tmp_path / 'monitor.db'}"),
        console=ConsoleConfig(enabled=False),
        onebot=OneBotConfig(enabled=True, group_ids=("123",)),
        qqbot=QqBotConfig(enabled=True, app_id="app", app_secret="secret", openid="openid"),
        targets=(TargetConfig(id="codex", name="Codex", url="https://example.test"),),
    )

    service = build_service(config)

    assert not any(isinstance(item, ConsoleNotifier) for item in service.notifier.notifiers)
    assert any(isinstance(item, OneBotNotifier) for item in service.notifier.notifiers)
    assert any(isinstance(item, QqBotNotifier) for item in service.notifier.notifiers)
