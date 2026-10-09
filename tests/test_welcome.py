"""Public release Phase 5a: first-run setup in the browser. A server with no key or team runs in setup
mode: every page leads to /welcome and the data API answers setup_needed. The welcome flow checks a key
with one /info call, lists the FBS schools, then writes CFBD_API_KEY, TEAM and CONFERENCE into .env and
restarts in place. Liked teams, conferences and states need a Tier 2 key. The key is never sent back.
Also: the .env writer, the restart signal, the plan summary and its forecast."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import restart
from app.cfbd.capabilities import Capabilities
from app.config import load_settings
from app.logging_setup import configure_logging, shutdown_logging
from app.main import create_app
from app.services import plan
from app.services.envfile import quote, set_values
from app.services.prefs import PrefsStore
from tests.conftest import TEST_KEY, FakeCfbd, fixture_payload

NEW_KEY = "Abc123def456ghi789jkl0+/=="


def info(level: int) -> dict:
    payload = dict(fixture_payload("info"))
    limit = {0: 1000, 1: 5000, 2: 30000}[level]
    payload.update({"patronLevel": level, "tierName": {0: "Free", 1: "Tier 1", 2: "Tier 2"}[level], "monthlyLimit": limit, "remainingCalls": limit - 5, "usedCalls": 5})
    return payload


@pytest.fixture
def setup_app(tmp_path: Path):
    env = tmp_path / ".env"
    settings = load_settings(env_file=env, cfbd_api_key="", team="", conference="", log_dir=str(tmp_path / "logs"), data_dir=str(tmp_path / "data"))
    fake = FakeCfbd()
    fake.fixture("/teams/fbs", "teams_fbs")
    configure_logging(settings)
    app = create_app(settings, cfbd_transport=fake.transport)
    with TestClient(app, base_url="http://testserver") as client:
        yield app, client, fake, env
    shutdown_logging()
    restart.reset()


def test_setup_mode_leads_every_page_to_welcome(setup_app):
    app, client, fake, _ = setup_app
    assert app.state.settings.setup_needed
    page = client.get("/", follow_redirects=False)
    assert page.status_code == 302 and page.headers["location"] == "/welcome"
    data = client.get("/api/season/overview")
    assert data.status_code == 503 and data.json()["errors"][0]["code"] == "setup_needed"
    assert client.get("/welcome").status_code == 200 and "Your CFBD key" in client.get("/welcome").text
    for open_path in ("/setup", "/setup/qr.svg", "/api/setup", "/static/js/welcome.js", "/status"):
        assert client.get(open_path).status_code == 200, open_path
    health = client.get("/api/health").json()["data"]
    assert health["setup_needed"] is True and any(c["name"] == "setup" for c in health["checks"])
    state = client.get("/api/welcome").json()["data"]
    assert state["setupNeeded"] and state["canSetKey"] and state["plan"] is None and state["envWritable"]
    assert not any(r.url.path not in ("/info",) for r in fake.requests)  # setup mode calls nothing else


def test_a_key_is_checked_then_the_team_saved_and_the_server_restarts(setup_app):
    app, client, fake, env = setup_app
    fake.route("/info", json=info(0))
    checked = client.post("/api/welcome/key", json={"key": f"  {NEW_KEY}  "})
    body = checked.text
    assert checked.status_code == 200 and NEW_KEY not in body  # the key never comes back
    data = checked.json()["data"]
    assert data["keyChecked"] and data["plan"]["tierName"] == "Free" and data["plan"]["profile"] == "free" and data["plan"]["likedAllowed"] is False
    assert data["plan"]["monthlyLimit"] == 1000 and " of 1,000 calls" in data["plan"]["forecast"]["text"]  # the guard learned the key's limit too
    assert fake.requests[-1].headers["Authorization"] == f"Bearer {NEW_KEY}"
    teams = client.get("/api/welcome/teams").json()["data"]
    assert any(t["school"] == "Swampwater Tech" and t["conference"] == "Biscuit Belt" for t in teams["teams"])
    assert "Biscuit Belt" in teams["conferences"] and len(teams["states"]) > 5
    assert fake.requests[-1].headers["Authorization"] == f"Bearer {NEW_KEY}"  # the checked key, before any restart
    refused = client.post("/api/welcome/finish", json={"team": "Swampwater Tech", "liked": {"teams": ["Silo City"]}})
    assert refused.status_code == 422 and refused.json()["errors"][0]["code"] == "tier2_needed"
    assert client.post("/api/welcome/finish", json={"team": "Nowhere U"}).status_code == 422
    done = client.post("/api/welcome/finish", json={"team": "swampwater tech"})
    assert done.status_code == 200 and done.json()["data"]["restarting"] is True and NEW_KEY not in done.text
    assert restart.requested()
    text = env.read_text(encoding="utf-8")
    assert f"CFBD_API_KEY={NEW_KEY}" in text and "TEAM=Swampwater Tech" in text and "CONFERENCE=Biscuit Belt" in text
    assert "# The name the server announces" in text  # a new .env starts from .env.example, comments and all
    after = load_settings(env_file=env)
    assert not after.setup_needed and after.team == "Swampwater Tech" and after.api_key_configured


def test_liked_teams_need_tier_2_and_are_saved_with_the_settings(setup_app):
    app, client, fake, _ = setup_app
    fake.route("/info", json=info(2))
    assert client.post("/api/welcome/key", json={"key": NEW_KEY}).json()["data"]["plan"]["likedAllowed"] is True
    bad = client.post("/api/welcome/finish", json={"team": "Swampwater Tech", "liked": {"teams": ["Not A School"]}})
    assert bad.status_code == 422 and bad.json()["errors"][0]["code"] == "bad_liked"
    liked = {"teams": ["silo city", "Swampwater Tech"], "conferences": ["Gravy Ten"], "states": ["Ohio"]}
    done = client.post("/api/welcome/finish", json={"team": "Swampwater Tech", "liked": liked})
    assert done.status_code == 200
    prefs = PrefsStore(app.state.settings.data_dir).prefs
    assert prefs.likedTeams == ["Silo City"] and prefs.likedConferences == ["Gravy Ten"] and prefs.likedStates == ["Ohio"]  # the main team is not also liked


@pytest.mark.parametrize(
    "answer, status, code",
    [
        (httpx.Response(401, json={"message": "Unauthorized"}), 422, "key_refused"),
        (httpx.ConnectError("no route"), 503, "cfbd_unreachable"),
        (httpx.Response(200, text="not json"), 502, "cfbd_error"),
    ],
)
def test_a_key_cfbd_refuses_or_cannot_check(setup_app, answer, status, code):
    _, client, fake, env = setup_app

    def respond(request: httpx.Request) -> httpx.Response:
        if isinstance(answer, Exception):
            raise answer
        return answer

    fake.route("/info", handler=respond)
    response = client.post("/api/welcome/key", json={"key": NEW_KEY})
    assert response.status_code == status and response.json()["errors"][0]["code"] == code
    assert not env.exists() and client.get("/api/welcome").json()["data"]["keyChecked"] is False


@pytest.mark.parametrize("key", ["", "short", "has a space in the middle of it", "x" * 300, 42])
def test_junk_keys_are_refused_before_any_call(setup_app, key):
    _, client, fake, _ = setup_app
    before = len(fake.requests)
    response = client.post("/api/welcome/key", json={"key": key})
    assert response.status_code == 422 and len(fake.requests) == before
    assert client.post("/api/welcome/key", content=b"not json", headers={"content-type": "application/json"}).status_code == 400


def test_finish_needs_a_key_first(setup_app):
    _, client, _, _ = setup_app
    assert client.post("/api/welcome/finish", json={"team": "Swampwater Tech"}).json()["errors"][0]["code"] == "key_needed"
    assert client.get("/api/welcome/teams").status_code == 409


def test_a_set_key_changes_only_from_the_server_computer(app, client: TestClient, monkeypatch, tmp_path):
    response = client.post("/api/welcome/key", json={"key": NEW_KEY})  # the test client is not the server computer
    assert response.status_code == 403 and response.json()["errors"][0]["code"] == "server_computer_only"
    assert client.get("/api/welcome").json()["data"]["canSetKey"] is False
    monkeypatch.setattr("app.api.welcome.on_server_computer", lambda request: True)
    read_only = client.post("/api/welcome/key", json={"key": NEW_KEY})
    assert read_only.status_code == 409 and read_only.json()["errors"][0]["code"] == "env_read_only"  # the test settings come from the environment


def test_settings_show_the_plan_with_a_note_for_every_locked_feature(client: TestClient):
    data = client.get("/api/settings").json()["data"]
    summary = data["plan"]
    assert summary["profile"] in ("free", "tier2") and summary["plansUrl"].startswith("https://collegefootballdata.com")
    locked = [f for f in summary["features"] if f["available"] is False]
    assert all(f["note"].startswith("Shows with a Tier") for f in locked)
    assert data["canChangeKey"] is False


# --- the pieces -------------------------------------------------------------------------------------------


def test_env_writer_keeps_comments_replaces_in_place_and_quotes_when_needed(tmp_path: Path, caplog, monkeypatch):
    monkeypatch.delenv("TEAM", raising=False)  # the process environment would win over the file
    env = tmp_path / ".env"
    env.write_text("# my settings\nTEAM=Old School\n# TEAM=commented copy stays\nPORT=8642\n", encoding="utf-8")
    set_values(env, {"TEAM": "Texas A&M", "CONFERENCE": "Big Ten", "CFBD_API_KEY": NEW_KEY}, template=tmp_path / "none")
    lines = env.read_text(encoding="utf-8").splitlines()
    assert lines[:4] == ["# my settings", "TEAM=Texas A&M", "# TEAM=commented copy stays", "PORT=8642"]
    assert "CONFERENCE=Big Ten" in lines and f"CFBD_API_KEY={NEW_KEY}" in lines
    assert NEW_KEY not in caplog.text  # names only in the log
    set_values(env, {"TEAM": "Hawai'i"}, template=tmp_path / "none")
    assert load_settings(env_file=env, cfbd_api_key=TEST_KEY).team == "Hawai'i"  # quoted and read back exactly
    assert quote("plain") == "plain" and quote('say "hi"') == '"say \\"hi\\""'
    with pytest.raises(ValueError):
        set_values(env, {"TEAM": "two\nlines"})
    with pytest.raises(ValueError):
        set_values(env, {"bad name": "x"})


def test_the_restart_signal_ends_a_real_server_and_run_server_says_so(tmp_path: Path):
    import socket

    from app.serving import run_server

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    settings = load_settings(env_file=None, cfbd_api_key="", team="", conference="", host="127.0.0.1", log_dir=str(tmp_path / "logs"), data_dir=str(tmp_path / "data"), port=port)
    configure_logging(settings)
    codes: list[int] = []
    thread = threading.Thread(target=lambda: codes.append(run_server(settings)), daemon=True)
    thread.start()
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:  # a loaded machine (the parallel run) can take far longer than 3 seconds to listen
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            break
        except OSError:
            time.sleep(0.2)
    time.sleep(0.5)
    restart.request("test")
    thread.join(60)
    shutdown_logging()
    restart.reset()
    assert codes == [restart.RESTART]


def test_the_cli_serves_again_after_a_restart(tmp_path: Path, monkeypatch):
    from app import cli

    monkeypatch.delenv("TEAM", raising=False)
    monkeypatch.delenv("CONFERENCE", raising=False)
    env = tmp_path / ".env"
    env.write_text(f"CFBD_API_KEY={TEST_KEY}\nTEAM=Swampwater Tech\nCONFERENCE=Biscuit Belt\nDATA_DIR={(tmp_path / 'data').as_posix()}\nLOG_DIR={(tmp_path / 'logs').as_posix()}\n", encoding="utf-8")
    seen: list[tuple[str, bool]] = []
    answers = iter([restart.RESTART, 0])

    def fake_run(settings, **kwargs):
        seen.append((settings.team, kwargs.get("restarting", False)))
        if len(seen) == 1:
            set_values(env, {"TEAM": "Silo City", "CONFERENCE": "Gravy Ten"})  # what the welcome page writes
        return next(answers)

    monkeypatch.setattr("app.serving.run_server", fake_run)
    assert cli.main(["--no-browser"], env_file=env) == 0
    assert seen == [("Swampwater Tech", False), ("Silo City", True)]  # the second serve reads the new .env


def test_plan_profiles_and_forecast():
    caps = Capabilities()
    assert plan.profile(caps, 1000) == "free" and plan.profile(caps, 30000) == "tier2"  # unknown tier: by the budget
    caps.tier_level = 1
    assert plan.profile(caps, 5000) == "free" and not plan.allows_liked(caps)  # Tier 1 runs the Free profile for now
    caps.tier_level = 2
    assert plan.profile(caps, 1000) == "tier2" and plan.allows_liked(caps)
    now = datetime(2026, 10, 11, tzinfo=timezone.utc)  # ten days into a 31-day month
    fits = plan.forecast(200, 1000, now)
    assert fits["fits"] is True and fits["projected"] == 620
    over = plan.forecast(500, 1000, now)
    assert over["fits"] is False and over["runsOutOn"] == "2026-10-21" and "lean on its cache" in over["text"]
    assert plan.forecast(None, 1000, now)["projected"] is None
