"""Phase 16 payload fields for the page streams: archived flags on the schedule, the program and
Swampwater Tech's team page; isUs on roster, impact and team-page roster rows; the edges' per-side keys
(defense rows reversed); the visitors' kickoff date; SP+ "of" 136 with the nationalAverages
pseudo-team gone; per-rating counts; metric keys on every ranked row."""

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from app.services.profiles import EDGE_PAIRS, PROFILE_ROWS
from tests.conftest import FakeCfbd
from tests.test_national import route_all

NEXT_GAME = 526001015
LAST_GAME = 526000600


def write_archive(app, game_id: int) -> None:
    folder = app.state.settings.data_dir / "archive"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{game_id}.json").write_text(json.dumps({"gameId": game_id, "state": {}}), encoding="utf-8")
    (folder / "notes.json").write_text("{}", encoding="utf-8")  # not a game id: ignored


def test_archived_flags_on_the_schedule_the_program_and_floridas_team_page(app, client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    write_archive(app, LAST_GAME)
    schedule = client.get("/api/season/overview").json()["data"]["schedule"]
    assert {r["gameId"] for r in schedule if r["archived"]} == {LAST_GAME} and all(isinstance(r["archived"], bool) for r in schedule)
    program = client.get(f"/api/program/{LAST_GAME}").json()["data"]
    assert program["game"]["archived"] is True
    assert {r["gameId"] for r in program["picker"] if r["archived"]} == {LAST_GAME}
    assert client.get("/api/program/next").json()["data"]["game"]["archived"] is False
    swt = client.get("/api/team/Swampwater Tech").json()["data"]["schedule"]
    assert {r["gameId"] for r in swt if r["archived"]} == {LAST_GAME}
    other = client.get("/api/team/Diner%20Tech").json()["data"]["schedule"]
    assert all("archived" not in r for r in other)  # another team's games are not the Mudpuppies' archive


def test_no_archive_folder_means_nothing_is_archived(client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    schedule = client.get("/api/season/overview").json()["data"]["schedule"]
    assert schedule and not any(r["archived"] for r in schedule)


def test_is_us_on_roster_impact_and_team_page_rows(client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    roster = client.get("/api/roster").json()["data"]
    assert roster["players"] and all(p["isUs"] is True for p in roster["players"])
    impact = roster["impact"]["offense"] + roster["impact"]["defense"]
    assert impact and all(p["isUs"] is True for p in impact)
    assert all(p["isUs"] is True for p in client.get("/api/team/Swampwater Tech").json()["data"]["roster"])
    assert all(p["isUs"] is False for p in client.get("/api/team/Diner%20Tech").json()["data"]["roster"])


def test_edges_name_each_sides_stat_with_defense_rows_reversed(client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    data = client.get("/api/program/next").json()["data"]
    profile_us = {r["key"]: r for r in data["profile"]["us"]}
    profile_them = {r["key"]: r for r in data["profile"]["them"]}
    pairs = {off: dfn for off, dfn, _ in EDGE_PAIRS}
    assert {e["side"] for e in data["edges"]} == {"offense", "defense"}
    for edge in data["edges"]:
        if edge["side"] == "offense":
            assert pairs[edge["usKey"]] == edge["themKey"]
        else:
            assert pairs[edge["themKey"]] == edge["usKey"]  # Swampwater Tech's defense stat, the opponent's offense stat
        assert profile_us[edge["usKey"]]["nationalRank"] == edge["usRank"] and profile_us[edge["usKey"]]["value"] == edge["usValue"]
        assert profile_them[edge["themKey"]]["nationalRank"] == edge["themRank"] and profile_them[edge["themKey"]]["value"] == edge["themValue"]
        assert edge["of"] == profile_us[edge["usKey"]]["nationalOf"] and edge["themOf"] == profile_them[edge["themKey"]]["nationalOf"]
        assert edge["usMetric"] == f"profile:{edge['usKey']}" and edge["themMetric"] == f"profile:{edge['themKey']}"
        fmt = {spec[2]: spec[4] for spec in PROFILE_ROWS}
        assert edge["usFormat"] == fmt[edge["usKey"]] and edge["themFormat"] == fmt[edge["themKey"]]


def test_visitors_carry_the_kickoff_date(client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    visitors = client.get("/api/recruiting").json()["data"]["visitors"]
    assert visitors["gameId"] == NEXT_GAME and visitors["date"].startswith("2026-09-2") and visitors["startTimeTbd"] in (True, False)
    classes = client.get("/api/recruiting").json()["data"]["classes"]
    assert classes[0]["classRank"]["metric"] == "class:2026"


def test_sp_of_136_and_no_pseudo_team_anywhere(client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    season = client.get("/api/season/overview").json()["data"]
    assert season["ratings"]["sp"]["of"] == 136 and all(g["spOf"] == 136 for g in season["roadAhead"])
    ratings = client.get("/api/ratings").json()["data"]
    assert len(ratings["rows"]) == 136 and all(r["team"] != "nationalAverages" for r in ratings["rows"])
    counts = ratings["counts"]
    assert counts["sp"] == 136 and counts["elo"] == 136 and counts["fpi"] == 136 and counts["talent"] == 136
    assert counts["srs"] > 136  # Division I (the 2025 recording stands in)
    assert counts["spSpecial"] == 136 and all(r["spSpecial"]["rank"] for r in ratings["rows"])  # ranked here: CFBD sends no special-teams rank
    assert ratings["metrics"]["sp"] == "rating:sp" and ratings["metrics"]["adjEpa"] == "adjusted:epa"
    program = client.get("/api/program/next").json()["data"]
    assert program["us"]["sp"]["of"] == 136 and program["them"]["sp"]["metric"] == "rating:sp"


def walk(value: Any, key: str) -> list[Any]:
    out = []
    if isinstance(value, dict):
        for k, v in value.items():
            if k == key:
                out.append(v)
            out += walk(v, key)
    elif isinstance(value, list):
        for v in value:
            out += walk(v, key)
    return out


def test_metric_keys_on_every_ranked_row(client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    season = client.get("/api/season/overview").json()["data"]
    assert all(r["metric"] == f"profile:{r['key']}" for r in season["profile"]["rows"])
    assert all(r["metric"] == f"advanced:{r['key']}" for r in season["advanced"]["rows"])
    assert all(r["metric"] == f"profile:{r['key']}" and r["metricYear"] == 2025 and r["now"]["year"] == 2026 and r["last"]["year"] == 2025 for r in season["lastSeason"]["rows"])
    assert [p["metric"] for p in season["polls"]] == [f"poll:{p['poll']}" for p in season["polls"]]
    assert season["record"]["spMetric"] == "rating:sp" and season["resume"]["remaining"]["metric"] == "rating:sosPlayed"
    assert season["profile"]["conference"] == "Biscuit Belt"
    program = client.get("/api/program/next").json()["data"]
    for side in ("us", "them"):
        assert all(r["metric"] == f"profile:{r['key']}" for r in program["profile"][side])
        assert all(r["metric"] == f"advanced:{r['key']}" for r in program["advanced"][side])
    assert all(r["metric"] == f"adjusted:{r['key']}" for r in program["adjusted"])
    assert all(r["metric"] == f"profile:{r['key']}" and r["metricYear"] == 2025 for r in program["lastSeason"]["rows"])
    leaders = client.get("/api/season/leaders").json()["data"]
    for board in leaders["boards"] + leaders["extraBoards"]:
        entries = board["team"] + board["opponent"] + board["conference"] + board["national"]
        assert all(e["metric"] == board["metric"] for e in entries), board["id"]
    team = client.get("/api/team/Diner%20Tech").json()["data"]
    assert all(r["metric"] for r in team["profile"]["rows"]) and all(r["metric"] for r in team["advanced"]["rows"])
    assert team["recruiting"]["talent"]["metric"] == "rating:talent"
    assert all(isinstance(m, str) or m is None for m in walk(season, "metric") + walk(program, "metric") + walk(leaders, "metric"))
