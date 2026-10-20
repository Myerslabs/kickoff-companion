"""In Game keeps the final (owner 2026-10-10): our last final is held until noon the day after the game, on every device,
after a reload and after a restart, built from the event log at each device's delay; then the next game's pregame sheet.
Also the LIVE marker: it holds until a delayed sheet shows the final even after the engine moved on to the next window."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.live.engine import LiveEngine
from app.live.events import LiveEvent

NOW = datetime(2026, 10, 10, 23, 30, tzinfo=timezone.utc)  # 7:30 PM in the East
GAME, NEXT = 7, 8


def window(game_id: int, kickoff: datetime, contains: bool) -> SimpleNamespace:
    return SimpleNamespace(game_id=game_id, home="Swampwater Tech", away="Diner Tech", week=6, kickoff=kickoff, opens_at=kickoff - timedelta(minutes=30), closes_at=kickoff + timedelta(hours=5), cap=kickoff + timedelta(hours=10), season_type="regular", contains=lambda now: contains)


def test_the_live_marker_holds_while_the_next_window_waits(app):
    """The engine opens the next game's window (not yet open) in the same pass as the final; that window must not hide the
    finished game from a device still behind it."""
    engine: LiveEngine = app.state.live
    engine._clock = lambda: NOW
    finished = window(GAME, NOW - timedelta(hours=3), contains=False)
    engine._last_closed = finished
    engine._final_seen = False
    engine._final_seen_at = NOW - timedelta(seconds=20)
    engine.window = window(NEXT, NOW + timedelta(days=7), contains=False)
    behind = engine.status(45)["window"]
    assert behind["gameId"] == GAME and behind["inProgress"] is True, "45 s behind: still our game, still live"
    caught_up = engine.status(0)["window"]
    assert caught_up["gameId"] == NEXT and caught_up["inProgress"] is False, "no delay: the next game's window"
    engine.window = window(NEXT, NOW + timedelta(minutes=10), contains=True)
    assert engine.status(45)["window"]["gameId"] == NEXT, "an open window is never hidden"


def test_held_until_noon_the_day_after_the_game(app):
    engine: LiveEngine = app.state.live
    tz = engine.settings.tzinfo
    saturday_night = datetime(2026, 10, 10, 19, 30, tzinfo=tz)
    until = engine.hold_until(window(GAME, saturday_night, False), saturday_night + timedelta(hours=3, minutes=20))
    assert until.astimezone(tz).date().isoformat() == "2026-10-11" and until.astimezone(tz).hour == 12
    late = datetime(2026, 10, 10, 22, 30, tzinfo=tz)  # a late kickoff whose final comes after midnight: still Sunday noon
    assert engine.hold_until(window(GAME, late, False), late + timedelta(hours=3, minutes=40)).astimezone(tz).date().isoformat() == "2026-10-11"
    odd = datetime(2026, 10, 11, 11, 45, tzinfo=tz)  # a final that late is still held an hour
    assert engine.hold_until(window(GAME, datetime(2026, 10, 10, 9, 0, tzinfo=tz), False), odd) == odd + timedelta(hours=1)


def test_the_held_record_survives_a_restart_and_a_broken_file_is_ignored(app, settings, fake_cfbd):
    engine: LiveEngine = app.state.live
    engine._clock = lambda: NOW
    engine._hold_final(window(GAME, NOW - timedelta(hours=3), False), NOW - timedelta(minutes=5))
    saved = json.loads(engine.held_path.read_text(encoding="utf-8"))
    assert saved["gameId"] == GAME and saved["home"] == "Swampwater Tech" and saved["until"].endswith("Z")
    again = LiveEngine(engine.client, settings, app.state.db, clock=lambda: NOW)
    assert again.held_final() is not None and again.held_final()["gameId"] == GAME
    assert again.held_final(NOW + timedelta(days=1)) is None, "past its time, nothing is held"
    for broken in ("{ not json", json.dumps([1, 2]), json.dumps({"gameId": "7", "until": "x", "finalAt": "y"}), json.dumps({"gameId": 7, "until": "nope", "finalAt": "2026-10-10T23:00:00Z"})):
        engine.held_path.write_text(broken, encoding="utf-8")
        assert LiveEngine(engine.client, settings, app.state.db, clock=lambda: NOW).held is None, broken


def _seed(engine: LiveEngine) -> None:
    engine.store.append([
        LiveEvent("status", "status", GAME, NOW - timedelta(minutes=10), {"status": "in_progress", "period": 4, "clock": {"minutes": 0, "seconds": 30}, "homeScore": 21, "awayScore": 17}),
        LiveEvent("play:1", "play", GAME, NOW - timedelta(minutes=9), {"id": "1", "period": 4, "offense": "Swampwater Tech", "defense": "Diner Tech", "playType": "Rush", "yardsGained": 3, "text": "run for 3 yards"}),
    ])
    engine.store.append([LiveEvent("status", "status", GAME, NOW - timedelta(seconds=20), {"status": "final", "period": 4, "clock": {"minutes": 0, "seconds": 0}, "homeScore": 21, "awayScore": 17})])


def test_the_held_state_follows_each_devices_delay(app):
    engine: LiveEngine = app.state.live
    engine._clock = lambda: NOW
    assert engine.held_state(0) is None, "nothing held"
    _seed(engine)
    engine._hold_final(window(GAME, NOW - timedelta(hours=3), False), NOW - timedelta(seconds=20))
    final = engine.held_state(0)
    assert final["status"] == "final" and final["gameId"] == GAME and final["held"]["finalAt"].endswith("Z")
    assert final["homeScore"] == 21 and final["team"] == engine.settings.team
    behind = engine.held_state(45)
    assert behind["status"] != "final" and behind["pending"] is True, "a device 45 s behind sees the last minute first, never the final early"
    status = engine.status(45)
    assert status["held"]["gameId"] == GAME and status["held"]["released"] is False
    assert engine.status(0)["held"]["released"] is True


def test_the_archive_stands_in_when_the_log_has_nothing(app):
    engine: LiveEngine = app.state.live
    engine._clock = lambda: NOW
    engine.archive_dir.mkdir(parents=True, exist_ok=True)
    (engine.archive_dir / f"{GAME}.json").write_text(json.dumps({"gameId": GAME, "state": {"gameId": GAME, "status": "final", "homeScore": 28, "awayScore": 3, "lastSeq": 0}}), encoding="utf-8")
    engine._hold_final(window(GAME, NOW - timedelta(hours=3), False), NOW - timedelta(seconds=20))
    assert engine.held_state(0)["homeScore"] == 28
    assert engine.held_state(45) is None, "the archive is the final itself: a device behind it waits"
    (engine.archive_dir / f"{GAME}.json").write_text("{ broken", encoding="utf-8")
    assert engine.held_state(0) is None


def test_the_final_route(client: TestClient, app):
    engine: LiveEngine = app.state.live
    assert client.get("/api/live/final?delay=45").json()["data"] == {"held": None, "waiting": False}
    engine._clock = lambda: NOW
    _seed(engine)
    engine._hold_final(window(GAME, NOW - timedelta(hours=3), False), NOW - timedelta(seconds=20))
    data = client.get("/api/live/final?delay=0").json()["data"]
    assert data["status"] == "final" and data["held"]["until"]
    assert client.get("/api/live/final?delay=999").status_code == 422
    engine.held = {**engine.held, "gameId": 999}  # held, but no log and no archive for it
    assert client.get("/api/live/final?delay=0").json()["data"]["waiting"] is True


def test_a_restart_picks_the_held_game_back_up_and_another_teams_final_is_ignored(app, settings):
    """Review 2026-10-10: after a restart a device still mid-game reconnects and its stream carries it to the final, so the
    held game is the current game again (no window, nothing polls); a final of another team (the home team changed) is not
    ours."""
    engine: LiveEngine = app.state.live
    engine._clock = lambda: NOW
    _seed(engine)
    team = engine.settings.team
    engine._hold_final(SimpleNamespace(game_id=GAME, home=team, away="Diner Tech", kickoff=NOW - timedelta(hours=3)), NOW - timedelta(seconds=20))
    again = LiveEngine(engine.client, settings, app.state.db, clock=lambda: NOW)
    assert again.current_game_id == GAME and again.home == team and again.mode == "idle" and again.window is None
    frame = again.state(0)
    assert frame["status"] == "final" and frame["held"]["until"], "a stream frame of the held game carries the hold"
    engine._hold_final(SimpleNamespace(game_id=GAME, home="Lake Effect", away="Diner Tech", kickoff=NOW - timedelta(hours=3)), NOW - timedelta(seconds=20))
    other = LiveEngine(engine.client, settings, app.state.db, clock=lambda: NOW)
    assert other.held is None and other.current_game_id is None, "not our team's final"


def test_the_program_says_how_long_the_final_is_held(app):
    """The program route marks its game with the hold's end (the server's time), so the cover offers In Game until then."""
    import asyncio

    from app.api.program import _mark_program

    engine: LiveEngine = app.state.live
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(live=engine, archive=None)))
    result = SimpleNamespace(data={"game": {"gameId": GAME}})
    asyncio.run(_mark_program(result, request))  # async since freeze wave F3 (the facts' venue)
    assert result.data["game"]["heldUntil"] is None
    engine.held = {"gameId": GAME, "home": "A", "away": "B", "kickoff": "2026-01-01T00:00:00Z", "finalAt": "2026-01-01T03:00:00Z", "until": "2999-01-01T16:00:00Z"}
    asyncio.run(_mark_program(result, request))  # async since freeze wave F3 (the facts' venue)
    assert result.data["game"]["heldUntil"] == "2999-01-01T16:00:00Z"
    result = SimpleNamespace(data={"game": {"gameId": GAME + 1}})
    asyncio.run(_mark_program(result, request))  # async since freeze wave F3 (the facts' venue)
    assert result.data["game"]["heldUntil"] is None, "another game is not held"
