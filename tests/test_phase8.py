"""Phase 8: the radio sources route, the ticker on both tiers with the Mudpuppies entry behind the
delay and the five-minute cadence on the Free tier, the analytics route (win probability and
play value) with malformed payloads, the archive carrying the win probability, and the client's
max_age ceiling with the unscaled ticker lifetime."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
from fastapi.testclient import TestClient

from app.cache import DataKind
from app.live.engine import GameWindow
from app.live.events import LiveEvent
from tests import league_facts as facts
from tests.conftest import ROLES, TEST_KEY, FakeCfbd, fixture_payload

NEXT_GAME = 526001015
LAST_GAME = 526000600
KICKOFF = datetime(2026, 9, 26, 19, 30, tzinfo=timezone.utc)  # Diner Tech at Swampwater Tech, week 4
TEAMS = {t["school"]: t for t in fixture_payload("teams_fbs") if isinstance(t, dict) and t.get("school")}


def route_week(fake: FakeCfbd) -> None:
    def games(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("team"):
            return httpx.Response(200, json=fixture_payload("games_team"))
        if params.get("week"):
            return httpx.Response(200, json=fixture_payload("games_week"))
        return httpx.Response(200, json=fixture_payload("games_week") + fixture_payload("games_team"))

    fake.route("/games", handler=games)
    fake.fixture("/teams/fbs", "teams_fbs")
    fake.fixture("/rankings", "rankings")
    fake.fixture("/calendar", "calendar")


def route_analytics(fake: FakeCfbd) -> None:
    fake.route("/games", handler=lambda r: httpx.Response(200, json=fixture_payload("games_team")))
    fake.fixture("/metrics/wp", "metrics_wp")
    fake.fixture("/ppa/games", "ppa_games")
    fake.fixture("/game/box/advanced", "game_box_advanced")  # Phase 13
    fake.route("/ppa/players/games", handler=lambda r: httpx.Response(200, json=fixture_payload("ppa_players_games") if r.url.params.get("team") == "Swampwater Tech" else []))


def set_clock(app, when: datetime) -> None:
    app.state.cfbd._clock = lambda: when


def quiet_engine(app, client: TestClient) -> None:
    """The background schedule watcher must not add calls of its own during a counted test."""
    client.portal.call(app.state.live.stop_background)


def isNum_rank(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def ap_ranked(school: str) -> bool:
    weeks = [w for w in fixture_payload("rankings") if isinstance(w, dict)]
    latest = max(weeks, key=lambda w: w.get("week") or 0)
    for poll in latest.get("polls") or []:
        if poll.get("poll") == "AP Top 25":
            return any(r.get("school") == school for r in poll.get("ranks") or [])
    return False


# --- radio -----------------------------------------------------------------------------------------


STATIONS = [
    {"name": "Station stream", "kind": "stream", "url": "https://radio.example.invalid/live.mp3"},
    {"name": "Station player", "kind": "embed", "url": "https://radio.example.invalid/player"},
    {"name": "Station page", "kind": "link", "url": "https://radio.example.invalid/listen"},
]


def test_no_radio_source_is_built_in(client: TestClient):
    body = client.get("/api/radio/sources").json()
    assert body["data"]["sources"] == [] and "delay" in body["data"]["note"]  # public release Phase 3: RADIO_SOURCES names the team's own


def test_radio_sources_are_listed_in_order_without_secrets(tmp_path, monkeypatch, fake_cfbd: FakeCfbd):
    from app.config import load_settings
    from app.main import create_app

    monkeypatch.setenv("RADIO_SOURCES", json.dumps(STATIONS))
    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, data_dir=str(tmp_path / "data"), log_dir=str(tmp_path / "logs"))
    with TestClient(create_app(settings, cfbd_transport=fake_cfbd.transport), base_url="https://testserver") as client:
        body = client.get("/api/radio/sources").json()
    sources = body["data"]["sources"]
    assert [s["kind"] for s in sources] == ["stream", "embed", "link"]
    assert sources[1]["url"] == STATIONS[1]["url"] and len({s["id"] for s in sources}) == 3
    assert TEST_KEY not in json.dumps(body) and "delay" in body["data"]["note"]


# --- ticker --------------------------------------------------------------------------------------------


def test_ticker_on_the_free_tier_reads_the_week_and_keeps_every_fbs_game(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_week(fake_cfbd)
    quiet_engine(app, client)
    set_clock(app, datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc))  # the Wednesday before
    body = client.get("/api/ticker?delay=30").json()
    assert body["errors"] == []
    data = body["data"]
    assert data["source"] == "games" and data["week"] == 4 and data["delaySeconds"] == 30
    games = data["games"]
    assert games and all(g["status"] == "pre" for g in games)
    for g in games:
        assert g["home"]["school"] in TEAMS or g["away"]["school"] in TEAMS, (g["home"]["school"], g["away"]["school"])  # every FBS game, nothing else
    schools = {g["home"]["school"] for g in games} | {g["away"]["school"] for g in games}
    assert {"Swampwater Tech", "Lake Effect"} <= schools and "Pebble Creek" not in schools  # an FCS team with no FBS game this week
    ranked = [g for g in games if isNum_rank(g["home"]["rank"]) or isNum_rank(g["away"]["rank"])]
    assert ranked and all(ap_ranked(g["home"]["school"]) or ap_ranked(g["away"]["school"]) for g in ranked)
    assert len(games) >= 40  # a full FBS Saturday, not a dozen games
    us = next(g for g in games if g["isUs"])
    assert us["gameId"] == NEXT_GAME and us["home"]["abbr"] == "SWT" and us["detail"].endswith("PM") and us["home"]["points"] is None
    calls = fake_cfbd.count("/games")
    again = client.get("/api/ticker?delay=30").json()["data"]
    assert fake_cfbd.count("/games") == calls and len(again["games"]) == len(games)  # nothing is on: the cached slate serves


def test_ticker_refreshes_every_five_minutes_only_while_games_are_on(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_week(fake_cfbd)
    quiet_engine(app, client)
    app.state.cfbd.capabilities.tier_level = 2  # a paid key; the Free profile's 20 minutes are tested below
    set_clock(app, KICKOFF - timedelta(minutes=50))
    client.get("/api/ticker")
    calls = fake_cfbd.count("/games")
    client.get("/api/ticker")
    assert fake_cfbd.count("/games") == calls  # within five minutes of the last slate
    set_clock(app, KICKOFF - timedelta(minutes=44))
    body = client.get("/api/ticker").json()
    assert fake_cfbd.count("/games") == calls + 1  # a game is within the hour and the slate is older than five minutes
    assert any(g["isUs"] for g in body["data"]["games"])
    set_clock(app, KICKOFF - timedelta(minutes=43))
    client.get("/api/ticker")
    assert fake_cfbd.count("/games") == calls + 1



def test_a_free_key_refreshes_the_ticker_every_twenty_minutes(app, client: TestClient, fake_cfbd: FakeCfbd):
    """Public release Phase 5a: the Free profile keeps a free key's 1,000 calls for the whole month."""
    route_week(fake_cfbd)
    quiet_engine(app, client)
    app.state.cfbd.capabilities.tier_level = 0

    def slates() -> int:  # the week's slate the ticker reads (the team's own schedule keeps its own timer)
        return sum(1 for r in fake_cfbd.requests if r.url.path == "/games" and "week" in r.url.params)

    set_clock(app, KICKOFF - timedelta(minutes=50))
    client.get("/api/ticker")
    calls = slates()
    set_clock(app, KICKOFF - timedelta(minutes=40))
    client.get("/api/ticker")
    assert slates() == calls  # ten minutes: the slate is still young enough
    set_clock(app, KICKOFF - timedelta(minutes=29))
    client.get("/api/ticker")
    assert slates() == calls + 1  # past twenty minutes: refreshed once

