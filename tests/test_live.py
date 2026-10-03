"""The live engine: normalizers from both sources, the store's dedupe and corrections, the
delay buffer, a full replay at high speed with zero errors, the stream with reconnect, the
poller's gating on the window, the tier, and connected clients, the raw recorder, and the
quota projection."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.cfbd.models import Drive, LiveGame, Play, parse_one, parse_records
from app.db import Database
from app.live.events import LiveEvent, events_from_finished, events_from_live, key_play_flags, play_success
from app.live.state import derive_state
from app.live.store import EventStore
from tests.conftest import FakeCfbd, fixture_payload

LAST_GAME = 526000600
NEXT_KICKOFF = datetime(2026, 9, 26, 19, 30, tzinfo=timezone.utc)


def route_live(fake: FakeCfbd, live_payload=None) -> None:
    fake.route("/games", handler=lambda r: httpx.Response(200, json=fixture_payload("games_team")))
    fake.fixture("/plays", "plays")
    fake.fixture("/drives", "drives")
    fake.fixture("/metrics/wp", "metrics_wp")
    fake.route("/games/teams", handler=lambda r: httpx.Response(200, json=[{**fixture_payload("games_teams")[0], "id": 526001015}]))
    fake.route("/games/players", handler=lambda r: httpx.Response(200, json=[{**fixture_payload("games_players")[0], "id": 526001015}]))
    if live_payload is not None:
        fake.route("/live/plays", handler=lambda r: httpx.Response(200, json=live_payload() if callable(live_payload) else live_payload))


def live_document(plays: int = 3, final: bool = False, extra_play=None) -> dict:
    """A live document in the spec's shape (no real sample exists on the Free tier yet)."""
    drive_plays = [
        {"id": f"p{i}", "homeScore": 0, "awayScore": 7 if i >= 3 else 0, "period": 1, "clock": f"{14 - i}:{30:02d}", "wallClock": f"2026-09-26T19:{40 + i:02d}:00.000Z", "team": "Swampwater Tech", "down": 1 if i == 1 else 2, "distance": 10, "yardsToGoal": 75 - 12 * i, "yardsGained": 12 if i < 3 else 39, "playType": "Rush" if i < 3 else "Passing Touchdown", "playText": f"Play {i}"}
        for i in range(1, plays + 1)
    ]
    if extra_play:
        drive_plays.append(extra_play)
    return {
        "id": 526001015,
        "status": "completed" if final else "in_progress",
        "period": 1,
        "clock": "11:30",
        "possession": "Swampwater Tech",
        "down": 1,
        "distance": 10,
        "yardsToGoal": 65,
        "teams": [{"teamId": 1, "team": "Diner Tech", "homeAway": "home", "points": 0}, {"teamId": 57, "team": "Swampwater Tech", "homeAway": "away", "points": 7 if plays >= 3 else 0}],
        "drives": [{"id": "d1", "offense": "Swampwater Tech", "defense": "Diner Tech", "playCount": len(drive_plays), "yards": 75, "startPeriod": 1, "startClock": "15:00", "startYardsToGoal": 75, "result": "TD" if plays >= 3 else None, "pointsGained": 7 if plays >= 3 else 0, "plays": drive_plays}],
    }


# --- normalizers ---------------------------------------------------------------------------------


def test_finished_game_normalizes_in_order_with_flags():
    plays = parse_records(Play, fixture_payload("plays"), context="t").records
    drives = parse_records(Drive, fixture_payload("drives"), context="t").records
    timeline = events_from_finished(LAST_GAME, plays, drives, "Silver Dollar", "Swampwater Tech")
    kinds = [e.kind for e, _ in timeline]
    assert kinds.count("play") == len(plays) and kinds.count("drive") == len({p.drive_id for p in plays if p.drive_id})
    assert kinds[0] == "drive" and kinds[1] == "play"
    first = timeline[1][0].data
    assert first["playType"] == "Kickoff" and first["period"] == 1 and first["clock"] == {"minutes": 15, "seconds": 0} and first["homeScore"] == 0
    flagged = [e.data for e, _ in timeline if e.kind == "play" and e.data["flags"]]
    assert any("td" in p["flags"] for p in flagged) and any("explosive" in p["flags"] for p in flagged)
    assert all(e.data["success"] is None for e, _ in timeline if e.kind == "play" and e.data["playType"] == "Kickoff")
    periods = [e.data["period"] for e, _ in timeline if e.kind == "play"]
    assert periods == sorted(periods)


