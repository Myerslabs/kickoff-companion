"""Phase 12: game-day comfort and a deeper Live sheet. Quarter splits, tendencies, the drive
summary and the fourth-down break-even from released plays; "Sync to my TV"; the build id that
tells an open tablet about new code; replay in its own store space; any Mudpuppies game day counts as
game day in the cache; the Newspaper's slate and scores on a bye Saturday; the live engine on the
status page; the keep-screen-on setting; the home-screen manifest and icons; the front-end
helpers under Node."""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app import build
from app.cache import DataKind, ttl_for
from app.cfbd.models import FieldGoalEp, LiveGame, PredictedPoints, parse_one, parse_records
from app.live.analysis import down_type, drive_summary, ep_table, fg_table, fourth_down, quarter_splits, rush_or_pass, tendencies
from app.live.engine import WINDOW_AFTER, WINDOW_BEFORE, GameWindow, LiveEngine
from app.live.events import LiveEvent, events_from_live
from app.live.state import derive_state
from tests.conftest import PROJECT_ROOT, FakeCfbd, fixture_payload
from tests.test_live import LAST_GAME, route_live
from tests.test_phase8 import KICKOFF, NEXT_GAME, quiet_engine, set_clock
from tests.test_program import pclient, program_app, route_program, sites  # noqa: F401 - fixtures used below
from tests.test_program import set_clock as set_program_clock

SEEN = datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc)
FIRST_DOWN = ep_table(parse_records(PredictedPoints, fixture_payload("ppa_predicted_1_10"), context="t").records)
FIELD_GOAL = fg_table(parse_records(FieldGoalEp, fixture_payload("metrics_fg_ep"), context="t").records)


def recorded_state() -> dict[str, Any]:
    game = parse_one(LiveGame, fixture_payload("live_plays"), context="t")
    assert game is not None
    return derive_state(events_from_live(game, SEEN), game_id=LAST_GAME, home="Silver Dollar", away="Swampwater Tech", ep_tables={"firstDown": FIRST_DOWN, "fieldGoal": FIELD_GOAL})


def snap(offense: str, period: int, gained: int, *, success: bool | None = None, ppa: float | None = None, down: int = 1, distance: int = 10, ytg: int = 60, play_type: str = "Rush", **extra: Any) -> dict[str, Any]:
    return {"offense": offense, "period": period, "yardsGained": gained, "success": success, "ppa": ppa, "down": down, "distance": distance, "yardsToGoal": ytg, "playType": play_type, "flags": [], **extra}


# --- quarter splits ----------------------------------------------------------------------------------


def test_quarter_splits_on_the_recorded_game_add_up():
    state = recorded_state()
    splits = state["splits"]
    assert splits["periods"] == ["Q1", "Q2", "Q3", "Q4"]
    for team in ("Swampwater Tech", "Silver Dollar"):
        by = splits["teams"][team]
        assert sum(by[p]["plays"] for p in splits["periods"]) == by["Game"]["plays"] == state["box"][team]["plays"]
        assert sum(by[p]["yards"] for p in splits["periods"]) == by["Game"]["yards"]
        assert by["Game"]["success"]["of"] <= by["Game"]["plays"]
    assert 1 <= len(splits["notes"]) <= 5 and all(isinstance(n, str) and n.endswith(".") for n in splits["notes"])


def test_split_notes_follow_fixed_thresholds():
    plays = [snap("A", 1, 6, success=True, ppa=0.3) for _ in range(9)] + [snap("B", 1, 2, success=False, ppa=-0.4) for _ in range(9)]
    plays += [snap("A", 2, 5, success=True) for _ in range(8)] + [snap("B", 2, 5, success=True) for _ in range(8)]  # an even quarter: no note
    out = quarter_splits(plays, ("A", "B"))
    assert out["notes"][0] == "Q1: A success 100% to B 0%."
    assert not any(n.startswith("Q2") for n in out["notes"])
    few = quarter_splits([snap("A", 1, 30, success=True)] + [snap("B", 1, 0, success=False)], ("A", "B"))
    assert few["notes"] == []  # too few snaps to compare
    assert out["teams"]["A"]["Q1"]["epaPerPlay"] == 0.3 and out["teams"]["A"]["Q1"]["explosive"] == 0


