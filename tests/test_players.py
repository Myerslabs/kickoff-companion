"""Leaders, roster, recruiting, and player cards from recorded fixtures: boards ranked locally
across FBS only, the recruiting join, impact players, the notes-file visitors, cards for Swampwater Tech
and opponent players, 404 for anyone else, malformed records skipped, and a failed part reported. Tables wave 3
(decision 3): our card loads its earlier seasons from the team-season answers (one call per earlier year in its
History, four at most, shared by every player of that team and year), a failed or empty season is skipped and
counted, and the game log and History name each team's abbreviation."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.cfbd.models import PlayerStat
from app.services.players import BOARDS, PAST_SEASONS, card_order, history_classes, past_team_seasons, season_lines
from tests.conftest import ROLES, FakeCfbd, fixture_payload, past_team_stats, route_depth2, team_player_stats


def route_players(fake: FakeCfbd) -> None:
    def games(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixture_payload("games_team"))

    def player_stats(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("team") == "Swampwater Tech" and params.get("year") not in (None, "2026"):
            return httpx.Response(200, json=past_team_stats(params.get("year")))  # decision 3: the card's earlier seasons
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
    # tables wave 3: each opponent's abbreviation ("at DT" at small), no postseason name in the regular season, our abbreviation
    # on every History row
    abbrs = {t["school"]: t.get("abbreviation") for t in fixture_payload("teams_fbs")}
    assert all(g["opponentAbbr"] == abbrs.get(g["opponent"]) for g in data["gameLog"]) and any(g["opponentAbbr"] for g in data["gameLog"])
    assert all(g["postseasonShort"] is None for g in data["gameLog"])
    assert all(h["teamAbbr"] == "SWT" for h in data["history"])


def test_opponent_player_card_uses_the_opponent_roster(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    opp_id = fixture_payload("roster_opponent")[0]["id"]
    data = client.get(f"/api/players/{opp_id}").json()["data"]
    assert data["player"]["isUs"] is False and data["player"]["team"] == "Diner Tech"
    assert data["history"] == [] and (data["player"]["highSchool"] is None or isinstance(data["player"]["highSchool"], str))
    assert fake_cfbd.count("/roster") == 2


# --- the card's past seasons (tables wave 3, owner decision 3) -------------------------------------------


def _team_season_calls(fake: FakeCfbd) -> list[str]:
    """The years of every team-season player stats call for Swampwater Tech, in the order made."""
    return [str(r.url.params.get("year")) for r in fake.requests if r.url.path == "/stats/player/season" and r.url.params.get("team") == "Swampwater Tech"]


def _roster_years(player_id: str) -> list[int]:
    return [y for y in range(2022, 2027) if any(r["id"] == player_id for r in fixture_payload("roster" if y == 2026 else f"roster_{y}"))]


def _lines(payload: list[dict], player_id: str, category: str) -> dict[str, str]:
    return {r["statType"]: r["stat"] for r in payload if r["playerId"] == player_id and r["category"] == category}


def test_our_card_loads_its_past_seasons(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    rb = ROLES["RBID"]
    years = _roster_years(rb)
    assert years[-1] == 2026 and len(years) >= 3, "the running back has earlier seasons on our rosters"
    body = client.get(f"/api/players/{rb}").json()
    assert body["errors"] == []
    data = body["data"]
    earlier = sorted((y for y in years if y < 2026), reverse=True)
    # one call per earlier season in the History, never more than the four the prior rosters cover, after this season's
    calls = _team_season_calls(fake_cfbd)  # the earlier seasons are asked together, in any order
    assert calls[0] == "2026" and sorted(calls[1:], reverse=True) == [str(y) for y in earlier] and len(earlier) <= PAST_SEASONS
    assert [h["year"] for h in data["history"]] == years and all(h["teamAbbr"] == "SWT" for h in data["history"])
    # the league plays last season, so 2025 has lines; the seasons before it come back empty: counted, never an error
    last = past_team_stats(2025)
    rushing = _lines(last, rb, "rushing")
    assert rushing, "the running back carried the ball last season"
    seasons = data["seasons"]
    assert {s["year"] for s in seasons} == {2026, 2025}
    mine = next(s for s in seasons if s["year"] == 2025 and s["category"] == "rushing")
    assert mine["stats"]["YDS"] == float(rushing["YDS"]) and mine["stats"]["CAR"] == float(rushing["CAR"])
    assert data["missingSeasons"] == [] and data["emptySeasons"] == [y for y in earlier if y != 2025] and data["missingHistory"] == []
    assert data["parts"]["stats_2025"]["status"] == "ok" and all(data["parts"][f"stats_{y}"]["status"] == "ok" for y in earlier)
    # reading order: the categories as the card lists them, the newest season first inside each
    keys = [card_order(s) for s in seasons]
    assert keys == sorted(keys) and seasons[0]["year"] == 2026
    assert [s["year"] for s in seasons if s["category"] == "rushing"] == [2026, 2025]


def test_past_seasons_are_shared_and_bounded(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    rb = ROLES["RBID"]
    client.get(f"/api/players/{rb}")
    first = _team_season_calls(fake_cfbd)
    # a second player of ours with seasons in the same years reads the same cached team-season answers: no new call
    other = next(r["id"] for r in fixture_payload("roster_2025") if r["id"] != rb and r["id"] in {p["id"] for p in fixture_payload("roster")})
    assert set(_roster_years(other)) - {2026} <= set(_roster_years(rb))
    assert client.get(f"/api/players/{other}").status_code == 200
    assert _team_season_calls(fake_cfbd) == first, "every player of a team and year shares its answer"
    # a player new this year has no earlier season to ask for
    fresh = next(r["id"] for r in fixture_payload("roster") if _roster_years(r["id"]) == [2026])
    before = len(fake_cfbd.requests)
    data = client.get(f"/api/players/{fresh}").json()["data"]
    assert [r for r in fake_cfbd.requests[before:] if r.url.path == "/stats/player/season" and r.url.params.get("year") != "2026"] == []
    assert data["missingSeasons"] == [] and data["emptySeasons"] == [] and {s["year"] for s in data["seasons"]} <= {2026}
    # the opponent's card reads no earlier rosters, so it asks for no earlier season
    opp = fixture_payload("roster_opponent")[0]["id"]
    before = len(fake_cfbd.requests)
    client.get(f"/api/players/{opp}")
    assert [r for r in fake_cfbd.requests[before:] if r.url.path == "/stats/player/season" and r.url.params.get("year") not in (None, "2026")] == []


def test_a_failed_past_season_is_skipped_and_named(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    healthy = fake_cfbd.routes["/stats/player/season"]
    fake_cfbd.route("/stats/player/season", handler=lambda r: httpx.Response(500, text="down") if r.url.params.get("year") == "2025" else healthy(r))
    rb = ROLES["RBID"]
    response = client.get(f"/api/players/{rb}")
    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["missingSeasons"] == [2025] and data["parts"]["stats_2025"]["status"] == "error"
    assert {s["year"] for s in data["seasons"]} == {2026}, "this season still shows"
    assert any(e["message"].startswith("stats_2025:") for e in body["errors"]), "the failure is reported, not swallowed"
    assert data["history"] and data["gameLog"], "the rest of the card is whole"


def test_a_failed_past_roster_is_named_on_the_card(client: TestClient, fake_cfbd: FakeCfbd):
    """Wave 3 review (fail loud): an earlier roster that does not load leaves its year out of the History and the past
    seasons asked for, so the card names the year rather than letting the career rows quietly miss it."""
    route_players(fake_cfbd)
    rb = ROLES["RBID"]
    failed = min(y for y in _roster_years(rb) if y < 2025)
    healthy = fake_cfbd.routes["/roster"]
    fake_cfbd.route("/roster", handler=lambda r: httpx.Response(500, text="down") if r.url.params.get("year") == str(failed) else healthy(r))
    body = client.get(f"/api/players/{rb}").json()
    data = body["data"]
    assert data["missingHistory"] == [failed]
    assert failed not in [h["year"] for h in data["history"]] and failed not in {s["year"] for s in data["seasons"]}
    assert str(failed) not in _team_season_calls(fake_cfbd), "no stats asked for a year the History does not have"
    assert any(e["message"].startswith(f"roster_{failed}:") for e in body["errors"])
    assert data["missingSeasons"] == [], "the past seasons that were asked for still load"


def test_malformed_past_season_records_are_skipped_and_counted(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    rb = ROLES["RBID"]
    good = past_team_stats(2025)
    junk = [
        None, "x", [], {"player": "No Id", "category": "rushing", "statType": "YDS", "stat": "5"},
        {"playerId": rb, "category": "rushing", "statType": "YDS", "stat": {"x": 1}},
        {"playerId": rb, "category": None, "statType": "YDS", "stat": "7"},
        {"playerId": rb, "season": 2019, "category": "rushing", "statType": "TD", "stat": "99"},  # another season: left out
        {"playerId": rb, "season": 2019, "category": "rushing", "statType": "FUMX", "stat": "4"},  # a stat the good line lacks
        {"playerId": rb, "season": 2025, "category": "rushing", "statType": "LONG", "stat": None},
    ]
    healthy = fake_cfbd.routes["/stats/player/season"]
    # the junk comes after the good lines, so another season's TD would overwrite the good one if the season filter failed
    fake_cfbd.route("/stats/player/season", handler=lambda r: httpx.Response(200, json=good + junk) if r.url.params.get("year") == "2025" else healthy(r))
    body = client.get(f"/api/players/{rb}").json()
    data = body["data"]
    assert data["parts"]["stats_2025"]["status"] == "ok" and data["parts"]["stats_2025"]["skipped"] >= 5
    assert any(e["code"] == "records_skipped" and e["message"].startswith("stats_2025:") for e in body["errors"])
    mine = next(s for s in data["seasons"] if s["year"] == 2025 and s["category"] == "rushing")
    want = _lines(good, rb, "rushing")
    assert mine["stats"]["YDS"] == float(want["YDS"]) and mine["stats"]["TD"] == float(want["TD"]), "the good lines stand, the junk never mixes in"
    assert "FUMX" not in mine["stats"], "another season's line never joins this one"


def test_an_empty_past_season_is_counted_not_shown(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    healthy = fake_cfbd.routes["/stats/player/season"]
    # last season answers with something that is not a list of lines: nothing to show, counted as empty, never an error
    fake_cfbd.route("/stats/player/season", handler=lambda r: httpx.Response(200, json={"message": "odd"}) if r.url.params.get("year") == "2025" else healthy(r))
    data = client.get(f"/api/players/{ROLES['RBID']}").json()["data"]
    assert 2025 in data["emptySeasons"] and data["missingSeasons"] == []
    assert {s["year"] for s in data["seasons"]} == {2026} and data["parts"]["stats_2025"]["status"] == "ok"


def test_past_season_helpers_guard_their_input():
    history = [
        {"year": 2026, "team": "Swampwater Tech"}, {"year": 2025, "team": "Swampwater Tech"}, {"year": 2025, "team": "Other"},
        {"year": 2024, "team": " "}, {"year": True, "team": "X"}, {"year": "2023", "team": "X"}, {"year": 2021, "team": "Too Old"},
        {"year": 2022, "team": "Swampwater Tech"}, {"year": 2023, "team": None}, {},
    ]
    assert past_team_seasons(history, 2026) == [(2025, "Swampwater Tech"), (2022, "Swampwater Tech")]
    assert len(past_team_seasons([{"year": y, "team": "T"} for y in range(2010, 2026)], 2026)) == PAST_SEASONS == 4
    assert past_team_seasons([], 2026) == []
    rows = [PlayerStat.model_validate(r) for r in [
        {"playerId": "9", "season": 2025, "category": "rushing", "statType": "YDS", "stat": "40"},
        {"playerId": "9", "season": 2024, "category": "rushing", "statType": "CAR", "stat": "8"},
        {"playerId": "9", "category": "rushing", "statType": "TD", "stat": "1"},
        {"playerId": "9", "season": 2025, "category": "fumbles", "statType": "FUM", "stat": None},
        {"playerId": "8", "season": 2025, "category": "rushing", "statType": "YDS", "stat": "3"},
    ]]
    assert season_lines(rows, "9", 2025) == [{"year": 2025, "category": "rushing", "stats": {"YDS": 40.0, "TD": 1.0}}], "another season and an empty line are left out"
    assert season_lines([], "9", 2025) == []
    lines = [{"year": 2025, "category": "puntReturns"}, {"year": 2026, "category": "oddball"}, {"year": 2025, "category": "passing"}, {"year": 2026, "category": "passing"}, {"year": None, "category": None}]
    assert [(r["category"], r["year"]) for r in sorted(lines, key=card_order)] == [("passing", 2026), ("passing", 2025), ("puntReturns", 2025), (None, None), ("oddball", 2026)]


def test_history_counts_classes_back_from_the_latest_season():
    # CFBD's old rosters repeat the current class: a 2026 junior listed as a junior in 2024 and 2025 too
    rows = [{"year": y, "team": "T", "classYear": 3, "position": "RB", "number": 13} for y in (2024, 2025, 2026)]
    assert [r["classYear"] for r in history_classes(rows)] == ["FR", "SO", "JR"]
    # a redshirt year counts below freshman: a dash, never a made-up class
    rows = [{"year": y, "classYear": 2} for y in (2023, 2024, 2025, 2026)]
    assert [r["classYear"] for r in history_classes(rows)] == [None, None, "FR", "SO"]
    # a fifth-year player counts back from year 5, and is a SR; a player gone from this year's roster counts from his last season
    assert [r["classYear"] for r in history_classes([{"year": 2023, "classYear": 1}, {"year": 2025, "classYear": 5}])] == ["JR", "SR"]
    # malformed or missing classes: no anchor, every class a dash, no crash
    assert [r["classYear"] for r in history_classes([{"year": 2025, "classYear": None}, {"year": 2026, "classYear": "JR"}, {"year": 2026, "classYear": 9}])] == [None, None, None]
    assert history_classes([]) == []


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
