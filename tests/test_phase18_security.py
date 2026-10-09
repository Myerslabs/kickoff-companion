"""Phase 18.1: the security review's fixes (S1 to S4, S6 to S10)."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.httpcap import ResponseTooLarge, get_capped
from app.limits import BodyLimit, RateLimit, Rule
from app.origin_guard import HostGuard, host_allowed


@pytest.mark.parametrize("host", ["localhost:8642", "127.0.0.1", "192.168.0.20:8642", "[::1]:8642", "homepc", "kickoff.local", "football.localdomain:8642", "testserver", "football.lan"])
def test_host_allowed_for_home_network_names(host):
    assert host_allowed(host)


@pytest.mark.parametrize("host", ["evil.example", "evil.example:8642", "a.b.example.com", "", None, "localhost.evil.com"])
def test_host_refused_for_names_a_stranger_owns(host):
    assert not host_allowed(host)


def test_announced_name_is_allowed_even_when_it_is_a_full_domain():
    assert host_allowed("game.example.com", {"game.example.com"})


def test_app_answers_421_to_a_rebinding_host_and_200_to_its_own(client: TestClient):
    assert client.get("/api/health", headers={"Host": "evil.example:8642"}).status_code == 421
    assert client.get("/api/health").status_code == 200


def test_notes_command_is_not_a_setting(client: TestClient):
    response = client.put("/api/settings", json={"notesCommand": "calc.exe"})
    assert response.status_code == 422 and "unknown setting" in response.json()["errors"][0]["message"]
    assert "notesCommand" not in client.get("/api/settings").json()["data"]["prefs"]


def test_desktop_shortcut_refused_for_other_devices(client: TestClient):
    response = client.post("/api/settings/desktop-shortcut")
    assert response.status_code == 403 or response.status_code == 200  # the test client calls from "testclient": not the server computer
    assert response.status_code == 403


async def _call(app, method="POST", path="/", body=b"", headers=None, client=("10.0.0.5", 1), query=b""):
    sent = []
    messages = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive():
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": method, "path": path, "query_string": query, "headers": headers or [], "client": client, "scheme": "http"}
    await app(scope, receive, send)
    return sent


async def _ok(scope, receive, send):
    while True:
        message = await receive()
        if message["type"] != "http.request" or not message.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def test_body_over_the_ceiling_is_refused_by_length_and_by_count():
    guard = BodyLimit(_ok, max_bytes=10)
    assert asyncio.run(_call(guard, body=b"x" * 5))[0]["status"] == 200
    assert asyncio.run(_call(guard, body=b"x" * 50, headers=[(b"content-length", b"50")]))[0]["status"] == 413
    assert asyncio.run(_call(guard, body=b"x" * 50))[0]["status"] == 413  # no Content-Length: counted as it arrives


def test_rate_limit_counts_per_client_and_forgets_after_the_window():
    now = [0.0]
    rules = (Rule("warm", "POST", "/api/myteams/warm", 2, 60), Rule("wide", "GET", "/api/search", 1, 60, query=lambda q: "wide=1" in q))
    guard = RateLimit(_ok, rules, clock=lambda: now[0])
    statuses = [asyncio.run(_call(guard, path="/api/myteams/warm"))[0]["status"] for _ in range(3)]
    assert statuses == [200, 200, 429]
    assert asyncio.run(_call(guard, path="/api/myteams/warm", client=("10.0.0.6", 1)))[0]["status"] == 200  # another device
    assert asyncio.run(_call(guard, method="GET", path="/api/search", query=b"q=a"))[0]["status"] == 200  # not a wide search
    assert asyncio.run(_call(guard, method="GET", path="/api/search", query=b"q=a&wide=1"))[0]["status"] == 200
    assert asyncio.run(_call(guard, method="GET", path="/api/search", query=b"q=b&wide=1"))[0]["status"] == 429
    now[0] = 61.0
    assert asyncio.run(_call(guard, path="/api/myteams/warm"))[0]["status"] == 200


def test_host_guard_blocks_websockets_too():
    guard = HostGuard(_ok)
    sent = []

    async def send(message):
        sent.append(message)

    asyncio.run(guard({"type": "websocket", "path": "/", "headers": [(b"host", b"evil.example")]}, None, send))
    assert sent == [{"type": "websocket.close", "code": 1008}]


def _client_with(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_get_capped_returns_a_normal_response_under_the_ceiling():
    async def run():
        async with _client_with(lambda r: httpx.Response(200, content=b"abc", headers={"content-type": "text/plain"})) as c:
            return await get_capped(c, "https://example.invalid/x", 10)

    response = asyncio.run(run())
    assert response.status_code == 200 and response.content == b"abc" and response.headers["content-type"] == "text/plain"


def test_get_capped_stops_a_declared_and_an_undeclared_oversize_answer():
    async def run(response):
        async with _client_with(lambda r: response) as c:
            with pytest.raises(ResponseTooLarge):
                await get_capped(c, "https://example.invalid/x", 10)

    asyncio.run(run(httpx.Response(200, content=b"x" * 50)))
    asyncio.run(run(httpx.Response(200, stream=httpx.ByteStream(b"x" * 50), headers={})))
