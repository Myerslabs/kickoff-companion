"""Game-night logging (2026-09-26): tablet errors reach the server log with a rate cap and repeat
suppression, access lines for page files and headshots stay out of the log, and the engine writes
a one-minute snapshot line and a five-minute state file during the window."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api import client_log
from app.live.engine import WINDOW_AFTER, WINDOW_BEFORE, GameWindow, LiveEngine
from app.live.events import LiveEvent
from app.logging_setup import DroppedConnectionFilter, QuietAccessFilter
from tests.conftest import PROJECT_ROOT
from tests.test_phase8 import KICKOFF, NEXT_GAME, quiet_engine


@pytest.fixture(autouse=True)
def fresh_rate_state():
    client_log.reset()
    yield
    client_log.reset()


def test_a_tablet_error_lands_in_the_log(client: TestClient, caplog):
    caplog.set_level(logging.INFO, logger="kickoff.client")
    body = {"level": "error", "kind": "error", "message": "TypeError: x is undefined at /static/js/views/live.js:10:5", "stack": "at render (live.js:10)", "page": "#live", "agent": "Mozilla/5.0 (iPad)"}
    assert client.post("/api/client-log", json=body).json()["data"] == {"logged": True}
    records = [r for r in caplog.records if r.name == "kickoff.client"]
    assert any(r.levelno == logging.ERROR and "TypeError: x is undefined" in r.getMessage() and "page=#live" in r.getMessage() and "stack: at render" in r.getMessage() for r in records)
    assert any("Mozilla/5.0 (iPad)" in r.getMessage() for r in records)
    warn = client.post("/api/client-log", json={"level": "warn", "message": "Live sheet: the visitors did not load"})
    assert warn.json()["data"]["logged"] and any(r.levelno == logging.WARNING for r in caplog.records if r.name == "kickoff.client")


def test_repeats_are_counted_and_the_rate_is_capped(client: TestClient, caplog):
    caplog.set_level(logging.INFO, logger="kickoff.client")
    same = {"message": "the same thing"}
    assert client.post("/api/client-log", json=same).json()["data"]["logged"] is True
    assert client.post("/api/client-log", json=same).json()["data"] == {"logged": False, "reason": "repeat"}
    for i in range(client_log.RATE_MAX):
        client.post("/api/client-log", json={"message": f"message {i}"})
    assert client.post("/api/client-log", json={"message": "one too many"}).json()["data"] == {"logged": False, "reason": "rate"}
    logged = [r for r in caplog.records if r.name == "kickoff.client" and "message " in r.getMessage()]
    assert len(logged) == client_log.RATE_MAX - 1  # the first report used one slot


def test_bad_reports_are_refused(client: TestClient):
    assert client.post("/api/client-log", content=b"not json", headers={"Content-Type": "application/json"}).status_code == 422
    assert client.post("/api/client-log", json={"level": "fatal", "message": "x"}).status_code == 422
    assert client.post("/api/client-log", json={"message": "x" * 3000}).status_code == 422
    assert client.post("/api/client-log", json={}).status_code == 422
    assert client.post("/api/client-log", json=["a list"]).status_code == 422


def access_record(path: str, status: int = 200) -> logging.LogRecord:
    return logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d', ("192.0.2.166:5000", "GET", path, "1.1", status), None)


def test_page_files_and_headshots_stay_out_of_the_access_log():
    quiet = QuietAccessFilter()
    assert not quiet.filter(access_record("/static/js/views/live.js"))
    assert not quiet.filter(access_record("/media/headshot/4536127"))
    assert quiet.filter(access_record("/media/headshot/1", 500))  # a failure still shows
    assert quiet.filter(access_record("/api/live/state?delay=30"))
    assert quiet.filter(access_record("/"))
    assert quiet.filter(logging.LogRecord("kickoff.live", logging.INFO, __file__, 1, "/static/ in a message", (), None))


def test_the_engine_writes_game_snapshots(app, client: TestClient, caplog):
    caplog.set_level(logging.INFO, logger="kickoff.live.snapshot")
    quiet_engine(app, client)
    engine: LiveEngine = app.state.live
    clock = {"now": KICKOFF + timedelta(minutes=40)}
    app.state.cfbd._clock = lambda: clock["now"]
    window = GameWindow(NEXT_GAME, "Swampwater Tech", "Diner Tech", 4, KICKOFF, KICKOFF - WINDOW_BEFORE, KICKOFF + WINDOW_AFTER)
    engine.window = window
    engine._open_window(window)
    client.portal.call(engine.publish, [LiveEvent("play:1", "play", NEXT_GAME, clock["now"], {"id": "1", "period": 2, "offense": "Swampwater Tech", "defense": "Diner Tech", "playType": "Rush", "yardsGained": 7, "text": "#1 A.B rush for 7 yards"}), LiveEvent("status", "status", NEXT_GAME, clock["now"], {"status": "in_progress", "period": 2, "clock": {"minutes": 4, "seconds": 5}, "homeScore": 17, "awayScore": 6, "down": 1, "distance": 10, "yardsToGoal": 40, "possession": "Swampwater Tech"})])
    client.portal.call(engine._snapshot, window)
    lines = [r.getMessage() for r in caplog.records if r.name == "kickoff.live.snapshot"]
    assert len(lines) == 1 and "Q2 4:05" in lines[0] and "Diner Tech 6-17" in lines[0] and "1 plays" in lines[0] and "feed" in lines[0]
    states = sorted((app.state.settings.data_dir / "live" / str(NEXT_GAME)).glob("state-*.json"))
    assert len(states) == 1
    saved = json.loads(states[0].read_text(encoding="utf-8"))["payload"]
    assert saved["homeScore"] == 17 and "plays" not in saved and "drives" not in saved and saved["box"]["Swampwater Tech"]["rushingYards"] == 7
    clock["now"] += timedelta(seconds=30)
    client.portal.call(engine._snapshot, window)
    assert len([r for r in caplog.records if r.name == "kickoff.live.snapshot"]) == 1  # once a minute
    clock["now"] += timedelta(seconds=40)
    client.portal.call(engine._snapshot, window)
    assert len([r for r in caplog.records if r.name == "kickoff.live.snapshot"]) == 2
    assert len(list((app.state.settings.data_dir / "live" / str(NEXT_GAME)).glob("state-*.json"))) == 1  # the state file every five minutes
    clock["now"] += timedelta(minutes=5)
    client.portal.call(engine._snapshot, window)
    assert len(list((app.state.settings.data_dir / "live" / str(NEXT_GAME)).glob("state-*.json"))) == 2


NODE = """import assert from "node:assert/strict";
const { admit } = await import(process.argv[2]);
const t = 1_000_000;
assert.equal(admit("a", t), true);
assert.equal(admit("a", t + 1000), false);  // the same message inside a minute
assert.equal(admit("a", t + 61_000), true);
for (let i = 0; i < 19; i += 1) assert.equal(admit(`m${i}`, t + 62_000), true);  // the first "a" has left the window: "a" again plus 19 fill the minute
assert.equal(admit("one more", t + 62_000), false);  // twenty a minute
assert.equal(admit("later", t + 200_000), true);
console.log("ok");
"""


def test_the_client_side_cap_under_node(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = tmp_path / "admit.mjs"
    script.write_text(NODE, encoding="utf-8")
    result = subprocess.run([node, str(script), (PROJECT_ROOT / "static" / "js" / "client-log.js").as_uri()], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert result.returncode == 0 and "ok" in result.stdout, result.stderr[-800:]


def test_a_dropped_device_is_one_info_line():
    try:
        raise ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host")
    except ConnectionResetError:
        import sys

        info = sys.exc_info()
    record = logging.LogRecord("asyncio", logging.ERROR, __file__, 1, "Exception in callback %s", ("_call_connection_lost",), info)
    assert DroppedConnectionFilter().filter(record) and record.levelno == logging.INFO and record.exc_info is None
    assert record.getMessage() == "A device dropped its connection (ConnectionResetError)"
    other = logging.LogRecord("asyncio", logging.ERROR, __file__, 1, "boom", (), None)
    assert DroppedConnectionFilter().filter(other) and other.levelno == logging.ERROR
