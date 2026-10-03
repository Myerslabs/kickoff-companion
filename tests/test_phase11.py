"""Phase 11 hardening: the ticker bills /scoreboard only while a game is on or the window is open,
TBD kickoffs open no window and a moved kickoff moves it, in-game win probability from the
scoreboard behind the delay, player lines from the play-by-play until the box score posts,
lenient live models (one bad field no longer drops a drive), the stream's goodbye at shutdown,
and the followed team in the state."""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app import shutdown as shutdown_signal
from app.cache import DataKind
from app.cfbd.models import LiveGame, ScoreboardGame, parse_one, parse_records
from app.live.engine import KICKOFF_RECHECK_MAX_AGE, WINDOW_AFTER, WINDOW_BEFORE, GameWindow, LiveEngine
from app.live.events import LiveEvent, events_from_live, wp_event
from app.live.play_leaders import play_player_lines, resolve
from app.live.state import derive_state
from tests.conftest import PROJECT_ROOT, FakeCfbd, fixture_payload
from tests.test_phase8 import KICKOFF, NEXT_GAME, TEAMS, quiet_engine, route_week, set_clock

SWEET_TEA_GAME = 526001298  # at Sweet Tea State, 2026-10-03, listed TBD in the recorded schedule
TUESDAY = datetime(2026, 9, 22, 18, 0, tzinfo=timezone.utc)
SEEN = datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc)


def scoreboard(**game: Any) -> list[dict[str, Any]]:
    entry = {
        "id": NEXT_GAME,
        "startDate": "2026-09-26T19:30:00.000Z",
        "status": "in_progress",
        "period": 2,
        "clock": "4:10",
        "homeTeam": {"id": TEAMS["Swampwater Tech"]["id"], "name": "Swampwater Tech Mudpuppies", "classification": "fbs", "points": 10, "winProbability": 0.62},
        "awayTeam": {"id": TEAMS["Diner Tech"]["id"], "name": "Diner Tech Rebels", "classification": "fbs", "points": 7, "winProbability": 0.38},
    }
    entry.update(game)
    return [entry]


def one(model: Any, payload: Any) -> Any:
    return parse_records(model, payload, context="t").records[0]


# --- 1. the ticker's scoreboard ------------------------------------------------------------------


