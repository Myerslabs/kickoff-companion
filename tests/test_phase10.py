"""Phase 10: the stat helpers (blue-chip ratio, PPA and usage rows, the ratings table) with junk in
the input, the ratings route, the leaders' play value and usage boards, the player card's PPA,
usage, per-game PPA, recruit line and category game log for a Mudpuppy and an opponent, the roster's
blue-chip ratio and new columns, the program's recruiting block, and the team page's blocks."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi.testclient import TestClient

from app.cfbd.models import PlayerSeasonPpa, PlayerUsage, Recruit, TeamElo, TeamFPI, TeamSP, TeamTalent, parse_records
from app.services.stats_extra import blue_chip, ppa_season_rows, ratings_rows, talent_lookup, usage_rows
from tests import league_facts as facts
from tests.conftest import ROLES, FakeCfbd, fixture_payload, route_depth2
from tests.test_players import route_players
from tests.test_program import route_program

# --- helpers -----------------------------------------------------------------------------------------------


def test_blue_chip_ratio_counts_four_and_five_stars_over_the_last_four_classes():
    def recruit(year, stars):
        return Recruit(id=f"{year}-{stars}-{id(object())}", year=year, stars=stars, name="x")

    classes = {2022: [recruit(2022, 5)] * 10, 2023: [recruit(2023, 4), recruit(2023, 3)], 2024: [recruit(2024, 5), recruit(2024, 4), recruit(2024, 2), recruit(2024, None)], 2025: [], 2026: [recruit(2026, 3)]}
    out = blue_chip(classes)
    assert [c["year"] for c in out["classes"]] == [2023, 2024, 2025, 2026]  # 2022 falls outside the last four
    assert out["blueChips"] == 3 and out["signees"] == 7 and out["ratio"] == round(3 / 7, 3)
    assert out["classes"][1] == {"year": 2024, "signees": 4, "rated": 3, "blueChips": 2, "ratio": 0.5}
    assert out["classes"][2]["ratio"] is None
    assert blue_chip({})["ratio"] is None and blue_chip({2026: ["junk", None]})["signees"] == 0


def test_ppa_and_usage_rows_read_the_real_shape_and_drop_junk():
    parsed = parse_records(PlayerSeasonPpa, fixture_payload("ppa_players_season") + [{"id": "x", "team": "Swampwater Tech", "averagePPA": {"all": "bad", "rush": None}, "totalPPA": {}}, {"id": "y", "team": "Swampwater Tech", "averagePPA": "bad"}, {"id": None}], context="t")
    assert parsed.skipped == 2  # a string where an object belongs, and no id
    rows = ppa_season_rows(parsed.records, "Swampwater Tech")
    assert rows and rows[-1]["playerId"] == "x"  # the empty one sorts last
    assert all(r["team"] == "Swampwater Tech" for r in rows) and set(rows[0]["average"]) == {"all", "pass", "rush", "firstDown", "secondDown", "thirdDown", "standardDowns", "passingDowns"}
    junk = next(r for r in rows if r["playerId"] == "x")
    assert junk["all"] is None and junk["plays"] is None and junk["average"]["rush"] is None
    # The season answer sends no play count; total over average gives it back, exact on the recording.
    plays = {r["name"]: r["plays"] for r in rows}
    truth = facts.ppa_play_counts()
    assert plays and all(plays[name] == truth[name] for name in plays if name in truth and plays[name] is not None)
    # So the ten-play minimum now applies: a player with fewer plays no longer leads, and a row with no count stays.
    ten = ppa_season_rows(parsed.records, "Swampwater Tech", 10)
    assert ten and all(r["plays"] is None or r["plays"] >= 10 for r in ten) and len(ten) <= len(rows)
    few = [r for r in rows if isinstance(r["plays"], int) and r["plays"] < 10]
    assert all(r["name"] not in {t["name"] for t in ten} for r in few)
    assert {"Micah Jones", "Justin Williams"}.isdisjoint(r["name"] for r in ten) and all(r["plays"] is None or r["plays"] >= 10 for r in ten)
    assert any(r["playerId"] == "x" for r in ten)
    usage = usage_rows(parse_records(PlayerUsage, fixture_payload("player_usage") + [{"id": "y", "team": "Swampwater Tech", "usage": None}], context="t").records, "Swampwater Tech")
    assert usage and 0 <= usage[0]["overall"] <= 1 and next(r for r in usage if r["playerId"] == "y")["overall"] is None


def test_ratings_rows_rank_every_team_and_keep_ours():
    sp = parse_records(TeamSP, fixture_payload("ratings_sp"), context="t").records
    elo = parse_records(TeamElo, fixture_payload("ratings_elo"), context="t").records
    fpi = parse_records(TeamFPI, fixture_payload("ratings_fpi"), context="t").records
    talent = parse_records(TeamTalent, fixture_payload("talent") + [{"team": "Nowhere", "talent": "x"}, "junk"], context="t").records
    rows = ratings_rows(sp, elo, fpi, talent, {"Swampwater Tech": "Biscuit Belt"})
    swt = next(r for r in rows if r["team"] == "Swampwater Tech")
    assert len(rows) > 100 and rows[0]["sp"]["rank"] == 1 and swt["conference"] == "Biscuit Belt"
    assert swt["sp"]["rating"] is not None and swt["spOffense"]["rank"] and swt["spDefense"]["rank"]
    assert swt["elo"]["rank"] and swt["fpi"]["rank"] and swt["talent"]["rank"]
    assert talent_lookup(talent)["Swampwater Tech"]["of"] == len(fixture_payload("talent"))


# --- routes -----------------------------------------------------------------------------------------------------


def test_ratings_route(app, client: TestClient, fake_cfbd: FakeCfbd):
    fake_cfbd.fixture("/ratings/sp", "ratings_sp")
    fake_cfbd.fixture("/ratings/elo", "ratings_elo")
    fake_cfbd.fixture("/ratings/fpi", "ratings_fpi")
    fake_cfbd.fixture("/talent", "talent")
    fake_cfbd.fixture("/teams/fbs", "teams_fbs")
    fake_cfbd.route("/games", json=fixture_payload("games_week") + fixture_payload("games_team"))
    route_depth2(fake_cfbd)
    body = client.get("/api/ratings").json()
    assert body["errors"] == []
    data = body["data"]
    assert data["team"] == "Swampwater Tech" and data["us"]["team"] == "Swampwater Tech" and data["counts"]["sp"] == len(data["rows"]) and data["counts"]["talent"] > 100
    assert data["rows"][0]["sp"]["rank"] == 1


def test_leaders_carry_play_value_and_usage_boards(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    body = client.get("/api/season/leaders").json()
    assert body["errors"] == []
    extra = {b["id"]: b for b in body["data"]["extraBoards"]}
    ppa = extra["ppa:all"]
    assert ppa["format"] == "+2f" and ppa["team"] and ppa["opponent"] and ppa["national"] and ppa["conference"]
    assert all(e["isUs"] for e in ppa["team"]) and all(e["team"] == "Diner Tech" for e in ppa["opponent"])
    assert ppa["national"][0]["rank"] == 1 and ppa["national"][0]["value"] >= ppa["national"][-1]["value"]
    assert [c["key"] for c in ppa["detailColumns"]] == ["plays", "pass", "rush"] and "plays" in ppa["team"][0]["detail"]
    usage = extra["usage:overall"]
    assert usage["format"] == "pct" and usage["team"] and usage["opponent"] and usage["national"] == [] and usage["conferenceOf"] is None


def test_our_player_card_carries_ppa_usage_recruit_and_category_game_log(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    rb = ROLES["RBID"]  # our first running back
    body = client.get(f"/api/players/{rb}").json()
    assert body["errors"] == []
    data = body["data"]
    assert data["ppa"]["season"]["playerId"] == rb and data["ppa"]["season"]["average"]["rush"] is not None and data["ppa"]["teamRank"] and data["ppa"]["teamOf"]
    assert data["ppa"]["games"] and data["ppa"]["games"][0]["week"] == int(ROLES["LASTWEEK"]) and data["ppa"]["games"][0]["opponent"] == "Silver Dollar"
    assert data["usage"]["playerId"] == rb and 0 <= data["usage"]["overall"] <= 1
    signed = [r for name in ("recruiting_players", "recruiting_players_2022", "recruiting_players_2023", "recruiting_players_2024", "recruiting_players_2025")
              for r in fixture_payload(name) if r.get("athleteId") == rb]
    recruit = data["player"]["recruit"]
    assert (recruit is None) if not signed else (recruit["stars"] == signed[0]["stars"] and recruit["year"] == signed[0]["year"])
    assert data["gameLog"] and all("lines" in g for g in data["gameLog"])
    joined = {r["athleteId"]: r for name in ("recruiting_players_2023", "recruiting_players_2024", "recruiting_players_2025")
              for r in fixture_payload(name) if r.get("athleteId")}
    pid = next(r["id"] for r in fixture_payload("roster") if r["id"] in joined)  # a player signed out of high school
    signed = client.get(f"/api/players/{pid}").json()["data"]
    recruit = signed["player"]["recruit"]
    want = joined[pid]
    assert recruit and recruit["stars"] == want["stars"] and recruit["nationalRank"] == want["ranking"] and recruit["year"] == want["year"] and recruit["rating"]


def test_opponent_player_card_gets_its_recruit_line_and_play_value(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    opp_id = fixture_payload("ppa_players_season_opponent")[0]["id"]
    roster_ids = {p["id"] for p in fixture_payload("roster_opponent")}
    if opp_id not in roster_ids:
        opp_id = next(iter(roster_ids))
    body = client.get(f"/api/players/{opp_id}").json()
    data = body["data"]
    assert data["player"]["team"] == "Diner Tech" and data["player"]["isUs"] is False
    assert "recruit" in data["player"] and "ppa" in data and "usage" in data and fake_cfbd.count("/recruiting/players") >= 4


def test_roster_carries_blue_chip_ratio_ppa_and_usage(client: TestClient, fake_cfbd: FakeCfbd):
    route_players(fake_cfbd)
    body = client.get("/api/roster").json()
    assert body["errors"] == []
    data = body["data"]
    bc = data["blueChip"]
    assert bc["signees"] > 0 and 0 <= bc["ratio"] <= 1 and [c["year"] for c in bc["classes"]] == [2023, 2024, 2025, 2026]
    with_ppa = [p for p in data["players"] if p["ppaPerPlay"] is not None]
    assert with_ppa and all("ppaPlays" in p for p in with_ppa) and any(p["usageShare"] is not None for p in data["players"])


def test_program_and_team_page_carry_talent_recruiting_and_play_value(pclient_program):
    pclient, fake = pclient_program
    body = pclient.get("/api/program/next").json()
    assert body["errors"] == []
    r = body["data"]["recruiting"]
    assert r["us"]["school"] == "Swampwater Tech" and r["them"]["school"] == "Diner Tech"
    assert r["us"]["talent"]["rank"] and r["them"]["talent"]["rank"] and r["us"]["talentOf"] > 100
    assert 0 <= r["us"]["blueChip"]["ratio"] <= 1 and 0 <= r["them"]["blueChip"]["ratio"] <= 1
    assert r["us"]["returning"]["percentPPA"] == facts.returning()["percentPPA"] and r["them"]["returning"]["percentPPA"] is not None
    ppa = body["data"]["ppa"]
    assert ppa["seasonLeaders"]["us"] and ppa["seasonLeaders"]["them"] and ppa["usage"]["us"]
    team = pclient.get("/api/team/Diner%20Tech").json()["data"]
    assert team["recruiting"]["talent"]["rank"] and team["recruiting"]["blueChip"]["signees"] > 0 and team["playValue"]["players"] and team["playValue"]["usage"]


import pytest  # noqa: E402


@pytest.fixture
def pclient_program(settings, fake_cfbd: FakeCfbd):
    from app.logging_setup import configure_logging, shutdown_logging
    from app.main import create_app
    from tests.test_program import FakeSites

    configure_logging(settings)
    route_program(fake_cfbd)  # before the app starts: the engine's first schedule check must find the route
    transport = httpx.MockTransport(FakeSites().handler)
    application = create_app(settings, cfbd_transport=fake_cfbd.transport, feeds_transport=transport, weather_transport=transport)
    with TestClient(application, base_url="https://testserver") as test_client:
        application.state.cfbd._clock = lambda: datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc)
        yield test_client, fake_cfbd
    shutdown_logging()