def test_live_document_normalizes_and_junk_is_dropped():
    doc = live_document(3, extra_play={"id": None, "playType": 5})
    doc["drives"].append("junk")
    game = parse_one(LiveGame, doc, context="t")
    events = events_from_live(game, datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc))
    kinds = [e.kind for e in events]
    assert kinds == ["drive", "play", "play", "play", "status"]
    td = events[3].data
    assert td["scoring"] and "td" in td["flags"] and "explosive" in td["flags"] and td["offenseScore"] == 7 and td["homeScore"] == 0
    assert events[1].data["clock"] == {"minutes": 13, "seconds": 30} and events[1].data["defense"] == "Diner Tech"
    status = events[-1].data
    assert status["status"] == "in_progress" and status["homeScore"] == 0 and status["awayScore"] == 7 and status["possession"] == "Swampwater Tech"
    assert events_from_live(parse_one(LiveGame, live_document(3, final=True), context="t"), datetime.now(timezone.utc))[-1].data["status"] == "final"


def test_flags_and_success_rules():
    assert key_play_flags("Rushing Touchdown", "", 3, True, 2) == ["td"]
    assert key_play_flags("Pass Interception Return", "", 0, False, 3) == ["turnover"]
    assert key_play_flags("Sack", "", -8, False, 4) == ["sack", "fourth"]
    assert key_play_flags("Penalty", "personal foul, 15 yards", 15, False, 1) == ["penalty"]
    assert key_play_flags("Punt", "", 45, False, 4) == []
    assert play_success(1, 10, 5, "Rush", False) is True and play_success(1, 10, 4, "Rush", False) is False
    assert play_success(2, 10, 7, "Pass Reception", False) is True and play_success(3, 8, 7, "Rush", False) is False
    assert play_success(4, 1, 0, "Passing Touchdown", True) is True and play_success(1, 10, 20, "Kickoff", False) is None
    assert play_success(None, 10, 5, "Rush", False) is None and play_success(1, "x", 5, "Rush", False) is None


# --- store: dedupe, corrections, delay -------------------------------------------------------------


def test_store_dedupes_corrects_and_releases_by_delay(tmp_path: Path):
    db = Database(tmp_path / "live.db")
    store = EventStore(db)
    t0 = datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc)
    play = LiveEvent("play:1", "play", 1, t0, {"id": "1", "text": "Run for 3"})
    assert [e.seq for e in store.append([play])] == [1]
    assert store.append([LiveEvent("play:1", "play", 1, t0 + timedelta(seconds=12), {"id": "1", "text": "Run for 3"})]) == []
    corrected = store.append([LiveEvent("play:1", "play", 1, t0 + timedelta(seconds=24), {"id": "1", "text": "Run for 4"})])
    assert corrected[0].version == 2 and corrected[0].seq == 2
    store.append([LiveEvent("play:2", "play", 1, t0 + timedelta(seconds=60), {"id": "2", "text": "Pass"})])
    assert [e.id for e in store.released(1, t0 + timedelta(seconds=30))] == ["play:1", "play:1"]
    assert store.released(1, t0 + timedelta(seconds=15)) and store.released(1, t0 + timedelta(seconds=15))[0].version == 1
    assert store.released(1, t0 - timedelta(seconds=1)) == []
    assert store.pending_after(1, t0 + timedelta(seconds=30), 2) and not store.pending_after(1, t0 + timedelta(seconds=61), 2)
    assert [e.id for e in store.released(1, t0 + timedelta(seconds=90), after_seq=2)] == ["play:2"]
    state = derive_state(store.released(1, t0 + timedelta(seconds=90)), game_id=1, home="A", away="B")
    assert [p["text"] for p in state["plays"]] == ["Pass", "Run for 4"]  # newest first, the correction applied
    assert store.count(1) == 3 and store.games() == [1]
    assert store.clear(1) == 3 and store.count(1) == 0
    db.close()


# --- replay end to end through the app ---------------------------------------------------------------


