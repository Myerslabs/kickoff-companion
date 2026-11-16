"""P5, the owner's two picked boards (2026-10-25): board 5, down and distance as a shaded grid with the number in every
cell, in the Tendencies band for both offenses (ENH-30); board 6, the conference race as the range of finishes each team
can still reach, above the four plain lines in What we need (ENH-31)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.depth2 import down_distance_grid, offense_snaps
from tests.fakedom import needs_node, run_scenario
from tests.test_any_team import lclient  # noqa: F401 - the league's client, used below


def snap(down, distance, success, kind="run"):
    return {"down": down, "distance": distance, "success": success, "kind": kind}


def test_the_grid_puts_each_snap_in_its_down_and_distance_and_leaves_out_what_cannot_be_judged():
    grid = down_distance_grid([
        snap(1, 10, True), snap(1, 10, False), snap(1, 2, True),
        snap(2, 5, True), snap(3, 12, False), snap(4, 1, True), snap(3, 7, True),
        snap(5, 3, True), snap(1, 0, True), snap(2, None, True), snap(2, 4, None), snap("1", 3, True),
    ])
    assert grid["distances"] == ["1-3", "4-6", "7-10", "11+"]
    first, second, third, fourth = (row["cells"] for row in grid["rows"])
    assert [c["of"] for c in first] == [1, 0, 2, 0] and first[2]["rate"] == 0.5 and first[1]["rate"] is None
    assert second[1] == {"distance": "4-6", "made": 1, "of": 1, "rate": 1.0}
    assert third[2]["of"] == 1 and third[3] == {"distance": "11+", "made": 0, "of": 1, "rate": 0.0}
    assert fourth[0]["made"] == 1
    assert sum(c["of"] for row in grid["rows"] for c in row["cells"]) == 7, "a 5th down, a 0 distance, no distance, no verdict: left out"


def test_the_snaps_are_one_offenses_with_kneels_and_spikes_left_out():
    rushes = [SimpleNamespace(offense="Florida", is_kneel=False, is_sack=False, down=1, distance=10, start_yards_to_goal=70, rushing_yards=6, success=True, rush_direction="Left", game_id=1),
              SimpleNamespace(offense="Florida", is_kneel=True, is_sack=False, down=1, distance=10, start_yards_to_goal=70, rushing_yards=-1, success=False, rush_direction=None, game_id=1),
              SimpleNamespace(offense="Texas", is_kneel=False, is_sack=False, down=1, distance=10, start_yards_to_goal=70, rushing_yards=3, success=False, rush_direction=None, game_id=1)]
    passes = [SimpleNamespace(offense="Florida", is_spike=False, down=3, distance=8, start_yards_to_goal=40, total_yards=12, success=True, pass_depth="deep", game_id=1),
              SimpleNamespace(offense="Florida", is_spike=True, down=2, distance=10, start_yards_to_goal=40, total_yards=0, success=False, pass_depth=None, game_id=1)]
    snaps = offense_snaps(rushes, passes, "Florida")
    assert [(s["kind"], s["down"]) for s in snaps] == [("run", 1), ("pass", 3)]


# --- board 5 In Game and in the program -------------------------------------------------------------------


def test_in_game_grids_come_from_the_released_runs_and_passes_of_each_offense():
    from app.live.analysis import down_distance
    from tests.test_phase12 import recorded_state
    from tests.test_phase12 import snap as live_snap

    plays = [
        live_snap("A", 1, 4, success=True, down=3, distance=2, rushPass="rush"),
        live_snap("A", 1, 0, success=False, down=3, distance=9, play_type="Pass Incompletion"),
        live_snap("A", 1, 0, play_type="Punt", success=True),
        live_snap("A", 1, 0, play_type="Penalty", success=True),
        live_snap("B", 1, 3, success=None, down=2, distance=5),
        live_snap("Nobody", 1, 3, success=True),
    ]
    grids = down_distance(plays, ("A", "B"))
    assert set(grids) == {"A", "B"}
    third = grids["A"]["rows"][2]["cells"]
    assert third[0]["made"] == 1 and third[0]["of"] == 1 and third[2]["made"] == 0 and third[2]["of"] == 1
    assert sum(c["of"] for row in grids["A"]["rows"] for c in row["cells"]) == 2, "the punt and the penalty are not runs or passes"
    assert sum(c["of"] for row in grids["B"]["rows"] for c in row["cells"]) == 0, "a play the feed did not judge is left out"
    state = recorded_state()
    for team in ("Florida", "Fresno State"):
        grid = state["downDistance"][team]
        judged = sum(c["of"] for row in grid["rows"] for c in row["cells"])
        assert 0 < judged <= state["box"][team]["plays"], team


def test_the_program_carries_our_offenses_grid_beside_theirs(lclient):  # noqa: F811 - the fixture imported above
    nxt = lclient.get("/api/program/next").json()["data"]
    assert nxt["tendencies"] and nxt["tendencies"]["grid"]["distances"] == ["1-3", "4-6", "7-10", "11+"]
    ours = nxt["ourGrid"]
    assert ours and [row["down"] for row in ours["rows"]] == [1, 2, 3, 4]
    assert sum(c["of"] for row in ours["rows"] for c in row["cells"]) > 0, "the league's season of runs and passes"


# --- board 6: the ranges ----------------------------------------------------------------------------------


def _five_teams():
    """A 1-1, B 2-0, C 2-0, D 1-2, E 0-3; left: B at C and A at D. B and C meet, so one of them gets a third win: A can
    finish second at best, never first, though counting from the records alone says first."""
    from tests.test_race import game

    played = [(1, "B", "D"), (2, "B", "E"), (3, "C", "D"), (4, "C", "E"), (5, "A", "E"), (6, "D", "A")]
    games = [game(gid, 1 + gid // 3, winner, loser, 28, 14) for gid, winner, loser in played]
    games += [game(7, 5, "C", "B"), game(8, 5, "D", "A")]
    return games


def test_the_ranges_play_every_outcome_out_when_few_games_are_left():
    from app.services.race import lines_of, place_ranges
    from tests.test_race import CONF

    ranges, exact = place_ranges(lines_of(_five_teams(), CONF))
    assert exact is True
    assert ranges == {"A": (2, 4), "B": (1, 3), "C": (1, 3), "D": (2, 4), "E": (5, 5)}


def test_too_many_games_left_counts_the_ends_from_the_records(monkeypatch):
    from app.services import race as race_module
    from tests.test_race import CONF

    lines = race_module.lines_of(_five_teams(), CONF)
    exact, _ = race_module.place_ranges(lines)
    monkeypatch.setattr(race_module, "RANGE_MAX_GAMES", 1)
    counted, is_exact = race_module.place_ranges(lines)
    assert is_exact is False and counted["A"] == (1, 4), "B and C both lose by the count: a bound, not the truth"
    for team, (best, worst) in exact.items():
        assert counted[team][0] <= best and counted[team][1] >= worst, f"{team}: the count bounds the true range"


def test_a_settled_race_gives_each_team_its_one_place_and_ties_share_a_range():
    from app.services.race import lines_of, place_ranges
    from tests.test_race import CONF, game

    games = [game(1, 1, "A", "B", 21, 7), game(2, 2, "C", "D", 21, 7), game(3, 3, "A", "D", 21, 7), game(4, 4, "C", "B", 21, 7)]
    ranges, exact = place_ranges(lines_of(games, CONF))
    assert exact is True and ranges == {"A": (1, 2), "C": (1, 2), "B": (3, 4), "D": (3, 4)}


def test_the_race_rows_us_and_the_programs_compact_race_carry_the_ranges():
    from app.services import race as race_module
    from tests.test_race import CONF, week9

    race_module._MEMO.clear()
    result = race_module.race(week9(), "Swamp", CONF, week=9)
    assert result["rangeExact"] is True
    for row in result["standings"]:
        assert 1 <= row["bestPlace"] <= row["worstPlace"] <= len(result["standings"]), row
    us = result["us"]
    assert (us["bestPlace"], us["worstPlace"]) == next((r["bestPlace"], r["worstPlace"]) for r in result["standings"] if r["isUs"])
    assert us["bestPlace"] == 1, "Swamp wins out: 7-1, and Silver can be held to 6"
    bagel = next(r for r in result["standings"] if r["team"] == "Bagel")
    assert bagel["bestPlace"] > result["spots"] and bagel["status"] == "out"
    small = race_module.compact(result, standings=2)
    assert small["us"]["bestPlace"] == us["bestPlace"] and all("bestPlace" in r for r in small["standings"])
    race_module._MEMO.clear()


def test_a_big_conference_early_counts_and_stays_quick():
    import time

    from app.services import race as race_module
    from tests.test_race import CONF, game

    games = []
    gid = 0
    teams = [f"T{i}" for i in range(16)]
    for week in range(1, 9):
        for i in range(0, 16, 2):
            gid += 1
            games.append(game(gid, week, teams[(i + week) % 16], teams[(i + 1 + week) % 16]))
    started = time.perf_counter()
    result = race_module.race(games, "T0", CONF, week=1)
    assert time.perf_counter() - started < 2.0
    assert result["rangeExact"] is False and all((r["bestPlace"], r["worstPlace"]) == (1, 16) for r in result["standings"])


# --- the two charts on the page (fake browser) -------------------------------------------------------------

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const cell = (distance, made, of) => ({ distance, made, of, rate: of ? made / of : null });
const GRID = {
  distances: ["1-3", "4-6", "7-10", "11+"],
  rows: [
    { down: 1, cells: [cell("1-3", 3, 4), cell("4-6", 0, 0), cell("7-10", 40, 80), cell("11+", 1, 6)] },
    { down: 2, cells: [cell("1-3", 8, 10), cell("4-6", 5, 10), cell("7-10", 9, 30), cell("11+", 0, 0)] },
    { down: 3, cells: [cell("1-3", 6, 9), null, { distance: "7-10", made: 2, of: 10, rate: NaN }, cell("11+", 1, 8)] },
    null,
    { down: 4, cells: [cell("1-3", 1, 1), cell("4-6", 0, 0), cell("7-10", 0, 0), cell("11+", 0, 0)] },
  ],
};

scenarios.ddgrid = async () => {
  const { AVERAGE, ddGrid, ddPair, shadeOf } = await import(moduleUrl("ui/dd-grid.js"));
  assert.equal(AVERAGE, 0.42);
  assert.equal(shadeOf(0.67, 8), 1, "25 points over the average on 8 snaps: the deepest green");
  assert.equal(shadeOf(0.42, 30), 0);
  assert.equal(shadeOf(0.17, 4), -0.5, "25 under on 4 snaps: half the red");
  assert.equal(shadeOf(1, 1), 0.13, "one snap is a hint");
  assert.equal(shadeOf(null, 4), 0);
  assert.equal(shadeOf(0.5, 0), 0);
  const grid = ddGrid(GRID, { label: "Texas offense", side: "them" });
  document.body.append(grid);
  const words = text(grid);
  assert.ok(!RAW.test(words), words);
  assert.ok(words.includes("Texas offense") && words.includes("1st") && words.includes("4th") && words.includes("11+"), words);
  const cells = grid.querySelectorAll(".ddgrid__cell");
  assert.equal(cells.length, 16, "four downs by four distances; the bad row is skipped");
  assert.equal(text(cells[2]), "50%");
  assert.equal(text(cells[1]), "–", "no snaps: a dash, never 0%");
  assert.ok(cells[1].className.includes("ddgrid__cell--none"));
  assert.ok(cells[4].className.includes("ddgrid__cell--good") && cells[4].style["--shade"] === "1", "2nd and short, 8 of 10: green");
  assert.ok(cells[6].className.includes("ddgrid__cell--bad"), "2nd and 7 to 10, 9 of 30: red");
  assert.equal(text(cells[9]), "–", "a missing cell");
  assert.equal(text(cells[10]), "–", "a rate that is not a number");
  assert.ok(cells[2].getAttribute("title").includes("1st and 7-10: 40 of 80 snaps a success"));
  assert.equal(ddGrid(null), null);
  assert.equal(ddGrid({ distances: ["1-3"], rows: [{ down: 1, cells: [cell("1-3", 0, 0)] }] }), null, "no snaps: no grid");
  const pair = ddPair(GRID, null, { usLabel: "Florida offense", themLabel: "Texas offense" });
  document.body.append(pair);
  assert.equal(pair.querySelectorAll(".ddgrid").length, 1, "one offense with plays: one grid");
  assert.ok(text(pair).includes("green above the FBS average of about 42%") && !RAW.test(text(pair)));
  assert.equal(ddPair(null, undefined), null);
};

const RANGES = {
  conference: "SEC", spots: 2, rangeExact: true,
  standings: [
    { place: 1, team: "Silver", status: "alive", isUs: false, bestPlace: 1, worstPlace: 3 },
    { place: 2, team: "Diner", status: "alive", isUs: false, bestPlace: 1, worstPlace: 5 },
    { place: 3, team: "Armadillo", status: "tiebreaker", isUs: false, bestPlace: 1, worstPlace: 4 },
    { place: 4, team: "Bass", status: "out", isUs: false, bestPlace: 3, worstPlace: 6 },
    { place: 5, team: "Apple", status: "alive", isUs: false, bestPlace: 4, worstPlace: 2 },
    null,
    { place: 6, team: "Cedar", status: "alive", isUs: false },
  ],
  us: { team: "Swamp", place: 7, bestPlace: 2, worstPlace: 7, status: "alive" },
};

scenarios.ranges = async () => {
  await useTeam();
  const { raceRanges } = await import(moduleUrl("ui/race-ranges.js"));
  const chart = raceRanges(RANGES);
  document.body.append(chart);
  const words = text(chart);
  assert.ok(!RAW.test(words), words);
  const rows = chart.querySelectorAll("li.race-ranges__row");
  assert.deepEqual(rows.map((r) => r.getAttribute("aria-label").split(":")[0]), ["Silver", "Diner", "Armadillo", "Swamp"], "out, upside-down and range-less rows left off; ours added from us");
  assert.ok(rows[3].className.includes("is-us") && rows[3].querySelector(".race-ranges__bar--us"));
  assert.equal(rows[0].getAttribute("aria-label"), "Silver: 1st at best, 3rd at worst, 1st now");
  assert.equal(rows[0].querySelector(".race-ranges__bar").style.gridColumn, "2 / 5", "1st to 3rd: columns two to four");
  assert.equal(rows[3].querySelector(".race-ranges__now").style.gridColumn, "8", "7th now, the seventh place column");
  assert.equal(chart.querySelectorAll(".race-ranges__place").length, 7, "places to the worst drawn: 7th");
  assert.equal(rows[0].querySelectorAll(".race-ranges__cell--spot").length, 2, "the two title-game spots shaded");
  assert.ok(words.includes("1 team out of the title game left off") && !words.includes("counted from the records"));
  const counted = raceRanges({ ...RANGES, rangeExact: false, spots: 1 });
  assert.ok(text(counted).includes("counted from the records") && text(counted).includes("the title-game spot"));
  const fourteen = raceRanges({ ...RANGES, us: { ...RANGES.us, worstPlace: 14, place: 20 } });
  const labels = fourteen.querySelectorAll(".race-ranges__place").map((p) => text(p));
  assert.equal(labels.length, 14);
  assert.deepEqual(labels.slice(0, 4), ["1", "", "3", ""], "past ten places, every other one named");
  assert.equal(labels[13], "14", "the last always named");
  assert.equal(labels[12], "", "and the one before it blank, so the two never touch");
  const short = raceRanges(RANGES, { abbreviations: { Silver: "SIL", Diner: 7 } });
  const names = short.querySelectorAll(".race-ranges__team").map((n) => text(n));
  assert.deepEqual(names, ["SIL", "Diner", "Armadillo", "Swamp"], "short names where the map has one, the school where it does not");
  assert.ok(short.querySelector("li").getAttribute("aria-label").startsWith("Silver:"), "the full name stays for a screen reader");
  const now = fourteen.querySelectorAll("li.race-ranges__row")[3].querySelector(".race-ranges__now");
  assert.equal(now.style.gridColumn, "15", "a place outside the range is drawn at its end");
  assert.equal(raceRanges(null), null);
  assert.equal(raceRanges({ standings: [RANGES.standings[0]] }), null, "one team is no race");
  assert.equal(raceRanges({ standings: "junk", us: "junk" }), null);
};

scenarios.bands = async () => {
  await useTeam();
  const { raceBand } = await import(moduleUrl("ui/race.js"));
  const section = raceBand({ ...RANGES, week: 9, settled: false, lines: [{ key: "winOut", lead: "Win out", text: "and we are in." }], watch: [] }, null);
  document.body.append(section);
  // BUG-15 (owner board 2026-10-27): the ranges ride in the standings table, row for row, the narrow band's chart under it,
  // and the four lines follow under Our way in
  const column = section.querySelector(".race__standings");
  assert.ok(column.querySelector(".race__table--ranges .race-ranges__strip") && column.querySelector(".race__ranges-alone .race-ranges"), "the ranges with the standings");
  const kids = section.querySelector(".race__grid").children.map((k) => k.className);
  assert.ok(kids.indexOf("race__standings") >= 0 && kids.indexOf("race__standings") < kids.indexOf("race__way"), "the ranges above the four lines: " + kids.join(", "));
  const { tendenciesBlock } = await import(moduleUrl("ui/depth2.js"));
  const { ddPair } = await import(moduleUrl("ui/dd-grid.js"));
  const block = tendenciesBlock({ plays: 300, games: 5, runRate: 0.5, bySituation: [], runDirection: [], passDepth: [] }, "TEX", { grids: ddPair(GRID, GRID, { usLabel: "Florida offense", themLabel: "Texas offense" }) });
  document.body.append(block);
  const table = block.querySelector(".tend__table");
  assert.equal(table.querySelectorAll(".ddgrid").length, 2, "both offenses above the table");
  assert.ok(table.querySelector("table"), "the table they add shade to stays");
  assert.ok(!RAW.test(text(block)), text(block));
  const plain = tendenciesBlock({ plays: 300, games: 5, runRate: 0.5, bySituation: [], runDirection: [], passDepth: [] }, "TEX");
  assert.equal(plain.querySelectorAll(".ddgrid").length, 0, "no grids given: the block as it was");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["ddgrid", "ranges", "bands"])
def test_the_two_boards_in_a_fake_browser(tmp_path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
