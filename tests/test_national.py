"""The national lists (Phase 16, N1 zero-call part): every list agrees with the chips that open it
(Season overview, program, team page, Ratings, Leaders, Recruiting), ties share a rank and the next
rank skips, asking for every list costs no CFBD call after the pages loaded, every metric key a page
sends answers, bad requests are 404 before any fetch, a failed part degrades the list, junk
payloads never crash it or leak NaN, and player boards send the top 100 plus every Mudpuppy."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

from app.cfbd.models import TeamElo, TeamFPI, TeamSP, TeamTalent
from app.services.depth2 import shared_ranks
from app.services.national import METRICS, resolve, validate
from app.services.profiles import ranked_list, tie_ranks
from app.services.stats_extra import PSEUDO_TEAMS, fpi_tables, rank_table, sp_tables, talent_table
from tests.conftest import ROLES, FakeCfbd, fixture_payload
from tests.test_program import route_program

SEASON = 2026
FBS = len(fixture_payload("teams_fbs"))  # every FBS team in the league
OTHER = ROLES["POSTTEAM"]  # a team from another conference
OTHER_CONF = next(t["conference"] for t in fixture_payload("teams_fbs") if t["school"] == OTHER)
OUR_CLASS = next(r for r in fixture_payload("recruiting_teams") if r["team"] == "Swampwater Tech")
PASSERS = len({r["playerId"] for r in fixture_payload("stats_player_season_all_passing") if r.get("statType") == "YDS"})
SP_FIRST = next(r["team"] for r in fixture_payload("ratings_sp") if r.get("ranking") == 1)


def route_all(fake: FakeCfbd) -> None:
    """Every page's sources from the recordings: the program's, plus the Leaders category pulls
    and the Ratings page's Elo and FPI."""
    route_program(fake)

    def player_stats(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("team") == "Swampwater Tech":
            return httpx.Response(200, json=fixture_payload("stats_player_season_team"))
        if params.get("team"):
            return httpx.Response(200, json=[r for r in fixture_payload("stats_player_season_conference") if r.get("team") == params.get("team")])
        if params.get("conference"):
            return httpx.Response(200, json=fixture_payload("stats_player_season_conference"))
        return httpx.Response(200, json=fixture_payload(f"stats_player_season_all_{params.get('category')}"))

    fake.route("/stats/player/season", handler=player_stats)
    fake.fixture("/ratings/elo", "ratings_elo")
    fake.fixture("/ratings/fpi", "ratings_fpi")


PAGES = ["/api/season/overview", "/api/season/leaders", "/api/ratings", "/api/program/next", "/api/team/Diner%20Tech", "/api/team/Swampwater Tech", "/api/recruiting", "/api/roster"]


def load_pages(client: TestClient) -> dict[str, Any]:
    out = {}
    for path in PAGES:
        response = client.get(path)
        assert response.status_code == 200, path
        out[path] = response.json()["data"]
    return out


def listing(client: TestClient, metric: str, **params: Any) -> dict[str, Any]:
    query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items() if v is not None)
    response = client.get(f"/api/national/{metric}" + (f"?{query}" if query else ""))
    assert response.status_code == 200, (metric, params, response.text[:300])
    return response.json()["data"]


def rank_of(data: dict[str, Any], team: str) -> int | None:
    return next((r["rank"] for r in data["rows"] + data["beyond"] if r.get("team") == team), None)


@pytest.fixture
def pages(client: TestClient, fake_cfbd: FakeCfbd) -> dict[str, Any]:
    route_all(fake_cfbd)
    return load_pages(client)


# --- agreement with the chips ---------------------------------------------------------------------------------


def test_every_profile_key_agrees_with_the_season_overview(client: TestClient, pages):
    rows = pages["/api/season/overview"]["profile"]["rows"]
    assert {r["metric"] for r in rows} == {m for m in METRICS if m.startswith("profile:")}
    for row in rows:
        data = listing(client, row["metric"])
        assert data["us"]["rank"] == row["nationalRank"] and data["of"] == row["nationalOf"], row["key"]
        conf = listing(client, row["metric"], scope="conference")
        assert conf["us"]["rank"] == row["conferenceRank"] and conf["of"] == row["conferenceOf"] and conf["conference"] == "Biscuit Belt", row["key"]
        assert all(r["conference"] == "Biscuit Belt" and r["nationalRank"] for r in conf["rows"])


