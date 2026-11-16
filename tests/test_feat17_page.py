"""FEAT-17 the Imperialism Map's page (the owner's board of 2026-10-30, "Build
as drawn"): the replay's scores on each take and the weeks still to come, then the page in a fake browser on a twelve-cell map:
the lattice and the cell under a tap, one color a school for the season (ours in --team-us, a close neighbor on its second
color, an unreadable one lightened), Most land's ranks, the words under the slider, our next game's stakes, the three bands,
the slider by key and by Play, a tap's card beside the territory on a tablet and from the bottom on a phone, Escape, the states
with no map, and its place in the band catalog and the menu's New."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.imperialism import Season, build_table
from tests.fakedom import needs_node, run_scenario
from tests.test_feat17_imperialism import NOW, game, small_season


def test_each_take_carries_its_score():
    g, enrollment, fbs, campuses, regular, post = small_season()
    season = Season(g, enrollment, fbs, campuses, NOW)
    season.replay(regular, post, [(n, i + 1) for i, n in enumerate(sorted(fbs)[:12])], "-")
    takes = [e for e in season.events if e["rule"] == "capped"]
    assert takes and all(e["winnerPoints"] > e["loserPoints"] for e in takes)
    assert all(e["winnerPoints"] is None for e in season.events if e["rule"] == "selection_sunday"), "Selection Sunday has no score"
    assert season.upcoming == ["QF", "SF", "Final"], "the first round is played: the rest of the playoff to come"


def test_the_weeks_still_to_come():
    g, enrollment, fbs, campuses, regular, _post = small_season()
    later = [game(900, 5, "T01", "T02", None, None, completed=False, start="2026-10-05T17:00:00.000Z"), game(901, 6, "T03", "T04", None, None, completed=False, start="2026-10-12T17:00:00.000Z", notes="Army-Navy")]
    season = Season(g, enrollment, fbs, campuses, NOW)
    season.replay(regular + later, [], None, "-")
    assert season.upcoming == ["Selection Sunday", "Wk 5", "Wk 6", "R1", "QF", "SF", "Final"], "weeks after the championships come after Selection Sunday"
    early = Season(g, enrollment, fbs, campuses, NOW)
    early.replay([x for x in regular if x.week <= 2] + [x.model_copy(update={"completed": False, "home_points": None, "away_points": None}) for x in regular if x.week >= 3], [], None, "-")
    assert early.upcoming[:3] == ["Wk 3", "CCG", "Selection Sunday"], "a week of title games alone is CCG"
    table = build_table(early, fbs, 2, {}, "test")
    assert table["upcoming"] == early.upcoming


SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object \w+\]/;
const text = (node) => (node ? node.textContent : "");

// a twelve-cell map: four columns of three, column by column
const cells = [];
for (let c = 0; c < 4; c += 1) for (let r = 0; r < 3; r += 1) cells.push(c, r);
const GRID = { format: 1, viewBox: [0, 0, 80, 80], side: 10, x0: 10, y0: 10, count: 12, cells, states: "M0 0L1 1", version: "g1" };
const TEAMS = [
  { team: "Akron", index: 0, quota: 5, abbreviation: "AKR", color: "#3a6af0", altColor: "#ffcc00", logo: null, logoDark: null, talentEdge: "#120 talent · 0.82 avg · 0% BCR" },
  { team: "Florida", index: 1, quota: 4, abbreviation: "FLA", color: "#0021a5", altColor: "#fa4616", logo: "/media/logo/57", logoDark: "/media/logo/57?v=dark", talentEdge: "#10 talent · 0.91 avg · 61% BCR" },
  { team: "Campbell State", index: 2, quota: 3, abbreviation: "CAM", color: "#111111", altColor: null, logo: null, logoDark: null, talentEdge: null },
];
const START = [0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2];
const WK1 = [0, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2];
const WK2 = [2, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2];
const DATA = {
  available: true, season: 2026, computedWeek: 2, gridVersion: "g1", cells: 12, ourTeam: "Florida",
  rules: "Starting land by enrollment. A win takes up to the winner's starting size from the loser.",
  runs: { lastGood: { status: "ok", finishedAt: "2026-11-01T06:02:00-05:00" }, last: { status: "ok", finishedAt: "2026-11-01T06:02:00-05:00" } },
  upcoming: ["Wk 3", "CCG", "Selection Sunday", "R1", "QF", "SF", "Final"],
  teams: TEAMS,
  snapshots: [
    { phase: "regular", week: 0, label: "Start", partial: false, owners: START, records: {} },
    { phase: "regular", week: 1, label: "Wk 1", partial: false, owners: WK1, records: { Florida: [1, 0], Akron: [0, 1] } },
    { phase: "regular", week: 2, label: "Wk 2", partial: true, owners: WK2, records: { Florida: [1, 0], Akron: [0, 2], "Campbell State": [1, 0] } },
  ],
  events: [
    { phase: "regular", week: 1, gameId: 1, winner: "Florida", loser: "Akron", winnerPoints: 27, loserPoints: 24, cellsMoved: 4, rule: "capped" },
    { phase: "regular", week: 2, gameId: 2, winner: "Campbell State", loser: "Akron", winnerPoints: 10, loserPoints: 7, cellsMoved: 1, rule: "capped" },
  ],
  schedule: [
    { week: 1, seasonType: "regular", opponent: "Akron", home: true, neutral: false, start: "2026-09-05T23:00:00.000Z", completed: true, us: 27, them: 24 },
    { week: 3, seasonType: "regular", opponent: "Campbell State", home: false, neutral: false, start: "2026-09-19T20:00:00.000Z", completed: false, us: null, them: null },
  ],
};
const clickAt = (node, x, y) => {
  const event = makeEvent("click", { bubbles: true });
  event.clientX = x;
  event.clientY = y;
  node.dispatchEvent(event);
};

scenarios.pure = async () => {
  await useTeam();
  const m = await import(moduleUrl("views/imperialism.js"));
  const geo = m.geometry(GRID);
  assert.equal(geo.n, 12);
  assert.deepEqual([...geo.near[4]].sort((a, b) => a - b), [1, 2, 3, 5, 7, 8], "an odd column's neighbors sit half a row lower");
  assert.equal(geo.hex[0].slice(0, 1), "M");
  const h = Math.sqrt(3) * 10;
  assert.equal(m.cellAt(geo, 25, 10 + h + h / 2), 4, "the cell under its own center");
  assert.equal(m.cellAt(geo, 26, 12 + h + h / 2), 4, "a little off its center");
  assert.equal(m.cellAt(geo, 300, 300), null, "the sea");
  assert.equal(m.geometry({ ...GRID, cells: [0, "x"] }), null, "a damaged grid draws nothing");
  assert.equal(m.geometry(null), null);
  const colors = m.colorsFor(TEAMS, [START, WK1, WK2], geo, { us: 1, usColor: "#3D6BFF" });
  assert.equal(colors[1], "#3D6BFF", "ours in the app's own color");
  assert.equal(colors[0], "#ffcc00", "a neighbor close to ours takes its second color");
  assert.ok(colors[2] && colors[2] !== "#111111", "a color that does not read on the panel is lightened");
  const rows = m.standings([0, 0, 1, 1, 2], [0, 1, 1, 1, 2], TEAMS);
  assert.deepEqual(rows.map((r) => [r.team, r.rank, r.cells, r.change]), [["Akron", 1, 2, 1], ["Florida", 1, 2, -1], ["Campbell State", 3, 1, 0]]);
  assert.equal(m.standings([], null, TEAMS).length, 0);
  assert.deepEqual(["Start", "Wk 7", "CCG", "Selection Sunday", "R1", "Final"].map(m.tickLabel), ["Start", "7", "CCG", "Sel.", "R1", "Final"]);
  assert.deepEqual(["Start", "Wk 7", "CCG", "QF"].map(m.after), ["at the start", "after week 7", "after championship week", "after the quarterfinals"]);
  const view = m.prepare(DATA, geo);
  assert.equal(view.us, 1);
  assert.deepEqual(view.events.map((e) => e.length), [0, 1, 1]);
  assert.equal(m.captionFor(view, 0), "The start: every school's land grown from its own campus, by its enrollment where there is room, one region each. Florida starts with 4 cells, 33.3% of the map. Week 2 is in progress.");
  assert.equal(m.captionFor(view, 1), "Week 1: Florida 27, Akron 24. Florida took 4 cells, its full starting size, from the side of Akron's land nearest its own. Week 2 is in progress.");
  assert.equal(m.captionFor(view, 2), "Week 2: Campbell State 10, Akron 7. Campbell State took 1 cell, all Akron had left. The week is still being played.");
  assert.equal(m.nextWords(view, 2), `Next: a bye in week 2, then Campbell State, ${new Date("2026-09-19T20:00:00.000Z").toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}, away. A win takes up to 4 of Campbell State's 4 cells; a loss gives Campbell State up to 3 of ours.`);
  const fcs = m.prepare({ ...DATA, schedule: [{ week: 3, seasonType: "regular", opponent: "Stetson", home: true, completed: false, start: null }] }, geo);
  assert.equal(m.nextWords(fcs, 2), "Next: Stetson, at home. Stetson holds no land on this map: nothing changes hands.");
  const over = m.prepare({ ...DATA, schedule: [{ week: 1, seasonType: "regular", opponent: "Akron", home: true, completed: true }] }, geo);
  assert.equal(m.nextWords(over, 2), "No games left this season.");
  assert.deepEqual(m.eventLine(DATA.events[0], "Florida", "Wk 1"), { week: "Wk 1", words: "Took from Akron", cells: 4 });
  assert.deepEqual(m.eventLine({ winner: "Georgia", loser: "Florida", cellsMoved: 9, rule: "winner_take_all" }, "Florida", "QF"), { week: "QF", words: "Lost all to Georgia", cells: -9 });
  assert.equal(m.prepare({ ...DATA, snapshots: [{ label: "Start", owners: [1, 2] }] }, geo), null, "owners of the wrong length are left out");
  // the logo's anchor (owner 2026-10-30: "the schools need to be anchored in their locations")
  assert.equal(m.anchorCell([5, 6, 7, 8], START, geo, 1, 6), 6, "on its own campus while it holds it");
  assert.equal(m.anchorCell([1, 2, 3, 4, 5, 6, 7, 8], WK1, geo, 1, 6), 6, "a conqueror's logo stays home, never in the middle of what it took");
  const lost = [2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2];
  assert.equal(m.anchorCell([0, 11], lost, geo, 2, 10), 11, "a lost campus: its land nearest home, not the far corner");
  assert.equal(m.anchorCell([5, 6, 7, 8], START, geo, 1, null), m.largestPiece([5, 6, 7, 8], START, geo, 1).middle, "no campus in the answer: the middle, as before");
  assert.equal(m.anchorCell([5, 6, 7, 8], START, geo, 1, 99), m.largestPiece([5, 6, 7, 8], START, geo, 1).middle, "a campus off the map: the middle");
  assert.equal(m.anchorCell([], START, geo, 1, 6), null, "no land: no logo");
};

async function mountPage(data = DATA, { grid = GRID } = {}) {
  installWindow();
  await useTeam();
  const m = await import(moduleUrl("views/imperialism.js"));
  m.forgetGrid();
  route("/api/imperialism/grid", grid instanceof Error ? { status: 503, body: { data: null, errors: [{ message: grid.message }] } } : envelope(grid));
  route("/api/imperialism/now", envelope(data));
  const container = document.createElement("main");
  document.body.append(container);
  const view = m.createImperialismView({ onStatus: () => {} });
  view.mount(container);
  await settle();
  await settle();
  return { m, view, container };
}

scenarios.page = async () => {
  const { view, container } = await mountPage();
  const words = text(container);
  assert.ok(!RAW.test(words), words.match(/.{0,40}(undefined|null|NaN|Infinity|object).{0,40}/)?.[0]);
  assert.deepEqual(container.querySelectorAll("section.band").map((s) => s.getAttribute("id")), ["imp-map", "imp-land", "imp-us"]);
  assert.equal(container.querySelectorAll(".imp-map__team").length, 2, "Akron holds nothing after week 2");
  assert.ok(container.querySelector(".imp-map__team--us") && !container.querySelector(".imp-map__team--us").getAttribute("fill"), "ours wears --team-us from the style sheet");
  assert.ok(container.querySelector(".imp-map__our-border").getAttribute("d").startsWith("M"), "our edge drawn on its own");
  const slider = container.querySelector(".imp-slider");
  assert.equal(slider.getAttribute("aria-valuenow"), "2", "the page opens on the latest week");
  assert.equal(slider.getAttribute("aria-valuetext"), "Week 2, in progress");
  const ticks = container.querySelectorAll(".imp-tick");
  assert.deepEqual(ticks.map(text), ["Start", "1", "2", "3", "CCG", "Sel.", "R1", "QF", "SF", "Final"]);
  assert.equal(container.querySelectorAll(".imp-tick.is-later").length, 7, "what is still to come, faded");
  assert.ok(ticks[2].classList.contains("is-partial") && ticks[2].classList.contains("is-current"));
  assert.ok(text(container.querySelector(".imp-caption")).startsWith("Week 2: Campbell State 10, Akron 7."));
  assert.ok(text(container.querySelector("#imp-map .band__summary")).includes("Week 2 (in progress) · 2 of 3 schools hold land"));
  const land = container.querySelector(".imp-land");
  assert.deepEqual(land.querySelectorAll("tbody tr").map((tr) => text(tr.querySelector(".team-link"))), ["Florida", "Campbell State"]);
  assert.ok(land.querySelector("tr.is-us") && text(land.querySelector("tr.is-us")).includes("66.7%"));
  const us = container.querySelector("#imp-us");
  assert.equal(text(us.querySelector(".band__title")), "Gators", "titled with our mascot");
  assert.ok(text(us).includes("1-0 · 1st of the 2 schools holding land · started with 4"));
  assert.deepEqual(us.querySelectorAll(".imp-us__line").map(text), ["Wk 1Took from Akron+4"]);
  assert.ok(text(us.querySelector(".imp-us__next")).startsWith("Next: a bye in week 2, then Campbell State"));
  assert.ok(us.querySelector(".imp-spark") && us.querySelectorAll(".imp-spark__tick").length === 3);
  assert.ok(text(container).includes("Worked out"), "when the map was worked out");

  // the slider by key: back a week, every band follows
  slider.dispatchEvent(makeEvent("keydown", { key: "ArrowLeft" }));
  assert.equal(slider.getAttribute("aria-valuenow"), "1");
  assert.ok(text(container.querySelector(".imp-caption")).startsWith("Week 1: Florida 27, Akron 24. Florida took 4 cells, its full starting size"));
  assert.equal(text(container.querySelector("#imp-land .band__summary")), "after week 1");
  assert.equal(container.querySelectorAll(".imp-map__team").length, 3);
  assert.ok(!container.querySelector(".imp-us__next"), "the next game's stakes only on the latest week");
  slider.dispatchEvent(makeEvent("keydown", { key: "Home" }));
  assert.equal(text(container.querySelector("#imp-land .band__summary")), "at the start");
  // Play steps a week every 0.7 s and stops at the latest
  const play = container.querySelector(".imp-play");
  play.click();
  assert.equal(play.getAttribute("aria-label"), "Pause");
  await advance(700);
  assert.equal(slider.getAttribute("aria-valuenow"), "1");
  await advance(700);
  assert.equal(slider.getAttribute("aria-valuenow"), "2");
  await advance(1400);
  assert.equal(play.getAttribute("aria-label"), "Play the season", "stopped at the latest week");

  // a tap on the tablet: the card beside the territory, the ring on the tapped cell
  const svg = container.querySelector(".imp-map__svg");
  const stage = container.querySelector(".imp-stage");
  svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 80, height: 80, right: 80, bottom: 80 });
  stage.clientWidth = 800;
  stage.clientHeight = 800;
  const h = Math.sqrt(3) * 10;
  clickAt(svg, 40, 10 + h);
  const card = stage.querySelector(".imp-card");
  assert.ok(card && !card.classList.contains("imp-card--sheet"), "beside the territory on a wide screen");
  const said = text(card);
  assert.ok(!RAW.test(said), said);
  assert.ok(said.includes("Florida") && said.includes("1-0 · 1st by land") && said.includes("8cells · 66.7% of the map") && said.includes("No change this week"), said);
  assert.ok(said.includes("#10 talent · 0.91 avg · 61% BCR") && said.includes("Took from: none this week"));
  assert.equal(container.querySelector(".imp-map__ring").getAttribute("cx"), "40");
  document.dispatchEvent(makeEvent("keydown", { key: "Escape" }));
  assert.ok(!stage.querySelector(".imp-card"), "Escape closes it");
  // over the sea: nothing opens
  clickAt(svg, 79, 79);
  assert.ok(!stage.querySelector(".imp-card"));
  // a phone: the card comes up from the bottom of the page
  stage.clientWidth = 340;
  clickAt(svg, 10, 10);
  const sheet = document.body.querySelector(".imp-card--sheet");
  assert.ok(sheet && text(sheet).includes("Campbell State") && text(sheet).includes("Took from: Akron (1)"), text(sheet));
  sheet.querySelector(".imp-card__close").click();
  assert.ok(!document.body.querySelector(".imp-card"), "closed");
  clickAt(svg, 10, 10);
  view.unmount();
  assert.ok(!document.body.querySelector(".imp-card"), "leaving the page takes the sheet with it");
};

scenarios.states = async () => {
  const never = await mountPage({ available: false, failed: false, message: "The Imperialism Map for 2026 has not been worked out yet." });
  assert.ok(text(never.container).includes("has not been worked out yet") && !never.container.querySelector(".imp-map__svg"), "words, never an empty map");
  never.view.unmount();
  const failed = await mountPage({ available: false, failed: true, message: "The Imperialism Map for 2026 is unavailable since 2026-11-01T06:02:00-05:00: CFBD data missing" });
  assert.ok(failed.container.querySelector(".note--error") && text(failed.container).includes("unavailable since"));
  failed.view.unmount();
  const stale = await mountPage({ ...DATA, runs: { lastGood: DATA.runs.lastGood, last: { status: "failed", startedAt: "2026-11-08T06:01:00-05:00", message: "CFBD down" } } });
  assert.ok(stale.container.querySelector(".imp-foot--stale") && text(stale.container).includes("The last run failed") && text(stale.container).includes("CFBD down"));
  stale.view.unmount();
  const noGrid = await mountPage(DATA, { grid: new Error("The map's grid could not be read") });
  assert.ok(text(noGrid.container).includes("could not be read"), text(noGrid.container));
  noGrid.view.unmount();
  const damaged = await mountPage({ ...DATA, snapshots: [{ label: "Start", owners: [0, 1] }] });
  assert.ok(text(damaged.container).includes("came back damaged"));
  damaged.view.unmount();
  const partly = await mountPage({ ...DATA, snapshots: [...DATA.snapshots, { label: "Wk 3", owners: [1] }], teams: [...TEAMS, { team: 7 }] });
  assert.ok(text(partly.container).includes("1 week of the map came back damaged"));
  assert.ok(!RAW.test(text(partly.container)));
  partly.view.unmount();
};

scenarios.placed = async () => {
  const cat = await import(moduleUrl("ui/band-catalog.js"));
  assert.deepEqual(cat.bandsOf("imperialism").map((b) => b.id), ["imp-map", "imp-land", "imp-us"]);
  assert.equal(cat.bandHref("imperialism", "imp-land"), "#band=imperialism:imp-land");
  const { MENU } = await import(moduleUrl("ui/menu-tree.js"));
  // placed under National (owner 2026-11-15: "the imperialism map can go under the national menu, as it's a national game")
  const national = MENU.groups.find((g) => g.id === "national").items;
  const row = national.find((e) => e && e.id === "imperialism");
  assert.ok(row && row.page === "imperialism" && !row.items, "under National, one row that opens the page (ENH-46, owner 2026-11-10: its bands are on the page)");
  assert.equal(national[national.length - 1], row, "at the bottom of National, the newest there");
  assert.ok(!MENU.groups.find((g) => g.id === "new").items.some((e) => e && /(^|:)imperialism$/.test(e.id)), "placed, so it left New");
  const app = (await import("node:fs")).readFileSync(new URL(moduleUrl("app.js")), "utf8");
  assert.ok(app.includes("imperialism: (opts) => createImperialismView(opts)"));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["pure", "page", "states", "placed"])
def test_the_page_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
