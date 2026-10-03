"""The program, the newspaper, and the team page from recorded fixtures: the next program builds
itself, a past game shows its final box, the notes file feeds schemes and availability, weather
comes from NWS with the CFBD tier lacking it, the newspaper gates the slate on game day and
reports the opening rule, a team page builds for any FBS team, and failures degrade cleanly."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.logging_setup import configure_logging, shutdown_logging
from app.main import create_app
from tests import league_facts as facts
from tests.conftest import ROLES, FakeCfbd, fixture_payload, route_depth2, team_player_stats

FEEDS = Path(__file__).parent / "fixtures" / "feeds"
NWS = Path(__file__).parent / "fixtures" / "nws"
NEXT_GAME = 526001015
LAST_GAME = 526000600


def route_program(fake: FakeCfbd) -> None:
    def games(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("team") == "Swampwater Tech":
            return httpx.Response(200, json=fixture_payload("games_team"))
        if params.get("team"):
            return httpx.Response(200, json=fixture_payload("games_opponent"))
        if params.get("week"):
            return httpx.Response(200, json=fixture_payload("games_week"))
        return httpx.Response(200, json=fixture_payload("games_week") + fixture_payload("games_team"))

    def by_week(name: str):
        def handler(request: httpx.Request) -> httpx.Response:
            week = request.url.params.get("week")
            if week == "3":
                return httpx.Response(200, json=fixture_payload(name))
            if week in ("1", "2"):
                return httpx.Response(200, json=fixture_payload(f"{name}_{week}"))
            return httpx.Response(200, json=[])
        return handler

    def media(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("week"):
            return httpx.Response(200, json=fixture_payload("games_media_week"))
        return httpx.Response(200, json=fixture_payload("games_media"))

    def lines(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixture_payload("lines_week" if request.url.params.get("week") and not request.url.params.get("team") else "lines"))

    def pregame(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixture_payload("metrics_wp_pregame_week" if not request.url.params.get("team") else "metrics_wp_pregame"))

    def records(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixture_payload("records_all"))

    def player_stats(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("team") == "Swampwater Tech":
            return httpx.Response(200, json=fixture_payload("stats_player_season_team"))
        return httpx.Response(200, json=team_player_stats(params.get("team")))

    def roster(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixture_payload("roster" if request.url.params.get("team") == "Swampwater Tech" else "roster_opponent"))

    fake.route("/games", handler=games)
    fake.route("/games/teams", handler=by_week("games_teams"))
    fake.route("/games/players", handler=by_week("games_players"))
    fake.route("/games/media", handler=media)
    fake.route("/lines", handler=lines)
    fake.route("/metrics/wp/pregame", handler=pregame)
    fake.route("/records", handler=records)
    fake.route("/stats/player/season", handler=player_stats)
    fake.route("/roster", handler=roster)
    fake.fixture("/rankings", "rankings")
    fake.fixture("/teams/fbs", "teams_fbs")
    fake.fixture("/stats/season", "stats_season_fbs")
    fake.fixture("/stats/season/advanced", "stats_season_advanced_fbs")
    fake.fixture("/ratings/sp", "ratings_sp")
    fake.fixture("/teams/matchup", "teams_matchup")
    fake.fixture("/venues", "venues")
    fake.fixture("/coaches", "coaches_opponent")
    fake.fixture("/games/weather", "games_weather")
    fake.fixture("/ppa/games", "ppa_games")

    def recruits(request: httpx.Request) -> httpx.Response:
        year = request.url.params.get("year")
        if request.url.params.get("team") == "Swampwater Tech":
            return httpx.Response(200, json=fixture_payload("recruiting_players" if year == "2026" else f"recruiting_players_{year}") if year in ("2022", "2023", "2024", "2025", "2026", "2027") else [])
        return httpx.Response(200, json=fixture_payload(f"recruiting_players_opponent_{year}") if year in ("2023", "2024", "2025", "2026") else [])

    fake.route("/recruiting/players", handler=recruits)

    def ppa_season(request: httpx.Request) -> httpx.Response:
        team = request.url.params.get("team")
        if team == "Swampwater Tech":
            return httpx.Response(200, json=fixture_payload("ppa_players_season"))
        if team:
            return httpx.Response(200, json=fixture_payload("ppa_players_season_opponent") if team == "Diner Tech" else [])
        return httpx.Response(200, json=fixture_payload("ppa_players_season_all"))

    def usage(request: httpx.Request) -> httpx.Response:
        team = request.url.params.get("team")
        return httpx.Response(200, json=fixture_payload("player_usage") if team == "Swampwater Tech" else fixture_payload("player_usage_opponent") if team == "Diner Tech" else [])

    def returning(request: httpx.Request) -> httpx.Response:
        team = request.url.params.get("team")
        return httpx.Response(200, json=fixture_payload("player_returning") if team == "Swampwater Tech" else fixture_payload("player_returning_opponent") if team == "Diner Tech" else [])

    def ppa_games(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixture_payload("ppa_players_games") if request.url.params.get("team") == "Swampwater Tech" and request.url.params.get("week") == ROLES["LASTWEEK"] else [])

    fake.route("/ppa/players/season", handler=ppa_season)
    fake.route("/player/usage", handler=usage)
    fake.route("/player/returning", handler=returning)
    fake.route("/ppa/players/games", handler=ppa_games)
    fake.fixture("/talent", "talent")
    route_depth2(fake)  # Phase 13: tendencies, adjusted metrics, the advanced box


class FakeSites:
    """Feeds and NWS on one transport, keyed by host."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(url)
        if self.down:
            return httpx.Response(503)
        if "weather.gov/points" in url:
            return httpx.Response(200, json=json.loads((NWS / "points.json").read_text(encoding="utf-8")))
        if "weather.gov" in url:
            return httpx.Response(200, json=json.loads((NWS / "forecast.json").read_text(encoding="utf-8")))
        for name in ("swampwatertech", "espn", "theathletic", "news.google"):
            if name in url:
                key = {"swampwatertech": "team", "espn": "espn", "theathletic": "athletic", "news.google": "google"}[name]
                return httpx.Response(200, content=(FEEDS / f"{key}.xml").read_bytes(), headers={"content-type": "application/xml"})
        return httpx.Response(404)


