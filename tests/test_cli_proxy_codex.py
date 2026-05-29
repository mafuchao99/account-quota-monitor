import pytest

from cpa_monitor.application.config import TargetConfig
from cpa_monitor.infrastructure.http.cli_proxy_codex import (
    CliProxyCodexCollector,
    collect_codex_quota,
    credential_summary,
    management_base_url,
    quota_result,
    select_credential,
)
from cpa_monitor.interfaces.cli import _credentials_report, _quota_one_report


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self):
        self.posts = []

    async def post(self, url, headers, json):
        self.posts.append({"url": url, "headers": headers, "json": json})
        return FakeResponse(
            {
                "status_code": 200,
                "body": (
                    '{"rate_limit":{"allowed":true,"limit_reached":false,'
                    '"primary_window":{"used_percent":25,"reset_at":1770000000},'
                    '"secondary_window":{"used_percent":40,"reset_at":1770500000}}}'
                ),
            }
        )


class FakeCollectClient:
    def __init__(self):
        self.calls = []

    async def post(self, url, headers, json):
        self.calls.append(json["authIndex"])
        return FakeResponse(
            {
                "status_code": 200,
                "body": '{"rate_limit":{"allowed":true,"limit_reached":false}}',
            }
        )


def test_management_base_url_accepts_domain_or_management_path():
    assert (
        management_base_url(TargetConfig(id="codex", name="Codex", base_url="https://example.test"))
        == "https://example.test/v0/management"
    )
    assert (
        management_base_url(
            TargetConfig(id="codex", name="Codex", base_url="https://example.test/v0/management")
        )
        == "https://example.test/v0/management"
    )


def test_quota_result_maps_remaining_percent_and_available_account():
    result = quota_result(
        {"label": "user@example.com"},
        200,
        {
            "rate_limit": {
                "allowed": True,
                "limit_reached": False,
                "primary_window": {"used_percent": 25},
                "secondary_window": {"used_percent": 40},
            }
        },
    )

    assert result.metric.type_name == "user@example.com"
    assert result.metric.available == 1
    assert result.metric.remaining_5h_percent == 75
    assert result.metric.remaining_7d_percent == 60
    assert result.metric.reset_5h_at is None


def test_quota_result_counts_unauthorized():
    result = quota_result({"name": "bad-token"}, 401, {})

    assert result.metric.available == 0
    assert result.metric.unauthorized == 1
    assert result.metric.other_errors == 0


def test_credential_summary_maps_status_fields():
    credential = credential_summary(
        {
            "label": "user@example.com",
            "auth_index": "1",
            "status": "active",
            "disabled": False,
            "unavailable": True,
            "account": "ChatGPT Plus",
        }
    )

    assert credential.name == "user@example.com"
    assert credential.auth_index == "1"
    assert credential.status == "active"
    assert credential.unavailable is True
    assert credential.account == "ChatGPT Plus"


def test_credentials_report_summarizes_status_counts():
    report = _credentials_report(
        "Codex 额度",
        [
            credential_summary({"label": "ok@example.com", "auth_index": "1", "status": "active", "account": "ok@example.com"}),
            credential_summary({"label": "bad@example.com", "auth_index": "", "status": "error", "unavailable": True}),
            credential_summary({"label": "off@example.com", "auth_index": "3", "status": "disabled", "disabled": True}),
        ],
    )

    assert "total=3" in report
    assert "active=2" in report
    assert "disabled=1" in report
    assert "unavailable=1" in report
    assert "missing_auth_index=1" in report
    assert "o***@example.com" in report
    assert "auth_index=-" in report
    assert "account=o***@example.com" in report


def test_select_credential_supports_masked_auth_index():
    selected = select_credential(
        [
            {"auth_index": "1234567890", "label": "first@example.com"},
            {"auth_index": "9d7d56247bf7a99d", "label": "gmail@example.com"},
        ],
        auth_index="9d7d...a99d",
    )

    assert selected["label"] == "gmail@example.com"


def test_select_credential_supports_unique_text_match():
    selected = select_credential(
        [
            {"auth_index": "1", "label": "first@example.com"},
            {"auth_index": "2", "label": "gmail@example.com"},
        ],
        match="gmail",
    )

    assert selected["auth_index"] == "2"


@pytest.mark.asyncio
async def test_collect_all_queries_sequentially_with_random_delay(monkeypatch):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("cpa_monitor.infrastructure.http.cli_proxy_codex.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("cpa_monitor.infrastructure.http.cli_proxy_codex.random.uniform", lambda start, end: 1.5)
    target = TargetConfig(id="codex", name="Codex", delay_min_seconds=0, delay_max_seconds=3)
    client = FakeCollectClient()

    results = await CliProxyCodexCollector()._collect_all(
        client,
        "https://example.test/v0/management",
        {},
        [{"auth_index": "1"}, {"auth_index": "2"}, {"auth_index": "3"}],
        target,
    )

    assert client.calls == ["1", "2", "3"]
    assert sleeps == [1.5, 1.5]
    assert len(results) == 3


@pytest.mark.asyncio
async def test_collect_codex_quota_posts_api_call_with_account_id():
    client = FakeClient()

    result = await collect_codex_quota(
        client,
        "https://example.test/v0/management",
        {"Authorization": "Bearer secret"},
        {
            "auth_index": "1",
            "label": "user@example.com",
            "id_token": {"chatgpt_account_id": "account-id"},
        },
    )

    assert result.metric.available == 1
    assert result.metric.reset_5h_at is not None
    assert client.posts[0]["url"] == "https://example.test/v0/management/api-call"
    assert client.posts[0]["json"]["authIndex"] == "1"
    assert client.posts[0]["json"]["header"]["Chatgpt-Account-Id"] == "account-id"


@pytest.mark.asyncio
async def test_collect_codex_quota_counts_missing_auth_index_as_other_error():
    result = await collect_codex_quota(FakeClient(), "https://example.test/v0/management", {}, {"name": "missing"})

    assert result.metric.available == 0
    assert result.metric.other_errors == 1
    assert result.error == "missing auth_index"