def test_the_opponent_highlight_agrees_with_the_program(client: TestClient, pages):
    program = pages["/api/program/next"]
    them = program["them"]["school"]
    assert them == "Diner Tech"
    for row in program["profile"]["them"]:
        data = listing(client, row["metric"], team=them)
        assert data["focus"] == {"team": them, "rank": row["nationalRank"], "value": row["value"]}, row["key"]
        assert data["of"] == row["nationalOf"] and any(r["isFocus"] for r in data["rows"]) == (row["nationalRank"] is not None)


def test_last_season_agrees_with_both_pages(client: TestClient, pages):
    season_rows = pages["/api/season/overview"]["lastSeason"]["rows"]
    program_rows = pages["/api/program/next"]["lastSeason"]["rows"]
    assert all(r["metricYear"] == SEASON - 1 for r in season_rows + program_rows)
    for row, prow in zip(season_rows, program_rows, strict=True):
        data = listing(client, row["metric"], year=SEASON - 1, team="Diner Tech")
        assert data["year"] == SEASON - 1 and data["us"]["rank"] == row["last"]["rank"] == prow["us"]["rank"], row["key"]
        assert data["of"] == row["last"]["of"] and data["focus"]["rank"] == prow["them"]["rank"]


def test_every_advanced_key_agrees_with_the_season_and_the_program(client: TestClient, pages):
    rows = pages["/api/season/overview"]["advanced"]["rows"]
    them_rows = {r["key"]: r for r in pages["/api/program/next"]["advanced"]["them"]}
    assert "advanced:defense_explosiveness" in {r["metric"] for r in rows}
    for row in rows:
        data = listing(client, row["metric"], team="Diner Tech")
        assert data["us"]["rank"] == row["nationalRank"] and data["of"] == row["nationalOf"], row["key"]
        assert data["focus"]["rank"] == them_rows[row["key"]]["nationalRank"]
    explosive = listing(client, "advanced:defense_explosiveness")
    assert explosive["label"] == "Explosiveness allowed" and explosive["higherIsBetter"] is False
    values = [r["value"] for r in explosive["rows"]]
    assert values == sorted(values)  # lower is better: the best defense first


def test_adjusted_keys_agree_with_the_program(client: TestClient, pages):
    rows = pages["/api/program/next"]["adjusted"]
    assert rows and all(r["metric"] == f"adjusted:{r['key']}" for r in rows)
    for row in rows:
        data = listing(client, row["metric"], team="Diner Tech")
        assert data["us"]["rank"] == row["usRank"] and data["focus"]["rank"] == row["themRank"] and data["of"] == row["of"], row["key"]


RATING_COLUMNS = {"sp": "sp", "spOffense": "spOffense", "spDefense": "spDefense", "spSpecial": "spSpecial", "elo": "elo", "fpi": "fpi", "talent": "talent", "core": "core", "coreOffense": "coreOffense", "coreDefense": "coreDefense", "srs": "srs", "sosPlayed": "sosPlayed", "adjEpa": "adjEpa", "adjEpaAllowed": "adjEpaAllowed"}


def test_rating_keys_agree_with_the_ratings_page_for_every_team(client: TestClient, pages):
    ratings = pages["/api/ratings"]
    by_team = {r["team"]: r for r in ratings["rows"]}
    assert "nationalAverages" not in by_team and len(by_team) == FBS
    for column, metric in ratings["metrics"].items():
        data = listing(client, metric)
        assert data["of"] == (ratings["counts"][column] or None), column
        listed = {r["team"]: r["rank"] for r in data["rows"]}
        if column in ("fpiSos", "fpiSor"):  # inside the FPI cell, checked below
            continue
        for team, row in by_team.items():
            cell = row.get(column) or {}
            assert cell.get("rank") == listed.get(team), (column, team)
    fpi = listing(client, "rating:fpiSos")
    assert fpi["valueless"] is True and all(r["value"] is None for r in fpi["rows"])
    assert {r["team"]: r["rank"] for r in fpi["rows"]} == {t: r["fpi"]["strengthOfSchedule"] for t, r in by_team.items() if r["fpi"]["strengthOfSchedule"]}


