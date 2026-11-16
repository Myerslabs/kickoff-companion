"""The poll path (ENH-19, chart 2; the owner's board of 2026-10-28, his marks of 2026-10-30 and "Build it"): the Résumé's poll
path as a line, both polls together, the next opponent beside, the game that led into each poll under its week."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cfbd.models import Game, PollWeek
from app.services import depth2
from app.services.season import next_opponent
from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]


def game(gid, week, home, away, hp=None, ap=None, done=True, neutral=False, season_type="regular"):
    return Game.model_validate({"id": gid, "week": week, "homeTeam": home, "awayTeam": away, "homePoints": hp, "awayPoints": ap, "completed": done, "neutralSite": neutral, "seasonType": season_type})


def poll_week(week, ap=None, coaches=None, season_type="regular"):
    polls = []
    if ap is not None:
        polls.append({"poll": "AP Top 25", "ranks": [{"rank": r, "school": s} for s, r in ap.items()]})
    if coaches is not None:
        polls.append({"poll": "Coaches Poll", "ranks": [{"rank": r, "school": s} for s, r in coaches.items()]})
    return PollWeek.model_validate({"season": 2026, "seasonType": season_type, "week": week, "polls": polls})


TEAMS = {"Auburn": {"abbreviation": "AUB"}, "Ole Miss": {"abbreviation": "MISS"}, "Georgia": {"abbreviation": "UGA", "color": "#ba0c2f", "altColor": "#000000"}}


def test_each_poll_carries_the_game_that_led_into_it():
    schedule = [
        game(1, 1, "Florida", "Florida Atlantic", 66, 21),
        game(3, 3, "Auburn", "Florida", 39, 44),  # away, a win
        game(4, 4, "Florida", "Ole Miss", 52, 28),
        game(5, 5, "Missouri", "Florida", 45, 17),  # away, a loss
        game(6, 6, "Florida", "Georgia", 24, 24, neutral=True),  # neutral, a tie
        game(9, 9, "Georgia", "Florida", done=False),  # not played yet
    ]
    polls = [poll_week(w, {"Florida": r} if r else {}, {}) for w, r in ((1, None), (2, None), (3, None), (4, 21), (5, 8), (6, 16), (7, None), (8, 20), (9, 17), (10, None))]
    path = depth2.led_into(depth2.poll_path(polls, "Florida"), schedule, "Florida", TEAMS)
    led = {row["week"]: row["led"] for row in path}
    assert led[1] is None, "the preseason poll follows no game"
    assert led[2]["result"] == "W" and led[2]["abbreviation"] is None and led[2]["opponent"] == "Florida Atlantic", "a school with no abbreviation keeps its name"
    assert led[3] == {"bye": True}, "no game in week 2"
    assert led[4] == {"result": "W", "opponent": "Auburn", "abbreviation": "AUB", "away": True, "neutral": False}
    assert led[6]["result"] == "L" and led[6]["away"] is True
    assert led[7]["result"] == "T" and led[7]["neutral"] is True and led[7]["away"] is False, "a neutral site is never away"
    assert led[8] == {"bye": True} and led[9] == {"bye": True}
    assert led[10] is None, "a game not played yet leads into nothing"
    assert [row["ap"] for row in path][:6] == [None, None, None, 21, 8, 16]


def test_the_final_poll_follows_the_postseason_game_and_damage_is_skipped():
    schedule = [game(1, 14, "Florida", "Florida State", 31, 10), game(2, 1, "Florida", "Texas", 20, 27, season_type="postseason")]
    path = depth2.led_into([{"week": 1, "seasonType": "postseason", "ap": 12, "coaches": 11}], schedule, "Florida", {})
    assert path[0]["led"]["result"] == "L" and path[0]["led"]["opponent"] == "Texas"
    assert depth2.led_into([{"week": 1, "seasonType": "postseason", "ap": None, "coaches": None}], [], "Florida", {})[0]["led"] is None
    junk = [game(1, 1, "Florida", "X", None, 3), "junk", None]
    out = depth2.led_into([{"week": 2, "seasonType": "regular", "ap": None, "coaches": None}, {"week": "x", "seasonType": "regular"}], junk, "Florida", {})
    assert out[0]["led"] is None, "a finished game with a missing score leads into nothing"
    assert out[1]["led"] is None


def test_the_next_opponent_line_and_its_colors():
    polls = [poll_week(1, {"Georgia": 3}, {"Georgia": 3}), poll_week(2, {"Georgia": 2}, {"Georgia": 2})]
    o = depth2.opponent_path(polls, "Georgia", TEAMS)
    assert o["school"] == "Georgia" and o["abbreviation"] == "UGA" and o["color"] == "#ba0c2f"
    assert [(p["week"], p["ap"], p["coaches"]) for p in o["polls"]] == [(1, 3, 3), (2, 2, 2)]
    assert depth2.opponent_path(polls, "Vanderbilt", TEAMS) is None, "never ranked: no line"
    assert depth2.opponent_path(polls, None, TEAMS) is None
    assert next_opponent(game(9, 9, "Georgia", "Florida", done=False), "Florida") == "Georgia"
    assert next_opponent(game(9, 9, "Florida", "Georgia", done=False), "Florida") == "Georgia"
    assert next_opponent(None, "Florida") is None
    assert next_opponent(game(9, 9, "Texas", "Ohio State", done=False), "Florida") is None, "a game that is not ours names nobody"


def test_the_resume_names_the_next_opponent_not_the_last_on_the_schedule():
    """The bug found while building (2026-10-30): the schedule loop's own `opponent` wrote over the next opponent."""
    schedule = [game(1, 1, "Florida", "Akron", 59, 13), game(2, 8, "Texas", "Florida", done=False), game(3, 14, "Florida", "Arkansas", done=False)]
    polls = [poll_week(1, {"Florida": 6, "Texas": 12, "Arkansas": 18}, {})]
    r = depth2.resume(schedule, schedule, "Florida", [], polls, next_team="Texas", teams={})
    assert r["opponentPolls"]["school"] == "Texas"