def test_replay_runs_a_finished_game_end_to_end_at_speed(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_live(fake_cfbd)
    engine = app.state.live
    started = client.post("/api/live/replay", json={"gameId": LAST_GAME, "speed": 3600})
    assert started.status_code == 200 and started.json()["data"]["running"]
    for _ in range(600):
        status = client.get("/api/live/replay").json()["data"]
        if not status["running"]:
            break
        import time

        time.sleep(0.05)
    assert status["finished"] and status["error"] is None
    plays = len(fixture_payload("plays"))
    drives = len({p["driveId"] for p in fixture_payload("plays") if p.get("driveId")})
    assert status["emitted"] == plays + drives
    state = client.get("/api/live/state?delay=0").json()
    data = state["data"]
    assert state["meta"]["source"] == "replay" or data["mode"] in ("idle", "replay")
    assert data["status"] == "final" and data["counts"]["plays"] == plays and data["counts"]["drives"] == drives
    last = next(g for g in fixture_payload("games_team") if g["id"] == 526000600)
    assert data["homeScore"] == last["homePoints"] and data["awayScore"] == last["awayPoints"] and data["home"] == "Silver Dollar" and data["away"] == "Swampwater Tech"
    box = data["box"]["Swampwater Tech"]
    assert box["plays"] > 60 and box["totalYards"] > 400 and box["thirdDown"]["of"] > 5
    assert box["successRate"] is None and box["successCounts"] is None  # the rate is CFBD's live-feed figure; a finished-game replay has none
    assert data["plays"][0]["period"] == 4 and data["lastPlay"]["success"] in (True, False)
    assert data["currentDriveId"]
    assert engine.stats.events_stored >= plays + drives + 2  # drives, plays, the pre and final statuses; identical statuses dedupe


def test_delay_holds_back_recent_events(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_live(fake_cfbd)
    engine = app.state.live
    client.portal.call(engine.stop_background)  # the schedule watcher must not open a real window over the game set here
    now = datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc)
    app.state.cfbd._clock = lambda: now
    engine.current_game_id, engine.home, engine.away = 1, "A", "B"

    async def feed():
        for i, offset in enumerate((60, 30, 0)):  # receipt order: oldest first, the way a poller stores them
            await engine.publish([LiveEvent(f"play:{i}", "play", 1, now - timedelta(seconds=offset), {"id": str(i), "text": f"Play {i}", "period": 1, "clock": {"minutes": 10 - i, "seconds": 0}, "offense": "A", "playType": "Rush", "yardsGained": 5})])

    asyncio.run(feed())
    assert client.get("/api/live/state?delay=0").json()["data"]["counts"]["plays"] == 3
    delayed = client.get("/api/live/state?delay=45").json()["data"]
    assert delayed["counts"]["plays"] == 1 and delayed["plays"][0]["text"] == "Play 0" and delayed["pending"] is True
    assert client.get("/api/live/state?delay=120").json()["data"]["counts"]["plays"] == 0
    assert client.get("/api/live/state?delay=999").status_code == 422


def test_stream_sends_state_and_resumes_from_last_event_id(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_live(fake_cfbd)
    engine = app.state.live
    client.portal.call(engine.stop_background)  # the schedule watcher must not open a real window over the game set here
    now = datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc)
    app.state.cfbd._clock = lambda: now
    engine.current_game_id, engine.home, engine.away = 1, "A", "B"
    asyncio.run(engine.publish([LiveEvent(f"play:{i}", "play", 1, now - timedelta(seconds=60), {"id": str(i), "text": f"Play {i}", "period": 1, "clock": {"minutes": 9, "seconds": 0}, "offense": "A", "playType": "Rush", "yardsGained": 4}) for i in range(3)]))

    def read_events(headers=None, want=2):
        got = []
        with client.stream("GET", "/api/live/stream?delay=0&ttl=2", headers=headers or {}) as response:
            assert response.headers["content-type"].startswith("text/event-stream")
            current = {}
            for line in response.iter_lines():
                if line.startswith("event:"):
                    current["event"] = line.split(":", 1)[1].strip()
                elif line.startswith("id:"):
                    current["id"] = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    current["data"] = json.loads(line.split(":", 1)[1])
                elif line == "":
                    if current:
                        got.append(current)
                        current = {}
                    if len(got) >= want:
                        break
        return got

    first = read_events()
    assert first[0]["event"] == "hello" and first[1]["event"] == "state"
    assert first[1]["id"] == "3" and first[1]["data"]["counts"]["plays"] == 3 and len(first[1]["data"]["new"]) == 3
    asyncio.run(engine.publish([LiveEvent("play:9", "play", 1, now - timedelta(seconds=1), {"id": "9", "text": "Late", "period": 1, "clock": {"minutes": 8, "seconds": 0}, "offense": "B", "playType": "Rush", "yardsGained": 1})]))
    resumed = read_events(headers={"Last-Event-ID": "3"})
    assert resumed[1]["id"] == "4" and resumed[1]["data"]["new"] == ["play:9"] and resumed[1]["data"]["counts"]["plays"] == 4


# --- the poller ------------------------------------------------------------------------------------------


def run_loop(coro):
    return asyncio.run(coro)


def test_poller_waits_for_window_tier_and_clients_then_polls_records_and_dedupes(app, fake_cfbd: FakeCfbd, tmp_path: Path):
    calls = {"n": 0}

    def payload():
        calls["n"] += 1
        return live_document(3 if calls["n"] < 3 else 4, final=calls["n"] >= 4)

    route_live(fake_cfbd, payload)
    engine = app.state.live
    cfbd = app.state.cfbd
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += timedelta(seconds=seconds)
        if len(sleeps) > 40:
            raise asyncio.CancelledError

    clock = {"now": NEXT_KICKOFF - timedelta(hours=2)}
    cfbd._clock = lambda: clock["now"]
    engine._sleep = fake_sleep
    cfbd.capabilities.live_plays = False

    async def scenario():
        with pytest.raises(asyncio.CancelledError):
            await engine.run()

    # 1. Two hours out: no window yet, nothing polled, one schedule check per minute.
    run_loop(scenario())
    assert fake_cfbd.count("/live/plays") == 0 and engine.mode == "idle" and sleeps[0] == 60

    # 2. Inside the window but the key has no live plays: still nothing polled.
    sleeps.clear()
    clock["now"] = NEXT_KICKOFF - timedelta(minutes=10)
    run_loop(scenario())
    assert fake_cfbd.count("/live/plays") == 0 and engine.mode == "live" and engine.window.game_id == 526001015

    # 3. Tier 2 but nobody watching: no polls. The key's /info must agree, or the next reconcile drops the tier again.
    sleeps.clear()
    info = fixture_payload("info")
    fake_cfbd.route("/info", json={**info, "patronLevel": 2, "tierName": "Tier 2", "monthlyLimit": 30000, "remainingCalls": 29000, "features": {**info["features"], "livePlayByPlay": True}})
    cfbd.capabilities.live_plays = True
    run_loop(scenario())
    assert fake_cfbd.count("/live/plays") == 0 and all(s == 5 for s in sleeps)

    # 4. A client arrives: polls every 12 s, records raw answers, dedupes, stores the fourth play, sees the final and closes the window.
    sleeps.clear()
    engine.note_state_poll()
    original = engine.note_state_poll

    async def scenario_watching():
        async def keep_watching():
            while True:
                original()
                await asyncio.sleep(0)
        watcher = asyncio.create_task(keep_watching())
        try:
            with pytest.raises(asyncio.CancelledError):
                await engine.run()
        finally:
            watcher.cancel()

    run_loop(scenario_watching())
    assert fake_cfbd.count("/live/plays") >= 4
    assert engine.stats.events_stored >= 8  # poll 1: drive, 3 plays, status; poll 2: nothing new; poll 3: play 4 and the changed drive; poll 4: the final
    assert engine.mode == "idle" and (engine.window is None or engine.window.game_id != 526001015) and engine.stats.polls >= 4  # the final closed the window; the next game is queued
    folder = app.state.settings.data_dir / "live" / "526001015"
    recorded = sorted(folder.glob("plays-*.json"))
    first = json.loads(recorded[0].read_text(encoding="utf-8"))
    assert len(recorded) >= 4 and first["kind"] == "plays" and first["payload"]["id"] == 526001015
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["plays"] == len(recorded) and manifest["counts"]["box-teams"] >= 2 and manifest["counts"]["wp"] == 1
    assert [s["status"] for s in manifest["statuses"]] == ["in_progress", "completed"] and manifest["home"] == "Swampwater Tech" and manifest["week"] == 4
    assert 12 in sleeps
    # the box poll ran with the first play poll and again at the final; its events reach the state
    assert fake_cfbd.count("/games/teams") >= 2 and fake_cfbd.count("/games/players") >= 2
    state = engine.state(0, 526001015)
    assert state["boxScore"]["Swampwater Tech"]["totalYards"] > 400 and state["playerStats"]["Swampwater Tech"]["passing"][0]["stats"]["YDS"] > 0
    # the archive holds the final state of the game the app watched, and nothing else
    archive = app.state.settings.data_dir / "archive" / "526001015.json"
    saved = json.loads(archive.read_text(encoding="utf-8"))
    assert saved["state"]["status"] == "final" and saved["state"]["counts"]["plays"] == 4 and saved["state"]["boxScore"]["Swampwater Tech"]["totalYards"] > 400
    assert sorted(p.name for p in archive.parent.glob("*.json")) == ["526001015.json"]


def test_status_reports_the_quota_projection(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_live(fake_cfbd)
    client.portal.call(app.state.live.stop_background)  # the fixture's Diner Tech window is real time on 2026-09-26; the watcher must not open it
    app.state.live.window, app.state.live.mode = None, "idle"  # it may already have, in the moment before it stopped
    data = client.get("/api/live/status").json()["data"]
    assert data["pollSeconds"] == 12 and data["projectedCallsPerGame"] == 1050 and data["projectedCallsPerGame"] < 2500
    assert data["livePlaysAvailable"] is False and data["mode"] == "idle"


def test_replay_of_an_unfinished_or_unknown_game_is_reported(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_live(fake_cfbd)
    import time

    client.post("/api/live/replay", json={"gameId": 526001015, "speed": 3600})
    for _ in range(100):
        status = client.get("/api/live/replay").json()["data"]
        if not status["running"]:
            break
        time.sleep(0.05)
    assert "not finished" in status["error"] and "gameId" in status
    assert client.post("/api/live/replay", json={"gameId": 0}).status_code == 422
    assert client.get("/debug/live").status_code == 200