def test_splits_skip_touchdown_epa_kicks_overtime_and_junk():
    plays = [
        snap("A", 1, 10, ppa=1.0),
        snap("A", 1, 25, ppa=6.0, play_type="Rushing Touchdown"),  # counted, but not in the EPA average
        snap("A", 1, 0, play_type="Kickoff"),  # not a snap
        snap("A", 5, 3),  # overtime
        snap("A", 6, 3),  # double overtime is still OT
        snap("C", 1, 9),  # not one of the teams
        {"offense": "A", "period": "x"},
        {"offense": "A", "period": 0, "playType": "Rush"},
    ]
    out = quarter_splits(plays, ("A", "B"))
    assert out["periods"] == ["Q1", "OT"] and out["teams"]["A"]["Q1"]["plays"] == 2 and out["teams"]["A"]["Q1"]["epaPerPlay"] == 1.0
    assert out["teams"]["A"]["OT"]["plays"] == 2 and out["teams"]["B"] == {}
    assert quarter_splits([], (None, None)) == {"periods": [], "teams": {}, "notes": []}


# --- tendencies ----------------------------------------------------------------------------------------


def test_run_or_pass_and_down_type_use_the_feed_tags_first():
    assert rush_or_pass({"rushPass": "pass", "playType": "Rush"}) == "pass"
    assert rush_or_pass({"rushPass": None, "playType": "Sack"}) == "pass"
    assert rush_or_pass({"playType": "Pass Interception Return"}) == "pass"
    assert rush_or_pass({"playType": "Rushing Touchdown"}) == "rush"
    assert rush_or_pass({"playType": "Punt"}) is None
    assert down_type({"downType": "passing", "down": 1, "distance": 10}) == "passing"
    assert down_type({"down": 2, "distance": 8}) == "passing" and down_type({"down": 2, "distance": 7}) == "standard"
    assert down_type({"down": 3, "distance": 5}) == "passing" and down_type({"down": 3, "distance": 4}) == "standard"
    assert down_type({"down": None}) is None


def test_tendencies_by_situation():
    plays = [
        snap("A", 1, 4, success=True, down=3, distance=2, rushPass="rush", ytg=15),
        snap("A", 1, 0, success=False, down=3, distance=9, play_type="Pass Incompletion"),
        snap("A", 1, 12, success=True, down=1, distance=10, play_type="Pass Reception"),
        snap("A", 1, 0, play_type="Punt"),
        snap("B", 1, 3, success=None, down=2, distance=9),
    ]
    rows = {r["key"]: r for r in tendencies(plays, ("A", "B"))["A"]}
    assert rows["third_short"] == {"key": "third_short", "label": "3rd and 1 to 3", "plays": 1, "passRate": 0.0, "runSuccess": {"made": 1, "of": 1}, "passSuccess": {"made": 0, "of": 0}}
    assert rows["third_long"]["passRate"] == 1.0 and rows["third_long"]["passSuccess"] == {"made": 0, "of": 1}
    assert rows["red_zone"]["plays"] == 1 and rows["standard"]["plays"] == 2 and rows["passing"]["plays"] == 1
    b = {r["key"]: r for r in tendencies(plays, ("A", "B"))["B"]}
    assert b["passing"]["plays"] == 1 and b["passing"]["runSuccess"] == {"made": 0, "of": 0}  # not judged: not counted in success


# --- drive summary ---------------------------------------------------------------------------------------


def test_drive_summary_counts_points_three_and_outs_turnovers_and_chances():
    drives = [
        {"id": "1", "offense": "A", "result": "TD", "pointsGained": 7, "scoringOpportunity": True},
        {"id": "2", "offense": "A", "result": "PUNT"},
        {"id": "3", "offense": "A", "result": "INT"},
        {"id": "4", "offense": "A", "result": "FG", "pointsGained": None},
        {"id": "5", "offense": "B", "result": None},  # still going
    ]
    plays = {
        "2": [snap("A", 1, 1, success=False), snap("A", 1, 2, success=False), snap("A", 1, 0, success=False), snap("A", 1, 0, play_type="Punt")],
        "4": [snap("A", 2, 12, success=True, ppa=0.5, down=1, ytg=35), snap("A", 2, 3, success=False, ppa=-0.1)],
    }
    out = drive_summary(drives, plays, ("A", "B"))
    assert out["A"] == {"drives": 4, "points": 10, "threeAndOuts": 1, "turnovers": 1, "opportunities": 2, "opportunityPoints": 10, "pointsPerDrive": 2.5, "pointsPerOpportunity": 5.0}
    assert out["B"]["drives"] == 0 and out["B"]["pointsPerDrive"] is None
    assert drives[3]["successCounts"] == {"made": 1, "of": 2} and drives[3]["epaPerPlay"] == 0.2
    assert drives[0]["successCounts"] == {"made": 0, "of": 0} and drives[0]["epaPerPlay"] is None