@pytest.fixture
def sites() -> FakeSites:
    return FakeSites()


@pytest.fixture
def program_app(settings: Settings, fake_cfbd: FakeCfbd, sites: FakeSites):
    configure_logging(settings)
    transport = httpx.MockTransport(sites.handler)
    application = create_app(settings, cfbd_transport=fake_cfbd.transport, feeds_transport=transport, weather_transport=transport)
    yield application
    shutdown_logging()


@pytest.fixture
def pclient(program_app):
    with TestClient(program_app, base_url="https://testserver") as test_client:
        yield test_client


def set_clock(app, when: datetime) -> None:
    app.state.cfbd._clock = lambda: when


# --- program ---------------------------------------------------------------------------------------


def test_next_program_builds_itself(pclient: TestClient, fake_cfbd: FakeCfbd, program_app, sites: FakeSites):
    route_program(fake_cfbd)
    set_clock(program_app, datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc))  # Wednesday of Diner Tech week
    response = pclient.get("/api/program/next")
    assert response.status_code == 200
    body = response.json()
    assert body["errors"] == []
    data = body["data"]
    game = data["game"]
    assert game["gameId"] == NEXT_GAME and game["week"] == 4 and game["homeIsUs"] and game["tv"] == facts.outlet(NEXT_GAME) and not game["completed"]
    assert game["venue"] == "Swampwater Tech Memorial Stadium" and game["venueDetail"]["capacity"] == facts.capacity("Swampwater Tech")
    assert data["us"]["school"] == "Swampwater Tech" and data["them"]["school"] == "Diner Tech" and data["them"]["apRank"] == facts.ap_rank("Diner Tech") and data["them"]["logo"]
    book = facts.line(NEXT_GAME)
    assert data["line"]["formatted"] == book["formattedSpread"] and data["line"]["overUnder"] == book["overUnder"]
    assert "provider" not in data["line"] and "Moneyline" not in json.dumps(data["line"])  # the line, never the book
    assert 0 < data["pregame"]["usWinProbability"] < 1
    weather = data["weather"]
    assert weather["available"] and weather["source"] == "National Weather Service" and isinstance(weather["tempF"], (int, float)) and weather["sky"]
    assert any("weather.gov" in url for url in sites.calls)
    assert len(data["profile"]["us"]) == 26 and len(data["profile"]["them"]) == 26
    assert data["profile"]["us"][1]["nationalRank"] and data["profile"]["them"][1]["nationalRank"]
    assert len(data["edges"]) >= 8 and all(isinstance(e["edge"], int) for e in data["edges"])
    assert all(abs(e["edge"]) < e["of"] <= 140 for e in data["edges"])  # FBS ranks only, never FCS teams from the all-games list
    assert abs(data["edges"][0]["edge"]) >= abs(data["edges"][-1]["edge"])
    leaders = {l["label"]: l for l in data["leaders"]}
    assert leaders["Passing yards"]["us"]["player"] and leaders["Passing yards"]["them"]["player"]
    assert data["series"]["team1Wins"] + data["series"]["team2Wins"] > 20 and len(data["series"]["lastTen"]) == 10
    assert data["notes"]["present"] is False and data["notes"]["error"] is None
    assert data["final"] is None
    assert len(data["picker"]) == 12 and next(g for g in data["picker"] if g["week"] == 4)["gameId"] == NEXT_GAME
    assert data["advanced"]["us"][0]["nationalRank"]
    assert fake_cfbd.count("/games/weather") == 0  # the Free tier has no weather, so the client never asks