def test_our_ticker_entry_follows_the_spoiler_delay(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_week(fake_cfbd)
    quiet_engine(app, client)
    now = KICKOFF + timedelta(minutes=40)
    set_clock(app, now)
    engine = app.state.live
    engine.mode, engine.current_game_id, engine.home, engine.away = "live", NEXT_GAME, "Swampwater Tech", "Diner Tech"
    engine.store.append([LiveEvent("status:1", "status", NEXT_GAME, now - timedelta(seconds=40), {"status": "in_progress", "homeScore": 14, "awayScore": 7, "period": 2, "clock": {"minutes": 3, "seconds": 20}, "possession": "Swampwater Tech"})])
    fresh = next(g for g in client.get("/api/ticker?delay=0").json()["data"]["games"] if g["isUs"])
    assert fresh["status"] == "live" and fresh["home"]["points"] == 14 and fresh["away"]["points"] == 7 and fresh["detail"] == "Q2 3:20"
    held = next(g for g in client.get("/api/ticker?delay=90").json()["data"]["games"] if g["isUs"])
    assert held["home"]["points"] != 14 and held["status"] != "final"  # the score from 40 s ago is not released at a 90 s delay
    others = [g for g in client.get("/api/ticker?delay=0").json()["data"]["games"] if not g["isUs"] and g["kickoff"] and g["kickoff"] <= now.isoformat()]
    assert others and all(g["status"] == "live" and g["detail"] == "In progress" for g in others)


def test_ticker_uses_the_scoreboard_when_the_key_has_it(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_week(fake_cfbd)
    quiet_engine(app, client)
    set_clock(app, KICKOFF + timedelta(hours=1))
    app.state.cfbd.capabilities.scoreboard = True
    # the real scoreboard names teams with their mascot and carries the team id (sample recorded 2026-09-23)
    fake_cfbd.route(
        "/scoreboard",
        json=[
            {"id": 1, "startDate": "2026-09-26T19:30:00.000Z", "status": "in_progress", "period": 3, "clock": "7:12", "homeTeam": {"id": TEAMS["Gravy Boat State"]["id"], "name": "Gravy Boat State Ladles", "conference": "Biscuit Belt", "points": 21}, "awayTeam": {"id": TEAMS["Bluegrass Bottoms"]["id"], "name": "Bluegrass Bottoms Banjos", "conference": "Biscuit Belt", "points": 10}},
            {"id": 2, "startDate": "2026-09-26T23:30:00.000Z", "status": "scheduled", "homeTeam": {"id": TEAMS["Lake Effect"]["id"], "name": "Lake Effect Flurries", "conference": "Lakeshore Lemonade", "points": None}, "awayTeam": {"id": TEAMS["Loon Lake"]["id"], "name": "Loon Lake Loons", "conference": "Lakeshore Lemonade", "points": None}},
            {"id": 3, "status": "completed", "homeTeam": {"name": "Moonpie Mountain Marshmallows", "conference": "Biscuit Belt", "points": 31}, "awayTeam": {"name": "Avalanche Valley Snowballs", "conference": "Mountain Muffin", "points": 20}},
            {"id": NEXT_GAME, "startDate": "2026-09-26T19:30:00.000Z", "status": "in_progress", "period": 1, "clock": "9:01", "homeTeam": {"id": TEAMS["Swampwater Tech"]["id"], "name": "Swampwater Tech Mudpuppies", "conference": "Biscuit Belt", "points": 7}, "awayTeam": {"id": TEAMS["Diner Tech"]["id"], "name": "Diner Tech Cooks", "conference": "Biscuit Belt", "points": 0}},
            "junk",
            {"id": 4, "homeTeam": None, "awayTeam": {"name": "Silver Dollar Griddles", "conference": "Biscuit Belt"}},
        ],
    )
    body = client.get("/api/ticker").json()
    data = body["data"]
    assert data["source"] == "scoreboard" and fake_cfbd.count("/scoreboard") == 1
    by_id = {g["gameId"]: g for g in data["games"]}
    assert set(by_id) == {1, 2, 3, NEXT_GAME}  # every FBS game; the junk row and the one without a home side are dropped
    assert by_id[2]["status"] == "pre" and by_id[2]["home"]["school"] == "Lake Effect" and by_id[2]["detail"].endswith("PM")
    assert by_id[1]["status"] == "live" and by_id[1]["detail"] == "Q3 7:12" and by_id[1]["home"]["points"] == 21
    assert by_id[1]["home"]["school"] == "Gravy Boat State" and by_id[1]["away"]["abbr"] == TEAMS["Bluegrass Bottoms"]["abbreviation"]  # resolved by id
    assert by_id[3]["status"] == "final" and by_id[3]["detail"] == "Final" and by_id[3]["away"]["points"] == 20 and by_id[3]["home"]["school"] == "Moonpie Mountain"  # resolved by name
    us = by_id[NEXT_GAME]
    assert us["isUs"] and us["home"]["school"] == "Swampwater Tech" and us["home"]["points"] is None and us["detail"] == "In progress"  # the app is not watching: no score leaks
    assert [g["gameId"] for g in data["games"]][-1] == 3  # live first, then finals
    assert any(e["code"] == "records_skipped" for e in body["errors"])


# --- analytics -------------------------------------------------------------------------------------------


def test_analytics_route_returns_win_probability_and_play_value(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_analytics(fake_cfbd)
    quiet_engine(app, client)
    set_clock(app, datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc))
    body = client.get(f"/api/games/{LAST_GAME}/analytics").json()
    assert body["errors"] == []
    data = body["data"]
    assert data["completed"] and data["homeIsUs"] is False and data["them"] == "Silver Dollar" and data["week"] == int(ROLES["LASTWEEK"])
    wp = data["winProbability"]
    plays = [p["play"] for p in wp["series"]]
    assert wp["available"] and len(plays) == facts.wp_points() and plays == sorted(plays)
    assert 0 <= wp["usFinal"] <= 1 and all(0 <= p["homeWp"] <= 1 for p in wp["series"]) and wp["note"] is None
    ppa = data["ppa"]
    assert ppa["available"] and ppa["teams"]["us"]["gameId"] == LAST_GAME and ppa["teams"]["us"]["offense"]["overall"] is not None and ppa["teams"]["them"] is None
    players = ppa["players"]["us"]
    assert players and all(p["opponent"] == "Silver Dollar" for p in players) and ppa["players"]["them"] == []
    assert players[0]["all"] >= players[-1]["all"]
    assert client.get("/api/games/12345/analytics").status_code == 404
    assert client.get("/api/games/abc/analytics").status_code == 404


def test_analytics_survives_malformed_payloads(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_analytics(fake_cfbd)
    quiet_engine(app, client)
    fake_cfbd.route("/metrics/wp", json=[{"playId": "a", "homeWinProbability": "bad"}, {"playId": "b", "homeWinProbability": 1.7, "playNumber": 2}, {"playId": "c", "homeWinProbability": 0.4, "playNumber": None}, "junk", {"playId": "d", "homeWinProbability": 0.6, "playNumber": 1}])
    fake_cfbd.route("/ppa/games", json=[{"gameId": LAST_GAME, "team": "Swampwater Tech", "offense": {"overall": "x"}, "defense": None}, {"gameId": "nope"}, None])
    fake_cfbd.route("/ppa/players/games", json=[{"id": "1", "name": "A", "team": "Swampwater Tech", "opponent": "Silver Dollar", "averagePPA": {"all": None}}, {"id": None}, 7])
    body = client.get(f"/api/games/{LAST_GAME}/analytics").json()
    data = body["data"]
    assert [p["play"] for p in data["winProbability"]["series"]] == [1, None] and data["winProbability"]["available"]
    assert data["ppa"]["teams"]["us"] is None and data["ppa"]["players"]["us"] == [{"playerId": "1", "name": "A", "position": None, "opponent": "Silver Dollar", "all": None, "pass": None, "rush": None}]
    assert any(e["code"] == "records_skipped" for e in body["errors"])
    fake_cfbd.route("/metrics/wp", json=[])
    fake_cfbd.route("/ppa/games", json=[])
    fake_cfbd.route("/ppa/players/games", json=[])
    empty = client.get("/api/games/526000153/analytics").json()["data"]  # the Campbell game: nothing cached for it yet
    assert empty["winProbability"]["available"] is False and empty["winProbability"]["note"] and empty["ppa"]["available"] is False and empty["ppa"]["note"]


def test_archive_carries_the_win_probability(app, client: TestClient, fake_cfbd: FakeCfbd):
    fake_cfbd.fixture("/metrics/wp", "metrics_wp")
    quiet_engine(app, client)
    engine = app.state.live
    series = client.portal.call(engine.fetch_win_probability, LAST_GAME)
    assert series and len(series) == facts.wp_points() and series[0]["play"] == 0
    window = GameWindow(LAST_GAME, "Silver Dollar", "Swampwater Tech", 3, KICKOFF, KICKOFF - timedelta(minutes=30), KICKOFF + timedelta(hours=5))
    path = engine.write_archive(window, series)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["winProbability"][0]["homeWp"] == series[0]["homeWp"] and saved["state"]["gameId"] == LAST_GAME
    fake_cfbd.route("/metrics/wp", status=401, json={"message": "Unauthorized"})
    assert client.portal.call(engine.fetch_win_probability, LAST_GAME) is None
    assert engine.write_archive(window, None) is not None and json.loads(path.read_text(encoding="utf-8"))["winProbability"] is None


# --- client: the max_age ceiling and the unscaled ticker lifetime ----------------------------------------


def test_max_age_forces_a_refresh_and_the_ticker_lifetime_is_not_scaled(app, client: TestClient, fake_cfbd: FakeCfbd):
    fake_cfbd.route("/games", handler=lambda r: httpx.Response(200, json=fixture_payload("games_team")))
    quiet_engine(app, client)
    cfbd = app.state.cfbd
    params = {"year": 2026, "week": 4}
    t0 = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)  # a Saturday: the schedule lifetime is 15 minutes, times four on the Free key
    cfbd._clock = lambda: t0
    client.portal.call(lambda: cfbd.get("/games", params, kind=DataKind.SCHEDULE))
    calls = fake_cfbd.count("/games")
    client.portal.call(lambda: cfbd.get("/games", params, kind=DataKind.SCHEDULE, max_age=timedelta(minutes=5)))
    assert fake_cfbd.count("/games") == calls  # brand new: under the ceiling
    cfbd._clock = lambda: t0 + timedelta(minutes=6)
    client.portal.call(lambda: cfbd.get("/games", params, kind=DataKind.SCHEDULE))
    assert fake_cfbd.count("/games") == calls  # still fresh by its own lifetime
    fetched = client.portal.call(lambda: cfbd.get("/games", params, kind=DataKind.TICKER, max_age=timedelta(minutes=5)))
    assert fake_cfbd.count("/games") == calls + 1 and fetched.source == "live"  # older than the ceiling: refetched, stored with the ticker lifetime
    cfbd._clock = lambda: t0 + timedelta(minutes=10)
    client.portal.call(lambda: cfbd.get("/games", params, kind=DataKind.TICKER))
    assert fake_cfbd.count("/games") == calls + 1  # four minutes old: inside five minutes
    cfbd._clock = lambda: t0 + timedelta(minutes=12)
    client.portal.call(lambda: cfbd.get("/games", params, kind=DataKind.TICKER))
    assert fake_cfbd.count("/games") == calls + 2  # six minutes old: the five-minute lifetime is not multiplied by four


# --- the real live document (Tier 2 sample recorded 2026-09-23) ---------------------------------------------


def test_real_live_document_normalizes_with_the_feed_efficiency_block():
    from app.cfbd.models import LiveGame, parse_one
    from app.live.events import events_from_live
    from app.live.state import derive_state

    game = parse_one(LiveGame, fixture_payload("live_plays"), context="t")
    assert game is not None and game.id == LAST_GAME
    events = events_from_live(game, datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc))
    kinds = {}
    for event in events:
        kinds[event.kind] = kinds.get(event.kind, 0) + 1
    plays, drives = facts.live_counts()
    assert kinds == {"drive": drives, "play": plays, "status": 1}
    state = derive_state(events, game_id=LAST_GAME, home="Silver Dollar", away="Swampwater Tech")
    home, away = facts.last_game()["homePoints"], facts.last_game()["awayPoints"]
    assert state["status"] == "final" and state["homeScore"] == home and state["awayScore"] == away
    assert state["homeLineScores"] == facts.last_game()["homeLineScores"] and state["awayLineScores"] == facts.last_game()["awayLineScores"]
    with_epa = sum(1 for d in facts.live_doc()["drives"] for p in d["plays"] if p.get("epa") is not None)
    assert sum(1 for p in state["plays"] if p["ppa"] is not None) == with_epa  # the feed's EPA per play rides as ppa
    feed = state["feedStats"]
    ours, theirs = facts.live_team("Swampwater Tech"), facts.live_team("Silver Dollar")
    assert feed["Swampwater Tech"]["successRate"] == ours["successRate"] and feed["Silver Dollar"]["successRate"] == theirs["successRate"] and feed["Silver Dollar"]["epaPerPlay"] == theirs["epaPerPlay"] and feed["Swampwater Tech"]["deserveToWin"] is not None
    assert set(feed["Swampwater Tech"]) >= {"successRate", "epaPerPlay", "explosiveness", "pointsPerOpportunity", "scoringOpportunities", "plays", "drives"}
    # Phase 10a (C3): the team success rate is the feed's, not a local count; results are drive-bar codes
    assert state["box"]["Swampwater Tech"]["successRate"] == ours["successRate"] and state["box"]["Silver Dollar"]["successRate"] == theirs["successRate"] and state["box"]["Swampwater Tech"]["successCounts"] is None
    codes = {d["result"] for d in state["drives"]}
    assert codes <= {"TD", "FG", "PUNT", "INT", "INT TD", "FUMBLE", "MISSED FG", "SAFETY", "DOWNS", "END OF HALF", "END OF GAME"} and {"TD", "PUNT"} <= codes
    assert state["drives"][0]["resultText"] == facts.live_doc()["drives"][0]["result"]
    assert state["lastPlay"]["playType"] == "Rush" and all(p["success"] is None for p in state["plays"] if p["playType"] in ("Kickoff", "Timeout", "Penalty", "Field Goal Good"))
