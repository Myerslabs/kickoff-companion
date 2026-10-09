"""Public release Phase 7: stat grades and realistic league rosters.

Grades: a percentile per component among FBS players at the same position with enough volume per team game,
weighted into 0 to 100; linemen and long snappers get none; too few plays says what is missing; junk rows,
NaN and missing parts never break a grade; the Leaders board, players to watch, the roster and the player
card read one table, built from the national lists the Leaders page caches (no extra call once loaded).
Rosters: every FBS team has a realistic mix (a few quarterbacks, a kicker, no 24 linebackers)."""

from __future__ import annotations

import json
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from app.cfbd.models import Game, PlayerStat
from app.services import grades
from tests.conftest import ROLES, FakeCfbd, league
from tests.test_national import route_all


def stat_rows(player_id: str, name: str, position: str, team: str, category: str, **stats: float) -> list[PlayerStat]:
    return [PlayerStat(playerId=player_id, player=name, position=position, team=team, conference="X", category=category, statType=k.replace("_", " "), stat=v) for k, v in stats.items()]


def games(team_games: dict[str, int]) -> list[Game]:
    out, gid = [], 1
    for team, n in team_games.items():
        for _ in range(n):
            out.append(Game(id=gid, week=1, completed=True, homeTeam=team, awayTeam="Opp"))
            gid += 1
    return out


def qb(pid: str, team: str, att: float, yds: float, td: float, interceptions: float, comp: float) -> list[PlayerStat]:
    return stat_rows(pid, f"QB {pid}", "QB", team, "passing", ATT=att, YDS=yds, TD=td, INT=interceptions, COMPLETIONS=comp)


# --- the grade math --------------------------------------------------------------------------------------


def test_a_better_quarterback_grades_higher_and_ranks_share_ties():
    rows = qb("1", "A", 300, 3000, 30, 3, 210) + qb("2", "B", 300, 2100, 12, 12, 170) + qb("3", "C", 300, 2550, 21, 7, 190) + qb("4", "D", 300, 2550, 21, 7, 190)
    table = grades.build({"passing": rows}, games({"A": 10, "B": 10, "C": 10, "D": 10}), None)
    best, worst, mid = table.get("1"), table.get("2"), table.get("3")
    assert best["grade"] > mid["grade"] > worst["grade"] and best["rank"] == 1 and worst["rank"] == 4
    assert mid["grade"] == table.get("4")["grade"] and mid["rank"] == table.get("4")["rank"] == 2  # a tie shares a rank
    assert best["label"] == grades.label_for(best["grade"]) and best["of"] == 4 and best["basis"] == "efficiency"
    parts = {c["key"]: c for c in best["components"]}
    assert parts["intRate"]["percentile"] > parts["intRate"]["percentile"] - 1 and parts["ypa"]["value"] == 10.0
    assert parts["wepaPass"]["percentile"] is None  # no adjusted data: the part sits out, the rest count for more


def test_too_few_plays_says_what_is_missing():
    table = grades.build({"passing": qb("1", "A", 300, 3000, 30, 3, 210) + qb("9", "A", 20, 300, 3, 0, 15)}, games({"A": 10}), None)
    backup = table.get("9")
    assert backup["grade"] is None and "2.0 passes a game, 14 needed" in backup["reason"] and backup["volume"]["perGame"] == 2.0
    assert table.counts()["QB"] == 1


def test_linemen_and_snappers_get_no_grade_and_the_reason_why():
    rows = stat_rows("5", "Big Man", "OL", "A", "receiving", REC=1, YDS=3) + stat_rows("6", "Snapper", "LS", "A", "defensive", TOT=2)
    table = grades.build({"receiving": rows[:2], "defensive": rows[2:]}, games({"A": 4}), None)
    assert table.get("5")["grade"] is None and "Offensive linemen" in table.get("5")["reason"]
    assert table.get("6")["grade"] is None and "Long snappers" in table.get("6")["reason"]
    assert table.for_position("OT")["reason"].startswith("Offensive linemen") and table.for_position("WR")["reason"] == "No stats this season yet."


def test_defenders_are_production_only_and_grouped_from_cfbd_positions():
    rows = []
    for pid, pos, tot, tfl, sacks in (("d1", "DE", 40, 12, 8), ("d2", "DT", 30, 5, 2), ("d3", "EDGE", 35, 9, 6)):
        rows += stat_rows(pid, pid, pos, "A", "defensive", TOT=tot, TFL=tfl, SACKS=sacks, QB_HUR=3, PD=1)
    table = grades.build({"defensive": rows}, games({"A": 10}), None)
    assert {table.get(p)["group"] for p in ("d1", "d2", "d3")} == {"DL"} and table.get("d1")["basis"] == "production"
    assert table.get("d1")["rank"] == 1 and table.get("d2")["rank"] == 3