def test_the_program_carries_both_teams_poll_paths(client, fake_cfbd):
    """ENH-19 on the Pre-Game Program (owner 2026-10-30: "Yes, add it"): both paths, ours with the game behind each poll."""
    from tests.test_enh11_strengths import route_program

    route_program(fake_cfbd)
    data = client.get("/api/program/next").json()["data"]
    pp = data["pollPath"]
    assert isinstance(pp["us"], list) and pp["us"], "every poll week of the season"
    assert all({"week", "seasonType", "ap", "coaches", "led"} <= set(row) for row in pp["us"])
    assert pp["them"] is None or (pp["them"]["school"] == data["them"]["school"] and isinstance(pp["them"]["polls"], list))


SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object \w+\]/;
const text = (node) => (node ? node.textContent : "");

scenarios.chart = async () => {
  installWindow();
  const pp = await import(moduleUrl("ui/poll-path.js"));
  assert.equal(pp.rankY(1), 14);
  assert.equal(pp.rankY(25), 170);
  assert.equal(pp.rankY(26), null);
  assert.equal(pp.rankY("3"), null);
  assert.equal(pp.weekLabel({ week: 1, seasonType: "regular" }), "Pre");
  assert.equal(pp.weekLabel({ week: 6, seasonType: "regular" }), "6");
  assert.equal(pp.weekLabel({ week: 1, seasonType: "postseason" }), "Final");
  assert.equal(pp.weekLabel({ week: 1, seasonType: "postseason" }, { short: true }), "F");
  assert.equal(pp.weekLabel(null), "");
  assert.deepEqual(pp.ledWords({ result: "W", opponent: "Auburn", abbreviation: "AUB", away: true }), { mark: "W", tone: "w", opponent: "@AUB" });
  assert.deepEqual(pp.ledWords({ result: "L", opponent: "South Carolina", abbreviation: null, away: false }), { mark: "L", tone: "l", opponent: "SOUT" });
  assert.deepEqual(pp.ledWords({ bye: true }), { mark: "bye", tone: "bye", opponent: "" });
  assert.deepEqual(pp.ledWords(null), { mark: "", tone: "", opponent: "" });
  assert.deepEqual(pp.ledWords({ result: "Q" }), { mark: "", tone: "", opponent: "" });
  // the opponent's color: readable on the panel, never ours (a Florida-orange school falls to its alternate or the neutral)
  const georgia = pp.lineColor({ color: "#ba0c2f", altColor: "#000000" });
  assert.ok(/^#[0-9a-f]{6}$/.test(georgia) && georgia !== "#ba0c2f", "lightened until it reads on the charcoal");
  assert.equal(pp.lineColor({ color: null, altColor: "junk" }), "#9AA1AE", "nothing usable: the neutral");
  const weeks = [
    { week: 1, seasonType: "regular", ap: null, coaches: null, led: null },
    { week: 2, seasonType: "regular", ap: null, coaches: 25, led: { result: "W", abbreviation: "FAU" } },
    { week: 3, seasonType: "regular", ap: 21, coaches: 22, led: { bye: true } },
    { week: 4, seasonType: "regular", ap: 8, coaches: 8, led: { result: "W", abbreviation: "MISS" } },
    { week: 5, seasonType: "regular", ap: 16, coaches: 15, led: { result: "L", abbreviation: "MIZ", away: true } },
    { week: 6, seasonType: "regular", ap: null, coaches: null, led: { result: "L", abbreviation: "SC" } },
    { week: 7, seasonType: "regular", ap: 20, coaches: 24, led: { result: "W", abbreviation: "TEX", away: true } },
    { week: 8, seasonType: "regular", ap: 17, coaches: 20, led: { bye: true } },
  ];
  const them = { name: "Georgia", color: "#ba0c2f", altColor: "#000000", polls: weeks.map((w, i) => ({ week: w.week, seasonType: "regular", ap: [3, 2, 2, 2, 2, 1, 5, 3][i], coaches: [3, 2, 2, 2, 2, 1, 4, 3][i] })) };
  const svg = pp.pollPathChart({ us: { name: "Florida", polls: weeks }, them, width: 500 });
  assert.equal(svg.getAttribute("viewBox"), "0 0 500 258", "drawn at its box's own width");
  assert.equal(svg.querySelectorAll("polyline.pp__line--us").length, 4, "ours: the AP and the Coaches, each broken by week 6");
  assert.equal(svg.querySelectorAll("polyline.pp__line--them").length, 2, "theirs: the AP and the Coaches");
  assert.equal(svg.querySelectorAll(".pp__nr circle").length, 3, "a hollow dot for each AP week out (the preseason, 2, 6)");
  assert.equal(text(svg.querySelector(".pp__now")), "17", "the AP rank now, in bold");
  const marks = svg.querySelectorAll(".pp__mark").map((n) => n.textContent);
  assert.deepEqual(marks, ["W", "bye", "W", "L", "L", "W", "bye"]);
  assert.ok(text(svg).includes("@MIZ") && text(svg).includes("@TEX"));
  assert.ok(svg.getAttribute("aria-label").includes("Florida: not ranked in the preseason") && svg.getAttribute("aria-label").includes("Georgia: 3rd in the AP"));
  const labels = svg.querySelectorAll(".pp__labels text");
  assert.ok(labels.every((t) => Number(t.getAttribute("x")) >= 34 || t.getAttribute("text-anchor") !== "end"), "no number pushed into the axis");
  // narrow: the weeks shorten and the opponents' names go
  const narrow = pp.pollPathChart({ us: { name: "Florida", polls: [...weeks, ...weeks.map((w) => ({ ...w, week: w.week + 8 }))] }, width: 300 });
  assert.ok(!text(narrow).includes("@MIZ"), "no room for the opponents' names");
  assert.ok(!RAW.test(text(svg)) && !RAW.test(text(narrow)));
  // the block: head, chart, key, the two rows
  const block = pp.pollPathBlock({ polls: weeks, opponent: { school: "Georgia", color: "#ba0c2f", polls: them.polls }, team: "Florida" });
  document.body.append(block);
  assert.ok(text(block).includes("AP and Coaches together"));
  assert.ok(block.querySelector(".pp__chart svg"));
  assert.ok(text(block.querySelector(".pp__key")).includes("Georgia") && !text(block.querySelector(".pp__key")).includes("this week"), "the key names the opponent, no 'this week' (his mark)");
  const rows = block.querySelectorAll(".pp__weeks tbody tr");
  assert.equal(rows.length, 2);
  assert.equal(text(rows[0]).replace(/\s+/g, ""), "APNRNR21816NR2017");
  assert.equal(rows[1].querySelector(".now").textContent, "20");
  // damage: nothing printed raw, no opponent line
  const broken = pp.pollPathBlock({ polls: [null, "x", { week: "y" }, { week: 3, ap: "9", coaches: NaN, led: "junk" }], opponent: { polls: "nope" } });
  assert.ok(!RAW.test(text(broken)), text(broken));
  assert.ok(!text(broken.querySelector(".pp__key")).includes("Georgia"));
};

scenarios.program = async () => {
  installWindow();
  const { pollPathBand, PROGRAM_BANDS } = await import(moduleUrl("views/program.js"));
  const us = [{ week: 4, seasonType: "regular", ap: 21, coaches: 22, led: null }, { week: 5, seasonType: "regular", ap: 17, coaches: 20, led: { result: "W", abbreviation: "TEX", away: true } }];
  const them = { school: "Georgia", abbreviation: "UGA", color: "#ba0c2f", altColor: "#000000", polls: [{ week: 4, seasonType: "regular", ap: 2, coaches: 2 }, { week: 5, seasonType: "regular", ap: 3, coaches: 3 }] };
  const data = { us: { school: "Florida", abbreviation: "FLA" }, them: { school: "Georgia", abbreviation: "UGA" }, pollPath: { us, them } };
  const b = pollPathBand(data);
  assert.equal(b.getAttribute("id"), "program-pollpath");
  assert.equal(text(b.querySelector(".band__summary")), "FLA 17th · UGA 3rd in the AP");
  assert.equal(b.querySelector(".pp__head"), null, "the band's own title says it: no heading inside");
  const out = pollPathBand({ ...data, pollPath: { us: [{ week: 5, seasonType: "regular", ap: null, coaches: null }], them } });
  assert.equal(text(out.querySelector(".band__summary")), "FLA not ranked · UGA 3rd in the AP", "a side out of the poll says so");
  const heads = b.querySelectorAll(".pp__weeks tbody th").map((th) => th.textContent);
  assert.deepEqual(heads, ["FLA AP", "FLA Coaches", "UGA AP", "UGA Coaches"], "both teams' rows of numbers");
  assert.ok(b.querySelector("polyline.pp__line--them"), "this week's opponent's line");
  assert.ok(!RAW.test(text(b)));
  assert.equal(pollPathBand({ us: {}, them: {} }), null, "an old lock with no poll path: no band");
  const none = pollPathBand({ us: { school: "Florida" }, them: { school: "Georgia" }, pollPath: { us: [{ week: 4, seasonType: "regular", ap: null, coaches: null }], them: null } });
  assert.ok(text(none).includes("Neither team has been ranked"), text(none));
  assert.ok(typeof PROGRAM_BANDS.week === "function", "Margin by week's flyout from the menu (wave 3, 2026-11-01: the poll path is My Team's, one team at a time)");
  const fallback = PROGRAM_BANDS.week({ us: {}, them: {} });
  assert.ok(text(fallback).includes("Margin by week"));
};

scenarios.resume = async () => {
  installWindow();
  const { resumeBlock } = await import(moduleUrl("ui/depth2.js"));
  const r = { wins: 5, losses: 2, polls: [{ week: 4, seasonType: "regular", ap: 21, coaches: 22, led: null }, { week: 5, seasonType: "regular", ap: 8, coaches: 8, led: null }], opponentPolls: null };
  const node = resumeBlock(r, "Florida");
  assert.ok(node.querySelector(".pp"), "the poll path is the chart now");
  const none = resumeBlock({ wins: 1, losses: 6, polls: [{ week: 4, seasonType: "regular", ap: null, coaches: null }] }, "Florida");
  assert.ok(!none.querySelector(".pp") && text(none).includes("has not been ranked in a poll this season"), "never ranked: the line as before");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["chart", "resume", "program"])
def test_the_poll_path_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
