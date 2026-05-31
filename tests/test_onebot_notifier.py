from pathlib import Path

import pytest

from cpa_monitor.application.config import OneBotConfig
from cpa_monitor.infrastructure.notify.onebot import OneBotClient, OneBotNotifier


class FakeResponse:
    def __init__(self, payload=None):
        self.payload = payload or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeHttpClient:
    gets = []
    posts = []

    def __init__(self, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def get(self, url, headers=None):
        self.gets.append({"url": url, "headers": headers or {}})
        return FakeResponse({"status": "ok", "retcode": 0, "data": {"user_id": 123456}})

    async def post(self, url, json, headers=None):
        self.posts.append({"url": url, "json": json, "headers": headers or {}})
        return FakeResponse({"status": "ok", "retcode": 0, "data": {"message_id": 42}})


class FakeOneBotClient:
    def __init__(self, fail_first_group_message=False):
        self.fail_first_group_message = fail_first_group_message
        self.group_messages = []
        self.private_messages = []

    async def send_group_msg(self, group_id, message):
        if self.fail_first_group_message:
            self.fail_first_group_message = False
            raise RuntimeError("OneBot action failed: retcode=200, message=ENOENT: no such file or directory")
        self.group_messages.append((group_id, message))
        return {"message_id": 1}

    async def send_private_msg(self, user_id, message):
        self.private_messages.append((user_id, message))
        return {"message_id": 2}


@pytest.fixture(autouse=True)
def reset_fake_http_client():
    FakeHttpClient.gets = []
    FakeHttpClient.posts = []


@pytest.mark.asyncio
async def test_onebot_client_calls_login_and_group_actions(monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeHttpClient)
    client = OneBotClient(
        OneBotConfig(endpoint="http://127.0.0.1:3301", access_token="token-123", retry_count=0)
    )

    assert await client.get_login_info() == {"user_id": 123456}
    result = await client.send_group_msg("1080790263", [{"type": "text", "data": {"text": "hello"}}])

    assert result == {"message_id": 42}
    assert FakeHttpClient.gets[0]["url"] == "http://127.0.0.1:3301/get_login_info"
    assert FakeHttpClient.gets[0]["headers"]["Authorization"] == "Bearer token-123"
    assert FakeHttpClient.posts[0]["url"] == "http://127.0.0.1:3301/send_group_msg"
    assert FakeHttpClient.posts[0]["json"]["group_id"] == "1080790263"


@pytest.mark.asyncio
async def test_onebot_client_sends_common_message_api(monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeHttpClient)
    client = OneBotClient(OneBotConfig(endpoint="http://127.0.0.1:3301", retry_count=0))

    await client.send_msg("private", "10001", [{"type": "text", "data": {"text": "hello"}}])

    assert FakeHttpClient.posts[0]["url"] == "http://127.0.0.1:3301/send_msg"
    assert FakeHttpClient.posts[0]["json"] == {
        "message_type": "private",
        "message": [{"type": "text", "data": {"text": "hello"}}],
        "user_id": "10001",
    }


@pytest.mark.asyncio
async def test_onebot_notifier_broadcasts_text_to_group_and_private_targets():
    fake_client = FakeOneBotClient()
    notifier = OneBotNotifier(
        OneBotConfig(group_ids=("1080790263",), private_user_ids=("10001",)),
        client=fake_client,
    )

    await notifier.send_text("CPA Monitor 通知测试")

    message = [{"type": "text", "data": {"text": "CPA Monitor 通知测试"}}]
    assert fake_client.group_messages == [("1080790263", message)]
    assert fake_client.private_messages == [("10001", message)]


@pytest.mark.asyncio
async def test_onebot_report_uses_array_segments_with_local_image_uri(tmp_path):
    image_path = tmp_path / "report.png"
    image_path.write_bytes(b"png")
    fake_client = FakeOneBotClient()
    notifier = OneBotNotifier(OneBotConfig(group_ids=("1080790263",)), client=fake_client)

    await notifier.send_report(image_path, "服务器报表")

    _, message = fake_client.group_messages[0]
    assert message[0] == {"type": "text", "data": {"text": "服务器报表\n"}}
    assert message[1] == {"type": "image", "data": {"file": Path(image_path).resolve().as_uri()}}


@pytest.mark.asyncio
async def test_onebot_report_retries_with_base64_when_local_image_path_is_unreadable(tmp_path):
    image_path = tmp_path / "report.png"
    image_path.write_bytes(b"png")
    fake_client = FakeOneBotClient(fail_first_group_message=True)
    notifier = OneBotNotifier(OneBotConfig(group_ids=("1080790263",)), client=fake_client)

    await notifier.send_report(image_path, "服务器报表")

    _, message = fake_client.group_messages[0]
    assert message[0] == {"type": "text", "data": {"text": "服务器报表\n"}}
    assert message[1]["type"] == "image"
    assert message[1]["data"]["file"].startswith("base64://")