def test_junk_values_never_break_a_grade():
    rows = qb("1", "A", 300, 3000, 30, 3, 210) + qb("2", "A", 300, float("nan"), 30, 3, 210) + [PlayerStat(playerId="3", player=None, position=None, team="A", category="passing", statType="ATT", stat="lots")]
    table = grades.build({"passing": rows, "kicking": []}, games({"A": 10}) + [Game(id=99, week=None, completed=None)], {"A"})
    assert table.get("1")["grade"] is not None
    junk = table.get("2")  # NaN yards: yards per attempt sits out, and with no play value either too little is left
    assert junk["grade"] is None and junk["reason"] == "Not enough stats to grade."
    assert all(c["percentile"] is None or 0 <= c["percentile"] <= 100 for c in junk["components"])
    assert "NaN" not in json.dumps(grades.public(table.get("2")), default=str)
    assert grades.build({}, [], None).counts() == {g: 0 for g in grades.GRADED}


def test_players_outside_fbs_are_not_graded():
    table = grades.build({"passing": qb("1", "A", 300, 3000, 30, 3, 210) + qb("2", "FCS U", 300, 3000, 30, 3, 210)}, games({"A": 10, "FCS U": 10}), {"A"})
    assert table.get("2") is None and table.get("1")["of"] == 1


# --- the routes on the made-up league --------------------------------------------------------------------


@pytest.fixture
def loaded(client: TestClient, fake_cfbd: FakeCfbd) -> TestClient:
    route_all(fake_cfbd)
    assert client.get("/api/season/overview").status_code == 200  # the season's games (each team's games played)
    assert client.get("/api/season/leaders").status_code == 200  # the national lists
    return client


def test_grades_cost_no_call_once_season_and_leaders_have_loaded(loaded: TestClient, fake_cfbd: FakeCfbd):
    calls = len(fake_cfbd.requests)
    board = loaded.get("/api/grades?group=QB&limit=10").json()
    assert len(fake_cfbd.requests) == calls, [r.url.path for r in fake_cfbd.requests[calls:]]
    data = board["data"]
    assert board["errors"] == [] and len(data["rows"]) == 10 and data["rows"][0]["rank"] == 1 and data["of"] >= 100
    assert [r["grade"] for r in data["rows"]] == sorted((r["grade"] for r in data["rows"]), reverse=True)
    ours = {r["playerId"] for r in data["ours"]}
    assert ROLES["QBID"] in ours and all(r["team"] == "Swampwater Tech" for r in data["ours"])
    assert {g["id"] for g in data["groups"]} == set(grades.GRADED) and "components" not in data["rows"][0]
    assert loaded.get("/api/grades?group=OL").status_code == 404


def test_roster_card_and_players_to_watch_read_the_same_grade(loaded: TestClient):
    board = loaded.get("/api/grades?group=QB&limit=200").json()["data"]
    ours = next(r for r in board["rows"] if r["playerId"] == ROLES["QBID"])
    roster = loaded.get("/api/roster").json()["data"]["players"]
    row = next(p for p in roster if p["playerId"] == ROLES["QBID"])
    assert row["grade"]["grade"] == ours["grade"] and row["grade"]["rank"] == ours["rank"]
    lineman = next(p for p in roster if p["position"] == "OL")
    assert lineman["grade"]["grade"] is None and "linemen" in lineman["grade"]["reason"]
    card = loaded.get(f"/api/players/{ROLES['QBID']}").json()["data"]["grade"]
    assert card["grade"] == ours["grade"] and card["components"] and all("percentile" in c for c in card["components"])
    watch = loaded.get(f"/api/grades/teams?teams=Swampwater Tech,{ROLES['OPP']}&top=3").json()["data"]["teams"]
    assert [t["team"] for t in watch] == ["Swampwater Tech", ROLES["OPP"]]
    assert all(len(t["players"]) == 3 for t in watch) and all(p["team"] == t["team"] for t in watch for p in t["players"])
    assert loaded.get("/api/grades/teams?teams=").status_code == 422


# --- the made-up league's rosters ------------------------------------------------------------------------


def test_every_fbs_roster_looks_like_a_real_one():
    world = league()
    season = world.season
    for team in world.league.fbs:
        mix = Counter(p.position for p in world.league.roster(team.id, season))
        size = sum(mix.values())
        assert 80 <= size <= 135, (team.school, size)
        assert 2 <= mix["QB"] <= 9 and mix["LB"] <= 18 and mix["PK"] >= 1 and mix["P"] >= 1, (team.school, dict(mix))
        assert mix["OL"] >= 10 and mix["DL"] >= 8 and mix["WR"] >= 8, (team.school, dict(mix))



def test_a_crowd_at_zero_ranks_at_the_bottom_not_the_middle():
    """Phase 17 (owner 2026-10-07): 0 interceptions sat near the 42nd percentile because most players tie at zero."""
    from app.services.grades import _percentiles

    values = {str(i): 0.0 for i in range(6)} | {"6": 1.0, "7": 2.0, "8": 2.0, "9": 3.0}
    p = _percentiles(values, higher=True)
    assert p["0"] == 0.0 and p["6"] == 65.0 and p["7"] == p["8"] == 80.0 and p["9"] == 95.0
    assert set(_percentiles({"a": 0.0, "b": 0.0}, higher=True).values()) == {50.0}, "all tied: the middle"
    low = _percentiles({"a": 0.0, "b": 0.0, "c": 5.0}, higher=False)
    assert low["a"] == low["b"] == 66.7 and low["c"] == 16.7, "lower is better keeps the mid-rank"
