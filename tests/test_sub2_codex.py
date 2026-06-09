from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from cpa_monitor.application.config import AppConfig, ConsoleConfig, MonitorConfig, OneBotConfig, QqBotConfig, TargetConfig
from cpa_monitor.application.service import MonitorService
from cpa_monitor.infrastructure.http.sub2_codex import (
    Sub2CodexCollector,
    account_metric,
    admin_base_url,
    fetch_accounts,
    is_codex_account,
    parse_accounts_page,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeAccountsClient:
    def __init__(self, pages):
        self.pages = pages
        self.urls = []

    async def get(self, url, headers):
        self.urls.append(url)
        return FakeResponse(self.pages[len(self.urls) - 1])


def test_admin_base_url_accepts_domain_or_admin_path():
    assert (
        admin_base_url(TargetConfig(id="sub2", name="sub2", base_url="https://example.test"))
        == "https://example.test/api/v1/admin"
    )
    assert (
        admin_base_url(TargetConfig(id="sub2", name="sub2", base_url="https://example.test/api/v1/admin"))
        == "https://example.test/api/v1/admin"
    )


def test_parse_accounts_page_supports_wrapped_items():
    items, total = parse_accounts_page({"data": {"items": [{"id": "a"}], "total": 1}})

    assert items == [{"id": "a"}]
    assert total == 1


def test_account_metric_maps_codex_snapshot_to_remaining_percent_and_reset_time():
    metric = account_metric(
        {
            "id": "1",
            "name": "user@example.com",
            "platform": "openai",
            "type": "oauth",
            "status": "active",
            "schedulable": True,
            "extra": {
                "codex_5h_used_percent": 25,
                "codex_5h_reset_at": "2026-06-09T05:00:00Z",
                "codex_7d_used_percent": 88,
                "codex_7d_reset_at": 1770500000,
                "codex_usage_updated_at": "2026-06-09T03:30:00Z",
            },
        }
    )

    assert metric.type_name == "user@example.com"
    assert metric.available == 1
    assert metric.remaining_5h_percent == 75
    assert metric.remaining_7d_percent == 12
    assert metric.reset_5h_at is not None
    assert metric.reset_7d_at is not None
    assert metric.usage_updated_at is not None


def test_account_metric_marks_exhausted_or_future_rate_limit_unavailable():
    captured_at = datetime(2026, 6, 9, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    exhausted = account_metric(
        {
            "name": "weekly@example.com",
            "status": "active",
            "schedulable": True,
            "extra": {"codex_5h_used_percent": 1, "codex_7d_used_percent": 100},
        },
        captured_at,
    )
    rate_limited = account_metric(
        {
            "name": "limited@example.com",
            "status": "active",
            "schedulable": True,
            "rate_limit_reset_at": "2026-06-11T08:28:27+08:00",
            "extra": {"codex_5h_used_percent": 18, "codex_7d_used_percent": 20},
        },
        captured_at,
    )
    expired_rate_limit = account_metric(
        {
            "name": "expired@example.com",
            "status": "active",
            "schedulable": True,
            "rate_limit_reset_at": "2026-06-08T08:28:27+08:00",
            "extra": {"codex_5h_used_percent": 18, "codex_7d_used_percent": 20},
        },
        captured_at,
    )

    assert exhausted.available == 0
    assert exhausted.remaining_7d_percent == 0
    assert rate_limited.available == 0
    assert expired_rate_limit.available == 1


def test_is_codex_account_requires_openai_codex_snapshot():
    assert is_codex_account({"platform": "openai", "extra": {"codex_5h_used_percent": 1}}) is True
    assert is_codex_account({"platform": "anthropic", "extra": {"codex_5h_used_percent": 1}}) is False
    assert is_codex_account({"platform": "openai", "extra": {}}) is False


@pytest.mark.asyncio
async def test_fetch_accounts_paginates_until_total_reached():
    client = FakeAccountsClient(
        [
            {"data": {"items": [{"id": "1"}, {"id": "2"}], "total": 3}},
            {"data": {"items": [{"id": "3"}], "total": 3}},
        ]
    )

    accounts = await fetch_accounts(
        client,
        "https://example.test/api/v1/admin",
        {"x-api-key": "key"},
        page_size=2,
    )

    assert [item["id"] for item in accounts] == ["1", "2", "3"]
    assert "page=1" in client.urls[0]
    assert "page=2" in client.urls[1]
    assert "platform=openai" in client.urls[0]


@pytest.mark.asyncio
async def test_fetch_accounts_waits_between_pages(monkeypatch):
    client = FakeAccountsClient(
        [
            {"data": {"items": [{"id": "1"}], "total": 2}},
            {"data": {"items": [{"id": "2"}], "total": 2}},
        ]
    )
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("cpa_monitor.infrastructure.http.sub2_codex.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("cpa_monitor.infrastructure.http.sub2_codex.random.uniform", lambda start, end: 1.25)

    accounts = await fetch_accounts(
        client,
        "https://example.test/api/v1/admin",
        {"x-api-key": "key"},
        page_size=1,
    )

    assert [item["id"] for item in accounts] == ["1", "2"]
    assert sleeps == [1.25]


@pytest.mark.asyncio
async def test_collect_builds_snapshot_from_account_list(monkeypatch):
    async def fake_fetch_accounts(client, base_url, headers, page_size):
        return [
            {
                "id": "1",
                "name": "ok@example.com",
                "platform": "openai",
                "status": "active",
                "schedulable": True,
                "rate_limit_reset_at": "2026-06-11T08:28:27+08:00",
                "extra": {"codex_5h_used_percent": 20, "codex_7d_used_percent": 40},
            },
            {
                "id": "2",
                "name": "off@example.com",
                "platform": "openai",
                "status": "disabled",
                "schedulable": False,
                "extra": {"codex_5h_used_percent": 10, "codex_7d_used_percent": 100},
            },
            {
                "id": "3",
                "name": "bad@example.com",
                "platform": "openai",
                "status": "error",
                "error_message": "upstream timeout",
                "extra": {"codex_5h_used_percent": 10},
            },
            {"id": "4", "platform": "openai", "extra": {}},
        ]

    monkeypatch.setattr("cpa_monitor.infrastructure.http.sub2_codex.fetch_accounts", fake_fetch_accounts)
    target = TargetConfig(id="sub2", name="sub2", collector="sub2_codex", base_url="https://example.test")

    snapshot = await Sub2CodexCollector().collect(
        target,
        datetime(2026, 6, 9, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert snapshot.total == 3
    assert snapshot.available == 0
    assert snapshot.disabled == 1
    assert snapshot.other_errors == 1
    assert [metric.type_name for metric in snapshot.type_metrics] == [
        "ok@example.com",
        "off@example.com",
        "bad@example.com",
    ]


@pytest.mark.asyncio
async def test_service_collect_once_skips_disabled_targets():
    class FakeCollector:
        async def collect(self, target, captured_at):
            raise AssertionError("disabled target should not be collected")

    class FakeStore:
        def latest_snapshot(self, target_id):
            return None

        def save_snapshot(self, snapshot):
            return None

    class FakeNotifier:
        async def send_text(self, message):
            return None

        async def send_alert(self, alert):
            return None

    class FakeReporter:
        pass

    config = MonitorConfig(
        app=AppConfig(),
        console=ConsoleConfig(),
        onebot=OneBotConfig(),
        qqbot=QqBotConfig(),
        targets=(TargetConfig(id="sub2", name="sub2", enabled=False),),
    )

    snapshots = await MonitorService(config, FakeCollector(), FakeStore(), FakeNotifier(), FakeReporter()).collect_once()

    assert snapshots == []