def test_tier2_ticker_uses_the_week_slate_when_no_game_is_on(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_week(fake_cfbd)
    quiet_engine(app, client)
    set_clock(app, TUESDAY)
    app.state.cfbd.capabilities.scoreboard = True
    fake_cfbd.route("/scoreboard", json=scoreboard())
    for _ in range(3):
        data = client.get("/api/ticker").json()["data"]
        assert data["source"] == "games" and data["games"]
    assert fake_cfbd.count("/scoreboard") == 0  # before Phase 11 this was one call per request, any day


def test_tier2_ticker_reads_the_scoreboard_while_a_game_is_on(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_week(fake_cfbd)
    quiet_engine(app, client)
    set_clock(app, KICKOFF + timedelta(minutes=30))
    app.state.cfbd.capabilities.scoreboard = True
    fake_cfbd.route("/scoreboard", json=scoreboard())
    assert client.get("/api/ticker").json()["data"]["source"] == "scoreboard" and fake_cfbd.count("/scoreboard") == 1


def test_tier2_ticker_reads_the_scoreboard_while_the_window_is_open(app, client: TestClient, fake_cfbd: FakeCfbd):
    """Pregame, inside the window: the slate says nothing is on yet, but the engine wants the scoreboard's win probability."""
    route_week(fake_cfbd)
    quiet_engine(app, client)
    now = KICKOFF - timedelta(minutes=10)
    set_clock(app, now)
    app.state.cfbd.capabilities.scoreboard = True
    fake_cfbd.route("/scoreboard", json=scoreboard(status="scheduled"))
    engine: LiveEngine = app.state.live
    engine.window = GameWindow(NEXT_GAME, "Swampwater Tech", "Diner Tech", 4, KICKOFF, KICKOFF - WINDOW_BEFORE, KICKOFF + WINDOW_AFTER)
    engine.mode = "live"
    assert engine.window_open(now)
    assert client.get("/api/ticker").json()["data"]["source"] == "scoreboard"
    engine.mode = "replay"
    assert not engine.window_open(now)  # a replay never counts as a real window


# --- 2. TBD kickoffs -----------------------------------------------------------------------------------


def schedule_with(changes: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    games = copy.deepcopy(fixture_payload("games_team"))
    for game in games:
        if isinstance(game, dict) and game.get("id") in changes:
            game.update(changes[game["id"]])
    return games


def test_a_tbd_kickoff_opens_no_window(app, client: TestClient, fake_cfbd: FakeCfbd, caplog):
    quiet_engine(app, client)
    fake_cfbd.route("/games", json=schedule_with({SWEET_TEA_GAME: {"startTimeTBD": True, "startDate": "2026-10-03T04:00:00.000Z"}}))  # a time to be announced
    set_clock(app, datetime(2026, 10, 3, 3, 45, tzinfo=timezone.utc))  # inside the placeholder window (local midnight minus 15 minutes)
    engine: LiveEngine = app.state.live
    window = client.portal.call(engine.find_window)
    assert window is None or window.game_id != SWEET_TEA_GAME
    assert "no kickoff time yet (TBD)" in caplog.text


def test_a_set_kickoff_opens_the_window(app, client: TestClient, fake_cfbd: FakeCfbd):
    quiet_engine(app, client)
    fake_cfbd.route("/games", json=schedule_with({SWEET_TEA_GAME: {"startTimeTBD": False, "startDate": "2026-10-03T16:00:00.000Z"}}))
    set_clock(app, datetime(2026, 10, 3, 15, 45, tzinfo=timezone.utc))
    window = client.portal.call(app.state.live.find_window)
    assert window is not None and window.game_id == SWEET_TEA_GAME and window.contains(datetime(2026, 10, 3, 15, 45, tzinfo=timezone.utc))


def test_a_kickoff_that_moves_before_the_first_play_moves_the_window(app, client: TestClient, fake_cfbd: FakeCfbd):
    quiet_engine(app, client)
    schedule = {"payload": schedule_with({SWEET_TEA_GAME: {"startTimeTBD": False, "startDate": "2026-10-03T16:00:00.000Z"}})}
    fake_cfbd.route("/games", handler=lambda r: httpx.Response(200, json=schedule["payload"]))
    clock = {"now": datetime(2026, 10, 3, 15, 31, tzinfo=timezone.utc)}
    app.state.cfbd._clock = lambda: clock["now"]
    engine: LiveEngine = app.state.live

    async def scenario() -> None:
        engine.window = await engine.find_window()
        assert engine.window is not None and engine.window.game_id == SWEET_TEA_GAME
        engine._open_window(engine.window)
        assert await engine._kickoff_recheck_due(clock["now"])
        assert not await engine._kickoff_recheck_due(clock["now"] + timedelta(seconds=30))  # once a minute at most
        schedule["payload"] = schedule_with({SWEET_TEA_GAME: {"startTimeTBD": False, "startDate": "2026-10-03T19:30:00.000Z"}})
        # past the schedule's lifetime for this key: 15 minutes on a Saturday, stretched four times on a free key
        # (the test fixture's), so the test never depends on which plan the fixture imitates
        lifetime = app.state.cfbd._ttl(DataKind.SCHEDULE, [], clock["now"], app.state.cfbd.quota.status(clock["now"]))
        clock["now"] += lifetime + timedelta(minutes=1)
        assert await engine._kickoff_recheck_due(clock["now"])
        moved = await engine.find_window()
        assert moved is not None and moved.kickoff == datetime(2026, 10, 3, 19, 30, tzinfo=timezone.utc) and not moved.contains(clock["now"])

    client.portal.call(scenario)


def test_the_recheck_stops_once_a_play_is_stored(app, client: TestClient, fake_cfbd: FakeCfbd):
    quiet_engine(app, client)
    engine: LiveEngine = app.state.live
    now = KICKOFF + timedelta(minutes=5)
    set_clock(app, now)
    window = GameWindow(NEXT_GAME, "Swampwater Tech", "Diner Tech", 4, KICKOFF, KICKOFF - WINDOW_BEFORE, KICKOFF + WINDOW_AFTER)
    engine.window = window
    engine._open_window(window)

    async def scenario() -> None:
        await engine.publish([LiveEvent("play:1", "play", NEXT_GAME, now, {"id": "1", "period": 1})])
        assert not await engine._kickoff_recheck_due(now)

    client.portal.call(scenario)


# --- 3. player lines from the play-by-play --------------------------------------------------------------


def play(team: str, play_type: str, text: str, gained: Any) -> dict[str, Any]:
    return {"offense": team, "playType": play_type, "text": text, "yardsGained": gained}


def test_player_lines_from_play_text():
    plays = [
        play("Silo City", "Pass Reception", "(14:59) No Huddle-Shotgun #16 A.Manley pass complete short right to #1 R.Wingate caught at SILO33, for 8 yards to the SILO33 (#6 Q.Mossberg)", 8),
        play("Silo City", "Passing Touchdown", "(13:13) Shotgun #16 A.Manley pass complete deep middle to #3 E.Mosby V caught at MAG22, for 43 yards TOUCHDOWN", 43),
        play("Silo City", "Pass Incompletion", "(10:41) #16 A.Manley pass incomplete short right to #14 B.Stanley thrown to MAG21 QB hurried by #95 I.Gifford", 0),
        play("Silo City", "Interception", "(12:13) No Huddle-Shotgun #16 A.Manley pass intercepted by #14 K.Leeds at MAG04, End Of Play", 0),
        play("Silo City", "Rushing Touchdown", "(11:03) No Huddle-Shotgun #0 R.Brownlee rush middle for 9 yards gain to the MAG00 TOUCHDOWN, clock 10:58", 9),
        play("Silo City", "Rush", "#5 D.Cooke rush middle for 1 yard gain. CALL OVERTURNED. (Original Play: #5 D.Cooke rush middle for 0 yards)", 1),
        play("Silo City", "Sack", "(07:32) No Huddle-Shotgun #16 A.Manley sacked for loss of 8 yards to the SILO18 (#18 T.Weatherford)", -8),
        play("Silo City", "Penalty", "#0 R.Brownlee rush middle for 2 yards loss PENALTY TENN Illegal Substitution 5 yards. NO PLAY", 5),
        play("Silo City", "Fumble Recovery (Own)", "Silo City rush middle for 12 yards loss to the SILO26 fumbled by Silo City", -12),
        play("Silo City", "Two Point Rush", "#0 R.Brownlee rush for 2 yards, TWO-POINT CONVERSION GOOD", 2),
        play("Magnolia Flats", "Kickoff", "#94 J.Turnbull kickoff 65 yards to the SILO00, Touchback", 0),
        play("Magnolia Flats", "Rush", "#18 D.Bishard rush middle for 4 yards gain", "4"),  # a string count: the carry counts, the yards do not
        None,
        {"offense": None, "text": "#1 X.Y rush for 3 yards", "yardsGained": 3},
        {"offense": "Silo City", "text": None},
    ]
    lines = play_player_lines(plays)  # type: ignore[arg-type]
    passing = {r["name"]: r["stats"] for r in lines["Silo City"]["passing"]}
    assert passing == {"A.Manley": {"C/ATT": "2/4", "YDS": 51, "TD": 1, "INT": 1}}
    receiving = {r["name"]: r["stats"] for r in lines["Silo City"]["receiving"]}
    assert receiving["E.Mosby V"] == {"REC": 1, "YDS": 43, "AVG": 43.0, "TD": 1, "LONG": 43} and receiving["R.Wingate"]["YDS"] == 8
    rushing = {r["name"]: r["stats"] for r in lines["Silo City"]["rushing"]}
    assert rushing["R.Brownlee"] == {"CAR": 1, "YDS": 9, "AVG": 9.0, "TD": 1, "LONG": 9}  # the NO PLAY and the two-point try do not count
    assert rushing["D.Cooke"]["CAR"] == 1 and rushing["A.Manley"] == {"CAR": 1, "YDS": -8, "AVG": -8.0, "TD": 0, "LONG": -8}  # the sack is a rush
    assert [r["name"] for r in lines["Silo City"]["receiving"]] == ["E.Mosby V", "R.Wingate"]  # by yards
    assert lines["Magnolia Flats"] == {"rushing": [{"playerId": None, "name": "D.Bishard", "stats": {"CAR": 1, "YDS": 0, "AVG": 0.0, "TD": 0, "LONG": None}}]}
    assert all(r["playerId"] is None for cats in lines.values() for rows in cats.values() for r in rows)
    assert play_player_lines([]) == {}


def test_player_lines_on_the_recorded_live_document():
    game = parse_one(LiveGame, fixture_payload("live_plays"), context="t")
    assert game is not None
    state = derive_state(events_from_live(game, SEEN), game_id=526000600, home="Silver Dollar", away="Swampwater Tech")
    assert state["playerStatsSource"] == {"Silver Dollar": "plays", "Swampwater Tech": "plays"}
    swt = state["playerStats"]["Swampwater Tech"]
    assert set(swt) == {"passing", "rushing", "receiving"}
    top = swt["passing"][0]["stats"]
    made, attempts = (int(x) for x in top["C/ATT"].split("/"))
    assert 0 < made <= attempts and top["YDS"] > 100
    assert sum(r["stats"]["REC"] for r in swt["receiving"]) <= sum(int(r["stats"]["C/ATT"].split("/")[0]) for r in swt["passing"])


def test_the_box_score_replaces_the_play_lines_team_by_team():
    plays = [LiveEvent("play:1", "play", 1, SEEN, {"id": "1", "period": 1, "offense": "A", "playType": "Rush", "text": "#1 A.One rush for 5 yards", "yardsGained": 5}), LiveEvent("play:2", "play", 1, SEEN, {"id": "2", "period": 1, "offense": "B", "playType": "Rush", "text": "#2 B.Two rush for 3 yards", "yardsGained": 3})]
    box = LiveEvent("players", "players", 1, SEEN, {"teams": {"A": {"rushing": [{"playerId": 7, "name": "Aaron One", "stats": {"CAR": 1, "YDS": 5}}]}, "B": {"rushing": []}}})
    state = derive_state([*plays, box], game_id=1, home="A", away="B")
    assert state["playerStatsSource"] == {"A": "box", "B": "plays"}
    assert state["playerStats"]["A"]["rushing"][0]["playerId"] == 7 and state["playerStats"]["B"]["rushing"][0]["name"] == "B.Two"
    empty = derive_state([], game_id=1, home="A", away="B")
    assert empty["playerStats"] is None and empty["playerStatsSource"] == {}


# --- 4. in-game win probability ------------------------------------------------------------------------


def test_wp_event_reads_the_scoreboard_entry():
    event = wp_event(one(ScoreboardGame, scoreboard()), SEEN)
    assert event is not None and event.kind == "wp" and event.id == "wp:2:250" and event.data["homeWp"] == 0.62
    assert event.data["clock"] == {"minutes": 4, "seconds": 10} and event.data["homeScore"] == 10
    only_away = wp_event(one(ScoreboardGame, scoreboard(homeTeam={"name": "Swampwater Tech Mudpuppies", "winProbability": None}, awayTeam={"name": "Diner Tech Rebels", "winProbability": 0.25})), SEEN)
    assert only_away is not None and only_away.data["homeWp"] == 0.75
    for bad in (scoreboard(status="scheduled"), scoreboard(status="completed"), scoreboard(homeTeam={"winProbability": 1.7}, awayTeam={"winProbability": "abc"}), scoreboard(homeTeam=None, awayTeam=None)):
        assert wp_event(one(ScoreboardGame, bad), SEEN) is None


def test_the_scoreboard_win_probability_follows_the_delay(app, client: TestClient, fake_cfbd: FakeCfbd):
    quiet_engine(app, client)
    engine: LiveEngine = app.state.live
    clock = {"now": KICKOFF + timedelta(minutes=40)}
    app.state.cfbd._clock = lambda: clock["now"]
    window = GameWindow(NEXT_GAME, "Swampwater Tech", "Diner Tech", 4, KICKOFF, KICKOFF - WINDOW_BEFORE, KICKOFF + WINDOW_AFTER)
    engine.window = window
    engine._open_window(window)
    client.portal.call(engine.record_scoreboard, scoreboard(period=2, clock="6:00", homeTeam={"name": "Swampwater Tech Mudpuppies", "winProbability": 0.55}))
    clock["now"] += timedelta(seconds=60)
    client.portal.call(engine.record_scoreboard, scoreboard(period=2, clock="4:10") + ["junk"])
    client.portal.call(engine.record_scoreboard, scoreboard(period=2, clock="4:10"))  # the same reading again: no new event
    now = client.get("/api/live/state?delay=0").json()["data"]["liveWinProbability"]
    assert now["homeWp"] == 0.62 and [p["homeWp"] for p in now["series"]] == [0.55, 0.62]
    held = client.get("/api/live/state?delay=45").json()["data"]["liveWinProbability"]
    assert held["homeWp"] == 0.55 and len(held["series"]) == 1  # the newer reading is still inside the delay
    assert engine.store.count_kind(NEXT_GAME, "wp") == 2
    engine.mode = "replay"
    client.portal.call(engine.record_scoreboard, scoreboard(period=3, clock="1:00"))
    assert engine.store.count_kind(NEXT_GAME, "wp") == 2  # never during a replay


# --- 5. lenient live models ----------------------------------------------------------------------------


def test_one_bad_field_no_longer_drops_a_drive(caplog):
    doc = copy.deepcopy(fixture_payload("live_plays"))
    plays_before = sum(len(d["plays"]) for d in doc["drives"])
    doc["drives"][0]["yards"] = "a lot"
    doc["drives"][1]["plays"][0]["down"] = 2.5
    doc["drives"][1]["plays"][1]["yardsGained"] = {"oops": 1}
    doc["period"] = "second"
    doc["teams"][0]["points"] = [7]
    game = parse_one(LiveGame, doc, context="t")
    assert game is not None and len(game.drives) == len(doc["drives"]) and sum(len(d.plays) for d in game.drives) == plays_before
    assert game.drives[0].yards is None and game.drives[1].plays[0].down is None and game.drives[1].plays[1].yards_gained is None
    assert game.period is None and game.teams[0].points is None
    assert "read as empty" in caplog.text


def test_a_record_without_its_id_is_still_dropped():
    doc = copy.deepcopy(fixture_payload("live_plays"))
    del doc["drives"][0]["plays"][0]["id"]
    doc["drives"][1]["id"] = None
    game = parse_one(LiveGame, doc, context="t")
    assert game is not None and len(game.drives) == len(doc["drives"]) - 1
    assert len(game.drives[0].plays) == len(doc["drives"][0]["plays"]) - 1
    assert parse_one(LiveGame, {"status": "in_progress"}, context="t") is None


# --- 6. the stream at shutdown -------------------------------------------------------------------------


def test_open_streams_say_goodbye_when_the_server_shuts_down(app, client: TestClient):
    quiet_engine(app, client)
    shutdown_signal.begin()
    try:
        events = []
        with client.stream("GET", "/api/live/stream?delay=0&ttl=30") as response:
            for line in response.iter_lines():
                if line.startswith("event:"):
                    events.append(line.split(":", 1)[1].strip())
        assert events == ["hello", "bye"]
    finally:
        shutdown_signal.reset()


def test_a_new_app_never_starts_out_shutting_down(settings):
    from app.main import create_app

    shutdown_signal.begin()
    create_app(settings)
    assert not shutdown_signal.stopping()


def test_a_failing_waker_does_not_stop_the_shutdown(caplog):
    shutdown_signal.reset()
    woke = []
    shutdown_signal.on_begin(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    shutdown_signal.on_begin(lambda: woke.append(True))
    shutdown_signal.begin()
    shutdown_signal.begin()  # a second call does nothing
    assert shutdown_signal.stopping() and woke == [True] and "wake-up callback failed" in caplog.text
    shutdown_signal.reset()


# --- 7. the followed team -------------------------------------------------------------------------------


def test_the_state_names_the_followed_team(app, client: TestClient):
    quiet_engine(app, client)
    engine: LiveEngine = app.state.live
    engine.current_game_id, engine.home, engine.away = 1, "Silo City", "Magnolia Flats"
    data = client.get("/api/live/state?delay=0").json()["data"]
    assert data["team"] == app.state.settings.team == "Swampwater Tech"
    assert json.dumps(data)  # still one serializable frame


# --- follow-ups (2026-09-26 evening): roster names, the engine's own scoreboard, fresher kickoffs ------


ROSTERS = {
    "Silo City": {
        16: [{"id": "4870906", "first": "Archer", "last": "Manley"}],
        3: [{"id": "111", "first": "Emmett", "last": "Mosby V"}],
        1: [{"id": "222", "first": "Ryan", "last": "Wingate"}, {"id": "223", "first": "Rian", "last": "Wingate"}],  # one number, same last name and initial
        0: [{"id": "333", "first": "Rodney", "last": "Brownlee"}, {"id": "334", "first": "Kevin", "last": "Jones"}],  # a shared number, told apart by name
    }
}


def test_play_names_resolve_to_roster_players_only_on_one_clean_match():
    assert resolve(ROSTERS, "Silo City", "A.Manley", 16) == ("4870906", "Archer Manley")
    assert resolve(ROSTERS, "Silo City", "E.Mosby V", 3) == ("111", "Emmett Mosby V")  # the suffix does not get in the way
    assert resolve(ROSTERS, "Silo City", "R.Wingate", 1) == (None, "R.Wingate")  # ambiguous: keep the short name
    assert resolve(ROSTERS, "Silo City", "R.Brownlee", 0) == ("333", "Rodney Brownlee")
    assert resolve(ROSTERS, "Silo City", "Q.Manley", 16) == (None, "Q.Manley")  # the initial disagrees
    assert resolve(ROSTERS, "Silo City", "A.Manley", 99) == (None, "A.Manley")
    assert resolve(ROSTERS, "Magnolia Flats", "A.Manley", 16) == (None, "A.Manley")
    assert resolve(None, "Silo City", "A.Manley", 16) == (None, "A.Manley")
    assert resolve({"Silo City": {16: [{"id": "", "first": "Archer", "last": "Manley"}]}}, "Silo City", "A.Manley", 16) == (None, "Archer Manley")


def test_play_lines_carry_roster_ids_and_full_names():
    plays = [
        play("Silo City", "Pass Reception", "#16 A.Manley pass complete short right to #1 R.Wingate caught at SILO33, for 8 yards", 8),
        play("Silo City", "Rush", "#0 R.Brownlee rush middle for 4 yards gain", 4),
        play("Silo City", "Rush", "#0 R.Brownlee rush middle for 6 yards gain", 6),
    ]
    lines = play_player_lines(plays, ROSTERS)
    assert lines["Silo City"]["passing"][0]["playerId"] == "4870906" and lines["Silo City"]["passing"][0]["name"] == "Archer Manley"
    assert lines["Silo City"]["receiving"][0] == {"playerId": None, "name": "R.Wingate", "stats": {"REC": 1, "YDS": 8, "AVG": 8.0, "TD": 0, "LONG": 8}}
    assert lines["Silo City"]["rushing"][0]["playerId"] == "333" and lines["Silo City"]["rushing"][0]["stats"]["CAR"] == 2  # one row across plays


def open_window(app, client: TestClient, now: datetime) -> tuple[LiveEngine, GameWindow]:
    quiet_engine(app, client)
    set_clock(app, now)
    engine: LiveEngine = app.state.live
    window = GameWindow(NEXT_GAME, "Swampwater Tech", "Diner Tech", 4, KICKOFF, KICKOFF - WINDOW_BEFORE, KICKOFF + WINDOW_AFTER)
    engine.window = window
    engine._open_window(window)
    return engine, window


def live_doc_for(game_id: int) -> dict[str, Any]:
    doc = copy.deepcopy(fixture_payload("live_plays"))
    doc["id"] = game_id
    doc["status"] = "in_progress"
    return doc


def quiet_box(fake: FakeCfbd) -> None:
    fake.route("/games/teams", json=[])
    fake.route("/games/players", json=[])


def test_the_engine_reads_the_scoreboard_itself_once_a_minute(app, client: TestClient, fake_cfbd: FakeCfbd):
    now = KICKOFF + timedelta(minutes=40)
    engine, window = open_window(app, client, now)
    clock = {"now": now}
    app.state.cfbd._clock = lambda: clock["now"]
    app.state.cfbd.capabilities.scoreboard = True
    fake_cfbd.route("/live/plays", json=live_doc_for(NEXT_GAME))
    fake_cfbd.route("/scoreboard", json=scoreboard())
    fake_cfbd.route("/roster", json=[])
    quiet_box(fake_cfbd)
    client.portal.call(engine.poll_once, window)
    assert fake_cfbd.count("/scoreboard") == 1 and engine.store.count_kind(NEXT_GAME, "wp") == 1
    clock["now"] += timedelta(seconds=30)
    client.portal.call(engine.poll_once, window)
    assert fake_cfbd.count("/scoreboard") == 1  # under a minute: not again
    clock["now"] += timedelta(seconds=45)
    client.portal.call(engine.record_scoreboard, scoreboard(clock="3:00"))  # the ticker just handed one over
    client.portal.call(engine.poll_once, window)
    assert fake_cfbd.count("/scoreboard") == 1 and engine.store.count_kind(NEXT_GAME, "wp") == 2
    clock["now"] += timedelta(seconds=90)
    fake_cfbd.route("/scoreboard", status=503, json={"message": "down"})
    client.portal.call(engine.poll_once, window)  # a failed scoreboard never stops the play poll
    assert engine.stats.consecutive_failures == 0 and engine.stats.polls == 4
    assert engine.store.count_kind(NEXT_GAME, "wp") == 2  # the client served its last good copy as stale: no new reading from it


def test_the_engine_skips_the_scoreboard_without_the_tier(app, client: TestClient, fake_cfbd: FakeCfbd):
    engine, window = open_window(app, client, KICKOFF + timedelta(minutes=40))
    app.state.cfbd.capabilities.scoreboard = False
    fake_cfbd.route("/live/plays", json=live_doc_for(NEXT_GAME))
    fake_cfbd.route("/roster", json=[])
    quiet_box(fake_cfbd)
    client.portal.call(engine.poll_once, window)
    assert fake_cfbd.count("/scoreboard") == 0


def test_the_engine_names_play_lines_from_the_rosters(app, client: TestClient, fake_cfbd: FakeCfbd):
    engine, window = open_window(app, client, KICKOFF + timedelta(minutes=40))
    doc = live_doc_for(NEXT_GAME)
    game = parse_one(LiveGame, doc, context="t")
    assert game is not None
    passer = next(p for d in game.drives for p in d.plays if p.play_type == "Pass Reception" and p.team == "Swampwater Tech" and p.play_text)
    after = passer.play_text.split("#", 1)[1].split()
    jersey, short = int(after[0]), after[1]
    initial, last = short.split(".", 1)
    swt = [{"id": "4536127", "firstName": f"{initial}aron", "lastName": last, "team": "Swampwater Tech", "jersey": jersey}, {"id": "9", "firstName": "No", "lastName": "Number", "jersey": None}, "junk"]
    fake_cfbd.route("/roster", handler=lambda r: httpx.Response(200, json=swt if r.url.params.get("team") == "Swampwater Tech" else [{"id": "x"}]))
    fake_cfbd.route("/live/plays", json=doc)
    quiet_box(fake_cfbd)
    client.portal.call(engine.poll_once, window)
    client.portal.call(engine.poll_once, window)
    assert fake_cfbd.count("/roster") == 2  # once per team per window
    assert engine._rosters["Swampwater Tech"][jersey][0]["id"] == "4536127" and engine._rosters["Diner Tech"] == {}
    engine.home, engine.away = "Silver Dollar", "Swampwater Tech"  # the document's own teams
    state = engine.state(0, NEXT_GAME)
    rows = state["playerStats"]["Swampwater Tech"]["passing"]
    assert any(r["playerId"] == "4536127" and r["name"] == f"{initial}aron {last}" for r in rows)


def test_a_missing_roster_keeps_short_names(app, client: TestClient, fake_cfbd: FakeCfbd):
    engine, window = open_window(app, client, KICKOFF + timedelta(minutes=40))
    fake_cfbd.route("/roster", status=500, json={"message": "down"})
    fake_cfbd.route("/live/plays", json=live_doc_for(NEXT_GAME))
    quiet_box(fake_cfbd)
    client.portal.call(engine.poll_once, window)
    engine.home, engine.away = "Silver Dollar", "Swampwater Tech"
    rows = engine.state(0, NEXT_GAME)["playerStats"]["Swampwater Tech"]["passing"]
    assert rows and all(r["playerId"] is None for r in rows)


def test_the_kickoff_recheck_reads_a_schedule_at_most_five_minutes_old(app, client: TestClient, fake_cfbd: FakeCfbd):
    quiet_engine(app, client)
    fake_cfbd.route("/games", json=schedule_with({SWEET_TEA_GAME: {"startTimeTBD": False, "startDate": "2026-10-03T16:00:00.000Z"}}))
    clock = {"now": datetime(2026, 10, 3, 15, 31, tzinfo=timezone.utc)}
    app.state.cfbd._clock = lambda: clock["now"]
    engine: LiveEngine = app.state.live

    async def scenario() -> None:
        await engine.find_window()
        calls = fake_cfbd.count("/games")
        clock["now"] += timedelta(minutes=3)
        await engine.find_window(KICKOFF_RECHECK_MAX_AGE)
        assert fake_cfbd.count("/games") == calls  # a three-minute-old copy is fine
        clock["now"] += timedelta(minutes=3)
        await engine.find_window(KICKOFF_RECHECK_MAX_AGE)
        assert fake_cfbd.count("/games") == calls + 1  # six minutes old: read again, inside the 15-minute Saturday lifetime

    client.portal.call(scenario)


NODE_HELPERS = """import assert from "node:assert/strict";
const { hasId, followedTeam } = await import(process.argv[2]);
const { pctLabel } = await import(process.argv[3]);
assert.equal(hasId("4536127"), true);  // CFBD box score and roster ids are digit strings
assert.equal(hasId(42), true);
for (const bad of [null, undefined, "", "abc", "12a", 0, -3, NaN, {}, []]) assert.equal(hasId(bad), false, String(bad));
assert.equal(followedTeam({ team: "Silo City" }, { us: { school: "Swampwater Tech" } }), "Silo City");
assert.equal(followedTeam({ team: "  " }, { us: { school: "Georgia" } }), "Georgia");
assert.equal(followedTeam(null, null), "Our team");  // no identity loaded: plain words
assert.equal(followedTeam({ team: 7 }, { us: { school: null } }), "Our team");
assert.equal(pctLabel("kicking"), "FG %");
assert.equal(pctLabel("Kicking"), "FG %");
assert.equal(pctLabel("passing"), "Comp %");
assert.equal(pctLabel(undefined), "Comp %");
console.log("ok");
"""


def test_front_end_helpers_under_node(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = tmp_path / "helpers.mjs"
    script.write_text(NODE_HELPERS, encoding="utf-8")
    views = PROJECT_ROOT / "static" / "js" / "views"
    result = subprocess.run([node, str(script), (views / "live.js").as_uri(), (views / "player.js").as_uri()], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert result.returncode == 0 and "ok" in result.stdout, result.stderr[-800:]
