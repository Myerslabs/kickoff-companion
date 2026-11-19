"""The season line's Wave 7 (owner 2026-11-15, Board 5: "Build as drawn, but make
sure there are more players stats, at least every starter"): the season in review is My Team at the season's end, with every
player who has a stat line, every starter of the latest depth chart (the linemen too), the bands that look ahead left out,
Print, and the rail's Season book stop opening it once every game is closed out. No network: the program's fixtures."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.services.notes import notes_path
from app.services.players import Line
from app.services.season_players import TABLES, season_tables, starters_from
from tests.conftest import FakeCfbd, fixture_payload
from tests.fakedom import needs_node, run_scenario
from tests.test_program import route_program

ROOT = Path(__file__).resolve().parents[1]


def line(pid: str, name: str, position: str, category: str, **stats) -> tuple[tuple[str, str], Line]:
    return (pid, category), Line(pid, name, position, "Florida", "SEC", category, dict(stats))


LINES = dict([
    line("1", "Aaron Philo", "QB", "passing", COMPLETIONS=126.0, ATT=180.0, PCT=0.7, YDS=1486.0, YPA=8.3, TD=9.0, INT=5.0),
    line("2", "Tramell Jones Jr.", "QB", "passing", COMPLETIONS=73.0, ATT=111.0, YDS=712.0, TD=4.0, INT=5.0),
    line("3", "Kahleil Jackson", "WR", "passing", COMPLETIONS=1.0, ATT=1.0, YDS=48.0),
    line("4", "Jadan Baugh", "RB", "rushing", CAR=178.0, YDS=905.0, YPC=5.1, TD=15.0, LONG=75.0),
    line("1", "Aaron Philo", "QB", "rushing", CAR=59.0, YDS=206.0, YPC=3.5, TD=4.0),
    line("5", "Myles Graham", "LB", "defensive", TOT=77.0, SOLO=43.0, TFL=6.5, SACKS=4.5),
    line("6", "Walk On", "DB", "defensive", TOT="n/a", SOLO=float("nan")),  # nothing that is a number: left out
    line("7", "Patrick Durkin", "PK", "kicking", FGM=12.0, FGA=13.0, PCT=0.923, PTS=70.0),
])


def test_every_player_with_a_stat_line_a_table_a_category_best_first():
    tables = season_tables(LINES)
    assert [t["category"] for t in tables] == ["passing", "rushing", "defensive", "kicking"], "in the page's order; empty categories left out"
    passing = tables[0]
    assert [r["name"] for r in passing["rows"]] == ["Aaron Philo", "Tramell Jones Jr.", "Kahleil Jackson"], "every passer, the best first, not the leaders only"
    assert [c["key"] for c in passing["columns"]] == ["COMPLETIONS", "ATT", "PCT", "YDS", "YPA", "TD", "INT"]
    assert passing["rows"][1]["stats"]["PCT"] is None, "a figure CFBD did not give is None, never made up"
    defense = next(t for t in tables if t["category"] == "defensive")
    assert [r["name"] for r in defense["rows"]] == ["Myles Graham"], "a line with no number is no line"
    assert "TD" not in [c["key"] for c in defense["columns"]], "a column no row fills is left out"
    assert season_tables({}) == [] and season_tables(None) == [] and season_tables("junk") == []
    assert {t[0] for t in TABLES} >= {"passing", "rushing", "receiving", "defensive", "interceptions", "kicking", "punting", "kickReturns", "puntReturns"}


def test_every_starter_the_linemen_too_matched_to_his_season_line():
    chart = {
        "team": "Florida",
        "slots": [
            {"unit": "Offense", "slot": "QB", "players": [{"name": "Aaron Philo", "number": 12}, {"name": "Tramell Jones Jr.", "number": 3}]},
            {"unit": "Offense", "slot": "LT", "players": [{"name": "Bryce Lovett", "number": 77}]},
            {"unit": "Offense", "slot": "RB", "players": [{"name": "Jadan Baugh", "number": 2}]},
            {"unit": "Defense", "slot": "MLB", "players": [{"name": "Myles Graham", "number": 41}]},
            {"unit": "Defense", "slot": "MLB", "players": [{"name": "Myles Graham", "number": 41}]},  # a doubled slot: once
            {"unit": "Offense", "slot": "TE", "players": []},
            {"unit": "Offense", "slot": "X", "players": [{"name": "  "}, "junk", {"name": "Dallas Wilson", "number": True}]},
            "junk",
        ],
    }
    starters = starters_from(chart, LINES)
    assert [(s["slot"], s["name"]) for s in starters] == [("QB", "Aaron Philo"), ("LT", "Bryce Lovett"), ("RB", "Jadan Baugh"), ("MLB", "Myles Graham"), ("X", "Dallas Wilson")]
    qb, lt = starters[0], starters[1]
    assert qb["playerId"] == "1" and qb["chips"] and qb["number"] == 12 and qb["unit"] == "Offense"
    assert lt["playerId"] is None and lt["chips"] == [] and lt["number"] == 77, "a lineman is listed though CFBD keeps no line for him"
    assert starters[-1]["number"] is None, "a jersey that is not a number is left out"
    for bad in (None, {}, {"slots": "x"}, "chart", []):
        assert starters_from(bad, LINES) == []
    assert starters_from(chart, None)[0]["playerId"] is None, "no season lines: the starters still listed"


def test_the_route_lists_every_player_and_the_starters_of_the_latest_chart(client: TestClient, fake_cfbd: FakeCfbd):
    route_program(fake_cfbd)
    first = client.get("/api/season/players").json()["data"]
    assert first["categories"] and first["starters"] == [] and first["chart"] is None, "no notes yet: no chart, the stats still there"
    passer = first["categories"][0]["rows"][0]
    played = [g for g in fixture_payload("games_team") if g.get("completed")]
    game = max(played, key=lambda g: g["startDate"])
    path = notes_path(client.app.state.settings.data_dir, game["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"gameId": game["id"], "lineups": {"us": {"team": "Florida", "source": "The team's game notes", "slots": [
        {"unit": "Offense", "slot": "QB", "players": [{"name": passer["name"], "number": 1}]},
        {"unit": "Offense", "slot": "C", "players": [{"name": "A Center", "number": 55}]},
    ]}}}), encoding="utf-8")
    data = client.get("/api/season/players").json()["data"]
    assert [s["slot"] for s in data["starters"]] == ["QB", "C"]
    assert data["starters"][0]["playerId"] == passer["playerId"] and data["starters"][0]["chips"]
    assert data["starters"][1]["chips"] == [], "a lineman: no stat line, still listed"
    assert data["chart"]["gameId"] == game["id"] and data["chart"]["source"] == "The team's game notes"


def test_the_page_is_my_team_at_the_seasons_end_in_the_boards_order():
    season = (ROOT / "static" / "js" / "views" / "season.js").read_text(encoding="utf-8")
    grid = season[season.index("function reviewGrid("): season.index("function render(envelope, container)")]
    order = ["reviewCover(", "scheduleBand(", '"review-lines"', "pollsBand(", "profileBand(", "numbersBox(", "...players", "ratingsBand(", "resumeBand(", "standingsBand(", "raceBand(", "trendsBand(", "landBand(", "blameHost(", "print,"]
    at = [grid.index(token) for token in order]
    assert at == sorted(at), "the board's order"
    for ahead in ("roadAheadBand", "injurySheetBand", "tripBand", "lineupBand", "tendenciesBand", "starsPart", "pickWindow", "followButton"):
        assert ahead not in grid, f"{ahead} looks ahead and is left out"
    assert '"/api/season/players"' in grid and "printButton()" in grid
    late = season[season.index("export function lateBands("): season.index("export function lateBands(") + 1600]
    assert "wrap.measure()" in late, "a late band's tables are measured as they land (they sat at large on a phone before)"
    players = (ROOT / "static" / "js" / "ui" / "season-players.js").read_text(encoding="utf-8")
    assert "const KEEP" in players and 'size: "large"' in players, "on a phone the tables keep their key columns, shortened, never cut"
    app = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "review: (opts, arg) => createSeasonView({ ...opts, review: true, past: pastYear(arg) })" in app  # rollover R2: #review=2026, that season's as kept
    stops = (ROOT / "app" / "stops_setup.py").read_text(encoding="utf-8")
    assert re.search(r'season_line\([^)]*book_href="#review"', stops), "the rail's Season book stop opens the season in review"


SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

scenarios.players = async () => {
  installWindow();
  const { playerBands, statText } = await import(moduleUrl("ui/season-players.js"));
  const tapped = [];
  const data = {
    chart: { week: 11, opponent: "Kentucky" },
    starters: [
      { unit: "Offense", slot: "QB", name: "Aaron Philo", number: 12, playerId: "1", chips: ["1,486 yds", "9 TD"] },
      { unit: "Offense", slot: "LT", name: "Bryce Lovett", number: 77, playerId: null, chips: [] },
      "junk",
    ],
    categories: [
      { category: "passing", title: "Passing", columns: [{ key: "ATT", label: "Att" }, { key: "PCT", label: "Pct" }, { key: "YDS", label: "Yds" }], rows: [{ playerId: "1", name: "Aaron Philo", position: "QB", stats: { ATT: 180, PCT: 0.7, YDS: 1486 } }, { playerId: "2", name: "Tramell Jones Jr.", position: "QB", stats: { ATT: 111, PCT: null, YDS: 712 } }] },
      { category: "defensive", title: "Defense", columns: [{ key: "SACKS", label: "Sacks" }], rows: [{ playerId: "5", name: "Myles Graham", position: "LB", stats: { SACKS: 4.5 } }] },
      { category: "empty", title: "Nothing", columns: [], rows: [] },
    ],
  };
  const { starters, players } = playerBands(data, { onPlayer: (row) => tapped.push(row.playerId) });
  document.body.append(starters, players);
  for (const node of [starters, players]) assert.ok(!RAW.test(text(node)), text(node));
  assert.ok(text(starters).includes("the depth chart for Week 11 against Kentucky"));
  assert.ok(text(starters).includes("Bryce Lovett") && text(starters).includes("no stat line"), "a lineman listed without a line");
  assert.ok(text(starters).includes("1,486 yds"), "the first figure of his line");
  assert.ok(text(players).includes("Tramell Jones Jr.") && text(players).includes("70.0%") && text(players).includes("4.5"));
  assert.equal(statText(0.923, "PCT"), "92.3%");
  assert.equal(statText(5.1, "YPC"), "5.1");
  assert.equal(statText(12, "FGM"), "12");
  assert.equal(statText(null, "YDS"), "–");
  const none = playerBands({});
  assert.equal(none.starters, null);
  document.body.append(none.players);
  assert.ok(text(none.players).includes("No player of ours has a stat line yet"));
};

scenarios.book = async () => {
  const { walk } = await import(moduleUrl("ui/rail.js"));
  const line = { items: [
    { kind: "preseason", href: "#preseason" },
    { kind: "week", gameId: 1, week: 1, stops: { pre: { href: "#program=1?tab=pre", state: "saved" }, post: { href: "#postgame=1", state: "saved" } } },
    { kind: "now", href: "#season" },
    { kind: "book", href: "#review", state: "open" },
  ] };
  assert.deepEqual(walk(line).map((s) => s.kind), ["preseason", "pre", "post", "season", "book"]);
  const closedOnly = { items: line.items.filter((i) => i.kind !== "now") };
  assert.deepEqual(walk(closedOnly).map((s) => s.kind).slice(-2), ["season", "book"], "Now before the book");
  const toCome = { items: [...line.items.slice(0, 3), { kind: "book", href: null, state: "to_come" }] };
  const last = walk(toCome).at(-1);
  assert.deepEqual([last.kind, last.href, last.state], ["book", "#review", "to_come"], "the book is the walk's last stop all season (batch 4: the bookends)");
};
"""


@needs_node
def test_the_player_bands_in_the_fake_browser(tmp_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "players")


@needs_node
def test_the_rail_walks_to_the_season_book_at_the_end(tmp_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "book")
