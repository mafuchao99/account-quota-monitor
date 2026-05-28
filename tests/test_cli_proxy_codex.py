import pytest

from cpa_monitor.application.config import TargetConfig
from cpa_monitor.infrastructure.http.cli_proxy_codex import (
    collect_codex_quota,
    management_base_url,
    quota_result,
)


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
                    '"primary_window":{"used_percent":25},'
                    '"secondary_window":{"used_percent":40}}}'
                ),
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


def test_quota_result_counts_unauthorized():
    result = quota_result({"name": "bad-token"}, 401, {})

    assert result.metric.available == 0
    assert result.metric.unauthorized == 1
    assert result.metric.other_errors == 0


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
    assert client.posts[0]["url"] == "https://example.test/v0/management/api-call"
    assert client.posts[0]["json"]["authIndex"] == "1"
    assert client.posts[0]["json"]["header"]["Chatgpt-Account-Id"] == "account-id"


@pytest.mark.asyncio
async def test_collect_codex_quota_counts_missing_auth_index_as_other_error():
    result = await collect_codex_quota(FakeClient(), "https://example.test/v0/management", {}, {"name": "missing"})

    assert result.metric.available == 0
    assert result.metric.other_errors == 1
    assert result.error == "missing auth_index"