def test_past_program_shows_the_final_box(pclient: TestClient, fake_cfbd: FakeCfbd, program_app):
    route_program(fake_cfbd)
    set_clock(program_app, datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc))
    data = pclient.get(f"/api/program/{LAST_GAME}").json()["data"]
    assert data["game"]["completed"] and (data["game"]["usPoints"], data["game"]["themPoints"]) == facts.scores(facts.last_game()) and not data["game"]["homeIsUs"]
    assert data["them"]["school"] == "Silver Dollar"
    final = data["final"]
    assert final["available"] and final["us"]["totalYards"] > 300 and final["them"]["points"] == facts.scores(facts.last_game())[1]
    assert final["us"]["thirdDown"]["of"] and final["players"]["us"]["passing"][0]["stats"]["YDS"]
    assert data["weather"]["available"] is False and "passed" in data["weather"]["error"]
    assert data["line"] is not None


def test_notes_file_feeds_schemes_and_availability(pclient: TestClient, fake_cfbd: FakeCfbd, program_app):
    route_program(fake_cfbd)
    set_clock(program_app, datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc))
    notes_dir: Path = program_app.state.settings.data_dir / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    (notes_dir / f"{NEXT_GAME}.json").write_text(json.dumps({
        "author": "hand", "writtenAt": "2026-09-23",
        "schemes": {"offense": "Spread", "defense": "4-2-5"},
        "sections": [{"heading": "Line movement", "paragraphs": ["Opened -1.5."]}, "junk"],
        "availability": [{"name": "A", "position": "WR", "status": "Out"}, {"name": "no status"}],
        "lineups": {"source": "Ourlads", "us": {"team": "Swampwater Tech", "slots": [{"unit": "Offense", "slot": "QB", "players": [{"name": ROLES["QBNAME"], "number": 12}, {"name": "Tramell Jones Jr."}, "junk"]}, {"players": [{"name": "no slot"}]}]}, "them": None},
    }), encoding="utf-8")
    notes = pclient.get("/api/program/next").json()["data"]["notes"]
    assert notes["present"] and notes["schemes"] == {"offense": "Spread", "defense": "4-2-5", "source": None}
    assert [s["heading"] for s in notes["sections"]] == ["Line movement"] and [a["name"] for a in notes["availability"]] == ["A"]
    # 2026-10-02: the published depth charts ride along, bad slots and names dropped, the missing team None
    lineups = notes["lineups"]
    assert lineups["source"] == "Ourlads" and lineups["them"] is None
    assert [s["slot"] for s in lineups["us"]["slots"]] == ["QB"]
    assert [p["name"] for p in lineups["us"]["slots"][0]["players"]] == [ROLES["QBNAME"], "Tramell Jones Jr."]
    assert lineups["us"]["slots"][0]["players"][0]["number"] == 12 and lineups["us"]["slots"][0]["players"][1]["number"] is None
    # the season lines attach chips and the id by name (Hamilton is in the recorded Swampwater Tech player stats)
    qb = lineups["us"]["slots"][0]["players"][0]
    assert qb["playerId"] and qb["chips"] and qb["chips"][0].endswith("passing yards")
    assert "chips" in lineups["us"]["slots"][0]["players"][1]
    (notes_dir / f"{NEXT_GAME}.json").write_text("{broken", encoding="utf-8")
    notes = pclient.get("/api/program/next").json()["data"]["notes"]
    assert notes["present"] is False and "not valid JSON" in notes["error"]


def test_unknown_game_is_404_and_a_failed_part_is_reported(pclient: TestClient, fake_cfbd: FakeCfbd, program_app):
    route_program(fake_cfbd)
    set_clock(program_app, datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc))
    assert pclient.get("/api/program/1").status_code == 404
    assert pclient.get("/api/program/abc").status_code == 404
    fake_cfbd.route("/teams/matchup", status=500, text="down")
    body = pclient.get("/api/program/next").json()
    assert body["data"]["series"] is None and body["data"]["parts"]["series"]["status"] == "error"
    assert any(e["message"].startswith("series:") for e in body["errors"]) and body["data"]["game"]["gameId"] == NEXT_GAME


def test_weather_far_out_and_dead_service_degrade(pclient: TestClient, fake_cfbd: FakeCfbd, program_app, sites: FakeSites):
    route_program(fake_cfbd)
    set_clock(program_app, datetime(2026, 9, 10, 16, 0, tzinfo=timezone.utc))  # sixteen days before Diner Tech
    weather = pclient.get("/api/program/next").json()["data"]["weather"]
    assert weather["available"] is False and "days away" in weather["error"]
    set_clock(program_app, datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc))
    sites.down = True
    weather = pclient.get("/api/program/next").json()["data"]["weather"]
    assert weather["available"] is False and "503" in weather["error"]


