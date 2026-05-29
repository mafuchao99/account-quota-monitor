from pathlib import Path

import pytest

from cpa_monitor.application.config import QqBotConfig
from cpa_monitor.infrastructure.notify.qqbot import QqBotNotifier


class FakeResponse:
    def __init__(self, payload=None):
        self.payload = payload or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self):
        self.posts = []

    async def post(self, url, json, headers=None):
        self.posts.append({"url": url, "json": json, "headers": headers or {}})
        if url.endswith("/getAppAccessToken"):
            return FakeResponse({"access_token": "token-123", "expires_in": 7200})
        return FakeResponse()


@pytest.mark.asyncio
async def test_qqbot_notifier_sends_private_text_message():
    client = FakeClient()
    notifier = QqBotNotifier(
        QqBotConfig(
            enabled=True,
            app_id="app-id",
            app_secret="secret",
            openid="openid",
            token_url="https://bots.qq.com/app/getAppAccessToken",
            api_base="https://api.sgroup.qq.com",
        )
    )

    await notifier._post_message_with_client(client, {"msg_type": 0, "content": "hello", "msg_seq": 1})

    assert client.posts[0]["url"] == "https://bots.qq.com/app/getAppAccessToken"
    assert client.posts[0]["json"] == {"appId": "app-id", "clientSecret": "secret"}
    assert client.posts[1]["url"] == "https://api.sgroup.qq.com/v2/users/openid/messages"
    assert client.posts[1]["headers"]["Authorization"] == "QQBot token-123"
    assert client.posts[1]["json"] == {"msg_type": 0, "content": "hello", "msg_seq": 1}


@pytest.mark.asyncio
async def test_qqbot_report_is_text_notice():
    client = FakeClient()
    notifier = QqBotNotifier(
        QqBotConfig(enabled=True, app_id="app-id", app_secret="secret", openid="openid")
    )

    await notifier._send_report_with_client(client, Path("/tmp/report.png"), "Codex 额度汇总")

    assert client.posts[1]["json"]["msg_type"] == 0
    assert isinstance(client.posts[1]["json"]["msg_seq"], int)
    assert "Codex 额度汇总" in client.posts[1]["json"]["content"]
    assert "/tmp/report.png" in client.posts[1]["json"]["content"]