def test_rating_keys_agree_with_the_season_page_program_and_road_ahead(client: TestClient, pages):
    season = pages["/api/season/overview"]
    r = season["ratings"]
    assert r["sp"]["of"] == FBS and r["sp"]["metric"] == "rating:sp"
    pairs = [(r["sp"], "rating:sp"), (r["sp"]["offense"], "rating:spOffense"), (r["sp"]["defense"], "rating:spDefense"), (r["elo"], "rating:elo"), (r["fpi"], "rating:fpi")]
    for block, metric in pairs:
        data = listing(client, metric)
        assert block["metric"] == metric and block["rank"] == data["us"]["rank"] and block["of"] == data["of"], metric
    sos = listing(client, "rating:fpiSos")
    assert r["fpi"]["strengthOfScheduleRank"] == sos["us"]["rank"] and r["fpi"]["strengthOfScheduleMetric"] == "rating:fpiSos"
    assert r["fpi"]["strengthOfRecordRank"] == listing(client, "rating:fpiSor")["us"]["rank"]
    sp = listing(client, "rating:sp")
    for game in season["roadAhead"]:
        assert game["spMetric"] == "rating:sp" and game["spRank"] == rank_of(sp, game["opponent"]) and game["spOf"] == sp["of"] == FBS
    program = pages["/api/program/next"]
    assert program["us"]["sp"]["rank"] == sp["us"]["rank"] and program["them"]["sp"]["rank"] == rank_of(sp, "Diner Tech") and program["them"]["sp"]["of"] == FBS
    talent = listing(client, "rating:talent")
    for side, team in (("us", "Swampwater Tech"), ("them", "Diner Tech")):
        block = program["recruiting"][side]["talent"]
        assert block["metric"] == "rating:talent" and block["rank"] == rank_of(talent, team) and block["of"] == talent["of"] == program["recruiting"][side]["talentOf"]
    played = listing(client, "rating:sosPlayed")
    assert season["resume"]["sosPlayed"]["metric"] == "rating:sosPlayed" and season["resume"]["sosPlayed"]["rank"] == played["us"]["rank"]
    assert season["resume"]["sosPlayed"]["of"] == played["of"]


def test_boards_agree_with_the_leaders_page(client: TestClient, pages):
    leaders = pages["/api/season/leaders"]
    boards = [b for b in leaders["boards"] + leaders["extraBoards"] if b["metric"]]
    assert {b["metric"] for b in boards} == {m for m in METRICS if m.startswith("board:")}
    assert next(b for b in leaders["extraBoards"] if b["id"] == "usage:overall")["metric"] is None
    for board in boards:
        data = listing(client, board["metric"])
        everyone = {r["playerId"]: r["rank"] for r in data["rows"] + data["beyond"]}
        assert data["of"] == board["nationalOf"], board["id"]
        for entry in board["team"] + board["opponent"]:
            assert entry["metric"] == board["metric"]
            if entry["isUs"] and entry["nationalRank"] is not None:
                assert entry["playerId"] in everyone, (board["id"], entry["player"])  # a Mudpuppy is never cut
            if entry["playerId"] in everyone:
                assert everyone[entry["playerId"]] == entry["nationalRank"], (board["id"], entry["player"])
        prefix = [(r["playerId"], r["rank"]) for r in data["rows"][: len(board["national"])]]
        assert prefix == [(e["playerId"], e["rank"]) for e in board["national"]], board["id"]
        conf = listing(client, board["metric"], scope="conference")
        assert conf["of"] == board["conferenceOf"] and conf["conference"] == "Biscuit Belt", board["id"]
        conf_ranks = {r["playerId"]: r["rank"] for r in conf["rows"] + conf["beyond"]}
        for entry in board["team"]:
            if entry["conferenceRank"] is not None:
                assert conf_ranks.get(entry["playerId"]) == entry["conferenceRank"], (board["id"], entry["player"])
        assert [(r["playerId"], r["rank"]) for r in conf["rows"][: len(board["conference"])]] == [(e["playerId"], e["rank"]) for e in board["conference"]]