# --- newspaper ---------------------------------------------------------------------------------------


def test_newspaper_on_a_weekday_has_headlines_and_no_slate(pclient: TestClient, fake_cfbd: FakeCfbd, program_app):
    route_program(fake_cfbd)
    set_clock(program_app, datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc))
    data = pclient.get("/api/newspaper").json()["data"]
    assert data["gameDay"] is False and data["opensHere"] is False and data["slate"] == [] and data["slateNote"]
    assert data["nextGame"]["gameId"] == NEXT_GAME and data["nextGame"]["opponent"] == "Diner Tech"
    assert len(data["news"]) >= 10 and all(h["title"] and h["source"] for h in data["news"])
    assert set(data["feeds"]) == {"team", "espn", "athletic", "google"} and all(f["status"] == "ok" for f in data["feeds"].values())
    assert fake_cfbd.count("/lines") == 0


def test_newspaper_on_game_day_opens_there_until_an_hour_before_kickoff(pclient: TestClient, fake_cfbd: FakeCfbd, program_app):
    route_program(fake_cfbd)
    set_clock(program_app, datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc))  # 8 am Eastern on game day
    data = pclient.get("/api/newspaper").json()["data"]
    assert data["gameDay"] and data["opensHere"] and data["gameId"] == NEXT_GAME
    assert len(data["slate"]) >= 8 and data["slate"][0]["isUs"] and data["slate"][0]["home"]["school"] == "Swampwater Tech"
    assert data["slate"][0]["line"]["formatted"] == facts.line(NEXT_GAME, "lines_week")["formattedSpread"] and 0 < data["slate"][0]["homeWinProbability"] < 1
    assert all(g["home"]["school"] and g["away"]["school"] for g in data["slate"])
    assert any(g["tv"] for g in data["slate"])
    set_clock(program_app, datetime(2026, 9, 26, 19, 0, tzinfo=timezone.utc))  # 3 pm Eastern, inside the hour
    data = pclient.get("/api/newspaper").json()["data"]
    assert data["gameDay"] and data["opensHere"] is False


def test_newspaper_survives_dead_feeds(pclient: TestClient, fake_cfbd: FakeCfbd, program_app, sites: FakeSites):
    route_program(fake_cfbd)
    set_clock(program_app, datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc))
    sites.down = True
    response = pclient.get("/api/newspaper")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["news"] == [] and all(f["status"] == "error" and "503" in f["error"] for f in data["feeds"].values())


# --- team page -----------------------------------------------------------------------------------------


def test_opponent_team_page(pclient: TestClient, fake_cfbd: FakeCfbd, program_app):
    route_program(fake_cfbd)
    set_clock(program_app, datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc))
    response = pclient.get("/api/team/Diner%20Tech")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["team"]["school"] == "Diner Tech" and data["team"]["apRank"] == facts.ap_rank("Diner Tech") and data["team"]["isUs"] is False and data["team"]["record"]["wins"] == facts.record("Diner Tech", "records_all")["total"]["wins"]
    assert len(data["profile"]["rows"]) == 26 and data["profile"]["rows"][1]["nationalRank"]
    assert len(data["schedule"]) == 12 and data["schedule"][0]["opponent"]["school"]
    assert len(data["roster"]) == len(fixture_payload("roster_opponent")) and data["roster"][0]["headshotUrl"].startswith("/media/headshot/")
    assert data["coaches"][0]["name"] == "{firstName} {lastName}".format(**fixture_payload("coaches_opponent")[0]) and data["coaches"][0]["hireDate"]
    assert data["series"]["usWins"] is not None
    assert pclient.get("/api/team/Nowhere%20State").status_code == 404


def test_program_carries_play_value(pclient: TestClient, fake_cfbd: FakeCfbd, program_app):
    route_program(fake_cfbd)
    set_clock(program_app, datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc))
    data = pclient.get("/api/program/next").json()["data"]
    ppa = data["ppa"]
    assert ppa["available"] and ppa["season"]["us"]["games"] == len(fixture_payload("ppa_games")) and ppa["season"]["us"]["offense"]["overall"] is not None
    assert [g["week"] for g in ppa["games"]["us"]] == [1, 2] and ppa["games"]["them"] == []  # the opponent fixture is Swampwater Tech-only
    assert ppa["players"]["usWeek"] == int(ROLES["LASTWEEK"]) and ppa["players"]["us"] and all(p["opponent"] == "Silver Dollar" for p in ppa["players"]["us"])
    assert data["parts"]["ppaUs"]["status"] == "ok"
