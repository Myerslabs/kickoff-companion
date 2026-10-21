"""Wave B in the fake browser: the expectations-and-results band (the line against the margin and who covered, the win
probability against the winner, season numbers against the game's, players to watch against their game lines; a program
never locked says so), the two-schools band (the trophy line, dashes, never an empty box), and the team header's facts."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const clean = (label, node) => {
  const t = text(node);
  assert.ok(!RAW.test(t), `${label} printed ${JSON.stringify(t.slice(0, 400))}`);
  return t;
};

const LOCKED = {
  gameId: 77, lockedAt: "2026-10-10T19:31:00Z", homeIsUs: true,
  us: { school: "Home U", abbreviation: "HOME" }, them: { school: "Away U", abbreviation: "AWAY" },
  line: { spread: -7.5, formatted: "HOME -7.5" }, pregame: { usWinProbability: 0.7 },
  profile: { us: [{ key: "ppg", label: "Points per game", value: 35.8, format: "1f" }, { key: "ypg", label: "Yards per game", value: 480, format: "0f" }, { key: "third", label: "Third down", value: 0.45, format: "pct" }, "junk"], them: [{ key: "ppg", value: 20.1, format: "1f" }] },
  leaders: [{ label: "Passing yards", category: "passing", stat: "YDS", us: { playerId: "1", player: "A. Arm", position: "QB", value: 1800 }, them: { playerId: "9", player: "B. Back", value: 900 } }, { label: "Tackles", category: "defensive", stat: "TOT", us: { playerId: "2", player: "C. Hit", value: 55 }, them: null }, "junk"],
  notes: { present: true, author: "Test chat" },
};
const DATA = {
  game: { gameId: 77, completed: true, usPoints: 31, themPoints: 17 },
  final: { us: { points: 31, totalYards: 512, netPassingYards: 300, rushingYards: 212, thirdDown: { made: 6, of: 12 }, turnovers: 1 }, them: { points: 17, totalYards: 301, thirdDown: { made: 3, of: 14 } },
    players: { us: { passing: [{ playerId: "1", name: "A. Arm", stats: { YDS: 212, TD: 2 } }], defensive: [{ playerId: "2", stats: { TOT: 7 } }] }, them: { passing: [{ playerId: "9", stats: { YDS: "junk" } }] } } },
};

scenarios.results = async () => {
  const { resultRows, resultsBand } = await import(moduleUrl("ui/results.js"));
  const { measures, players } = resultRows(LOCKED, DATA);
  assert.deepEqual(measures.map((m) => m.label), ["Points", "Yards", "Pass yards", "Rush yards", "Third down", "Turnovers"]);
  assert.equal(measures[0].us.expected, "35.8"); assert.equal(measures[0].us.result, "31"); assert.equal(measures[0].them.result, "17");
  assert.equal(measures[4].us.expected, "45%"); assert.equal(measures[4].us.result, "50%"); assert.equal(measures[4].them.expected, "–");
  assert.equal(measures[2].them.result, "–", "no number in the box: a dash");
  assert.deepEqual(players.map((p) => [p.player, p.season, p.game]), [["A. Arm", "1,800", "212"], ["B. Back", "900", "–"], ["C. Hit", "55", "7"]]);
  const band = resultsBand({ locked: LOCKED, data: DATA });
  document.body.append(band);
  const t = clean("results band", band);
  assert.ok(t.includes("Expectations and results") && t.includes("HOME -7.5") && t.includes("HOME by 14 (HOME covered)") && t.includes("70% HOME") && t.includes("HOME won"));
  assert.ok(t.includes("A. Arm (QB)") && t.includes("Test chat"));
  // the favorite wins but not by the number: the other side covered; a tie; the away side as us
  const close = resultsBand({ locked: LOCKED, data: { ...DATA, game: { ...DATA.game, usPoints: 21, themPoints: 17 } } });
  assert.ok(text(close).includes("HOME by 4 (AWAY covered)"));
  const push = resultsBand({ locked: { ...LOCKED, line: { spread: -7 } }, data: { ...DATA, game: { ...DATA.game, usPoints: 24, themPoints: 17 } } });
  assert.ok(text(push).includes("HOME by 7 (a push)"));
  const away = resultsBand({ locked: { ...LOCKED, homeIsUs: false, line: { spread: 3 } }, data: { ...DATA, game: { ...DATA.game, usPoints: 20, themPoints: 21 } } });
  assert.ok(text(away).includes("AWAY by 1 (AWAY covered)"), "as the away side favored by three, losing by one: the home dog covered");
  const none = resultsBand({ locked: null, data: DATA });
  assert.ok(text(none).includes("not locked at kickoff"));
  clean("junk results", resultsBand({ locked: { gameId: 1 }, data: { game: "junk", final: 5 } }));
};

scenarios.schools = async () => {
  const { trophyLine, twoSchoolsBand } = await import(moduleUrl("ui/two-schools.js"));
  const us = { school: "Home U", abbreviation: "HOME" };
  const them = { school: "Away U", abbreviation: "AWAY" };
  const facts = { us: { founded: 1853, allTimeRecord: "750-440-40", nationalTitles: [1996, 2006], conferenceTitles: 8, heismans: ["A", "B"], stadium: "The Bog", capacity: 88548, rivalries: [{ rival: "away u", trophy: "The Rusty Skillet", firstMeeting: 1915, record: "68-44-2" }] }, them: null };
  assert.equal(trophyLine(facts, us, them), "The Rusty Skillet: HOME 68-44-2, since 1915");
  assert.equal(trophyLine({ us: null, them: { rivalries: [{ rival: "Home U", record: "44-68-2" }] } }, us, them), "A rivalry: AWAY 44-68-2");
  assert.equal(trophyLine({}, us, them), null);
  const band = twoSchoolsBand({ us, them, facts });
  document.body.append(band);
  const t = clean("two schools", band);
  assert.ok(t.includes("The two schools") && t.includes("2 (last 2006)") && t.includes("The Bog, 88,548 seats") && t.includes("Away U facts are not loaded yet"));
  assert.ok(band.querySelector('a[href="#prompts"]'));
  assert.equal(twoSchoolsBand({ us, them, facts: { us: null, them: null } }), null, "no facts: no band");
  assert.equal(twoSchoolsBand({ us: "junk", them: 5, facts: "junk" }), null);
  clean("junk schools", twoSchoolsBand({ us: null, them: null, facts: { us: { nationalTitles: "x", rivalries: 5 }, them: { founded: "1900" } } }));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["results", "schools"])
def test_wave_b_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_the_program_and_the_header_use_the_new_bands() -> None:
    js = Path(__file__).resolve().parents[1] / "static" / "js"
    program = (js / "views" / "program.js").read_text(encoding="utf-8")
    assert "resultsSlot(data, state)" in program and "twoSchoolsBand({ us: data.us, them: data.them, facts: data.facts })" in program
    assert '"program-results", "program-schools"' in program, "both span two columns"
    team = (js / "views" / "team.js").read_text(encoding="utf-8")
    assert team.count("headerFacts(team, data.facts)") == 2, "the page and the sheet"
    app = (js / "app.js").read_text(encoding="utf-8")
    assert 'id: "today"' in app and "startTodayNote().catch" in app and 'title: "On this day"' in app