def test_the_recorded_game_carries_drive_efficiency():
    state = recorded_state()
    summary = state["driveSummary"]
    assert summary["Swampwater Tech"]["drives"] >= 10 and summary["Swampwater Tech"]["points"] >= 14
    assert all("successCounts" in d for d in state["drives"])


# --- fourth down --------------------------------------------------------------------------------------


def test_expected_points_tables_read_the_recorded_answers():
    table = {r["yardLine"]: r["predictedPoints"] for r in fixture_payload("ppa_predicted_1_10")}
    assert FIRST_DOWN[90] == table[90] and FIRST_DOWN[25] == table[25] and len(FIRST_DOWN) == len(table)
    kick = next(r for r in fixture_payload("metrics_fg_ep") if r["yardsToGoal"] == 0)
    assert FIELD_GOAL[0] == pytest.approx(kick["expectedPoints"] / 3) and all(0 <= v <= 1 for v in FIELD_GOAL.values())
    assert ep_table([object(), None]) == {} and fg_table(None) == {}


def test_fourth_down_by_hand():
    """4th and 5 at the opponent's 20, worked through the same tables by hand."""
    f = fourth_down(4, 5, 20, FIRST_DOWN, FIELD_GOAL)
    assert f is not None and f["best"] == "fieldGoal" and f["punt"] is None  # nobody punts from the 20
    after_score = -FIRST_DOWN[25]
    make = FIELD_GOAL[20]
    miss = -FIRST_DOWN[100 - (80 - 7)]
    assert f["fieldGoal"] == {"distance": 37, "makeChance": round(make, 3), "ep": round(make * (3 + after_score) + (1 - make) * miss, 2)}
    success, fail = FIRST_DOWN[85], -FIRST_DOWN[20]
    assert f["go"] == {"success": round(success, 2), "fail": round(fail, 2)}
    assert f["breakEven"] == round((f["fieldGoal"]["ep"] - fail) / (success - fail), 3)


def test_fourth_down_edges():
    assert fourth_down(3, 5, 20, FIRST_DOWN, FIELD_GOAL) is None
    assert fourth_down(4, 5, 20, {}, FIELD_GOAL) is None
    assert fourth_down(4, None, 20, FIRST_DOWN, FIELD_GOAL) is None and fourth_down(4, 5, 0, FIRST_DOWN, FIELD_GOAL) is None and fourth_down("4", 5, 20, FIRST_DOWN, FIELD_GOAL) is None
    goal = fourth_down(4, 2, 2, FIRST_DOWN, FIELD_GOAL)
    assert goal is not None and goal["go"]["success"] == round(6.95 - FIRST_DOWN[25], 2)  # converting is the touchdown
    own = fourth_down(4, 10, 80, FIRST_DOWN, FIELD_GOAL)
    assert own is not None and own["fieldGoal"] is None and own["best"] == "punt"  # a 97-yard kick is no choice
    no_fg_table = fourth_down(4, 5, 20, FIRST_DOWN, {})
    assert no_fg_table is None  # inside the 35 with no field-goal table: no kick to compare
    for ytg in range(1, 100):
        for distance in (1, 3, 7, 12):
            f = fourth_down(4, distance, ytg, FIRST_DOWN, FIELD_GOAL)
            assert f is None or 0.0 <= f["breakEven"] <= 1.0


def test_the_state_has_the_fourth_down_row_only_on_a_live_fourth_down():
    status = {"status": "in_progress", "down": 4, "distance": 3, "yardsToGoal": 40, "period": 2}
    events = [LiveEvent("status", "status", 1, SEEN, status)]
    tables = {"firstDown": FIRST_DOWN, "fieldGoal": FIELD_GOAL}
    assert derive_state(events, game_id=1, home="A", away="B", ep_tables=tables)["fourthDown"]["breakEven"] > 0
    assert derive_state(events, game_id=1, home="A", away="B")["fourthDown"] is None  # no tables yet
    final = [LiveEvent("status", "status", 1, SEEN, {**status, "status": "final"})]
    assert derive_state(final, game_id=1, home="A", away="B", ep_tables=tables)["fourthDown"] is None
    third = [LiveEvent("status", "status", 1, SEEN, {**status, "down": 3})]
    assert derive_state(third, game_id=1, home="A", away="B", ep_tables=tables)["fourthDown"] is None


