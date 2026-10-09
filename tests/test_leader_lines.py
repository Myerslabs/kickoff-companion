"""Phase 17 #17: each Game program leader's whole line. Ranks among FBS players and among the conference's players
(ties share a rank, rates and interceptions thrown get none), the line summed over conference games from the box
scores (completions and attempts split out, the long the longest, rates worked out again, a game counted once,
damaged rows skipped), and the route."""

from __future__ import annotations

from app.cfbd.models import GamePlayerStats
from app.services.leader_lines import RankIndex, game_totals, leader_detail
from app.services.players import Line


def line(pid, team, category, **stats):
    return Line(pid, f"Player {pid}", "QB", team, None, category, {k: float(v) for k, v in stats.items()})


NATIONAL = {
    "passing": {(p.player_id, "passing"): p for p in [
        line("1", "Alpha", "passing", YDS=900, TD=8, INT=3, PCT=0.6),
        line("2", "Beta", "passing", YDS=1200, TD=8, INT=1),
        line("3", "Gamma", "passing", YDS=900, TD=2),
        line("4", "Delta", "passing", YDS=0),
    ]},
}
CONFERENCES = {"Alpha": "East", "Beta": "East", "Gamma": "West"}


def test_ranks_national_and_in_the_conference_with_ties():
    index = RankIndex(NATIONAL, CONFERENCES)
    assert index.ranks("passing", "YDS", "1") == ({"rank": 2, "of": 3}, {"rank": 2, "of": 2, "conference": "East"})
    assert index.ranks("passing", "YDS", "3") == ({"rank": 2, "of": 3}, {"rank": 1, "of": 1, "conference": "West"})
    assert index.ranks("passing", "TD", "2")[0] == {"rank": 1, "of": 3}, "8 and 8 share first"
    assert index.ranks("passing", "INT", "1") == (None, None), "an interception thrown is not ranked"
    assert index.ranks("passing", "PCT", "1") == (None, None), "a rate is not ranked"
    assert index.ranks("passing", "YDS", "4") == (None, None), "zero is not a rank"
    assert index.ranks("rushing", "YDS", "1") == (None, None), "no national pull for the category"


def test_a_leaders_detail_keeps_the_reading_order():
    detail = leader_detail(NATIONAL["passing"][("1", "passing")], "passing", RankIndex(NATIONAL, CONFERENCES))
    assert [s["stat"] for s in detail["stats"]] == ["YDS", "TD", "INT", "PCT"]
    assert leader_detail(None, "passing", RankIndex({}, {})) is None


def box(game_id, rows):
    return GamePlayerStats.model_validate({"id": game_id, "teams": [{"team": "Alpha", "categories": rows}]})


def test_conference_game_totals():
    g1 = box(1, [
        {"name": "passing", "types": [{"name": "C/ATT", "athletes": [{"id": "1", "name": "A", "stat": "20/30"}]}, {"name": "YDS", "athletes": [{"id": "1", "name": "A", "stat": "250"}]}, {"name": "QBR", "athletes": [{"id": "1", "name": "A", "stat": "70"}]}]},
        {"name": "rushing", "types": [{"name": "CAR", "athletes": [{"id": "9", "name": "R", "stat": "10"}]}, {"name": "YDS", "athletes": [{"id": "9", "name": "R", "stat": "55"}]}, {"name": "LONG", "athletes": [{"id": "9", "name": "R", "stat": "20"}]}]},
        {"name": "kicking", "types": [{"name": "PTS", "athletes": [{"id": "5", "name": "K", "stat": "9"}]}]},
    ])
    g2 = box(2, [
        {"name": "passing", "types": [{"name": "C/ATT", "athletes": [{"id": "1", "name": "A", "stat": "10/20"}, {"id": "", "name": "No id", "stat": "1/1"}]}, {"name": "YDS", "athletes": [{"id": "1", "name": "A", "stat": "--"}]}]},
        {"name": "rushing", "types": [{"name": "CAR", "athletes": [{"id": "9", "name": "R", "stat": "5"}]}, {"name": "YDS", "athletes": [{"id": "9", "name": "R", "stat": "45"}]}, {"name": "LONG", "athletes": [{"id": "9", "name": "R", "stat": "35"}]}]},
    ])
    totals = game_totals([g1, g2, g1, None, "junk"])
    passing = totals[("1", "passing")]
    assert passing["COMPLETIONS"] == 30 and passing["ATT"] == 50 and passing["YDS"] == 250 and passing["PCT"] == 0.6 and passing["YPA"] == 5.0
    assert "QBR" not in passing, "a game rate is not summed"
    rushing = totals[("9", "rushing")]
    assert rushing == {"CAR": 15.0, "YDS": 100.0, "LONG": 35.0, "YPC": 6.7}
    assert ("5", "kicking") not in totals and all(pid for pid, _ in totals)
    assert game_totals([]) == {}


def test_the_route(client, fake_cfbd):
    from tests.test_program import route_program

    route_program(fake_cfbd)
    body = client.get("/api/program/next/leaders").json()
    assert body["errors"] == []
    cats = body["data"]["categories"]
    assert [c["label"] for c in cats] == ["Passing yards", "Rushing yards", "Receiving yards", "Tackles", "Sacks"]
    us = cats[0]["us"]
    assert us["detail"]["stats"][0]["stat"] == "YDS" and us["value"] == us["detail"]["stats"][0]["value"]
    assert us["detail"]["stats"][0]["metric"] == "board:passing:YDS", "the chips open the Leaders board's national list"
    assert all(s["metric"] is None for s in us["detail"]["stats"] if s["stat"] in ("TD", "INT", "PCT")), "no board, no link"
    assert client.get("/api/program/abc/leaders").status_code == 404
    assert client.get("/api/program/999999999/leaders").status_code == 404
