"""Freeze wave F4 (2026-10-20): the prompts' data woven into the screens.

- The roster costs beside each player (cost_players_of) and a player's standing this week (player_status).
- The notes block carries the visitors; the Top 25 service carries our game's TV crew; the season overview carries the
  facts' dated events.
- In the fake browser: the matchup card's coaches line, the lineup heads' coordinator and scheme, the cover's facts and
  trophy, the schedule's "On this day" lines, the History tab's Dates row, the paper's crew, the program's visitors band."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.services.players import cost_players_of, player_status
from tests.fakedom import needs_node, run_scenario


def test_cost_players_by_name_key():
    costs = {"players": [{"name": "K. Crawford Jr.", "position": "QB", "amountUsd": 1200000, "note": "reported"}, {"name": "Nobody", "amountUsd": "x"}, {"name": "Zero", "amountUsd": 0}, "junk", {"name": "", "amountUsd": 5}]}
    out = cost_players_of(costs)
    assert out == {"k crawford": (1200000, "reported")}
    assert cost_players_of(None) == {} and cost_players_of({"players": "junk"}) == {}


def test_player_status_this_week_then_the_preseason():
    notes = SimpleNamespace(availability=[
        SimpleNamespace(name="Hurt Guy", team="Alpha", status="Questionable", note="ankle"),
        SimpleNamespace(name="Their Guy", team="Beta", status="Out", note=None),
        SimpleNamespace(name="No Team", team=None, status=None, note="hand"),
    ])
    preseason = SimpleNamespace(injuries=[SimpleNamespace(name="Long Guy", position="WR", status="Out for the season", detail="ACL", expectedReturn="2027")])
    assert player_status(notes, preseason, "Hurt Guy", "Alpha") == "Questionable, ankle (this week's report)"
    assert player_status(notes, preseason, "Their Guy", "Alpha") is None, "a row naming another team is not his"
    assert player_status(notes, preseason, "No Team", "Alpha") == "Listed, hand (this week's report)"
    assert player_status(notes, preseason, "Long Guy", "Alpha") == "Out for the season, ACL, back 2027 (preseason load)"
    assert player_status(None, None, "Fine Guy", "Alpha") is None and player_status(notes, preseason, "", "Alpha") is None


SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const coaches = { us: { team: "Home U", headCoach: "Al Home", offensiveCoordinator: "Oc Home", defensiveCoordinator: "Dc Home" }, them: { team: "Away U", headCoach: "Al Away", offensiveCoordinator: "Oc Away", defensiveCoordinator: null } };
const schemes = { offense: "Spread", defense: "4-2-5", opponent: { offense: "Pro style", defense: null } };
const slot = (unit, name, players) => ({ unit, slot: name, players });
const lineups = {
  us: { team: "Home U", scheme: "Spread option", slots: [slot("Offense", "QB", [{ name: "Q One", number: 1, classYear: "JR", note: "limited in practice" }, { name: "Q Two", classYear: "FR" }]), slot("Defense", "DE", [{ name: "D One", classYear: "GR" }])] },
  them: { team: "Away U", scheme: "3-4", slots: [slot("Defense", "DE", [{ name: "E One", classYear: "FR" }]), slot("Offense", "QB", [{ name: "R One", classYear: "SO" }])] },
};
const us = { school: "Home U", abbreviation: "HU" };
const them = { school: "Away U", abbreviation: "AU" };

scenarios.coachesAndLineups = async () => {
  const { coachesLine, matchupCard } = await import(moduleUrl("ui/matchup-card.js"));
  assert.equal(coachesLine(coaches.them), "HC Al Away · OC Oc Away");
  assert.equal(coachesLine({ headCoach: " " }), null);
  const card = matchupCard({ us, them: { ...them, apRank: 9 }, coaches: coaches.them, rows: [] });
  document.body.append(card);
  assert.ok(!RAW.test(text(card)));
  assert.equal(text(card.querySelector(".mcard__staff")), "HC Al Away · OC Oc Away", "their coaches under the hero's name");
  const { lineupBlock } = await import(moduleUrl("ui/lineups_combined.js"));
  const node = lineupBlock({ lineups, us, them, availability: [], coaches, schemes });
  document.body.append(node);
  const t = text(node);
  assert.ok(!RAW.test(t), t.slice(0, 500));
  const details = node.querySelectorAll(".lu-head__detail").map(text);
  assert.ok(details.includes("OC Oc Home · Spread"), "our offense's head: the coordinator and the scheme: " + details.join(" | "));
  assert.ok(details.includes("DC Dc Home · 4-2-5"), "our defense's head");
  assert.ok(details.includes("OC Oc Away · Pro style"), "their offense's head");
  assert.ok(details.some((d) => d === "3-4"), "no scheme in the notes for their defense: the chart's own heading");
  assert.ok(t.includes("limited in practice"), "the chart's own note on a starter when the report says nothing");
  const bare = lineupBlock({ lineups, us, them, availability: [] });
  assert.equal(bare.querySelectorAll(".lu-head__detail").filter((d) => text(d) && !/Spread option|3-4/.test(text(d))).length, 0, "no coaches or schemes: only the charts' own headings");
};

scenarios.coverAndSchedule = async () => {
  const { cover } = await import(moduleUrl("ui/cover.js"));
  const facts = { us: { founded: 1853, stadium: "Home Field", stadiumOpened: 1930 }, them: { founded: 1900 } };
  const node = cover({ us, them, homeIsUs: true, date: "2026-10-24T19:30:00Z", facts, trophy: "The Rusty Skillet: HU leads 68-44, since 1915", state: "pre", now: new Date("2026-10-20T12:00:00Z") });
  document.body.append(node);
  const t = text(node);
  assert.ok(!RAW.test(t), t.slice(0, 500));
  assert.ok(node.querySelectorAll(".cover__facts").map(text).includes("Founded 1853 · Home Field, opened 1930"), "our facts under our block");
  assert.ok(node.querySelectorAll(".cover__facts").map(text).includes("Founded 1900"), "theirs under theirs, only what is known");
  assert.equal(text(node.querySelector(".cover__trophy")), "The Rusty Skillet: HU leads 68-44, since 1915");
  const plain = cover({ us, them, homeIsUs: true, date: "2026-10-24T19:30:00Z", state: "pre", now: new Date("2026-10-20T12:00:00Z") });
  assert.equal(plain.querySelector(".cover__facts"), null);
  assert.equal(plain.querySelector(".cover__trophy"), null);
  // the schedule: a dated event under the row it falls on, by month and day, the year named when it differs
  const { scheduleList, eventsByDay } = await import(moduleUrl("ui/schedule.js"));
  const events = [{ date: "1996-10-24", event: "The first night game" }, { date: "1923", event: "A year alone" }, { date: "2026-10-24", event: "A same-year anniversary" }, "junk", { date: "x", event: "y" }];
  assert.deepEqual([...eventsByDay(events).keys()], ["10-24"]);
  const games = [{ gameId: 1, week: 8, date: "2026-10-24T19:30:00Z", opponent: { school: "Away U" }, homeAway: "home", completed: false }, { gameId: 2, week: 9, date: "2026-10-31T19:30:00Z", opponent: { school: "Other U" }, homeAway: "away", completed: false }];
  const list = scheduleList({ games, events });
  document.body.append(list);
  const days = list.querySelectorAll(".sched__day").map(text);
  assert.equal(days.length, 1, "one row has an event");
  assert.ok(days[0].includes("On this day in 1996: The first night game") && days[0].includes("On this day: A same-year anniversary"), days[0]);
  assert.equal(scheduleList({ games }).querySelector(".sched__day"), null, "no events: nothing added");
  // the History tab's Dates row
  const { factRows } = await import(moduleUrl("ui/school-facts.js"));
  const rows = factRows({ dates: [{ date: "1996-10-24", event: "The first night game" }, { date: "1923", event: "A year alone" }, { date: "", event: "x" }] });
  const dates = rows.find((r) => r.label === "Dates");
  assert.ok(dates && dates.value.includes("1996: The first night game") && dates.value.includes("1923: A year alone"), dates && dates.value);
  assert.equal(factRows({}).find((r) => r.label === "Dates").value, "–");
};

scenarios.crewAndVisitors = async () => {
  const { crewText } = await import(moduleUrl("ui/game-staff.js"));
  const broadcast = { network: "ESPN", playByPlay: "Pat Voice", analyst: "Al Color", sideline: ["Sue Side"] };
  assert.equal(crewText({ broadcast }, { tv: "ABC" }), "ESPN: Pat Voice, Al Color, Sue Side (sideline)");
  const { visitorRows, visitorsTable } = await import(moduleUrl("ui/in-game-tables.js"));
  const rows = visitorRows([{ name: "Big Recruit", position: "WR", stars: 4, highSchool: "Central", hometown: "Town, ST", classYear: 2027, status: "committed" }, null]);
  assert.equal(rows.length, 1);
  const table = visitorsTable(rows, { caption: "x" });
  assert.ok(!RAW.test(text(table)) && text(table).includes("Big Recruit"));
};
"""


@needs_node
def test_coaches_and_schemes_head_the_lineups_and_the_card(tmp_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "coachesAndLineups")


@needs_node
def test_facts_on_the_cover_and_dates_on_the_schedule(tmp_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "coverAndSchedule")


@needs_node
def test_the_crew_and_the_visitors_kits(tmp_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "crewAndVisitors")