def test_the_engine_loads_the_tables_once(app, client: TestClient, fake_cfbd: FakeCfbd):
    quiet_engine(app, client)
    engine: LiveEngine = app.state.live
    fake_cfbd.fixture("/ppa/predicted", "ppa_predicted_1_10")
    fake_cfbd.fixture("/metrics/fg/ep", "metrics_fg_ep")
    client.portal.call(engine._load_ep_tables)
    client.portal.call(engine._load_ep_tables)
    assert fake_cfbd.count("/ppa/predicted") == 1 and fake_cfbd.count("/metrics/fg/ep") == 1
    assert engine._ep_tables["firstDown"][90] == next(r["predictedPoints"] for r in fixture_payload("ppa_predicted_1_10") if r["yardLine"] == 90)


def test_the_engine_retries_failed_tables_after_ten_minutes(app, client: TestClient, fake_cfbd: FakeCfbd):
    quiet_engine(app, client)
    engine: LiveEngine = app.state.live
    clock = {"now": SEEN}
    app.state.cfbd._clock = lambda: clock["now"]
    fake_cfbd.route("/ppa/predicted", status=500, json={"message": "down"})
    client.portal.call(engine._load_ep_tables)
    client.portal.call(engine._load_ep_tables)
    calls = fake_cfbd.count("/ppa/predicted")
    assert engine._ep_tables == {} and calls >= 1
    clock["now"] += timedelta(minutes=11)
    fake_cfbd.fixture("/ppa/predicted", "ppa_predicted_1_10")
    fake_cfbd.fixture("/metrics/fg/ep", "metrics_fg_ep")
    client.portal.call(engine._load_ep_tables)
    assert engine._ep_tables["fieldGoal"]


# --- sync to my TV --------------------------------------------------------------------------------------