def test_polls_and_the_class_agree_with_their_pages(client: TestClient, pages):
    for block in pages["/api/season/overview"]["polls"]:
        data = listing(client, block["metric"])
        assert [(r["team"], r["rank"]) for r in data["rows"]] == sorted(((r["school"], r["rank"]) for r in block["ranks"]), key=lambda x: (x[1], x[0]))
        assert data["us"]["rank"] == block["usRank"] and data["rankSource"] == "cfbd"
    cfp = listing(client, "poll:CFP")
    assert cfp["rows"] == [] and cfp["note"]
    for block in pages["/api/recruiting"]["classes"]:
        rank = block["classRank"]
        if rank is None:
            continue
        data = listing(client, rank["metric"])
        assert rank["metric"] == "class:2026" and data["us"]["rank"] == rank["rank"] == OUR_CLASS["rank"]
        assert data["of"] == rank["of"] == len(fixture_payload("recruiting_teams"))
        assert data["population"].startswith("Division I")


def test_team_pages_rank_inside_the_teams_own_conference(client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    other = client.get(f"/api/team/{quote(OTHER)}").json()["data"]
    assert other["profile"]["conference"] == OTHER_CONF != "Biscuit Belt"
    rows = [r for r in other["profile"]["rows"] if r["conferenceRank"] is not None]
    assert len(rows) >= 20  # a non-Biscuit Belt team page has a real conference column now
    for row in rows[:6]:
        data = listing(client, row["metric"], team=OTHER, scope="conference")
        assert data["conference"] == OTHER_CONF and data["focus"]["rank"] == row["conferenceRank"] and data["of"] == row["conferenceOf"]
        explicit = listing(client, row["metric"], scope="conference", conf=OTHER_CONF)
        assert explicit["rows"] == [{**r, "isFocus": False} for r in data["rows"]]
    opponent = client.get("/api/team/Diner%20Tech").json()["data"]
    assert opponent["profile"]["conference"] == "Pancake Athletic" and opponent["team"]["sp"]["metric"] == "rating:sp"


def test_edges_open_the_right_list_on_both_sides(client: TestClient, pages):
    edges = pages["/api/program/next"]["edges"]
    assert edges and {e["side"] for e in edges} == {"offense", "defense"}
    for edge in edges:
        assert edge["usMetric"] == f"profile:{edge['usKey']}" and edge["themMetric"] == f"profile:{edge['themKey']}"
        mine = listing(client, edge["usMetric"])
        theirs = listing(client, edge["themMetric"], team="Diner Tech")
        assert mine["us"]["rank"] == edge["usRank"] and mine["of"] == edge["of"]
        assert theirs["focus"]["rank"] == edge["themRank"] and theirs["of"] == edge["themOf"]
        if edge["side"] == "defense":  # Swampwater Tech's defense against the opponent's offense
            assert edge["usKey"] in ("ypp_d", "opp_ppg", "rush_ypg_d", "pass_ypg_d", "third_d", "takeaways_pg")


# --- ties -----------------------------------------------------------------------------------------------------


def test_ties_share_a_rank_the_next_skips_and_names_order_the_tie(client: TestClient, pages):
    data = listing(client, "rating:elo")
    shared = next(rank for rank in (r["rank"] for r in data["rows"]) if sum(r["rank"] == rank for r in data["rows"]) >= 2)
    tie = [r for r in data["rows"] if r["rank"] == shared]
    assert all(r["tied"] for r in tie) and not any(r["tied"] for r in data["rows"] if r["value"] not in {t["value"] for t in data["rows"] if t["tied"]})
    assert len({r["value"] for r in tie}) == 1 and [r["team"] for r in tie] == sorted(r["team"] for r in tie)
    after = data["rows"][data["rows"].index(tie[-1]) + 1]
    assert after["rank"] == shared + len(tie)  # the next rank skips past the tie
    ranks = [r["rank"] for r in data["rows"]]
    assert ranks == sorted(ranks)


def test_the_tie_rule_on_synthetic_values():
    assert tie_ranks([9.0, 8.0, 8.0, 7.0, 7.0, 7.0, 1.0]) == [1, 2, 2, 4, 4, 4, 7]
    listed = ranked_list({"Zeta": 5.0, "Alpha": 5.0, "Mid": 7.0, "Low": 1.0}, True)
    assert listed == [("Mid", 7.0, 1, False), ("Alpha", 5.0, 2, True), ("Zeta", 5.0, 2, True), ("Low", 1.0, 4, False)]
    assert ranked_list({"A": 1.0, "B": 2.0}, False)[0] == ("A", 1.0, 1, False)
    assert shared_ranks([{"playerId": "a", "value": 3}, {"playerId": "b", "value": 3}, {"playerId": "c", "value": 1}]) == {"a": 1, "b": 1, "c": 3}
    assert ranked_list({}, True) == []


def test_ppa_and_adjusted_board_ties_share_a_rank_now(client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    passing = [{"athleteId": str(i), "athleteName": f"Player {name}", "team": team, "conference": "Biscuit Belt", "wepa": value, "plays": 100} for i, (name, team, value) in enumerate([("B", "Diner Tech", 0.5), ("A", "Swampwater Tech", 0.5), ("C", OTHER, 0.4)], start=1)]
    fake_cfbd.route("/wepa/players/passing", json=passing)
    board = next(b for b in client.get("/api/season/leaders").json()["data"]["extraBoards"] if b["id"] == "wepa:passing")
    assert [(e["player"], e["rank"]) for e in board["national"]] == [("Player A", 1), ("Player B", 1), ("Player C", 3)]
    data = listing(client, "board:wepa:passing")
    assert [(r["player"], r["rank"], r["tied"]) for r in data["rows"]] == [("Player A", 1, True), ("Player B", 1, True), ("Player C", 3, False)]


# --- zero extra calls and no dead chip ------------------------------------------------------------------------------


def every_request() -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for key, metric in METRICS.items():
        out.append((key, {}))
        out.append((key, {"team": "Diner Tech"}))
        if "conference" in metric.scopes:
            out.append((key, {"scope": "conference"}))
        if metric.last_season:
            out.append((key, {"year": SEASON - 1}))
    out += [("class:2026", {}), ("class:2027", {})]
    return out


def test_every_list_costs_no_call_after_the_pages_loaded(client: TestClient, fake_cfbd: FakeCfbd, pages):
    before = fake_cfbd.count()
    for metric, params in every_request():
        listing(client, metric, **params)
    assert fake_cfbd.count() == before


def collect_metrics(value: Any, found: set[tuple[str, int | None]], year: int | None = None) -> None:
    if isinstance(value, dict):
        own_year = value.get("metricYear") if isinstance(value.get("metricYear"), int) else year
        for key, item in value.items():
            if key in ("metric", "usMetric", "themMetric", "spMetric", "strengthOfScheduleMetric", "strengthOfRecordMetric") and isinstance(item, str):
                found.add((item, own_year if key == "metric" else None))
            elif key == "metrics" and isinstance(item, dict):
                found.update((m, None) for m in item.values() if isinstance(m, str))
            else:
                collect_metrics(item, found, year)
    elif isinstance(value, list):
        for item in value:
            collect_metrics(item, found, year)


def test_no_dead_chip(client: TestClient, pages):
    found: set[tuple[str, int | None]] = set()
    collect_metrics(pages, found)
    assert len({m for m, _ in found}) >= 90 and any(y == SEASON - 1 for _, y in found)
    for metric, year in sorted(found, key=lambda x: (x[0], x[1] or 0)):
        assert resolve(metric, SEASON) is not None, metric
        listing(client, metric, year=year)


# --- validation --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/national/profile:nope",
        "/api/national/profile",
        "/api/national/PROFILE:ypp",
        "/api/national/profile:ypp;drop",
        "/api/national/profile:" + "y" * 60,
        "/api/national/board:usage:overall",
        "/api/national/class:2019",
        "/api/national/class:20260",
        "/api/national/profile:ypp?year=2019",
        "/api/national/profile:ypp?year=twenty",
        "/api/national/rating:sp?year=2025",
        "/api/national/profile:ypp?team=" + "x" * 81,
        "/api/national/profile:ypp?scope=galaxy",
        "/api/national/poll:AP?scope=conference",
        "/api/national/profile:ypp?scope=conference&conf=" + "c" * 61,
        "/api/national/",
    ],
)
def test_bad_requests_are_404_before_any_call(client: TestClient, fake_cfbd: FakeCfbd, path: str):
    route_all(fake_cfbd)
    before = fake_cfbd.count()
    response = client.get(path)
    assert response.status_code == 404 and response.json()["errors"][0]["code"] == "not_found"
    assert fake_cfbd.count() == before


