"""ENH-10 (owner 2026-10-23: "menu - stats - passing should show the entire 136 passing list. The leaders only shows the top
10"; "both, similar the the SP+"; "Passing is all passers, but there should be a cutoff, we have minimum's for other parts"):
the Stats menu's full national lists, every FBS team and every player at or over the stat grades' minimum per team game.

The CFBD names are checked against the recorded 2026 answers; the lists against made-up records (minimums by position, the
defense's joined interceptions, junk values); the route against the test league, at no CFBD call once the pages loaded;
the page in the fake browser."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.cfbd.models import PlayerStat, TeamStat
from app.services import fullstats
from app.services.fullstats import CATEGORIES, minimum_for, minimum_words, player_rows, team_rows, team_totals
from tests.conftest import FakeCfbd, fixture_payload
from tests.fakedom import needs_node, run_scenario
from tests.test_national import load_pages, route_all

RECORDED = Path(__file__).resolve().parent / "fixtures" / "cfbd"


def recorded(name: str) -> list[dict]:
    return json.loads((RECORDED / f"{name}.json").read_text(encoding="utf-8"))["payload"]


@pytest.mark.skipif(not RECORDED.is_dir(), reason="the CFBD recordings stay private; the public tree has none")
def test_cfbd_interception_names_read_as_the_recordings_say():
    """A team's `interceptions` are the passes it threw that were picked off; `passesIntercepted` its defense's picks."""
    totals = team_totals([TeamStat.model_validate(r) for r in recorded("stats_season_fbs")], None)
    thrown, made = Counter(), Counter()
    for r in recorded("stats_player_season_all_passing"):
        if r["statType"] == "INT":
            thrown[r["team"]] += float(r["stat"])
    for r in recorded("stats_player_season_all_interceptions"):
        if r["statType"] == "INT":
            made[r["team"]] += float(r["stat"])
    checked = 0
    for team in ("Georgia", "Alabama", "Texas", "Ohio State"):
        if thrown[team] != made[team]:  # a team whose two counts differ tells them apart
            assert totals[team]["interceptions"] == thrown[team], team
            assert totals[team]["passesIntercepted"] == made[team], team
            checked += 1
    assert checked >= 2


def _team(team: str, **stats: float) -> list[TeamStat]:
    return [TeamStat(team=team, stat_name=name, stat_value=value) for name, value in stats.items()]


def test_team_rows_value_and_rank_every_column_the_right_way():
    records = [
        *_team("A", games=4, passCompletions=80, passAttempts=120, netPassingYards=1200, passingTDs=10, interceptions=2, netPassingYardsOpponent=800, passAttemptsOpponent=100, passCompletionsOpponent=55, passingTDsOpponent=4, passesIntercepted=6),
        *_team("B", games=4, passCompletions=90, passAttempts=150, netPassingYards=1200, passingTDs=12, interceptions=6, netPassingYardsOpponent=1000, passAttemptsOpponent=130, passCompletionsOpponent=80, passingTDsOpponent=9, passesIntercepted=2),
        *_team("C", games=5, passCompletions=70, passAttempts=100, netPassingYards=1000, passingTDs=8, interceptions=2, netPassingYardsOpponent=900, passAttemptsOpponent=110, passCompletionsOpponent=70, passingTDsOpponent=6, passesIntercepted=4),
        TeamStat(team="FCS U", stat_name="netPassingYards", stat_value=5000),  # not FBS: left out
    ]
    meta = {t: {"conference": "SEC", "abbreviation": t} for t in ("A", "B", "C")}
    offense, allowed = team_rows(team_totals(records, set(meta)), meta, CATEGORIES["passing"])
    assert [r["team"] for r in offense] == ["A", "B", "C"], "by passing yards a game, a tie sharing the rank"
    a = offense[0]
    assert a["ypg"] == 300.0 and a["ypa"] == 10.0 and a["pct"] == round(80 / 120, 4) and a["games"] == 4
    assert offense[0]["ypgRank"] == offense[1]["ypgRank"] == 1 and offense[2]["ypgRank"] == 3
    assert a["intRank"] == 1 and next(r for r in offense if r["team"] == "B")["intRank"] == 3, "fewer interceptions thrown rank higher"
    assert [r["team"] for r in allowed] == ["C", "A", "B"], "the defense: fewest passing yards allowed a game first (180, 200, 250)"
    assert next(r for r in allowed if r["team"] == "A")["intRank"] == 1, "the defense's interceptions: more is better"
    assert all("FCS U" != r["team"] for r in offense)


def _line(pid: str, name: str, pos: str, team: str, category: str, **stats: float) -> list[PlayerStat]:
    return [PlayerStat(player_id=pid, player=name, position=pos, team=team, category=category, stat_type=k.replace("_", " "), stat=v) for k, v in stats.items()]


def test_players_meet_their_position_groups_minimum_by_their_teams_games():
    games = {"A": 4.0, "B": 4.0}
    meta = {"A": {"conference": "SEC"}, "B": {"conference": "SEC"}}
    passing = [*_line("1", "Q One", "QB", "A", "passing", ATT=60, COMPLETIONS=40, YDS=700, TD=6, INT=1), *_line("2", "Q Two", "QB", "B", "passing", ATT=52, COMPLETIONS=30, YDS=400, TD=2, INT=3), *_line("3", "Q Far", "QB", "FCS", "passing", ATT=200, COMPLETIONS=150, YDS=2000, TD=20, INT=1)]
    rows, counts = player_rows({"passing": passing}, games, meta, CATEGORIES["passing"])
    assert [r["player"] for r in rows] == ["Q One"] and counts == {"withStat": 2, "qualified": 1}, "15 passes a game in, 13 out; not FBS, not counted"
    assert rows[0]["ypg"] == 175.0 and rows[0]["pct"] == round(40 / 60, 4) and rows[0]["ydsRank"] == 1
    receiving = [*_line("4", "T End", "TE", "A", "receiving", REC=5, YDS=60, TD=1, LONG=20), *_line("5", "W Out", "WR", "A", "receiving", REC=5, YDS=90, TD=0, LONG=40)]
    rows, _ = player_rows({"receiving": receiving}, games, meta, CATEGORIES["receiving"])
    assert [r["player"] for r in rows] == ["T End"], "a tight end needs a catch a game, a receiver 1.5"
    defense = [
        *_line("6", "D Line", "DL", "A", "defensive", TOT=7, SOLO=4, TFL=3, SACKS=2, QB_HUR=1, PD=0, TD=1),
        *_line("7", "L Back", "LB", "A", "defensive", TOT=9, SOLO=5, TFL=1, SACKS=0, QB_HUR=0, PD=1, TD=0),
        *_line("6", "D Line", "DL", "A", "interceptions", INT=1, YDS=40, TD=1, AVG=40),
        *_line("8", "C Back", "CB", "B", "interceptions", INT=2, YDS=10, TD=0, AVG=5),  # picks, no tackles line: not in the list
    ]
    rows, counts = player_rows({"defensive": defense[:14], "interceptions": defense[14:]}, games, meta, CATEGORIES["defense"])
    assert [r["player"] for r in rows] == ["D Line"] and counts["qualified"] == 1, "1.75 tackles a game is a lineman's, not a linebacker's 2.5"
    assert rows[0]["int"] == 1.0 and rows[0]["td"] == 1.0 and rows[0]["tpg"] == 1.8, "the pick joins; the tackles line keeps its own TD"
    assert minimum_for(CATEGORIES["defense"], "S") == 2.0 and minimum_for(CATEGORIES["defense"], None) == 2.0
    assert minimum_words(CATEGORIES["receiving"]) == "1.5 catches a game (a tight end 1)"
    assert minimum_words(CATEGORIES["passing"]) == "14 passes a game"


def test_junk_records_never_break_a_list_or_leak_nan():
    records = [
        *_team("A", games=0, netPassingYards=500, passAttempts=0),
        TeamStat(team="A", stat_name="passCompletions", stat_value="abc"),
        TeamStat(team="A", stat_name="passingTDs", stat_value="NaN"),
        TeamStat(team="", stat_name="games", stat_value=3),
        *_team("B", games=3),
    ]
    totals = team_totals(records, None)
    offense, allowed = team_rows(totals, {}, CATEGORIES["passing"])
    blob = json.dumps({"o": offense, "a": allowed})
    assert "NaN" not in blob and "Infinity" not in blob
    a = next(r for r in offense if r["team"] == "A")
    assert a["ypg"] is None and a["ypa"] is None and a["cmp"] is None and a["td"] is None and a["games"] is None
    players = [PlayerStat(player_id="9", player=None, position=None, team="B", category="passing", stat_type="ATT", stat="lots"), PlayerStat(player_id="10", team="B", category="passing", stat_type=None, stat=5)]
    rows, counts = player_rows({"passing": players}, {"B": 3.0}, {}, CATEGORIES["passing"])
    assert rows == [] and counts == {"withStat": 0, "qualified": 0}
    assert set(fullstats.CATEGORIES) == {"passing", "rushing", "receiving", "defense"}


@pytest.fixture
def loaded(client: TestClient, fake_cfbd: FakeCfbd):
    route_all(fake_cfbd)
    load_pages(client)
    return client


def test_the_route_answers_every_category_at_no_call_once_the_pages_loaded(loaded: TestClient, fake_cfbd: FakeCfbd):
    before = fake_cfbd.count()
    fbs = len(fixture_payload("teams_fbs"))
    for key in CATEGORIES:
        response = loaded.get(f"/api/stats/{key}")
        assert response.status_code == 200, (key, response.text[:300])
        data = response.json()["data"]
        assert data["category"] == key and data["teams"]["count"] == len(data["teams"]["offense"]["rows"]) == len(data["teams"]["allowed"]["rows"])
        assert 100 <= data["teams"]["count"] <= fbs
        players = data["players"]
        assert 0 < players["qualified"] == len(players["rows"]) <= players["withStat"]
        assert any(r["isUs"] for r in data["teams"]["offense"]["rows"]), "our team is in every team list"
        assert [c["key"] for c in players["columns"]] and all("size" in c for c in players["columns"])
        lead = players["lead"]
        ranks = [r[f"{lead}Rank"] for r in players["rows"]]
        assert ranks == sorted(ranks), "the players come in the lead stat's order"
        assert "NaN" not in response.text
    assert fake_cfbd.count() == before, "the full lists cost no CFBD call: every answer is one the pages already keep"
    assert loaded.get("/api/stats/kicking").status_code == 404
    assert loaded.get("/api/stats/" + "x" * 300).status_code == 404


def test_the_menu_opens_the_full_lists():
    menu = (Path(__file__).resolve().parents[1] / "static" / "js" / "ui" / "menu-tree.js").read_text(encoding="utf-8")
    catalog = (Path(__file__).resolve().parents[1] / "static" / "js" / "ui" / "band-catalog.js").read_text(encoding="utf-8")
    for key in ("passing", "rushing", "receiving", "defense"):  # ENH-46 (owner 2026-11-10): each row opens its page, the list's three tables on it
        assert f'pageRow("stats-{key}", {{ id: "lead-{key}" }})' in menu, key
        assert f'route: "stats={key}"' in catalog, key
    assert 'page: "leaders=passing:YDS:national"' not in menu, "the Stats menu no longer opens the top-ten board"


SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const col = (key, label, size = null, format = "0f", long = label) => ({ key, label, long, format, higherIsBetter: true, size });
const DATA = {
  category: "passing", label: "Passing", season: 2026, team: "Florida", next: "Texas",
  players: {
    lead: "yds", withStat: 4, qualified: 3, minimum: { words: "14 passes a game" },
    columns: [col("cmp", "Cmp", "large"), col("pct", "Pct", "medium", "pct"), col("yds", "Yds"), col("ypg", "Y/G", null, "1f"), col("td", "TD"), col("int", "INT")],
    rows: [
      { playerId: "1", player: "Kade Crawford", position: "QB", team: "Florida", abbreviation: "FLA", conference: "SEC", conferenceShort: "SEC", cmp: 100, pct: 0.66, yds: 1500, ypg: 250, td: 12, int: 2, ydsRank: 1, isUs: true },
      { playerId: "2", player: "Cole Phillips", position: "QB", team: "Texas", abbreviation: "TEX", conference: "SEC", conferenceShort: "SEC", cmp: 90, pct: 0.6, yds: 1400, ypg: 233.3, td: 9, int: null, ydsRank: 2, isNext: true },
      { playerId: "3", player: "Al Third", position: "QB", team: "Iowa", abbreviation: null, conference: null, cmp: null, pct: null, yds: 900, ypg: null, td: 3, int: 5, ydsRank: 3 },
    ],
  },
  teams: {
    count: 2,
    offense: { title: "Passing offense", lead: "ypg", columns: [col("yds", "Yds"), col("ypg", "Y/G", null, "1f", "Passing yards a game")], rows: [{ team: "Florida", abbreviation: "FLA", conference: "SEC", games: 6, yds: 2000, ypg: 333.3, ypgRank: 1, isUs: true }, { team: "Texas", abbreviation: "TEX", conference: "SEC", games: 6, yds: null, ypg: null, ypgRank: null, isNext: true }] },
    allowed: { title: "Passing defense", lead: "ypg", columns: [col("yds", "Yds"), col("ypg", "Y/G", null, "1f")], rows: [{ team: "Texas", abbreviation: "TEX", conference: "SEC", games: 6, yds: 1100, ypg: 183.3, ypgRank: 1 }] },
  },
  parts: {},
};

async function mount(params) {
  installWindow();
  await useTeam();
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  route("/api/stats/", () => envelope(clone(DATA)));
  const { createStatsView } = await import(moduleUrl("views/stats.js"));
  const main = document.createElement("main");
  document.body.append(main);
  const view = createStatsView(params);
  view.mount(main);
  await settle();
  return { main, view };
}

scenarios.players = async () => {
  const { main, view } = await mount({ arg: "passing" });
  const words = text(main);
  assert.ok(!RAW.test(words), words.match(/.{0,40}(undefined|null|NaN|Infinity).{0,40}/)?.[0]);
  assert.ok(words.includes("Passing: every qualified player") && words.includes("3 players of 4") && words.includes("14 passes a game"));
  const rows = main.querySelectorAll("#stats-players tbody tr");
  assert.equal(rows.length, 3, "every qualified player, no cut");
  assert.ok(rows[0].className.includes("is-us") && rows[1].className.includes("is-next"));
  const links = main.querySelectorAll(".stats__switches a").map((a) => [a.getAttribute("href"), a.getAttribute("aria-current")]);
  assert.deepEqual(links.slice(0, 4).map((l) => l[0]), ["#stats=passing", "#stats=rushing", "#stats=receiving", "#stats=defense"]);
  assert.deepEqual(links.slice(4), [["#stats=passing", "page"], ["#stats=passing?view=teams", null]]);
  assert.equal(links[0][1], "page");
  assert.deepEqual(view.state.target, { category: "passing", view: "players" });
  view.unmount();
};

scenarios.teams = async () => {
  const { main, view } = await mount({ arg: "passing", params: { view: "teams" } });
  const words = text(main);
  assert.ok(!RAW.test(words), words.match(/.{0,40}(undefined|null|NaN|Infinity).{0,40}/)?.[0]);
  assert.ok(main.querySelector("#stats-teams") && main.querySelector("#stats-allowed") && !main.querySelector("#stats-players"));
  assert.ok(words.includes("Passing offense") && words.includes("Passing defense") && words.includes("Florida #1 in passing yards a game"));
  assert.equal(main.querySelectorAll("#stats-teams tbody tr").length, 2);
  const { statsTarget, statsHref } = await import(moduleUrl("views/stats.js"));
  assert.deepEqual(statsTarget("bogus", { view: "nope" }), { category: "passing", view: "players" });
  assert.deepEqual(statsTarget("defense", { view: "teams" }), { category: "defense", view: "teams" });
  assert.equal(statsHref("rushing", "teams"), "#stats=rushing?view=teams");
  view.unmount();
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["players", "teams"])
def test_the_full_lists_page(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