def live_engine_with_plays(app, client: TestClient, now: datetime, feed_lag: float = 40.0) -> LiveEngine:
    quiet_engine(app, client)
    set_clock(app, now)
    engine: LiveEngine = app.state.live
    window = GameWindow(NEXT_GAME, "Swampwater Tech", "Diner Tech", 4, KICKOFF, KICKOFF - WINDOW_BEFORE, KICKOFF + WINDOW_AFTER)
    engine.window = window
    engine._open_window(window)
    events = []
    for i in range(12):  # a snap every 30 s, each reaching the feed feed_lag + i seconds later
        wall = now - timedelta(seconds=400 - 30 * i)
        events.append(LiveEvent(f"play:{i}", "play", NEXT_GAME, wall + timedelta(seconds=feed_lag + i), {"id": str(i), "period": 2, "clock": {"minutes": 10 - i // 2, "seconds": 0}, "offense": "Swampwater Tech", "down": 1 + i % 3, "distance": 10, "yardsToGoal": 60, "wallclock": wall.isoformat().replace("+00:00", "Z"), "text": f"RESULT {i}", "yardsGained": 9}))
    client.portal.call(engine.publish, events)
    return engine


def test_sync_measures_the_tv_lag_and_suggests_a_delay(app, client: TestClient):
    now = KICKOFF + timedelta(hours=1)
    engine = live_engine_with_plays(app, client, now)
    tap = now  # the newest snap happened 70 s ago; the viewer saw it just now
    out = engine.sync(tap)
    assert out["feedLatency"] == {"fastSeconds": 41.0, "medianSeconds": 46.0, "plays": 12}
    first = out["candidates"][0]
    assert first["id"] == "11" and first["tvLagSeconds"] == 70.0
    assert first["suggestedDelay"] == 40  # 70 + 7 - 41 = 36, rounded up to 40
    assert len(out["candidates"]) == 3 and [c["id"] for c in out["candidates"]] == ["11", "10", "9"]
    assert all("text" not in c and "yardsGained" not in c for c in out["candidates"])  # never a result
    assert all(0 <= c["suggestedDelay"] <= 120 and c["suggestedDelay"] % 5 == 0 for c in out["candidates"])


def test_sync_clamps_and_explains(app, client: TestClient):
    now = KICKOFF + timedelta(hours=1)
    engine = live_engine_with_plays(app, client, now, feed_lag=90)
    out = engine.sync(now - timedelta(seconds=40))  # the newest snap was 30 s before the tap
    # The newest snap (70 s before now) has not reached the feed yet (90 s behind), so the choices start one snap earlier.
    assert out["candidates"][0]["id"] == "10" and out["candidates"][0]["tvLagSeconds"] == 60.0
    assert out["candidates"][0]["suggestedDelay"] == 0  # 60 + 7 - 91 < 0: the feed is slower than the TV, no delay needed
    assert out["candidates"][-1]["suggestedDelay"] <= 120
    later = engine.sync(now + timedelta(minutes=10))
    assert later["candidates"] == [] and "Waiting" in later["note"]
    engine.mode = "idle"
    assert engine.sync(now)["note"] == "Sync works during a live game."


def test_sync_without_snap_times(app, client: TestClient):
    quiet_engine(app, client)
    now = KICKOFF + timedelta(minutes=40)
    set_clock(app, now)
    engine: LiveEngine = app.state.live
    window = GameWindow(NEXT_GAME, "Swampwater Tech", "Diner Tech", 4, KICKOFF, KICKOFF - WINDOW_BEFORE, KICKOFF + WINDOW_AFTER)
    engine.window = window
    engine._open_window(window)
    client.portal.call(engine.publish, [LiveEvent("play:1", "play", NEXT_GAME, now, {"id": "1", "wallclock": "not a time"}), LiveEvent("play:2", "play", NEXT_GAME, now, {"id": "2", "wallclock": None})])
    assert "No plays with a snap time" in engine.sync(now)["note"]


def test_the_sync_route(app, client: TestClient):
    now = KICKOFF + timedelta(hours=1)
    live_engine_with_plays(app, client, now)
    first = client.get("/api/live/sync").json()["data"]
    assert first["tapAt"].startswith("2026-09-26T20:30")
    again = client.get(f"/api/live/sync?tapAt={first['tapAt']}").json()["data"]
    assert again["candidates"] and again["tapAt"] == first["tapAt"]
    assert client.get("/api/live/sync?tapAt=2026-09-26T20:30:00").status_code == 200  # a naive time reads as UTC
    bad = client.get("/api/live/sync?tapAt=yesterday")
    assert bad.status_code == 422 and bad.json()["errors"][0]["code"] == "bad_tap"


# --- replay in its own space -------------------------------------------------------------------------------


def test_a_replay_never_touches_the_games_real_event_log(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_live(fake_cfbd)
    quiet_engine(app, client)
    engine: LiveEngine = app.state.live
    real = [LiveEvent(f"play:real{i}", "play", LAST_GAME, SEEN, {"id": f"real{i}", "period": 1}) for i in range(5)]
    client.portal.call(engine.publish, real)
    assert engine.store.count(LAST_GAME) == 5
    client.post("/api/live/replay", json={"gameId": LAST_GAME, "speed": 3600})
    for _ in range(600):
        if not client.get("/api/live/replay").json()["data"]["running"]:
            break
        time.sleep(0.05)
    assert engine.store.count(LAST_GAME) == 5  # untouched
    assert engine.store.count(-LAST_GAME) > 100
    state = client.get("/api/live/state?delay=0").json()["data"]
    assert state["gameId"] == LAST_GAME and state["status"] == "final" and state["counts"]["plays"] > 100  # the sheet shows the replay
    client.post("/api/live/replay", json={"gameId": LAST_GAME, "speed": 3600})  # a second replay clears only the replay space
    for _ in range(600):
        if not client.get("/api/live/replay").json()["data"]["running"]:
            break
        time.sleep(0.05)
    assert engine.store.count(LAST_GAME) == 5
    window = GameWindow(LAST_GAME, "Silver Dollar", "Swampwater Tech", 3, SEEN, SEEN - WINDOW_BEFORE, SEEN + WINDOW_AFTER)
    engine._open_window(window)  # a real window: the real log again
    assert engine.store_key(LAST_GAME) == LAST_GAME and engine.state(0, LAST_GAME)["counts"]["plays"] == 5


# --- game day in the cache ---------------------------------------------------------------------------------


def test_any_game_day_of_ours_counts_as_game_day_in_the_cache():
    friday = datetime(2026, 11, 27, 12, 0)  # Swampwater Tech at Swampwater Tech State
    assert ttl_for(DataKind.SCHEDULE, friday) == timedelta(hours=1)  # other teams play Fridays (Phase 14)
    assert ttl_for(DataKind.SCHEDULE, friday, game_day=True) == timedelta(minutes=15)
    assert ttl_for(DataKind.SEASON_STATS, friday, game_day=True) == timedelta(hours=1)
    assert ttl_for(DataKind.SEASON_STATS, datetime(2026, 11, 25, 12, 0)) == timedelta(hours=6)
    assert ttl_for(DataKind.SCHEDULE, datetime(2026, 11, 28, 12, 0)) == timedelta(minutes=15)  # Saturdays as before


def test_the_engine_sets_game_day_from_the_schedule(app, client: TestClient, fake_cfbd: FakeCfbd):
    quiet_engine(app, client)
    games = copy.deepcopy(fixture_payload("games_team"))
    for g in games:
        if g.get("id") == NEXT_GAME:
            g["startDate"] = "2026-09-25T23:00:00.000Z"  # moved to a Friday night
    fake_cfbd.route("/games", json=games)
    set_clock(app, datetime(2026, 9, 25, 14, 0, tzinfo=timezone.utc))
    client.portal.call(app.state.live.find_window)
    assert app.state.cfbd.game_day is True
    set_clock(app, datetime(2026, 9, 24, 14, 0, tzinfo=timezone.utc))
    client.portal.call(app.state.live.find_window)
    assert app.state.cfbd.game_day is False


# --- the bye Saturday ---------------------------------------------------------------------------------------


def bye_schedule() -> list[dict[str, Any]]:
    return [g for g in fixture_payload("games_team") if isinstance(g, dict) and g.get("id") != NEXT_GAME]


def test_the_newspaper_shows_the_slate_on_a_bye_saturday(pclient: TestClient, fake_cfbd: FakeCfbd, program_app):  # noqa: F811
    route_program(fake_cfbd)
    fake_cfbd.fixture("/calendar", "calendar")

    def games(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("team") == "Swampwater Tech":
            return httpx.Response(200, json=bye_schedule())
        if params.get("week"):
            return httpx.Response(200, json=[g for g in fixture_payload("games_week") if "Swampwater Tech" not in (g.get("homeTeam"), g.get("awayTeam"))])
        return httpx.Response(200, json=fixture_payload("games_opponent"))

    fake_cfbd.route("/games", handler=games)
    pclient.portal.call(program_app.state.live.stop_background)  # its schedule read on real 2026-09-26 would cache the Diner Tech game
    program_app.state.cfbd.cache.clear()
    set_program_clock(program_app, datetime(2026, 9, 26, 14, 0, tzinfo=timezone.utc))
    data = pclient.get("/api/newspaper").json()["data"]
    assert data["gameDay"] is False and data["slateDay"] is True and data["byeWeek"] is True and data["slateWeek"] == 4
    assert data["slate"] and data["slateNote"] is None
    assert not any(g["isUs"] for g in data["slate"])
    watch = [g for g in data["slate"] if g["watch"]]
    order = [g["watch"] or "z" for g in data["slate"]]
    assert order == sorted(order, key=lambda w: {"next": 0, "future": 1}.get(w, 2))  # pinned first
    opponents = {g.get("homeTeam") if g.get("awayTeam") == "Swampwater Tech" else g.get("awayTeam") for g in bye_schedule()}
    assert all((g["home"]["school"] in opponents or g["away"]["school"] in opponents) for g in watch)


def test_the_newspaper_on_a_weekday_still_has_no_slate(pclient: TestClient, fake_cfbd: FakeCfbd, program_app):  # noqa: F811
    route_program(fake_cfbd)
    fake_cfbd.fixture("/calendar", "calendar")
    set_program_clock(program_app, datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc))
    data = pclient.get("/api/newspaper").json()["data"]
    assert data["slateDay"] is False and data["byeWeek"] is False and data["slate"] == []
    assert fake_cfbd.count("/calendar") == 0  # only a Saturday asks


def test_the_ticker_takes_its_week_from_the_calendar(app, client: TestClient, fake_cfbd: FakeCfbd):
    from tests.test_phase8 import route_week

    route_week(fake_cfbd)
    quiet_engine(app, client)

    def games(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("team"):
            return httpx.Response(200, json=bye_schedule())
        return httpx.Response(200, json=fixture_payload("games_week"))

    fake_cfbd.route("/games", handler=games)
    set_clock(app, datetime(2026, 9, 26, 14, 0, tzinfo=timezone.utc))
    data = client.get("/api/ticker").json()["data"]
    assert data["week"] == 4 and data["games"]  # not the next Mudpuppies week
    fake_cfbd.route("/calendar", status=500, json={"message": "down"})


# --- the build id -------------------------------------------------------------------------------------------


def test_the_build_id_follows_the_static_files(tmp_path, monkeypatch):
    folder = tmp_path / "static"
    folder.mkdir()
    (folder / "a.js").write_text("one", encoding="utf-8")
    monkeypatch.setattr(build, "STATIC_DIR", folder)
    build.reset()
    first = build.build_id()
    assert len(first) == 12 and build.build_id() == first  # cached
    (folder / "a.js").write_text("two, longer", encoding="utf-8")
    assert build.build_id() == first  # inside the 30 s cache
    build.reset()
    assert build.build_id() != first
    build.reset()


def test_every_envelope_and_the_hello_carry_the_build(app, client: TestClient):
    quiet_engine(app, client)
    build.reset()
    ids = {client.get(path).json()["meta"]["build"] for path in ("/api/health", "/api/live/status", "/api/settings")}
    assert len(ids) == 1
    with client.stream("GET", "/api/live/stream?delay=0&ttl=1") as response:
        for line in response.iter_lines():
            if line.startswith("data:") and '"build"' in line:
                assert json.loads(line.split(":", 1)[1])["build"] == ids.pop()
                break


# --- the live engine on the status page ------------------------------------------------------------------


def test_the_status_page_reports_the_live_engine(app, client: TestClient):
    quiet_engine(app, client)
    engine: LiveEngine = app.state.live
    data = client.get("/api/health").json()["data"]
    live = next(c for c in data["checks"] if c["name"] == "live")
    assert live["status"] == "ok" and data["engine"]["mode"] in ("idle", "live")
    now = KICKOFF + timedelta(minutes=40)
    app.state.cfbd._clock = lambda: now
    window = GameWindow(NEXT_GAME, "Swampwater Tech", "Diner Tech", 4, KICKOFF, KICKOFF - WINDOW_BEFORE, KICKOFF + WINDOW_AFTER)
    engine.window = window
    engine._open_window(window)
    app.state.cfbd.capabilities.live_plays = True
    live = next(c for c in client.get("/api/health").json()["data"]["checks"] if c["name"] == "live")
    assert live["status"] == "ok" and "Diner Tech at Swampwater Tech" in live["detail"] and "waiting" in live["detail"]
    engine._poll_succeeded(now - timedelta(minutes=5))
    engine._feed_error = "ReadTimeout"
    health = client.get("/api/health").json()["data"]
    live = next(c for c in health["checks"] if c["name"] == "live")
    assert live["status"] == "degraded" and "stale" in live["detail"] and "ReadTimeout" in live["detail"] and health["status"] == "degraded"
    engine.mode = "replay"
    live = next(c for c in client.get("/api/health").json()["data"]["checks"] if c["name"] == "live")
    assert live["status"] == "ok" and "replaying" in live["detail"]


# --- settings, manifest, icons --------------------------------------------------------------------------------


def test_keep_screen_on_is_a_setting(client: TestClient):
    assert client.get("/api/settings").json()["data"]["prefs"]["keepScreenOn"] == "gameday"
    assert client.put("/api/settings", json={"keepScreenOn": "always"}).json()["data"]["prefs"]["keepScreenOn"] == "always"
    bad = client.put("/api/settings", json={"keepScreenOn": "sometimes"})
    assert bad.status_code == 422
    assert client.get("/api/settings").json()["data"]["prefs"]["keepScreenOn"] == "always"


def test_the_home_screen_manifest_and_icons(client: TestClient):
    static = client.get("/static/manifest.webmanifest").json()
    assert static["short_name"] == "Kickoff"  # the neutral file; the server names it for the team
    response = client.get("/manifest.webmanifest")
    assert response.status_code == 200 and response.headers["content-type"].startswith("application/manifest+json")
    manifest = response.json()
    assert manifest["display"] == "standalone" and manifest["start_url"] == "/" and manifest["short_name"] and "Kickoff Companion" in manifest["name"]
    assert all(icon["src"].startswith("/icons/") for icon in manifest["icons"])
    for icon in manifest["icons"]:
        png = client.get(icon["src"])
        assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n"
        width, height = int.from_bytes(png.content[16:20], "big"), int.from_bytes(png.content[20:24], "big")
        assert f"{width}x{height}" == icon["sizes"]
    page = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")
    for needle in ('rel="manifest"', 'name="theme-color"', 'rel="apple-touch-icon"', "/icons/icon-180.png", "apple-mobile-web-app-capable"):
        assert needle in page
    assert client.get("/static/icons/icon-180.png").status_code == 200


# --- front-end helpers under Node ---------------------------------------------------------------------------

NODE_SCRIPT = """import assert from "node:assert/strict";
const [liveUrl, driveUrl, buildUrl, wakeUrl] = process.argv.slice(2);
const live = await import(liveUrl);
const { driveEfficiency } = await import(driveUrl);
const { noteBuild, resetBuild } = await import(buildUrl);
const { wantsScreenOn, sameLocalDay } = await import(wakeUrl);

assert.equal(live.periodClock(2, { minutes: 8, seconds: 5 }), "Q2 8:05");
assert.equal(live.periodClock(5, null), "OT");
assert.equal(live.periodClock(6, null), "2OT");
assert.equal(live.periodClock(null, "junk"), "–");
assert.equal(live.downText(3, 5), "3rd & 5");
assert.equal(live.downText(1, 10), "1st & 10");
assert.equal(live.downText(4, null), null);
assert.equal(live.splitsHint({ period: 2, clock: { minutes: 0, seconds: 0 } }), "Halftime");
assert.equal(live.splitsHint({ period: 3, clock: { minutes: 0, seconds: 0 } }), "End Q3");
assert.equal(live.splitsHint({ period: 4, clock: { minutes: 3, seconds: 0 } }), "Q4");
assert.equal(live.splitsHint({ status: "final" }), "final");
assert.equal(live.splitsHint(null), "by quarter");
assert.equal(live.madeOf({ made: 3, of: 8 }), "3 of 8");
assert.equal(live.madeOf({ made: 0, of: 0 }), "–");
assert.equal(live.madeOf(null), "–");

assert.equal(driveEfficiency({ successCounts: { made: 3, of: 5 }, epaPerPlay: 0.214 }), " · success 3 of 5 · EPA +0.21/play");
assert.equal(driveEfficiency({ successCounts: { made: 0, of: 0 }, epaPerPlay: -0.5 }), " · EPA -0.50/play");
assert.equal(driveEfficiency({}), "");
assert.equal(driveEfficiency(null), "");

resetBuild();
assert.equal(noteBuild("aaa"), false);
assert.equal(noteBuild("aaa"), false);
assert.equal(noteBuild(undefined), false);
assert.equal(noteBuild("bbb"), true);
assert.equal(noteBuild("ccc"), false);  // announced once

assert.equal(wantsScreenOn("always", false), true);
assert.equal(wantsScreenOn("off", true), false);
assert.equal(wantsScreenOn("gameday", true), true);
assert.equal(wantsScreenOn("gameday", false), false);
assert.equal(wantsScreenOn(undefined, true), true);
const now = new Date(2026, 8, 26, 12, 0);
assert.equal(sameLocalDay(new Date(2026, 8, 26, 19, 30).toISOString(), now), true);
assert.equal(sameLocalDay(new Date(2026, 8, 27, 1, 0).toISOString(), now), false);
assert.equal(sameLocalDay("nonsense", now), false);
assert.equal(sameLocalDay(null, now), false);
console.log("ok");
"""


def test_phase12_front_end_helpers_under_node(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = tmp_path / "phase12.mjs"
    script.write_text(NODE_SCRIPT, encoding="utf-8")
    js = PROJECT_ROOT / "static" / "js"
    args = [(js / "views" / "live.js").as_uri(), (js / "ui" / "drive-bar.js").as_uri(), (js / "build.js").as_uri(), (js / "wake.js").as_uri()]
    result = subprocess.run([node, str(script), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert result.returncode == 0 and "ok" in result.stdout, result.stderr[-1200:]