def test_an_unknown_conference_is_a_404_after_the_list_loaded(client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    response = client.get("/api/national/profile:ypp?scope=conference&conf=Big%20Sky%20West")
    assert response.status_code == 404 and "Big Sky West" in response.json()["errors"][0]["message"]


def test_validate_and_resolve_directly():
    assert resolve("board:passing:YDS", SEASON).unit == "player"
    assert resolve("class:2027", SEASON).family == "class" and resolve("class:2025", SEASON) is None
    assert resolve(None, SEASON) is None and resolve(5, SEASON) is None
    ok = validate("profile:ypp", team="  Texas A&M ", year="2025", scope=None, conf=None, season=SEASON)
    assert not isinstance(ok, str) and ok.team == "Texas A&M" and ok.year == 2025 and ok.scope == "national"
    assert isinstance(validate("profile:ypp", team=["x"], year=None, scope=None, conf=None, season=SEASON), str)


# --- degraded -------------------------------------------------------------------------------------------------------


def test_a_failed_part_gives_a_part_error_and_a_200(client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    fake_cfbd.route("/stats/season", status=500, text="boom")
    response = client.get("/api/national/profile:ypp")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["rows"] == [] and body["data"]["parts"]["stats"]["status"] == "error"
    assert any(e["code"] == "part_unavailable" and e["message"].startswith("stats:") for e in body["errors"])
    assert body["data"]["us"] == {"team": "Swampwater Tech", "rank": None, "value": None, "of": None}


def test_everything_down_is_a_503(client: TestClient, fake_cfbd: FakeCfbd):
    for path in ("/teams/fbs", "/stats/season", "/games", "/ratings/sp", "/stats/player/season"):
        fake_cfbd.route(path, status=500, text="boom")
    for metric in ("profile:ypp", "rating:sp", "board:passing:YDS"):
        response = client.get(f"/api/national/{metric}")
        assert response.status_code == 503 and response.json()["errors"][0]["code"] == "upstream_unavailable"


def test_stale_lists_are_served_when_the_upstream_dies(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    fresh = client.get("/api/national/profile:ypp").json()
    assert fresh["meta"]["stale"] is False
    for path in ("/teams/fbs", "/stats/season", "/games"):
        fake_cfbd.route(path, status=500, text="boom")
    app.state.cfbd._clock = lambda: datetime.now(timezone.utc) + timedelta(days=40)  # every lifetime has passed
    body = client.get("/api/national/profile:ypp").json()
    assert body["meta"]["stale"] is True and body["data"]["rows"] == fresh["data"]["rows"]
    assert body["data"]["parts"]["stats"]["status"] == "stale" and body["data"]["parts"]["stats"]["ageSeconds"] > 30 * 24 * 3600


# --- malformed payloads ---------------------------------------------------------------------------------------------


def nan_json(payload: Any) -> httpx.Response:
    return httpx.Response(200, content=json.dumps(payload).encode(), headers={"content-type": "application/json"})


def strict(text: str) -> Any:
    def refuse(token: str) -> Any:
        raise AssertionError(f"{token} in the answer")

    return json.loads(text, parse_constant=refuse)


def test_junk_team_stats_are_skipped_and_counted(client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    rows = fixture_payload("stats_season_fbs")
    junk = ["junk", 7, None, {"statName": "games", "statValue": 3}, {"team": "Ghost U", "statName": "totalYards", "statValue": True}, {"team": "Ghost U", "statName": "games", "statValue": "abc"}, {"team": "Swampwater Tech", "statName": "totalYards", "statValue": float("nan")}]
    fake_cfbd.route("/stats/season", handler=lambda r: nan_json(rows + junk))
    response = client.get("/api/national/profile:ypp")
    assert response.status_code == 200
    body = strict(response.text)
    assert any(e["code"] == "records_skipped" for e in body["errors"]) and body["data"]["parts"]["stats"]["skipped"] >= 4
    assert "Ghost U" not in {r["team"] for r in body["data"]["rows"]}


def test_junk_advanced_stats_never_crash_or_leak_nan(client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    rows = fixture_payload("stats_season_advanced_fbs")
    junk = [{"team": "Nulls", "offense": None, "defense": None}, {"team": "Havoc", "defense": {"havoc": {"total": "x"}, "explosiveness": float("nan")}}, {"team": "Inf", "defense": {"explosiveness": float("inf")}}, "junk", None]
    fake_cfbd.route("/stats/season/advanced", handler=lambda r: nan_json(rows + junk))
    for metric in ("advanced:defense_explosiveness", "advanced:defense_havoc_total"):
        response = client.get(f"/api/national/{metric}")
        assert response.status_code == 200
        data = strict(response.text)["data"]
        assert {"Nulls", "Havoc", "Inf"}.isdisjoint({r["team"] for r in data["rows"]}) and data["of"] == FBS


def test_junk_sp_ratings(client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    rows = [dict(r) for r in fixture_payload("ratings_sp")]
    first = next(r for r in rows if r["team"] == SP_FIRST)
    first["ranking"] = "1"  # a numeric string still reads as the rank
    second = next(r for r in rows if r["team"] == "Swampwater Tech")
    second["ranking"] = None  # CFBD left one team unranked
    fake_cfbd.route("/ratings/sp", json=rows + [{"team": "Junk", "rating": "high"}, {"rating": 5}, 9])
    response = client.get("/api/national/rating:sp")
    assert response.status_code == 200
    data = strict(response.text)["data"]
    teams = {r["team"] for r in data["rows"]}
    assert "nationalAverages" not in teams and "Junk" not in teams and rank_of(data, SP_FIRST) == 1
    assert data["us"]["rank"] is None and data["unranked"] == 1 and data["of"] == FBS - 1


def test_junk_player_stats_and_wepa(client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    passing = fixture_payload("stats_player_season_all_passing")
    junk = [{"playerId": "1", "player": "No Type", "team": "Swampwater Tech", "category": "passing", "stat": "900"}, {"playerId": "2", "player": "Word", "team": "Swampwater Tech", "category": "passing", "statType": "YDS", "stat": "abc"}, {"player": "No Id"}, "junk"]
    fake_cfbd.route("/stats/player/season", handler=lambda r: httpx.Response(200, json=passing + junk if r.url.params.get("category") == "passing" else []))
    data = strict(client.get("/api/national/board:passing:YDS").text)["data"]
    assert {"No Type", "Word", "No Id"}.isdisjoint({r["player"] for r in data["rows"] + data["beyond"]}) and data["of"] == PASSERS
    fake_cfbd.route("/wepa/players/rushing", json=[{"athleteName": "No Id", "team": "Swampwater Tech", "wepa": 0.9}, {"athleteId": "5", "athleteName": "Ok", "team": "Swampwater Tech", "wepa": 0.3}, {"athleteId": "6", "athleteName": "Nan", "team": "Swampwater Tech", "wepa": "NaN"}])
    body = strict(client.get("/api/national/board:wepa:rushing").text)
    assert [r["player"] for r in body["data"]["rows"]] == ["Ok"] and any(e["code"] == "records_skipped" for e in body["errors"])


def test_junk_polls(client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    weeks = json.loads(json.dumps(fixture_payload("rankings")))
    ap = next(p for p in weeks[0]["polls"] if p["poll"] == "AP Top 25")
    ap["ranks"][0]["rank"] = None
    ap["ranks"].append("junk")
    fake_cfbd.route("/rankings", json=weeks)
    data = strict(client.get("/api/national/poll:AP").text)["data"]
    assert data["of"] == 24 and all(isinstance(r["rank"], int) for r in data["rows"])


@pytest.mark.parametrize("payload", [{"team": "Swampwater Tech", "statName": "games", "statValue": 3}, "a string", None, 42])
def test_a_payload_of_the_wrong_shape_never_crashes(client: TestClient, fake_cfbd: FakeCfbd, payload):
    route_all(fake_cfbd)
    for path in ("/stats/season", "/ratings/sp", "/rankings", "/wepa/players/passing", "/recruiting/teams"):
        fake_cfbd.route(path, json=payload) if payload is not None else fake_cfbd.route(path, text="null", headers={"content-type": "application/json"})
    for metric in ("profile:ypp", "rating:sp", "poll:AP", "board:wepa:passing", "class:2026"):
        response = client.get(f"/api/national/{metric}")
        assert response.status_code == 200, (metric, payload)
        data = strict(response.text)["data"]
        assert isinstance(data["rows"], list) and all(isinstance(r["rank"], int) for r in data["rows"])


# --- player boards: the top 100 plus every Mudpuppy --------------------------------------------------------------------


def test_player_lists_send_the_top_100_and_every_one_of_ours_below(client: TestClient, pages):
    data = listing(client, "board:defensive:TOT", team="Diner Tech")
    assert data["cut"] == 100 and len(data["rows"]) == 100 and data["of"] > 1000
    assert data["beyond"] and all(r["isUs"] or r["isFocus"] for r in data["beyond"])
    assert all(r["rank"] >= data["rows"][-1]["rank"] for r in data["beyond"])
    swt_rows = [e for e in pages["/api/season/leaders"]["boards"][3]["team"]]
    listed = {r["playerId"] for r in data["rows"] + data["beyond"]}
    assert all(e["playerId"] in listed for e in swt_rows)
    assert data["shown"] == len(data["rows"]) + len(data["beyond"])
    assert data["us"]["playerId"] and data["us"]["rank"] == min(r["rank"] for r in data["rows"] + data["beyond"] if r["isUs"])
    assert data["focus"]["team"] == "Diner Tech" and data["focus"]["rank"] is not None
    small = listing(client, "rating:sp")
    assert small["cut"] is None and small["beyond"] == [] and len(small["rows"]) == FBS


# --- the pure builders ------------------------------------------------------------------------------------------------


def test_rating_tables_drop_the_pseudo_team_and_fall_back_to_the_tie_rule():
    sp = [TeamSP(team="A", rating=10.0, ranking=2), TeamSP(team="B", rating=12.0, ranking=1), TeamSP(team="nationalAverages", rating=0.8), TeamSP(team="C", rating=None, ranking=3)]
    tables = sp_tables(sp, None)
    assert tables["sp"].ranks == {"A": 2, "B": 1} and tables["sp"].source == "cfbd" and tables["sp"].of == 2
    assert "nationalAverages" in PSEUDO_TEAMS and "nationalAverages" not in tables["sp"].values
    assert sp_tables(sp, {"A"})["sp"].ranks == {"A": 2}
    local = rank_table({"X": 1.0, "Y": 3.0, "Z": None}, False)
    assert local.source == "local" and local.ranks == {"X": 1, "Y": 2} and local.of == 2
    fpi = fpi_tables([TeamFPI(team="A", fpi=3.0, resume_ranks={"fpi": 4, "strengthOfSchedule": 9}), TeamFPI(team="B", fpi=None)], None)
    assert fpi["fpi"].rank("A") == 4 and fpi["fpiSos"].rank("A") == 9 and fpi["fpiSos"].values == {"A": None} and fpi["fpiSor"].of == 0
    talent = talent_table([TeamTalent(team="A", talent=900.0), TeamTalent(team="B", talent=900.0), TeamTalent(team="C", talent=float("nan"))], None)
    assert talent.ranks == {"A": 1, "B": 1} and all(math.isfinite(v) for v in talent.values.values())
    assert TeamElo(team="A", elo=1500).elo == 1500
