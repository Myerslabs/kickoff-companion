"""Leaders, roster, recruiting, and player cards from recorded fixtures: boards ranked locally
across FBS only, the recruiting join, impact players, the notes-file visitors, cards for Swampwater Tech
and opponent players, 404 for anyone else, malformed records skipped, and a failed part reported."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.services.players import BOARDS
from tests.conftest import ROLES, FakeCfbd, fixture_payload, route_depth2, team_player_stats


def route_players(fake: FakeCfbd) -> None:
    def games(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixture_payload("games_team"))

    def player_stats(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("team") == "Swampwater Tech":
            return httpx.Response(200, json=fixture_payload("stats_player_season_team"))
        if params.get("team"):
            return httpx.Response(200, json=team_player_stats(params.get("team")))  # the next opponent is outside our conference
        if params.get("conference"):
            return httpx.Response(200, json=fixture_payload("stats_player_season_conference"))
        category = params.get("category")
        return httpx.Response(200, json=fixture_payload(f"stats_player_season_all_{category}"))

    def roster(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("team") != "Swampwater Tech":
            return httpx.Response(200, json=fixture_payload("roster_opponent"))
        year = params.get("year")
        return httpx.Response(200, json=fixture_payload("roster" if year == "2026" else f"roster_{year}"))

    def recruits(request: httpx.Request) -> httpx.Response:
        year = request.url.params.get("year")
        if request.url.params.get("team") not in (None, "Swampwater Tech"):
            return httpx.Response(200, json=fixture_payload(f"recruiting_players_opponent_{year}") if year in ("2023", "2024", "2025", "2026") else [])
        name = "recruiting_players" if year == "2026" else f"recruiting_players_{year}"
        return httpx.Response(200, json=fixture_payload(name))

    def boxes(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("week") == ROLES["LASTWEEK"]:
            return httpx.Response(200, json=fixture_payload("games_players"))
        return httpx.Response(200, json=[])

    fake.route("/games", handler=games)
    fake.route("/stats/player/season", handler=player_stats)
    fake.route("/roster", handler=roster)
    fake.route("/recruiting/players", handler=recruits)
    fake.route("/games/players", handler=boxes)
    fake.fixture("/teams/fbs", "teams_fbs")
    route_depth2(fake)  # Phase 13: adjusted boards, the portal, class ranks

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


# --- leaders -------------------------------------------------------------------------------------


def test_leaders_boards_in_every_scope(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    response = client.get("/api/season/leaders")
    assert response.status_code == 200
    body = response.json()
    assert body["errors"] == []
    data = body["data"]
    assert data["team"]["abbreviation"] == "SWT"
    conf = {t["school"]: t["conference"] for t in fixture_payload("teams_fbs")}
    assert data["opponent"]["school"] == "Diner Tech" and data["opponent"]["inConference"] is (conf["Diner Tech"] == conf["Swampwater Tech"])
    boards = {b["id"]: b for b in data["boards"]}
    assert list(boards) == [b.id for b in BOARDS]

    passing = boards["passing:YDS"]
    assert 1 <= len(passing["team"]) <= 5 and passing["team"][0]["isUs"] and passing["team"][0]["value"] > 500
    assert passing["team"][0]["nationalRank"] >= 1 and passing["nationalOf"] > 100
    assert passing["team"][0]["conferenceRank"] >= 1 and passing["conferenceOf"] > 16
    assert passing["team"][0]["headshotUrl"].startswith("/media/headshot/")
    assert len(passing["opponent"]) >= 1 and all(row["team"] == "Diner Tech" for row in passing["opponent"])
    assert len(passing["conference"]) == 10 and passing["conference"][0]["rank"] == 1
    assert len(passing["national"]) == 10 and passing["national"][0]["rank"] == 1
    assert all(row["team"] for row in passing["national"])
    assert passing["usBest"]["conferenceRank"] == passing["team"][0]["conferenceRank"]

    tackles = boards["defensive:TOT"]
    assert tackles["national"][0]["value"] >= tackles["national"][9]["value"]
    punting = boards["punting:YPP"]
    assert punting["minimum"] == {"stat": "NO", "value": 5.0}
    assert all(row["detail"]["NO"] >= 5 for row in punting["national"])

    assert data["parts"]["national_defensive"]["status"] == "ok" and "opponent" in data["parts"]  # a non-conference opponent: its own pull
    assert fake_cfbd.count("/stats/player/season") == 10  # team, conference, the non-conference opponent, seven categories


def test_national_boards_hold_fbs_players_only(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    good = fixture_payload("stats_player_season_all_passing")
    fcs = [{"playerId": "999999", "player": "FCS Star", "position": "QB", "team": "Montana", "conference": "Big Sky", "category": "passing", "statType": "YDS", "stat": "99999"}]
    fake_cfbd.route("/stats/player/season", handler=lambda r: httpx.Response(200, json=fcs + good) if r.url.params.get("category") == "passing" else httpx.Response(200, json=fixture_payload("stats_player_season_team") if r.url.params.get("team") else fixture_payload("stats_player_season_conference") if r.url.params.get("conference") else []))
    data = client.get("/api/season/leaders").json()["data"]
    passing = next(b for b in data["boards"] if b["id"] == "passing:YDS")
    assert all(row["player"] != "FCS Star" for row in passing["national"])


def test_one_failed_category_does_not_kill_the_boards(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    original = fake_cfbd.routes["/stats/player/season"]

    def flaky(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("category") == "rushing":
            return httpx.Response(500, text="down")
        return original(request)

    fake_cfbd.route("/stats/player/season", handler=flaky)
    body = client.get("/api/season/leaders").json()
    data = body["data"]
    assert data["parts"]["national_rushing"]["status"] == "error"
    rushing = next(b for b in data["boards"] if b["id"] == "rushing:YDS")
    assert rushing["national"] == [] and len(rushing["team"]) >= 1 and rushing["team"][0]["nationalRank"] is None
    passing = next(b for b in data["boards"] if b["id"] == "passing:YDS")
    assert len(passing["national"]) == 10
    assert any(e["message"].startswith("national_rushing:") for e in body["errors"])


def test_malformed_stat_rows_are_skipped(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    original = fake_cfbd.routes["/stats/player/season"]
    junk = [None, 7, "x", {"player": "No id"}, {"playerId": "1", "category": "passing", "statType": "YDS", "stat": "not a number"}, {"playerId": "2", "category": None, "statType": "YDS", "stat": 5}]

    def dirty(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("team") == "Swampwater Tech":
            return httpx.Response(200, json=junk + fixture_payload("stats_player_season_team"))
        return original(request)

    fake_cfbd.route("/stats/player/season", handler=dirty)
    body = client.get("/api/season/leaders").json()
    assert body["data"]["parts"]["team"]["skipped"] == 4  # None, 7, "x", and the row with no id
    passing = next(b for b in body["data"]["boards"] if b["id"] == "passing:YDS")
    assert passing["team"][0]["value"] > 500 and all(row["playerId"] not in ("1", "2") for row in passing["team"])


# --- roster ---------------------------------------------------------------------------------------


def test_roster_joins_recruiting_and_lists_impact_players(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    body = client.get("/api/roster").json()
    data = body["data"]
    players = data["players"]
    assert len(players) == len(fixture_payload("roster")) and players[0]["number"] is not None
    with_hs = [p for p in players if p["highSchool"]]
    assert len(with_hs) >= 40 and all(p["stars"] for p in with_hs)
    assert data["rated"] == len([p for p in players if p["stars"]]) and 3 < data["average"] < 5
    assert sum(data["starCounts"].values()) == data["rated"]
    sample = next(p for p in players if p["playerId"] == ROLES["RBID"])
    row = next(r for r in fixture_payload("roster") if r["id"] == ROLES["RBID"])
    assert sample["name"] == ROLES["RBNAME"] and sample["heightText"] == f"{row['height'] // 12}-{row['height'] % 12}" and sample["hometown"] == f"{row['homeCity']}, {row['homeState']}" and sample["headshotUrl"] == f"/media/headshot/{ROLES['RBID']}"
    assert len(data["impact"]["offense"]) == 3 and 2 <= len(data["impact"]["defense"]) <= 3  # a board with no entry yet (no interception in two games) adds no card
    assert data["impact"]["offense"][0]["board"] == "passing:YDS" and data["impact"]["offense"][0]["chips"][0].endswith("passing yards")
    assert len({p["playerId"] for p in data["impact"]["offense"]}) == 3
    # five of Swampwater Tech's classes, plus the four nationwide classes behind the blue-chip rank (Phase 16 NV)
    assert fake_cfbd.count("/recruiting/players") == 9 and fake_cfbd.count("/roster") == 1


def test_roster_survives_missing_recruiting(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    fake_cfbd.route("/recruiting/players", status=500, text="down")
    body = client.get("/api/roster").json()
    data = body["data"]
    assert len(data["players"]) == len(fixture_payload("roster")) and all(p["highSchool"] is None for p in data["players"])
    assert data["parts"]["recruits_2026"]["status"] == "error" and data["parts"]["roster"]["status"] == "ok"
    assert data["rated"] == 0 and data["average"] is None


# --- recruiting -------------------------------------------------------------------------------------


def test_recruiting_classes_and_empty_visitors(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    data = client.get("/api/recruiting").json()["data"]
    years = [c["year"] for c in data["classes"]]
    assert years == [2026, 2027]
    current = data["classes"][0]
    signed = fixture_payload("recruiting_players")
    stars = [r["stars"] for r in signed if isinstance(r["stars"], int)]
    assert current["count"] == len(signed) and current["starCounts"]["4"] == stars.count(4)
    assert abs(current["average"] - sum(stars) / len(stars)) < 0.01
    assert current["commits"][0]["nationalRank"] <= current["commits"][1]["nationalRank"]
    assert current["commits"][0]["highSchool"] and current["commits"][0]["hometown"]
    assert data["classes"][1]["count"] == len(fixture_payload("recruiting_players_2027"))
    visitors = data["visitors"]
    assert visitors["gameId"] == 526001015 and visitors["opponent"] == "Diner Tech"
    assert visitors["home"] == [] and visitors["away"] == [] and visitors["error"] is None and "No visitors list" in visitors["note"]


def test_visitors_come_from_the_notes_file(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    notes_dir: Path = app.state.settings.data_dir / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    (notes_dir / "526001015.json").write_text(
        json.dumps(
            {
                "gameId": 526001015,
                "visitors": {
                    "source": "example recruiting site",
                    "sourceUrl": "https://example.invalid/visitors",
                    "updatedAt": "2026-09-25",
                    "home": [{"name": "Recruit A", "position": "WR", "stars": 4, "highSchool": "Example High", "hometown": "Ocala, FL", "classYear": 2027, "status": "confirmed"}, {"name": None}, "junk"],
                    "away": [{"name": "Recruit B", "position": "OL", "stars": 3}],
                },
            }
        ),
        encoding="utf-8",
    )
    visitors = client.get("/api/recruiting").json()["data"]["visitors"]
    assert [v["name"] for v in visitors["home"]] == ["Recruit A"] and visitors["away"][0]["name"] == "Recruit B"
    assert visitors["source"] == "example recruiting site" and visitors["error"] is None and visitors["note"] is None


def test_broken_notes_file_is_reported_not_fatal(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    notes_dir: Path = app.state.settings.data_dir / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    (notes_dir / "526001015.json").write_text("{not json", encoding="utf-8")
    response = client.get("/api/recruiting")
    assert response.status_code == 200
    visitors = response.json()["data"]["visitors"]
    assert "not valid JSON" in visitors["error"] and visitors["home"] == []


# --- player cards --------------------------------------------------------------------------------------


def test_our_player_card(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    leaders = client.get("/api/season/leaders").json()["data"]
    qb = next(b for b in leaders["boards"] if b["id"] == "passing:YDS")["team"][0]
    response = client.get(f"/api/players/{qb['playerId']}")
    assert response.status_code == 200
    data = response.json()["data"]
    player = data["player"]
    assert player["name"] == qb["player"] and player["isUs"] is True and player["teamAbbr"] == "SWT"
    assert player["heightText"] and player["weight"] and player["hometown"]
    categories = [s["category"] for s in data["seasons"]]
    assert "passing" in categories and data["seasons"][0]["stats"]["YDS"] > 500
    last = int(ROLES["LASTWEEK"])
    assert len(data["gameLog"]) == 2 and data["gameLog"][-1]["week"] == last and data["gameLog"][-1]["result"].startswith("W")
    assert any(line["category"] == "passing" for line in data["gameLog"][-1]["lines"])
    assert data["gameLog"][0]["lines"] == []  # week 1 box not recorded: an honest empty line, not a crash
    assert data["missingWeeks"] == []
    assert [h["year"] for h in data["history"]][-1] == 2026 and len(data["history"]) >= 1
    assert data["parts"][f"box_Swampwater Tech_{last}"]["status"] == "ok"


def test_opponent_player_card_uses_the_opponent_roster(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    opp_id = fixture_payload("roster_opponent")[0]["id"]
    data = client.get(f"/api/players/{opp_id}").json()["data"]
    assert data["player"]["isUs"] is False and data["player"]["team"] == "Diner Tech"
    assert data["history"] == [] and (data["player"]["highSchool"] is None or isinstance(data["player"]["highSchool"], str))
    assert fake_cfbd.count("/roster") == 2


def test_unknown_player_is_404(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    assert client.get("/api/players/1").status_code == 404
    assert client.get("/api/players/not-an-id").status_code == 404
    assert client.get("/api/players/1").json()["errors"][0]["code"] == "not_found"


def test_everything_down_is_503(client: TestClient, fake_cfbd: FakeCfbd):
    for path in ("/games", "/stats/player/season", "/roster", "/recruiting/players", "/games/players", "/teams/fbs"):
        fake_cfbd.route(path, status=500, text="boom")
    for url in ("/api/season/leaders", "/api/roster", "/api/recruiting"):
        assert client.get(url).status_code == 503, url
