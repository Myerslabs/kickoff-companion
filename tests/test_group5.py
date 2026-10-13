"""Group five (the final pass's decided features): the HTTPS switch and the away-from-home gate."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_the_https_switch_works_from_the_server_computer_only(client: TestClient, app, monkeypatch) -> None:
    assert client.post("/api/settings/https", json={"on": True}).status_code == 403, "another device cannot switch it"
    monkeypatch.setattr("app.api.settings._on_server_computer", lambda request: True)
    monkeypatch.setattr("app.api.settings._game_under_way", lambda request: False)
    written: list[tuple[object, dict[str, str]]] = []
    asked: list[str] = []
    monkeypatch.setattr("app.api.settings.set_values", lambda path, values: written.append((path, values)))
    monkeypatch.setattr("app.api.settings.restart.request", lambda reason: asked.append(reason))
    monkeypatch.setattr(app.state.settings, "https", False)
    same = client.post("/api/settings/https", json={"on": False})
    assert same.status_code == 200 and same.json()["data"] == {"restarting": False, "https": False}
    assert not written and not asked
    on = client.post("/api/settings/https", json={"on": True})
    assert on.status_code == 200 and on.json()["data"] == {"restarting": True, "https": True}
    assert written[-1][1] == {"HTTPS": "on"} and asked == ["HTTPS switched on from Settings"]
    crossed = client.post("/api/settings/https", json={"on": True}, headers={"Host": "kickoff.local:8642", "Origin": "http://evil.example"})
    assert crossed.status_code == 403 and crossed.json()["errors"][0]["code"] == "cross_site"
    monkeypatch.setattr(app.state.settings, "https", True)
    monkeypatch.setattr("app.api.settings._game_under_way", lambda request: True)
    busy = client.post("/api/settings/https", json={"on": False})
    assert busy.status_code == 409 and busy.json()["errors"][0]["code"] == "game_under_way"
    forced = client.post("/api/settings/https", json={"on": False, "force": True})
    assert forced.status_code == 200 and written[-1][1] == {"HTTPS": "off"}
    assert client.get("/api/settings").json()["data"]["network"] == {"https": True, "canSwitch": True}


def test_https_on_answers_plain_http_without_a_redirect(plain_client: TestClient) -> None:
    for path in ("/", "/api/health", "/setup"):
        response = plain_client.get(path, follow_redirects=False)
        assert response.status_code == 200, path


@pytest.fixture
def away(app, monkeypatch):
    """Away from home on, the server's address known, and the test client a stranger (not the server computer)."""
    monkeypatch.setattr("app.api.host.lan_ip", lambda: "192.168.0.20")
    monkeypatch.setattr("app.api.setup.lan_ip", lambda: "192.168.0.20")
    monkeypatch.setattr("app.guests.on_server_computer", lambda scope: False)
    app.state.prefs.update({"awayFromHome": True})
    yield
    app.state.prefs.update({"awayFromHome": False})


def test_away_from_home_gates_strangers_and_admits_the_code(client: TestClient, app, away) -> None:
    page = client.get("/")
    assert page.status_code == 200 and "away from home" in page.text.lower() and "scan the host" in page.text.lower()
    refused = client.get("/api/settings")
    assert refused.status_code == 403 and refused.json()["errors"][0]["code"] == "away_from_home"
    assert client.get("/api/health").status_code == 200, "the health route stays open"
    assert client.get("/join/nope", follow_redirects=False).status_code == 403
    code = app.state.host_access.join_token()
    assert len(code) == 12 and code == app.state.host_access.join_token(), "the code is stable"
    joined = client.get(f"/join/{code}", follow_redirects=False)
    assert joined.status_code == 303 and joined.headers["location"] == "/" and "kickoff_join=" in joined.headers.get("set-cookie", "")
    assert "away from home" not in client.get("/").text.lower()
    assert client.get("/api/settings").status_code == 200
    invite = client.get("/api/invite").json()["data"]
    assert invite["away"] is True and invite["url"] == f"http://192.168.0.20:{app.state.settings.port}/join/{code}"
    assert client.get(f"/setup/qr.svg?url={invite['url']}").status_code == 200, "the QR draws the join link"
    assert client.get(f"/setup/qr.svg?url=http://192.168.0.20:{app.state.settings.port}/join/bad").status_code == 404
    assert invite["copyUrl"], "the repository is public: the invite page offers a copy"


def test_the_host_is_never_gated_and_home_lets_everyone_in(client: TestClient, app, monkeypatch) -> None:
    monkeypatch.setattr("app.guests.on_server_computer", lambda scope: True)
    app.state.prefs.update({"awayFromHome": True})
    try:
        assert "away from home" not in client.get("/").text.lower()
        assert client.get("/api/settings").status_code == 200
    finally:
        app.state.prefs.update({"awayFromHome": False})
    monkeypatch.setattr("app.guests.on_server_computer", lambda scope: False)
    assert client.get("/api/settings").status_code == 200, "back home, every device on the network can watch"


def test_away_from_home_switches_the_network_name(client: TestClient, app, monkeypatch) -> None:
    class Job:
        def __init__(self) -> None:
            self.stopped = 0
            self.started = 0

        async def stop(self) -> None:
            self.stopped += 1

        def start(self) -> None:
            self.started += 1

    job = Job()
    monkeypatch.setattr(app.state, "mdns", job, raising=False)
    monkeypatch.setattr("app.guests.on_server_computer", lambda scope: True)
    on = client.put("/api/settings", json={"awayFromHome": True})
    assert on.status_code == 200 and job.stopped == 1 and job.started == 0
    off = client.put("/api/settings", json={"awayFromHome": False})
    assert off.status_code == 200 and job.started == 1
    assert client.get("/api/settings").json()["data"]["prefs"]["awayFromHome"] is False
