"""Phase 9: server-side settings (defaults, saving, refusals, a broken file), the settings routes
with the quota readout and no secrets, the start-at-login launcher with a captured PowerShell
runner, the archive list and one game read back with CFBD's post-game data, unreadable archive
files, and the notes runner with a missing command and with a fake command whose answer the app saves."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services.launcher import SHORTCUT_NAME, Launcher
from app.services.notes_task import NotesRunner
from app.services.prefs import PrefsError, PrefsStore
from tests import league_facts as facts
from tests.conftest import ROLES, TEST_KEY, FakeCfbd, fixture_payload

LAST_GAME = 526000600


# --- settings store --------------------------------------------------------------------------------------


def test_prefs_default_save_refuse_and_survive_a_broken_file(tmp_path: Path):
    store = PrefsStore(tmp_path)
    assert store.as_dict()["delaySeconds"] == 30 and store.as_dict()["theme"] == "dark" and store.error is None
    store.update({"delaySeconds": 45, "theme": "light", "radioSourceId": ""})
    again = PrefsStore(tmp_path)
    assert again.as_dict()["delaySeconds"] == 45 and again.as_dict()["theme"] == "light" and again.as_dict()["radioSourceId"] is None
    with pytest.raises(PrefsError, match="delaySeconds"):
        store.update({"delaySeconds": 500})
    with pytest.raises(PrefsError, match="unknown setting"):
        store.update({"colour": "orange"})
    with pytest.raises(PrefsError, match="theme"):
        store.update({"theme": "neon"})
    with pytest.raises(PrefsError, match="notesCommand"):
        store.update({"notesCommand": "   "})
    assert store.as_dict()["delaySeconds"] == 45  # a refused change leaves the saved value alone
    (tmp_path / "settings.json").write_text("{not json", encoding="utf-8")
    broken = PrefsStore(tmp_path)
    assert broken.as_dict()["delaySeconds"] == 30 and "defaults apply" in broken.error
    (tmp_path / "settings.json").write_text(json.dumps({"delaySeconds": "lots"}), encoding="utf-8")
    assert "bad value" in PrefsStore(tmp_path).error


def test_settings_routes_show_options_and_quota_without_secrets(app, client: TestClient):
    body = client.get("/api/settings").json()
    data = body["data"]
    assert data["prefs"]["delaySeconds"] == 30 and data["prefs"]["theme"] == "dark"
    assert data["radioSources"] == []  # no station is built in (public release Phase 3); RADIO_SOURCES names the team's own
    assert set(data["quota"]) >= {"used", "remaining", "budget", "pctUsed", "mode", "tierName"}
    assert data["server"]["team"] == "Swampwater Tech" and "notes" in data and "autoStart" in data
    assert TEST_KEY not in json.dumps(body) and "cfbd_api_key" not in json.dumps(body)
    saved = client.put("/api/settings", json={"theme": "light", "delaySeconds": 60}).json()
    assert saved["data"]["prefs"]["theme"] == "light" and saved["data"]["prefs"]["delaySeconds"] == 60 and saved["errors"] == []
    assert (app.state.settings.data_dir / "settings.json").is_file()
    refused = client.put("/api/settings", json={"delaySeconds": -5})
    assert refused.status_code == 422 and "delaySeconds" in refused.json()["errors"][0]["message"]
    assert client.put("/api/settings", content=b"nope", headers={"Content-Type": "application/json"}).status_code == 400
    assert client.get("/api/settings").json()["data"]["prefs"]["delaySeconds"] == 60


# --- launcher ---------------------------------------------------------------------------------------------------


def test_launcher_writes_and_removes_the_startup_shortcut(tmp_path: Path, app, client: TestClient):
    calls: list[list[str]] = []
    appdata = tmp_path / "AppData"
    startup = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    startup.mkdir(parents=True)
    root = tmp_path / "project"
    root.mkdir()
    (root / "start.ps1").write_text("# stub", encoding="utf-8")

    def runner(args: list[str]) -> tuple[int, str]:
        calls.append(args)
        (startup / SHORTCUT_NAME).write_text("lnk", encoding="utf-8")  # what WScript.Shell would do
        return 0, ""

    launcher = Launcher(root, runner=runner, platform="win32", appdata=str(appdata), home=tmp_path / "home")
    assert launcher.status() == {"supported": True, "system": "windows", "method": "a shortcut in the Windows Startup folder", "tray": True, "enabled": False,
                                 "shortcut": str(startup / SHORTCUT_NAME), "script": str(root / "start.ps1"), "scriptExists": True}
    on = launcher.set_enabled(True, tray=True)
    assert on["enabled"] and "error" not in on and len(calls) == 1
    assert "CreateShortcut" in calls[0][0] and "-Tray" in calls[0][0] and str(root / "start.ps1") in calls[0][0]
    off = launcher.set_enabled(False)
    assert not off["enabled"] and not (startup / SHORTCUT_NAME).exists()
    elsewhere = Launcher(root, runner=runner, platform="sunos5", appdata="")
    assert elsewhere.set_enabled(True)["error"] and not elsewhere.supported and elsewhere.desktop_shortcut()["error"]

    # through the settings route, with the app's launcher swapped for the fake
    app.state.launcher = launcher
    body = client.put("/api/settings", json={"autoStart": True}).json()
    assert body["data"]["prefs"]["autoStart"] and body["data"]["autoStart"]["enabled"] and body["errors"] == []

    def failing(args: list[str]) -> tuple[int, str]:
        return 1, "COM error"

    launcher.runner = failing
    body = client.put("/api/settings", json={"autoStart": False}).json()
    assert body["data"]["autoStart"]["enabled"] is False and body["errors"] == []  # removal needs no PowerShell
    body = client.put("/api/settings", json={"autoStart": True}).json()
    assert body["data"]["prefs"]["autoStart"] and any(e["code"] == "autostart_failed" and "COM error" in e["message"] for e in body["errors"])


def test_launcher_on_linux_is_a_systemd_user_service(tmp_path: Path):
    calls: list[list[str]] = []
    root = tmp_path / "project dir"  # a space in the path is quoted in the unit and the launcher
    root.mkdir()
    (root / "start.sh").write_text("#!/usr/bin/env bash" + chr(10), encoding="utf-8")
    home = tmp_path / "home"
    launcher = Launcher(root, runner=lambda args: calls.append(args) or (0, ""), platform="linux", home=home)
    unit = home / ".config" / "systemd" / "user" / "kickoff-companion.service"
    status = launcher.status()
    assert status["supported"] and status["system"] == "linux" and status["tray"] is False and status["shortcut"] == str(unit) and not status["enabled"]
    on = launcher.set_enabled(True)
    assert on["enabled"] and "error" not in on
    text = unit.read_text(encoding="utf-8")
    assert f"ExecStart=/bin/bash '{root / 'start.sh'}' --service" in text and "WantedBy=default.target" in text and "Restart=on-failure" in text
    assert calls == [["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "kickoff-companion.service"]]  # enabled for next login, not started
    calls.clear()
    off = launcher.set_enabled(False)
    assert not off["enabled"] and not unit.exists() and calls[0] == ["systemctl", "--user", "disable", "kickoff-companion.service"]
    # no systemd: the file is not left behind and the message says why
    broken = Launcher(root, runner=lambda args: (1, "systemctl: command not found"), platform="linux", home=home)
    result = broken.set_enabled(True)
    assert "systemd" in result["error"] and not unit.exists() and not result["enabled"]
    icon = launcher.desktop_shortcut()
    menu = home / ".local" / "share" / "applications" / "kickoff-companion.desktop"
    assert icon["created"] and Path(icon["path"]).is_file() and menu.is_file()
    entry = menu.read_text(encoding="utf-8")
    assert entry.startswith("[Desktop Entry]") and "Terminal=true" in entry and "start.sh" in entry and "icon-192.png" in entry


def test_launcher_on_macos_is_a_launch_agent(tmp_path: Path):
    import plistlib

    root = tmp_path / "project"
    root.mkdir()
    home = tmp_path / "home"
    launcher = Launcher(root, runner=lambda args: (1, "never called"), platform="darwin", home=home)
    assert launcher.set_enabled(True)["error"] == "start.sh is missing from the project folder"
    (root / "start.sh").write_text("#!/usr/bin/env bash" + chr(10), encoding="utf-8")
    on = launcher.set_enabled(True)
    agent = home / "Library" / "LaunchAgents" / "com.kickoff-companion.server.plist"
    assert on["enabled"] and on["system"] == "mac" and "error" not in on
    plist = plistlib.loads(agent.read_bytes())
    assert plist["ProgramArguments"] == ["/bin/bash", str(root / "start.sh"), "--service"] and plist["RunAtLoad"] is True and plist["KeepAlive"] == {"SuccessfulExit": False}
    assert not launcher.set_enabled(False)["enabled"] and not agent.exists()
    icon = launcher.desktop_shortcut()
    command = home / "Desktop" / "Kickoff Companion.command"
    assert icon["created"] and command.read_text(encoding="utf-8").startswith("#!/bin/bash") and "start.sh" in command.read_text(encoding="utf-8")


# --- archive ------------------------------------------------------------------------------------------------------


def route_archive(fake: FakeCfbd) -> None:
    def games(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("team") == "Swampwater Tech":
            return httpx.Response(200, json=fixture_payload("games_team"))
        if request.url.params.get("team"):
            return httpx.Response(200, json=fixture_payload("games_opponent"))
        return httpx.Response(200, json=fixture_payload("games_week") + fixture_payload("games_team"))

    fake.route("/games", handler=games)
    fake.fixture("/metrics/wp", "metrics_wp")
    fake.fixture("/ppa/games", "ppa_games")
    fake.route("/ppa/players/games", handler=lambda r: httpx.Response(200, json=fixture_payload("ppa_players_games") if r.url.params.get("team") == "Swampwater Tech" else []))
    fake.fixture("/teams/fbs", "teams_fbs")
    fake.route("/records", handler=lambda r: httpx.Response(200, json=fixture_payload("records_all")))
    fake.fixture("/rankings", "rankings")
    fake.fixture("/stats/season", "stats_season_fbs")
    fake.fixture("/games/media", "games_media")
    fake.fixture("/lines", "lines")
    fake.fixture("/metrics/wp/pregame", "metrics_wp_pregame")
    fake.fixture("/stats/season/advanced", "stats_season_advanced_fbs")
    fake.route("/stats/player/season", handler=lambda r: httpx.Response(200, json=fixture_payload("stats_player_season_team") if r.url.params.get("team") == "Swampwater Tech" else []))
    fake.fixture("/teams/matchup", "teams_matchup")
    fake.fixture("/venues", "venues")
    fake.fixture("/ratings/sp", "ratings_sp")
    fake.route("/games/teams", handler=lambda r: httpx.Response(200, json=fixture_payload("games_teams") if r.url.params.get("week") == ROLES["LASTWEEK"] else []))
    fake.route("/games/players", handler=lambda r: httpx.Response(200, json=fixture_payload("games_players") if r.url.params.get("week") == ROLES["LASTWEEK"] else []))


def write_archive_file(app) -> Path:
    from app.cfbd.models import LiveGame, parse_one
    from app.live.events import events_from_live
    from app.live.state import derive_state

    game = parse_one(LiveGame, fixture_payload("live_plays"), context="t")
    events = events_from_live(game, datetime(2026, 9, 20, 3, 0, tzinfo=timezone.utc))
    state = derive_state(events, game_id=LAST_GAME, home="Silver Dollar", away="Swampwater Tech", mode="archive")
    folder = app.state.settings.data_dir / "archive"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{LAST_GAME}.json"
    path.write_text(json.dumps({"gameId": LAST_GAME, "week": 3, "home": "Silver Dollar", "away": "Swampwater Tech", "kickoff": "2026-09-19T23:00:00+00:00", "savedAt": "2026-09-20T03:00:00+00:00", "winProbability": None, "state": state}), encoding="utf-8")
    return path


def test_archive_lists_and_reads_back_a_watched_game(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_archive(fake_cfbd)
    client.portal.call(app.state.live.stop_background)
    app.state.cfbd._clock = lambda: datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc)
    assert client.get("/api/archive").json()["data"] == {**client.get("/api/archive").json()["data"], "games": [], "count": 0, "skipped": 0}
    write_archive_file(app)
    (app.state.settings.data_dir / "archive" / "junk.json").write_text("{", encoding="utf-8")
    (app.state.settings.data_dir / "archive" / "999.json").write_text(json.dumps({"gameId": "x"}), encoding="utf-8")
    listing = client.get("/api/archive").json()["data"]
    assert listing["count"] == 1 and listing["skipped"] == 2
    row = listing["games"][0]
    ours, theirs = facts.scores(facts.last_game())
    plays, drives = facts.live_counts()
    assert row["gameId"] == LAST_GAME and row["opponent"] == "Silver Dollar" and row["usScore"] == ours and row["themScore"] == theirs and row["plays"] == plays and row["hasWinProbability"] is False
    body = client.get(f"/api/archive/{LAST_GAME}").json()
    data = body["data"]
    rate = facts.live_team()["successRate"]
    assert data["state"]["status"] == "final" and data["state"]["counts"]["drives"] == drives and data["state"]["feedStats"]["Swampwater Tech"]["successRate"] == rate
    red = data["state"]["box"]["Swampwater Tech"]["redZone"]
    assert data["state"]["box"]["Swampwater Tech"]["successRate"] == rate and data["state"]["box"]["Swampwater Tech"]["successCounts"] is None
    assert isinstance(red["trips"], int) and 0 <= red["scores"] <= red["trips"] and red["trips"] >= 1  # C3: a 50-point game reached the red zone
    assert data["winProbability"]["available"] and len(data["winProbability"]["series"]) == facts.wp_points()  # from CFBD since the file had none
    assert data["ppa"]["available"] and data["ppa"]["teams"]["us"]["gameId"] == LAST_GAME and data["ppa"]["players"]["us"]
    assert data["final"]["available"] and data["game"]["completed"] and data["them"]["school"] == "Silver Dollar" and data["us"]["abbreviation"] == "SWT"
    assert "boxTeams" in data["parts"] and "wp" in data["parts"]
    assert client.get("/api/archive/526001015").status_code == 404 and client.get("/api/archive/abc").status_code == 404


# --- notes runner -----------------------------------------------------------------------------------------------------


def test_notes_runner_reports_a_missing_command_and_runs_a_fake_one(app, client: TestClient, fake_cfbd: FakeCfbd, tmp_path: Path):
    fake_cfbd.route("/games", handler=lambda r: httpx.Response(200, json=fixture_payload("games_team")))
    client.portal.call(app.state.live.stop_background)
    app.state.cfbd._clock = lambda: datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc)
    runner: NotesRunner = app.state.notes
    status = client.get("/api/notes/run").json()["data"]
    assert status["command"] == "claude" and status["running"] is False and status["promptFile"].endswith("PROMPT.md")
    app.state.prefs.update({"notesCommand": str(tmp_path / "no-such-tool")})
    refused = client.post("/api/notes/run", json={}).json()
    assert refused["errors"] and "not found" in refused["errors"][0]["message"] and refused["data"]["commandFound"] is False
    # a fake tool: answers with notes JSON on its output (public release Phase 6: the app reads and saves the answer)
    notes_dir = app.state.settings.data_dir / "notes"
    target = notes_dir / "526001015.json"
    answer = json.dumps({"gameId": 526001015, "sections": [{"heading": "Coaching matchup", "paragraphs": ["Text."]}], "sources": [{"label": "Beat", "url": "https://example.invalid/beat"}]})
    if sys.platform.startswith("win"):
        tool = tmp_path / "fake-claude.cmd"
        tool.write_text(f'@echo off\r\necho prompt was received\r\necho {answer}\r\n', encoding="utf-8")
    else:
        tool = tmp_path / "fake-claude"
        tool.write_text(f"#!/bin/sh\necho 'prompt was received'\necho '{answer}'\n", encoding="utf-8")
        os.chmod(tool, 0o755)
    app.state.prefs.update({"notesCommand": str(tool)})
    started = client.post("/api/notes/run", json={}).json()
    assert started["errors"] == [] and started["data"]["gameId"] == 526001015 and started["data"]["commandFound"]
    for _ in range(100):
        status = client.get("/api/notes/run").json()["data"]
        if not status["running"]:
            break
        time.sleep(0.1)
    assert status["running"] is False and status["exitCode"] == 0 and status["error"] is None and status["fileWritten"] is True
    assert target.is_file() and json.loads(target.read_text(encoding="utf-8"))["sections"][0]["heading"] == "Coaching matchup"
    assert "526001015" in runner.build_prompt({"gameId": 526001015, "home": "Swampwater Tech", "away": "Diner Tech"})
    log = app.state.settings.log_dir / "notes-526001015.log"
    assert log.is_file() and "prompt was" in log.read_text(encoding="utf-8")
    assert client.post("/api/notes/run", json={"gameId": 12345}).status_code == 404
