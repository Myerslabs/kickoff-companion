"""Phase 16 wave 3, the server side: the Origin check on every change, restarting from the app, the update check, the
"code changed" flag, and the tray for the packaged program. GitHub is scripted; no test reaches the network."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app import build, restart
from app.api import server as server_api
from app.origin_guard import same_origin
from app.services.launcher import Launcher
from app.services.updates import UpdateChecker, version_key
from tests.test_package import frozen_layout

# --- the Origin check ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(("origin", "host", "scheme", "ok"), [
    (None, "kickoff.local:8642", "http", True),
    ("http://kickoff.local:8642", "kickoff.local:8642", "http", True),
    ("http://KICKOFF.local:8642", "kickoff.local:8642", "http", True),
    ("http://kickoff.local", "kickoff.local:80", "http", True),
    ("https://kickoff.local", "kickoff.local", "https", True),
    ("http://evil.example", "kickoff.local:8642", "http", False),
    ("http://kickoff.local:9999", "kickoff.local:8642", "http", False),
    ("null", "kickoff.local:8642", "http", False),
    ("", "kickoff.local:8642", "http", False),
    ("file://", "kickoff.local:8642", "http", False),
    ("http://kickoff.local:8642", None, "http", False),
])
def test_same_origin(origin, host, scheme, ok):
    assert same_origin(origin, host, scheme) is ok


def test_a_change_from_another_site_is_refused(client):
    assert client.put("/api/settings", json={"theme": "light"}, headers={"Origin": "http://evil.example"}).status_code == 403
    refused = client.post("/api/notes/preview", json={"gameId": 1, "text": "x"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert refused.status_code == 403 and refused.json()["errors"][0]["code"] == "cross_site"
    assert client.get("/api/settings", headers={"Origin": "http://evil.example"}).status_code == 200, "reading is never refused"
    same = client.put("/api/settings", json={"theme": "light"}, headers={"Origin": "https://testserver"})
    assert same.status_code == 200, same.text
    assert client.put("/api/settings", json={"theme": "dark"}).status_code == 200, "no Origin (curl, a test) passes"


# --- restarting from the app ----------------------------------------------------------------------------------


@pytest.fixture
def fresh_restart():
    server_api._last["at"] = 0.0
    restart.reset()
    yield
    server_api._last["at"] = 0.0
    restart.reset()


def test_restart_needs_json_and_a_confirm(client, fresh_restart):
    assert client.post("/api/server/restart", content="confirm=true", headers={"Content-Type": "application/x-www-form-urlencoded"}).status_code in (415, 422)
    assert client.post("/api/server/restart", json={}).status_code == 422
    assert restart.requested() is None


def test_restart_asks_once_a_minute_and_waits_for_a_game(client, app, fresh_restart, monkeypatch):
    monkeypatch.setattr(app.state.live, "status", lambda: {"window": {"inProgress": True}})
    during = client.post("/api/server/restart", json={"confirm": True})
    assert during.status_code == 409 and "under way" in during.json()["errors"][0]["message"] and restart.requested() is None
    ok = client.post("/api/server/restart", json={"confirm": True, "force": True})
    assert ok.status_code == 200 and ok.json()["data"]["restarting"] is True and restart.requested()
    again = client.post("/api/server/restart", json={"confirm": True, "force": True})
    assert again.status_code == 429


def test_the_code_changed_flag(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(build, "APP_DIR", tmp_path)
    monkeypatch.setattr(build, "CODE_AT_START", build._code_stamp())
    build.reset()
    assert build.code_changed() is False
    (tmp_path / "a.py").write_text("x = 2  # longer\n", encoding="utf-8")
    build.reset()
    assert build.code_changed() is True
    monkeypatch.setattr("sys.frozen", True, raising=False)
    build.reset()
    assert build.code_changed() is False, "the packaged program's code never changes on disk"


def test_every_envelope_says_whether_a_restart_is_needed(client):
    assert client.get("/api/settings").json()["meta"]["restartNeeded"] in (True, False)


# --- the update check ---------------------------------------------------------------------------------------


def releases(*tags, draft=()):
    return [{"tag_name": t, "html_url": f"https://github.com/Myerslabs/kickoff-companion/releases/tag/{t}", "body": "Notes for " + t, "published_at": "2026-10-09T00:00:00Z", "prerelease": True, "draft": t in draft} for t in tags]


def checker(tmp_path, answers, now, **kw):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        answer = answers.pop(0)
        return answer if isinstance(answer, httpx.Response) else httpx.Response(200, json=answer)

    return UpdateChecker(tmp_path, transport=httpx.MockTransport(handler), clock=lambda: now[0], **kw), calls


def test_version_keys():
    assert version_key("v0.12.1") == (0, 12, 1) and version_key("1.2") == (1, 2, 0)
    assert [version_key(x) for x in ("nope", None, "v1.2.3-rc1", 5)] == [None, None, None, None]


def test_a_newer_release_is_found_once_a_day(tmp_path):
    now = [datetime(2026, 10, 9, tzinfo=timezone.utc)]
    c, calls = checker(tmp_path, [releases("v0.12.0", "v0.13.1", "v0.14.0", "junk", draft=("v0.14.0",))], now, current="0.12.1")
    got = asyncio.run(c.status())
    assert got["newer"] is True and got["latest"] == "0.13.1" and got["url"].endswith("/v0.13.1") and got["notes"] == "Notes for v0.13.1"
    assert asyncio.run(c.status())["latest"] == "0.13.1" and len(calls) == 1, "kept for a day"
    now[0] += timedelta(days=1, seconds=1)
    c._http._transport = httpx.MockTransport(lambda r: httpx.Response(200, json=releases("v0.12.1")))
    assert asyncio.run(c.status())["newer"] is False


def test_failures_and_the_switch(tmp_path):
    now = [datetime(2026, 10, 9, tzinfo=timezone.utc)]
    c, calls = checker(tmp_path, [httpx.Response(503), {"not": "a list"}], now, current="0.12.1")
    down = asyncio.run(c.status())
    assert down["newer"] is False and "didn't get an answer" in down["error"]
    assert "earlier" in asyncio.run(c.status())["error"] and len(calls) == 1, "paused after a failure"
    off, offcalls = checker(tmp_path / "off", [], now, enabled=lambda: False)
    assert asyncio.run(off.status(force=True))["enabled"] is False and offcalls == []
    (tmp_path / "update.json").write_text("{broken", encoding="utf-8")
    assert c._stored() == {}


def test_the_route(settings, fake_cfbd):
    from fastapi.testclient import TestClient

    from app.logging_setup import configure_logging, shutdown_logging
    from app.main import create_app

    configure_logging(settings)
    application = create_app(settings, cfbd_transport=fake_cfbd.transport, updates_transport=httpx.MockTransport(lambda r: httpx.Response(200, json=releases("v99.0.0"))))
    try:
        with TestClient(application, base_url="https://testserver") as tc:
            tc.portal.call(application.state.live.stop_background)
            data = tc.get("/api/updates").json()["data"]
            assert data["newer"] is True and data["latest"] == "99.0.0"
            tc.put("/api/settings", json={"updateCheck": False})
            assert tc.get("/api/updates?force=1").json()["data"]["enabled"] is False
    finally:
        shutdown_logging()
    stored = json.loads((settings.data_dir / "update.json").read_text(encoding="utf-8"))
    assert stored["latest"] == "99.0.0"


# --- the tray for the packaged program ------------------------------------------------------------------------


def test_the_packaged_program_gets_the_tray_when_its_script_is_bundled(tmp_path):
    program, bundle = frozen_layout(tmp_path)
    (bundle / "static").mkdir()
    (bundle / "tools").mkdir()
    (bundle / "tools" / "tray.ps1").write_text("# tray", encoding="utf-8")
    install = tmp_path / "install"
    scripts: list[str] = []
    launcher = Launcher(tmp_path / "appdata", runner=lambda args: scripts.append(args[0]) or (0, ""), platform="win32", appdata=str(tmp_path / "Roaming"), home=tmp_path, program=program, static_dir=bundle / "static", install_root=install)
    assert launcher.tray_supported is True and launcher.status()["tray"] is True
    assert launcher.set_enabled(True, tray=True).get("error") is None
    assert "$s.TargetPath = 'powershell.exe'" in scripts[0] and f'-Program "{program}"' in scripts[0] and f'-Root "{install}"' in scripts[0] and "-Login" in scripts[0]
    assert str(bundle / "tools" / "tray.ps1") in scripts[0]
    launcher.desktop_shortcut(tray=False)
    assert f"$s.TargetPath = '{program}'" in scripts[-1], "tray off: the program itself"


def test_the_tray_script_reads_the_scheme_and_takes_the_program():
    from pathlib import Path

    text = Path("tools/tray.ps1").read_text(encoding="utf-8")
    assert "[string]$Program" in text and "KICKOFF_NO_PAUSE" in text and '"HTTPS" "off"' in text
    assert "https://$hostName" not in text, "plain HTTP unless HTTPS=on"


def test_a_private_repository_is_not_a_failure(tmp_path):
    # Phase 18.4: GitHub answers 404 for a private repository's releases. Nothing to compare is not an error in Settings.
    now = [datetime(2026, 10, 9, tzinfo=timezone.utc)]
    c, calls = checker(tmp_path, [httpx.Response(404)], now, current="0.12.2")
    got = asyncio.run(c.status())
    assert got["newer"] is False and got["error"] is None and len(calls) == 1
    assert asyncio.run(c.status())["error"] is None and len(calls) == 1, "asked again tomorrow, not on every look"
