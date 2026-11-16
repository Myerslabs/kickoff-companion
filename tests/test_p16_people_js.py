"""Phase 16, stream PEOPLE: Leaders, Roster, Recruiting and the player card in the fake browser
(tests/fakedom.py), plus the pure helpers under Node. Chips in tappable rows never open the card, a link
arrival keeps the remembered Leaders scope, the Gators below the cut sit in their own tbody, the roster's
position select is visible and its sort survives a refresh, depth rows carry the jersey number with no
anchor inside the button, the loading card states nothing as fact and never draws Florida as the opponent,
game-log opponents are team links, the sparkline needs two games, the by-state table survives nulls, and
no damaged payload prints undefined, null or NaN. Tables wave 3: every Leaders board sizes itself (the position, the team
and each rank in columns of their own, a league list's order as its chip turning plain at small, the details by size), and
"vs opponent" is the two-team kit with a player column on each side. Step 4: Recruiting's tables size themselves (the class's
national rank its own order, the recruit's position its own column, one column per star count, the visitors a sorting table of
players) and keep the reader's order across a redraw. Step 5: the player card's tables size themselves (the seasons per
category with a real Career row from two seasons up, the game log and play value by game sorting with the opponent "at DT" at
small, the splits' short names, the History newest first with the team's abbreviation and "#" at small) and a past season
that failed is named in the note. The player card's patience (owner 2026-11-15): the card waits like a page (a round of
FETCH_TIMEOUT_MS, up to SLOW_TRIES), says after the first round that the numbers are still coming from CFBD, then shows the
time-out in plain words with Try again where the tabs go; closing it lets the request go and says nothing; a board row's
short card shows only real values; fetchPatient without the new options behaves as before."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const clean = (label, node) => {
  const t = text(node);
  assert.ok(!RAW.test(t), `${label} printed ${JSON.stringify(t.match(/.{0,60}\b(undefined|null|NaN|Infinity)\b.{0,60}|.{0,40}\[object Object\].{0,40}/)?.[0] || t.slice(0, 200))}`);
  return t;
};
const click = (node) => node.dispatchEvent(makeEvent("click", { bubbles: true }));
Object.getPrototypeOf(document.body).scrollIntoView = function (opts) { this.scrolledInto = opts || true; };
const JUNK = [null, undefined, NaN, Infinity, "", "abc", {}, [], true, -3, "[object Object]"];

function entry(over = {}) {
  return {
    playerId: "p1", player: "Mason Hamilton", position: "QB", team: "Florida", teamAbbr: "FLA", metric: "board:passing:YDS", isUs: true,
    value: 721, detail: { ATT: 64, COMPLETIONS: 47, INT: 2, PCT: 0.734, TD: 6, YPA: 11.3 }, rank: null,
    conferenceRank: 6, conferenceOf: 43, nationalRank: 47, nationalOf: 358, headshotUrl: "/media/headshot/p1", ...over,
  };
}

function leadersData() {
  const national = Array.from({ length: 10 }, (_, i) => entry({ playerId: `n${i}`, player: `National ${i}`, team: i === 3 ? "Fresno State" : "USC", teamAbbr: i === 3 ? "FRES" : "USC", isUs: false, rank: i + 1, nationalRank: i + 1, value: 1200 - i * 10 }));
  const conference = Array.from({ length: 10 }, (_, i) => entry({ playerId: `c${i}`, player: `SEC ${i}`, team: "Fresno State", teamAbbr: "FRES", isUs: false, rank: i + 1, conferenceRank: i + 1, value: 1100 - i * 10 }));
  return {
    season: 2026,
    team: { school: "Florida", abbreviation: "FLA", mascot: "Gators", conference: "SEC" },
    opponent: { school: "Fresno State", abbreviation: "FRES", mascot: "Miners", conference: "SEC" },
    boards: [
      {
        id: "passing:YDS", metric: "board:passing:YDS", category: "passing", stat: "YDS", label: "Passing yards", format: "0f",
        team: [entry(), entry({ playerId: "p2", player: "Tramell Jones Jr.", value: 126, nationalRank: 160, conferenceRank: 20 })],
        opponent: [entry({ playerId: "o1", player: "Byron Brooks", team: "Fresno State", teamAbbr: "FRES", isUs: false, value: 753, nationalRank: 37 })],
        conference, national, conferenceOf: 43, nationalOf: 358, usBest: { conferenceRank: 6, nationalRank: 47 },
      },
    ],
    extraBoards: [
      { id: "usage:overall", metric: null, category: "usage", stat: "Usage", label: "Usage, share of the team's plays", format: "pct", detailColumns: [{ key: "pass", label: "Pass", format: "pct" }], team: [entry({ metric: null, value: 0.4, detail: { pass: 0.8 }, nationalRank: null, conferenceRank: null })], opponent: [], conference: [], national: [], conferenceOf: null, nationalOf: null, usBest: { conferenceRank: null, nationalRank: null } },
    ],
    parts: {},
  };
}

function rosterPlayer(over = {}) {
  return { playerId: "r1", number: 12, name: "Mason Hamilton", firstName: "Aaron", lastName: "Hamilton", team: "Florida", position: "QB", classYear: "JR", height: 73, heightText: "6-1", weight: 207, hometown: "Bogart, GA", highSchool: "Oconee", stars: 4, rating: 0.9379, recruitRank: 142, headshotUrl: "/media/headshot/r1", isUs: true, transfer: null, ppaPerPlay: 0.4, ppaPlays: 81, usageShare: 0.3, ...over };
}

function rosterData() {
  return {
    season: 2026,
    team: { school: "Florida" },
    players: [
      rosterPlayer(),
      rosterPlayer({ playerId: "r2", number: 9, name: "Tramell Jones", firstName: "Tramell", lastName: "Jones", ppaPlays: 18, rating: 0.91, weight: 190 }),
      rosterPlayer({ playerId: "r3", number: 70, name: "Big Tackle", firstName: "Big", lastName: "Tackle", position: "OL", ppaPlays: null, ppaPerPlay: null, rating: 0.95, weight: 320, recruitMetric: "recruit:2024" }),
      rosterPlayer({ playerId: "r4", number: 71, name: "Other Guard", firstName: "Other", lastName: "Guard", position: "OL", ppaPlays: null, ppaPerPlay: null, rating: 0.88, weight: 310 }),
      rosterPlayer({ playerId: "r5", number: 5, name: "Myles Ashford", firstName: "Myles", lastName: "Graham", position: "LB", ppaPlays: null, rating: 0.98, weight: 228 }),
    ],
    starCounts: { 5: 0, 4: 5, 3: 0 }, average: 4, rated: 5,
    blueChip: { ratio: 0.7, blueChips: 61, signees: 86, classes: [{ year: 2025, signees: 20, blueChips: 14 }] },
    impact: { offense: [{ playerId: "r1", name: "Mason Hamilton", position: "QB", number: 12, classYear: "JR", headshotUrl: "/media/headshot/r1", chips: ["721 passing yards", "64 ATT", "3 QB HUR"], isUs: true }], defense: [] },
    parts: {},
  };
}

function recruitingData() {
  const commit = (i, over = {}) => ({ recruitId: `c${i}`, athleteId: null, name: `Recruit ${i}`, position: "WR", stars: 4, rating: 0.9755 - i / 100, nationalRank: 55 + i, highSchool: "Lone Star", hometown: "Frisco, TX", heightText: "6-1", weight: 190, ...over });
  return {
    season: 2026,
    classes: [
      { year: 2026, count: 3, commits: [commit(1), commit(2, { metric: "recruit:2026" }), commit(3)], starCounts: { 5: 0, 4: 3, 3: 0 }, average: 4, partName: "recruits_2026", classRank: { year: 2026, rank: 17, points: 250.98, of: 221, metric: "class:2026" }, byState: [{ state: "FL", commits: 2, stars: { 5: 0, 4: 1, 3: 1 }, averageRating: 0.9011 }, { state: "TX", commits: 1, stars: { 5: 0, 4: 1, 3: 0 }, averageRating: 0.96 }], inState: { state: "FL", commits: 2, of: 3, share: 0.667 }, unknownState: 0 },
      { year: 2027, count: 1, commits: [commit(4)], starCounts: { 5: 0, 4: 1 }, average: 4, partName: "recruits_2027", classRank: null, byState: [], inState: null, unknownState: 1 },
    ],
    visitors: { gameId: 526000600, opponent: "Fresno State", date: "2026-10-03T16:00:00.000Z", startTimeTbd: false, home: [{ name: "Visitor One", position: "QB", stars: 4, highSchool: "X", hometown: "Y", classYear: 2027, status: "confirmed" }], away: [], source: null, note: null, error: null },
    parts: {},
  };
}

function playerData() {
  const abbr = { "Florida Atlantic": "SWTA", "Texas State": "DT" };
  const game = (week, opponent, homeAway, result, yds) => ({ gameId: 400 + week, week, postseason: null, date: "2026-09-05T23:45:00.000Z", opponent, opponentAbbr: abbr[opponent] || null, homeAway, result, lines: [{ category: "receiving", stats: { REC: 5, YDS: yds, AVG: 10.2, TD: 1, LONG: 40 } }, { category: "kicking", stats: { FG: "1/1", PCT: 100.0 } }] });
  return {
    player: { playerId: "p9", number: 1, name: "Darnell Brooks III", team: "Florida", teamAbbr: "FLA", position: "WR", classYear: "SO", heightText: "5-11", weight: 180, hometown: "Jacksonville, FL", highSchool: "Jackson", stars: 4, rating: 0.9379, recruitRank: 123, recruit: { year: 2024, stars: 4, rating: 0.9379, nationalRank: 123, position: "ATH", type: "HighSchool" }, transfer: { from: "Georgia Tech", stars: 3, rating: 0.89, date: "2026-01-06", eligibility: "Immediate" }, headshotUrl: "/media/headshot/p9", isUs: true },
    seasons: [{ year: 2026, category: "receiving", stats: { LONG: 49, REC: 14, TD: 2, YDS: 246, YPR: 17.6 } }],
    gameLog: [game(1, "Florida Atlantic", "home", "W 66-21", 50), game(2, "Campbell", "home", "W 52-3", 80), game(3, "Texas State", "away", "L 20-24", 117)],
    missingWeeks: [],
    history: [{ year: 2025, team: "Florida", teamAbbr: "FLA", classYear: "FR", position: "WR", number: 1 }],
    ppa: { season: { plays: 20, average: { all: 0.5, pass: 0.6 }, total: { all: 10 } }, teamRank: 3, teamOf: 18, games: [{ week: 3, opponent: "Texas State", all: 0.8, pass: 0.9, rush: null }] },
    usage: { overall: 0.2, pass: 0.3 },
    parts: {},
  };
}

async function mountView(factory, opts = {}) {
  const main = document.createElement("main");
  document.body.replaceChildren(main);
  const view = factory(opts);
  view.mount(main);
  await settle();
  return { main, view };
}

scenarios.labels = async () => {
  const labels = await import(moduleUrl("ui/stat-labels.js"));
  const passing = labels.boardDetail({ id: "passing:YDS", category: "passing" }, [{ detail: { ATT: 64, COMPLETIONS: 47, INT: 2, PCT: 0.7, TD: 6, YPA: 11.3 } }]);
  assert.deepEqual(passing.map((c) => c.label), ["Cmp", "Att", "Y/A", "TD", "INT"]);
  assert.deepEqual(passing.map((c) => c.key), ["COMPLETIONS", "ATT", "YPA", "TD", "INT"]);
  const sacks = labels.boardDetail({ id: "defensive:SACKS", category: "defensive" }, [{ detail: { PD: 0, "QB HUR": 1, SOLO: 3, TD: 0, TFL: 4, TOT: 5 } }]);
  assert.deepEqual(sacks.map((c) => c.label), ["TFL", "Hurries", "Tkl", "Solo"]);
  const punting = labels.boardDetail({ id: "punting:YPP", category: "punting" }, [{ detail: { "In 20": 3, LONG: 50, NO: 9, TB: 1, YDS: 400 } }]);
  assert.deepEqual(punting.map((c) => c.label), ["No.", "Yds", "Inside 20", "Touchbacks", "Long"]);
  // an unknown board keeps the old behaviour: the first four keys under their own names
  const unknown = labels.boardDetail({ id: "mystery:X" }, [{ detail: { b: 1, a: 2, c: 3, d: 4, e: 5 } }, null, "junk", { detail: null }]);
  assert.deepEqual(unknown.map((c) => c.label), ["b", "a", "c", "d"]);
  // the server's own columns win
  assert.deepEqual(labels.boardDetail({ id: "ppa:all", detailColumns: [{ key: "plays", label: "Plays", format: "0f" }, null, { key: 3 }] }, []).map((c) => c.label), ["Plays"]);
  for (const bad of JUNK) {
    assert.ok(Array.isArray(labels.boardDetail(bad, bad)));
    assert.ok(Array.isArray(labels.categoryColumns(bad, bad)));
    assert.equal(typeof labels.statLabel(bad), "string");
    assert.equal(typeof labels.plainChip(bad), "string");
  }
  assert.deepEqual(labels.categoryColumns("passing", ["ATT", "COMPLETIONS", "INT", "PCT", "TD", "YDS", "YPA"]).map((c) => c.label), ["Cmp", "Att", "Comp %", "Yds", "Y/A", "TD", "INT"]);
  assert.equal(labels.statLabel("PCT", "kicking"), "FG %");
  assert.equal(labels.normalizeStat("PCT", 100), 1);
  assert.equal(labels.normalizeStat("PCT", 0.7), 0.7);
  assert.equal(labels.plainChip("64 ATT"), "64 Att");
  assert.equal(labels.plainChip("3 QB HUR"), "3 Hurries");
  assert.equal(labels.plainChip("721 passing yards"), "721 passing yards");
  assert.equal(labels.categoryTitle("defensive"), "Defense");
  assert.equal(labels.categoryTitle(""), "Stats");
  assert.equal(labels.trendKey("defensive").key, "TOT");
  assert.equal(labels.trendKey("kicking"), null);
  // the route arg of Leaders
  const { parseLeadersArg } = await import(moduleUrl("views/leaders.js"));
  assert.deepEqual(parseLeadersArg("passing:YDS:national"), { board: "passing:YDS", scope: "national" });
  assert.deepEqual(parseLeadersArg("ppa:all:conference"), { board: "ppa:all", scope: "conference" });
  assert.deepEqual(parseLeadersArg("national:passing-YDS"), { board: "passing:YDS", scope: "national" });
  assert.deepEqual(parseLeadersArg("board:wepa:passing:conf"), { board: "wepa:passing", scope: "conference" });
  assert.deepEqual(parseLeadersArg("team"), { board: null, scope: "team" });
  for (const bad of JUNK) assert.deepEqual(parseLeadersArg(bad).scope ?? null, parseLeadersArg(bad).scope ?? null);
  const { parseRecruitingArg } = await import(moduleUrl("views/recruiting.js"));
  assert.deepEqual(parseRecruitingArg("national"), { year: null, part: "national" });
  assert.deepEqual(parseRecruitingArg("2027:where"), { year: 2027, part: "where" });
  assert.deepEqual(parseRecruitingArg(null), { year: null, part: null });
};

scenarios.leadersChips = async () => {
  route("/api/season/leaders", () => envelope(leadersData()));
  const players = [];
  route("/api/players/", (url) => { players.push(url); return envelope(playerData()); });
  localStorage.setItem("leaders:scope", JSON.stringify("team"));
  const { createLeadersView } = await import(moduleUrl("views/leaders.js"));
  const { main } = await mountView(createLeadersView);
  const band = main.querySelector("#leaders-passing-YDS");
  assert.ok(band, "the passing band");
  clean("leaders", main);
  // wave 3 (owner 2026-10-10): the board sizes itself; each rank has its own column (rule 3), the position its own column
  // at large and medium (decision 1), each board's details by the smallest size that still shows them
  const wrap = band.querySelector(".stat-table-wrap");
  assert.equal(wrap.dataset.size, "large");
  const ths = band.querySelectorAll("thead th");
  const marks = (list) => list.map((th) => (th.className.includes("st__min-large") ? "L" : th.className.includes("st__min-medium") ? "M" : ""));
  assert.deepEqual(ths.map((th) => th.dataset.term), ["#", "Player", "Pos", "Yds", "FBS rank", "Conf rank", "Cmp", "Att", "Y/A", "TD", "INT"]);
  assert.deepEqual(marks(ths), ["", "", "M", "", "M", "L", "L", "M", "M", "", ""], "the phone keeps the value, TD and INT");
  assert.equal(ths[4].querySelector(".sz-t--mid").textContent, "FBS");
  const first = band.querySelector("tbody tr").querySelectorAll("td");
  assert.ok(first[1].querySelector(".sz-t--long .leader-who .face, .sz-t--long .leader-who img, .sz-t--long .leader-who span"), "the face and name at large and medium");
  assert.deepEqual(["full", "initial", "last"].map((f) => pnText(first[1].querySelector(".sz-t--short"), f)), ["Mason Hamilton", "M. Hamilton", "Hamilton"], "item 6: the name alone at small, stepping down with the table");
  assert.deepEqual(["full", "initial"].map((f) => pnText(first[1].querySelector(".sz-t--long .leader-who__name"), f)), ["Mason Hamilton", "M. Hamilton"], "beside the face too");
  assert.ok(first[1].className.includes("st__person") && band.querySelector(".stat-table-wrap").dataset.pn === "full", "a person column; full names at large");
  assert.equal(first[1].querySelector("small"), null, "no position drawn under the name");
  assert.equal(text(first[2]), "QB");
  assert.equal(first[3].querySelector(".rank-chip"), null, "the value stands alone");
  assert.equal(text(first[3]), "721");
  assert.equal(first[4].querySelector("a.rank-chip--link").getAttribute("aria-label"), "Mason Hamilton: 47 of 358. Open the national list");
  // the national chip and the SEC chip open their lists; the summary carries a linked chip
  const chips = band.querySelectorAll("tbody a.rank-chip--link");
  assert.ok(chips.length >= 4, `linked chips in the rows (${chips.length})`);
  const hrefs = chips.map((a) => a.getAttribute("href"));
  assert.ok(hrefs.includes("#national=board%3Apassing%3AYDS?team=Florida"), hrefs.join(" "));
  assert.ok(hrefs.includes("#national=board%3Apassing%3AYDS?team=Florida&scope=conference"), hrefs.join(" "));
  const summary = band.querySelector(".band__summary a.rank-chip--link");
  assert.ok(summary, "the summary chip is a link");
  assert.equal(text(summary), "#47");
  // a chip inside a tappable row takes the tap: no player card, no player fetch
  const taken = [];
  document.addEventListener("kickoff:rank-link", (e) => { taken.push(e.detail.href); e.preventDefault(); });
  click(chips[0]);
  await settle();
  assert.equal(players.length, 0, "a chip tap never opens the card");
  assert.equal(document.body.querySelector(".card-layer"), null);
  assert.equal(taken.length, 1);
  // the row itself still opens the card
  click(band.querySelector("tbody tr td"));
  await settle();
  assert.equal(players.length, 1);
  assert.ok(document.body.querySelector(".card-layer"));
  // a usage board has no lists: its chips stay plain, never an anchor to nowhere, and it has no rank columns
  const usage = main.querySelector("#leaders-usage-overall");
  assert.equal(usage.querySelectorAll("a.rank-chip--link").length, 0);
  assert.deepEqual(usage.querySelectorAll("thead th").map((th) => th.dataset.term), ["#", "Player", "Pos", "Usage", "Pass"]);
  // the play value board's head says PPA per play in its three forms
  const { boardDetail } = await import(moduleUrl("ui/stat-labels.js"));
  assert.deepEqual(boardDetail({ id: "ppa:all", detailColumns: [{ key: "plays", label: "Plays" }, { key: "pass", label: "Pass" }, { key: "rush", label: "Rush" }] }, []).map((c) => c.size), [null, "medium", "medium"]);
  assert.deepEqual(boardDetail({ id: "punting:YPP", category: "punting" }, [{ detail: { "In 20": 3, LONG: 50, NO: 9, TB: 1, YDS: 400 } }]).map((c) => [c.label, c.labelShort, c.size]), [["No.", null, null], ["Yds", null, "large"], ["Inside 20", "In 20", "medium"], ["Touchbacks", "TB", "large"], ["Long", null, "medium"]]);
};

scenarios.leadersArrival = async () => {
  await useTeam();
  clearCache();
  route("/api/season/leaders", () => envelope(leadersData()));
  localStorage.setItem("leaders:scope", JSON.stringify("team"));
  const { createLeadersView } = await import(moduleUrl("views/leaders.js"));
  const { main } = await mountView(createLeadersView, { arg: "passing:YDS:national" });
  const pressed = main.querySelector('.leaders__scope button[aria-pressed="true"]');
  assert.equal(text(pressed), "National top 10");
  assert.equal(localStorage.getItem("leaders:scope"), JSON.stringify("team"), "a link arrival never overwrites the remembered scope");
  const band = main.querySelector("#leaders-passing-YDS");
  assert.ok(band.scrolledInto, "the board scrolls into view");
  assert.ok(band.className.includes("flash"));
  // a board with no league lists shows its team table when a link asks for a league scope
  const usage = await mountView(createLeadersView, { arg: "usage:overall:national" });
  assert.ok(usage.main.querySelector("#leaders-usage-overall tbody tr td"), "usage falls back to the team table");
  // only a tap on the switch is remembered
  const conf = [...main.querySelectorAll(".leaders__scope button")].find((b) => text(b) === "SEC top 10");
  click(conf);
  assert.equal(localStorage.getItem("leaders:scope"), JSON.stringify("conference"));
};

scenarios.leadersGrades = async () => {
  // post-freeze Wave 1 (tester report 2026-10-24): a position chip keeps the table on screen until the new group is in,
  // so the page never grows shorter under the reader and jumps up
  await useTeam();
  clearCache();
  route("/api/season/leaders", () => envelope(leadersData()));
  const graded = (group, names) => envelope({ group, groupName: group === "QB" ? "quarterbacks" : "defensive backs", of: 140, basis: "efficiency", rows: names.map((name, i) => ({ playerId: `${group}${i}`, name, position: group, team: "Texas State", teamAbbr: "DT", grade: 90 - i, rank: i + 1, of: 140 })), beyond: [] });
  let release = null;
  route("/api/grades", (url) => (String(url).includes("group=DB")
    ? new Promise((resolve) => { release = () => resolve(graded("DB", ["Ball Hawk", "Cover Man"])); })
    : graded("QB", ["Avery Passer", "Diner Arm", "Late Bloomer"])));
  localStorage.setItem("leaders:gradeGroup", JSON.stringify("QB"));
  const { createLeadersView } = await import(moduleUrl("views/leaders.js"));
  const { main } = await mountView(createLeadersView);
  const grades = () => main.querySelector("#leaders-grades");
  assert.ok(text(grades()).includes("Avery Passer"), "the QB table");
  const db = [...grades().querySelectorAll(".seg button")].find((b) => text(b) === "DB");
  click(db);
  await settle();
  assert.ok(text(grades()).includes("Avery Passer"), "the QB table stays while the DB grades load");
  assert.equal(grades().querySelector(".skel"), null, "no loading rows in its place");
  assert.equal(grades().querySelector('.seg button[aria-pressed="true"]').textContent, "DB", "the tapped chip is pressed at once");
  assert.ok(grades().querySelector(".leaders-grades--pending")?.getAttribute("aria-busy") === "true", "the old table is marked as waiting");
  assert.ok(text(grades().querySelector(".band__summary")).includes("Getting the DB grades"));
  release();
  await settle();
  assert.ok(text(grades()).includes("Ball Hawk") && !text(grades()).includes("Avery Passer"), "the DB table replaces it once in");
  assert.equal(grades().querySelector(".leaders-grades--pending"), null);
  clean("grades", main);
};

scenarios.leadersOtherGroup = async () => {
  // a remembered group that is not one of ours (OL) opens the board on QB
  await useTeam();
  clearCache();
  route("/api/season/leaders", () => envelope(leadersData()));
  const asked = [];
  route("/api/grades", (url) => { asked.push(String(url)); return envelope({ group: "QB", groupName: "quarterbacks", of: 140, basis: "efficiency", rows: [{ playerId: "q1", name: "Avery Passer", position: "QB", team: "Texas State", teamAbbr: "DT", grade: 88, rank: 1, of: 140 }], beyond: [] }); });
  localStorage.setItem("leaders:gradeGroup", JSON.stringify("OL"));
  const { createLeadersView } = await import(moduleUrl("views/leaders.js"));
  const { main } = await mountView(createLeadersView);
  const grades = main.querySelector("#leaders-grades");
  assert.ok(text(grades).includes("Avery Passer"), "our stat grades");
  assert.deepEqual(asked.map((u) => u.split("?")[1].split("&")[0]), ["group=QB"], "OL is not one of ours: the board opens on QB");
  assert.ok(!grades.querySelectorAll(".seg button").some((b) => text(b) === "OL"));
  clean("our grades", main);
};

scenarios.leadersGap = async () => {
  await useTeam();
  clearCache();
  route("/api/season/leaders", () => envelope(leadersData()));
  localStorage.setItem("leaders:scope", JSON.stringify("national"));
  const { createLeadersView, windowRows } = await import(moduleUrl("views/leaders.js"));
  const { main } = await mountView(createLeadersView);
  const table = main.querySelector("#leaders-passing-YDS table");
  const bodies = table.querySelectorAll("tbody");
  assert.equal(bodies.length, 2, "the Gators below the cut have their own tbody");
  assert.equal(bodies[0].querySelectorAll("tr").length, 10, "the top 10 alone in the first");
  assert.equal(bodies[0].querySelectorAll("tr.is-window").length, 0);
  const tail = bodies[1].querySelectorAll("tr");
  assert.ok(tail[0].className.includes("gap-row"), "the gap row leads the second tbody");
  assert.equal(text(tail[0]), "⋯", "ENH-8: no sentence repeating what the marked rows show");
  assert.equal(tail[0].querySelector("td").getAttribute("aria-label"), "Below the top 10", "its meaning for a screen reader");
  assert.equal(tail.length, 3, "gap row plus both Gators");
  assert.ok(tail[1].className.includes("is-us"));
  // wave 3 (decision 2): the list's own order is its chip at large and medium, a plain number at small
  const place = tail[1].querySelector("td");
  assert.equal(place.querySelector(".sz-t--short").textContent, "47");
  assert.equal(place.querySelector(".sz-t--long a.rank-chip--link").getAttribute("href"), "#national=board%3Apassing%3AYDS?team=Florida");
  assert.equal(tail[0].querySelector("td").getAttribute("colspan"), "10", "the gap row spans every column the table draws");
  // decision 1: the position and the team in columns of their own at large and medium, gone at small; the national list's
  // # is the FBS rank, so it has no second rank column
  const ths = table.querySelectorAll("thead th");
  assert.deepEqual(ths.map((th) => th.dataset.term), ["#", "Player", "Pos", "Team", "Yds", "Cmp", "Att", "Y/A", "TD", "INT"]);
  assert.deepEqual(ths.map((th) => (th.className.includes("st__min-large") ? "L" : th.className.includes("st__min-medium") ? "M" : "")), ["", "", "M", "M", "", "L", "M", "M", "", ""]);
  const row = bodies[0].querySelector("tr").querySelectorAll("td");
  assert.equal(row[3].querySelector("button.team-link").dataset.team, "USC");
  assert.deepEqual(["full", "initial", "last"].map((f) => pnText(row[1], f)), ["National 0", "N. 0", "0"], "item 6: the name steps down with the table");
  assert.equal(row[1].querySelector("small"), null, "nothing drawn under the name");
  // the conference top 10 gains each player's FBS rank from medium (owner 2026-10-10)
  localStorage.setItem("leaders:scope", JSON.stringify("conference"));
  const confView = await mountView(createLeadersView);
  const cths = confView.main.querySelectorAll("#leaders-passing-YDS thead th");
  assert.deepEqual(cths.map((th) => th.dataset.term).slice(0, 6), ["#", "Player", "Pos", "Team", "Yds", "FBS rank"]);
  assert.ok(cths[5].className.includes("st__min-medium"));
  const cfirst = confView.main.querySelector("#leaders-passing-YDS tbody tr").querySelectorAll("td");
  assert.equal(cfirst[0].querySelector("a.rank-chip--link").getAttribute("href"), "#national=board%3Apassing%3AYDS?team=Fresno%20State&scope=conference", "a conference place opens the conference list");
  assert.equal(cfirst[5].querySelector("a.rank-chip--link").getAttribute("href"), "#national=board%3Apassing%3AYDS?team=Fresno%20State");
  clean("conference scope", confView.main);
  localStorage.setItem("leaders:scope", JSON.stringify("national"));
  // the next opponent is marked in the league list
  assert.equal(bodies[0].querySelectorAll("tr.is-opp").length, 1);
  // a sort keeps the split
  click(table.querySelectorAll("thead th")[2].querySelector("button"));
  const again = main.querySelector("#leaders-passing-YDS table").querySelectorAll("tbody");
  assert.equal(again.length, 2);
  assert.equal(again[0].querySelectorAll("tr.is-window").length, 0, "no Mudpuppy window row leaks into the top list after a sort");
  assert.ok(again[1].querySelector("tr").className.includes("gap-row"));
  clean("national scope", main);
  // junk boards never throw
  for (const bad of JUNK) assert.deepEqual(windowRows(bad, "national"), []);
  // vs opponent (wave 3, rule 9): the two-team kit centered on the tug bar, each side's player outermost, his position,
  // FBS rank and conference rank in columns of their own, the place in the middle
  localStorage.setItem("leaders:scope", JSON.stringify("opponent"));
  const players = [];
  route("/api/players/", (url) => { players.push(url); return envelope(playerData()); });
  const vs = await mountView(createLeadersView);
  const vband = vs.main.querySelector("#leaders-passing-YDS");
  const tt = vband.querySelector("table.tt");
  assert.ok(tt && tt.className.includes("tt--centered") && tt.className.includes("tt--tug"), "the two-team kit with the tug bar");
  const long = (th) => th.querySelector(".tt__t--long")?.textContent ?? text(th);
  const mid = (th) => th.querySelector(".tt__t--mid")?.textContent ?? text(th);
  assert.deepEqual(tt.querySelectorAll("thead tr.tt__head--a th.tt__team").map(long), ["Florida Gators", "Fresno State Miners"], "school and mascot over each side at large");
  assert.deepEqual(tt.querySelectorAll("thead tr.tt__head--b th").map(text), ["Player", "Pos", "FBS rank", "SEC rank", "", "", "SEC rank", "FBS rank", "Pos", "Player"]);
  assert.deepEqual(tt.querySelectorAll("thead tr.tt__head--one th").map(mid), ["Player", "Pos", "FBS", "Florida", "#", "Fresno State", "FBS", "Pos", "Player"]);
  const [one, two] = tt.querySelectorAll("tbody tr");
  const cells = one.querySelectorAll("td");
  assert.equal(cells.length, 11);
  assert.equal(pnText(cells[0].querySelector("button.tt__who-btn .tt__t--short"), "last"), "Hamilton", "item 6: the name alone at small (whoName), stepping down");
  assert.ok(cells[0].querySelector("button.tt__who-btn .leader-who"), "the face and name at large and medium");
  assert.deepEqual([text(cells[1]), text(cells[9])], ["QB", "QB"]);
  assert.ok(cells[1].className.includes("tt__min-medium"), "the position from medium");
  assert.equal(cells[2].querySelector("a.rank-chip--link").getAttribute("href"), "#national=board%3Apassing%3AYDS?team=Florida");
  assert.equal(cells[3].querySelector("a.rank-chip--link").getAttribute("href"), "#national=board%3Apassing%3AYDS?team=Florida&scope=conference");
  assert.equal(cells[8].querySelector("a.rank-chip--link").getAttribute("href"), "#national=board%3Apassing%3AYDS?team=Fresno%20State");
  assert.deepEqual([text(cells[4]), text(cells[6])], ["721", "753"]);
  assert.ok(cells[6].className.includes("lead") && cells[4].className.includes("trail"), "the bigger number leads");
  assert.ok(!cells[5].querySelector(".tug") && cells[5].className.includes("tt__mid--plain"), "ENH-34 (owner 2026-10-27): no bar under the place; the bold number says who leads");
  assert.equal(text(cells[5].querySelector(".tt__mid-words")), "1", "the place in the middle");
  assert.deepEqual(["full", "initial", "last"].map((f) => pnText(cells[10].querySelector(".tt__t--short"), f)), ["Byron Brooks", "B. Brooks", "Brooks"]);
  const theirs = two.querySelectorAll("td");
  assert.deepEqual([text(theirs[6]), text(theirs[10])], ["–", "–"], "no opponent at that place: dashes");
  cells[0].querySelector("button.tt__who-btn").click();
  await settle();
  assert.equal(players.length, 1, "the name opens the player card");
  clean("vs opponent", vs.main);
};

scenarios.leadersVersusPpa = async () => {
  // wave 3 review: a PPA board's vs table leans by the gap on the PPA scale when a side has no national rank (a backup
  // under the national cut), never by the two values' share, which made +0.05 against -0.03 the whole bar
  await useTeam();
  clearCache();
  const data = leadersData();
  data.boards = [{
    id: "ppa:all", metric: "board:ppa:all", category: "ppa", stat: "all", label: "PPA per play", format: "+2f",
    team: [entry({ playerId: "v1", metric: "board:ppa:all", value: 0.05, nationalRank: null, conferenceRank: null, detail: {} })],
    opponent: [entry({ playerId: "v2", player: "Byron Brooks", team: "Fresno State", teamAbbr: "FRES", isUs: false, metric: "board:ppa:all", value: -0.03, nationalRank: null, conferenceRank: null, detail: {} })],
    conference: [], national: [], conferenceOf: null, nationalOf: null, usBest: { conferenceRank: null, nationalRank: null },
  }];
  data.extraBoards = [];
  route("/api/season/leaders", () => envelope(data));
  localStorage.setItem("leaders:scope", JSON.stringify("opponent"));
  const { createLeadersView } = await import(moduleUrl("views/leaders.js"));
  const vs = await mountView(createLeadersView);
  // ENH-34 (owner 2026-10-27): the vs table has no bar now; the leader is the bold number (the PPA scale still sizes the
  // bars of the program's tables)
  const [ours, theirs] = [...vs.main.querySelectorAll("table.tt tbody td.tt__us, table.tt tbody td.tt__them")].filter((td) => td.className.includes("tt__cell"));
  assert.ok(ours && ours.className.includes("lead") && theirs.className.includes("trail"), "ours leads: +0.05 against -0.03");
  assert.equal(vs.main.querySelectorAll("table.tt .tug").length, 0);
  localStorage.setItem("leaders:scope", JSON.stringify("national"));
  clean("vs opponent, PPA", vs.main);
};

scenarios.rosterTable = async () => {
  clearCache();
  let version = 0;
  route("/api/roster", () => { version += 1; return envelope({ ...rosterData(), asked: version }); }); // each answer new, so a refresh rebuilds (the poller keeps a page whose data did not change)
  const { createRosterView } = await import(moduleUrl("views/roster.js"));
  const { main, view } = await mountView(createRosterView);
  const band = main.querySelector("#roster-table");
  const select = band.querySelector("select");
  assert.ok(select, "a position select");
  assert.ok(!select.className.includes("depth-card__sort"), "not the depth card's hidden select");
  assert.ok(select.className.includes("setting__select"), "styled like the settings selects (visible, 44 px)");
  assert.equal(band.querySelector(".band__head select"), null, "not in the band head");
  assert.ok(band.querySelector(".band__body select"));
  assert.equal(text(band.querySelector(".roster-filter__label")), "Position");
  const wrap = band.querySelector(".stat-table-wrap");
  assert.ok(!wrap.className.includes("--box"), "every player on the page, never a scroll box (owner 2026-10-10)");
  // sized by its own box (owner 2026-10-10, "size them now"): the phone keeps number, name, position and class
  assert.equal(wrap.dataset.size, "large");
  const heads = band.querySelectorAll("thead th");
  const head = (word) => heads.find((th) => text(th).includes(word));
  assert.ok(head("Hometown").className.includes("st__min-large"), "hometown only at large");
  assert.ok(head("Grade").className.includes("st__min-medium"), "the grade from medium");
  assert.ok(!head("Pos").className.includes("st__min"), "the position at every size");
  assert.equal(wrap.style["--table-max"], undefined);
  assert.ok(band.className.includes("band--foldable"), "the band folds instead");
  // wave 3 review: the height sorts, by inches (6-10 is taller than 6-2)
  const ht = band.querySelectorAll("thead th").find((th) => text(th) === "Ht");
  assert.ok(ht && ht.querySelector("button"), "the Ht head is a sort button");
  // sort by weight, then refresh: the sort stays
  const wt = band.querySelectorAll("thead th").find((th) => text(th) === "Wt");
  click(wt.querySelector("button"));
  assert.equal(band.querySelectorAll("thead th").find((th) => text(th) === "Wt").getAttribute("aria-sort"), "descending");
  view.refresh(); // 1.40.3 (owner 2026-11-14): manual refresh only, never a timer; Refresh beside the status pill does this
  await settle();
  assert.ok(version >= 2, "refreshed");
  const band2 = main.querySelector("#roster-table");
  assert.notEqual(band2, band, "the page was rebuilt");
  assert.equal(band2.querySelectorAll("thead th").find((th) => text(th) === "Wt").getAttribute("aria-sort"), "descending", "the sort survived the refresh");
  // and a position change keeps it too
  const sel2 = band2.querySelector("select");
  sel2.value = "OL";
  sel2.dispatchEvent(makeEvent("change", { bubbles: true }));
  assert.equal(band2.querySelectorAll("thead th").find((th) => text(th) === "Wt").getAttribute("aria-sort"), "descending");
  assert.equal(band2.querySelectorAll("tbody tr").length, 2);
  // stars as 4-star, the recruit rank a chip (a link once the row carries its list key)
  const cells = band2.querySelectorAll("tbody tr")[0].querySelectorAll("td").map((td) => text(td));
  assert.ok(cells.includes("4-star"), cells.join("|"));
  assert.ok(band2.querySelector('tbody a.rank-chip--link[href="#national=recruit%3A2024"]'), "the recruit chip links once recruitMetric is there");
  // impact chips read plain labels; sub-headings are the DS-14 subhead
  const impact = main.querySelector("#roster-impact");
  assert.ok(text(impact).includes("64 Att") && text(impact).includes("3 Hurries"), text(impact));
  assert.equal(impact.querySelectorAll("h3.subhead").length, 2);
  clean("roster", main);
};

scenarios.cardLoading = async () => {
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    if (String(url).startsWith("/api/players/")) {
      await pending;
      return { ok: true, status: 200, json: async () => ({ data: playerData(), errors: [], meta: {} }) };
    }
    return realFetch(url);
  };
  const { openPlayer } = await import(moduleUrl("views/player.js"));
  document.body.replaceChildren();
  const opened = openPlayer("p9", { name: "Darnell Brooks III", number: 1, position: "WR", team: "Florida", isUs: true });
  await settle();
  const card = document.body.querySelector(".player-card");
  assert.ok(card, "the loading card is up");
  const loadingText = clean("loading card", card);
  for (const sentence of ["No season stats yet", "Game log appears", "No roster history", "No play value"]) assert.ok(!loadingText.includes(sentence), `the loading card says "${sentence}"`);
  assert.ok(loadingText.includes("#1 Darnell Brooks III"));
  assert.ok(card.className.includes("is-loading"));
  assert.equal(card.querySelectorAll(".number-badge--them").length, 0, "a Florida player is not them");
  assert.ok(card.querySelector(".player-card__hero--us"));
  assert.ok(card.querySelector(".skel-table"), "skeleton bars");
  // a Florida row without isUs (older rows) is not them either
  const other = await import(moduleUrl("ui/player-card.js"));
  // the answer fills the same card in place: one layer, the same article, the tab kept
  const tabs = card.querySelectorAll(".player-card__tabs button");
  click(tabs[1]);
  release();
  const close = await opened;
  await settle();
  assert.equal(document.body.querySelectorAll(".card-layer").length, 1);
  assert.equal(document.body.querySelector(".player-card"), card, "updated in place");
  assert.ok(!card.className.includes("is-loading"));
  assert.equal(text(card.querySelector('.player-card__tabs [aria-selected="true"]')), "Game log", "the tab the reader picked stays");
  const full = clean("loaded card", card);
  assert.ok(full.includes("Recruit rating 94 · #123 nationally"), "star line: both recruiting numbers labelled (Phase 17)");
  assert.ok(full.includes("2024 class, as ATH"), "the Recruit fact is cut to class and position");
  assert.ok(card.querySelector('.player-card__bio button.team-link[data-team="Florida"]'), "the team in the bio line links");
  assert.ok(card.querySelector('.player-card__facts button.team-link[data-team="Georgia Tech"]'), "the transfer school links");
  assert.ok(card.querySelector('[aria-label="History"] button.team-link'), "History's team links");
  close();
  assert.equal(document.body.querySelector(".card-layer"), null);
  assert.equal(close.update({ player: { name: "Late" } }), false, "an answer after close never reopens the card");
  globalThis.fetch = realFetch;
  assert.ok(other.cardHeading("X").className.includes("player-card__h"));
};

// The player card's patience (owner 2026-11-15, Grant Godfrey's card gave up at 15 s while the server fetched Kentucky's
// numbers game by game). A scripted /api/players/ (and /slow/) that honours the request's signal as a browser's fetch does:
// "hang" waits until the signal aborts, then rejects with its reason; an answer object answers at once; a function picks one
// per call. Every call is kept with its signal.
function playerServer() {
  const server = { calls: [], answer: "hang" };
  const realFetch = globalThis.fetch;
  globalThis.fetch = (url, opts = {}) => {
    const u = String(url);
    if (!u.startsWith("/api/players/") && !u.startsWith("/slow/")) return realFetch(url, opts);
    const signal = opts && opts.signal ? opts.signal : null;
    server.calls.push({ url: u, signal });
    return new Promise((resolve, reject) => {
      const abort = () => reject(signal.reason ?? new DOMException("The operation was aborted.", "AbortError"));
      if (signal && signal.aborted) return abort();
      if (signal) signal.addEventListener("abort", abort, { once: true });
      const answer = typeof server.answer === "function" ? server.answer(u) : server.answer;
      if (answer === "hang") return;
      if (signal) signal.removeEventListener("abort", abort);
      if (answer instanceof Error) return reject(answer);
      resolve({ ok: answer.status >= 200 && answer.status < 300, status: answer.status, json: async () => answer.body });
    });
  };
  server.restore = () => { globalThis.fetch = realFetch; };
  return server;
}
const answered = (data) => ({ status: 200, body: { data, errors: [], meta: {} } });

scenarios.cardSlow = async () => {
  const { FETCH_TIMEOUT_MS, SLOW_TRIES } = await import(moduleUrl("views/common.js"));
  const { openPlayer, slowWords } = await import(moduleUrl("views/player.js"));
  const server = playerServer();
  document.body.replaceChildren();
  const row = { name: "Grant Godfrey", number: 22, position: "WR", team: "Kentucky", isUs: false };
  const opened = openPlayer("4870001", row);
  await settle();
  const card = document.body.querySelector(".player-card");
  assert.ok(card && card.className.includes("is-loading"), "the loading card is up");
  assert.equal(server.calls.length, 1);
  assert.ok(server.calls[0].url.endsWith("/api/players/4870001?team=Kentucky"), server.calls[0].url);
  assert.ok(!text(card).includes("Still gathering"), "no slow words before the first round runs out");
  // the old card gave up at 15 s: this one is still waiting on the same request
  await advance(15000);
  assert.ok(card.className.includes("is-loading"), "still loading at 15 s");
  assert.equal(server.calls.length, 1);
  assert.ok(!server.calls[0].signal.aborted);
  await advance(FETCH_TIMEOUT_MS - 15000);
  assert.equal(server.calls.length, 2, "asked again when the first round ran out");
  assert.ok(server.calls[0].signal.aborted, "the first round's request was let go");
  assert.equal(document.body.querySelector(".player-card"), card, "the same card");
  assert.ok(card.className.includes("is-loading"));
  const waiting = clean("slow card", card);
  assert.ok(waiting.includes(slowWords(row).waiting), waiting);
  assert.ok(waiting.includes("Still gathering Kentucky's numbers from CFBD."), waiting);
  assert.ok(card.querySelector(".skel-table"), "the skeleton stays under the words");
  for (const sentence of ["No season stats yet", "Game log appears", "No roster history", "aborted"]) assert.ok(!waiting.includes(sentence), `the slow card says "${sentence}"`);
  // the rest of the rounds: SLOW_TRIES in all, then the time-out in plain words
  await advance(FETCH_TIMEOUT_MS * (SLOW_TRIES - 2));
  assert.equal(server.calls.length, SLOW_TRIES, "every round asked");
  assert.ok(card.className.includes("is-loading"), "still waiting in the last round");
  await advance(FETCH_TIMEOUT_MS);
  const close = await opened;
  assert.equal(server.calls.length, SLOW_TRIES, "no round past SLOW_TRIES");
  assert.equal(document.body.querySelector(".player-card"), card, "the same card says it");
  assert.ok(!card.className.includes("is-loading"));
  const failed = clean("timed-out card", card);
  assert.equal(text(card.querySelector(".state-block__lead")), "Kentucky's numbers are still coming in from CFBD.");
  assert.equal(text(card.querySelector(".state-block__detail")), "The server keeps working on them, so another try is usually quick.");
  assert.ok(card.querySelector(".state-block--error"));
  assert.ok(!/\.\s*\./.test(failed), `a doubled period: ${failed}`);
  for (const word of ["aborted", "Value", "Still gathering", "No season stats yet", "Game log appears"]) assert.ok(!failed.includes(word), `the timed-out card says "${word}"`);
  assert.equal(card.querySelector(".player-card__tabs"), null, "no empty tabs that read as fact");
  assert.equal(card.querySelector(".player-card__facts"), null, "no rows of dashes for facts it never had");
  assert.ok(failed.includes("#22 Grant Godfrey"), "the face and the name stay");
  assert.ok(card.querySelector(".player-card__hero--them"), "Kentucky's man is not ours");
  // nothing asks while the card waits on the reader
  await advance(FETCH_TIMEOUT_MS * 3);
  assert.equal(server.calls.length, SLOW_TRIES);
  // Try again asks again into the same card: loading first, then filled in place
  server.answer = "hang";
  const again = card.querySelector(".state-block__action");
  assert.equal(text(again), "Try again");
  click(again);
  await settle();
  assert.equal(server.calls.length, SLOW_TRIES + 1);
  assert.ok(card.className.includes("is-loading"), "Try again shows the loading card");
  assert.equal(card.querySelector(".state-block"), null);
  server.answer = answered(playerData());
  await advance(FETCH_TIMEOUT_MS);
  assert.equal(server.calls.length, SLOW_TRIES + 2, "the next round answers");
  assert.equal(document.body.querySelectorAll(".card-layer").length, 1, "one layer");
  assert.equal(document.body.querySelector(".player-card"), card, "filled in place");
  assert.ok(!card.className.includes("is-loading"));
  assert.ok(card.querySelector(".player-card__tabs"), "the tabs are back");
  const full = clean("filled after Try again", card);
  assert.ok(full.includes("Darnell Brooks III") && !full.includes("Still gathering"), full.slice(0, 200));
  close();
  assert.equal(document.body.querySelector(".card-layer"), null);
  server.restore();
};

scenarios.cardClose = async () => {
  const { FETCH_TIMEOUT_MS, SLOW_TRIES } = await import(moduleUrl("views/common.js"));
  const { openPlayer } = await import(moduleUrl("views/player.js"));
  const server = playerServer();
  document.body.replaceChildren();
  errors.length = 0;
  // closed in the first round, by its own close button
  const first = openPlayer("4870001", { name: "Grant Godfrey", team: "Kentucky", isUs: false });
  await settle();
  click(document.body.querySelector(".player-card__close"));
  await settle();
  assert.ok(server.calls[0].signal.aborted, "closing the card lets its request go");
  const close1 = await first; // settles quietly, never throws
  assert.equal(typeof close1, "function");
  await advance(FETCH_TIMEOUT_MS * SLOW_TRIES);
  assert.equal(server.calls.length, 1, "no round after the close");
  assert.equal(document.body.querySelector(".card-layer"), null, "no card comes back to say it failed");
  assert.equal(close1.update({ player: { name: "Late" } }), false);
  assert.ok(close1.signal && close1.signal.aborted, "the card's signal says it closed");
  // closed while it says it is still gathering, by the scrim
  const second = openPlayer("4870002", { name: "Other Man", team: "Kentucky", isUs: false });
  await settle();
  await advance(FETCH_TIMEOUT_MS);
  assert.equal(server.calls.length, 3);
  assert.ok(text(document.body.querySelector(".player-card")).includes("Still gathering Kentucky's numbers"));
  click(document.body.querySelector(".card-layer__scrim"));
  await settle();
  await second;
  assert.ok(server.calls[2].signal.aborted, "the round in flight is let go");
  await advance(FETCH_TIMEOUT_MS * SLOW_TRIES);
  assert.equal(server.calls.length, 3, "and no more rounds");
  assert.equal(document.body.querySelector(".card-layer"), null);
  // an answer that lands after the close never reopens it
  server.answer = () => answered(playerData());
  const third = openPlayer("4870003", { name: "Third Man", isUs: true });
  click(document.body.querySelector(".player-card__close"));
  await third;
  await settle();
  assert.equal(document.body.querySelector(".card-layer"), null, "the late answer stays out");
  assert.deepEqual(errors.filter((line) => /api\/players|slow-answer/.test(line)), [], "nothing logged as an error");
  server.restore();
};

scenarios.cardFallback = async () => {
  const { openPlayer, rowStats, whoseNumbers, slowWords } = await import(moduleUrl("views/player.js"));
  const server = playerServer();
  const message = "No card for this player: cards cover our team, the next opponent, and this season's players of an FBS team found by search.";
  server.answer = { status: 404, body: { data: null, errors: [{ message }], meta: {} } };
  const shown = () => document.body.querySelector(".player-card");
  const statsOf = () => shown().querySelector('[aria-label="Stats"]');
  const statRows = () => statsOf().querySelectorAll("tbody tr").map((tr) => text(tr)); // the rows, not the Stat | Value heads
  document.body.replaceChildren();
  // a board row with no value: no "Value –" row, only the real details
  let close = await openPlayer("4870001", { name: "Grant Godfrey", team: "Kentucky", isUs: false, category: "receiving", value: null, detail: { YDS: 120, TD: null, AVG: "NaN", REC: "", LONG: {} } });
  clean("short card, no value", statsOf());
  let rows = statRows();
  assert.equal(rows.length, 1, rows.join(" | "));
  assert.ok(rows[0].includes("120") && !rows[0].includes("Value"), rows[0]);
  assert.ok(clean("short card", shown()).includes("Full cards exist for our team and the next opponent only."));
  assert.equal(shown().querySelector(".state-block__action"), null, "a 404 has no Try again");
  close();
  // a real value keeps its row, under the board's own label when it has one
  close = await openPlayer("4870001", { name: "Grant Godfrey", team: "Kentucky", isUs: false, boardLabel: "PPA per play", value: "+0.31" });
  clean("short card, labelled", statsOf());
  rows = statRows();
  assert.equal(rows.length, 1, rows.join(" | "));
  assert.ok(rows[0].includes("PPA per play") && rows[0].includes("+0.31"), rows[0]);
  close();
  close = await openPlayer("4870001", { name: "Grant Godfrey", team: "Kentucky", isUs: false, value: 721 });
  clean("short card, value", statsOf());
  rows = statRows();
  assert.equal(rows.length, 1, rows.join(" | "));
  assert.ok(rows[0].includes("Value") && rows[0].includes("721"), rows[0]);
  close();
  // nothing real at all: the plain empty line, no table
  close = await openPlayer("4870001", { name: "Grant Godfrey", isUs: false, value: undefined, detail: { YDS: null } });
  assert.equal(statsOf().querySelector("tbody"), null);
  assert.ok(clean("short card, nothing", statsOf()).includes("No season stats yet."));
  close();
  // a 404 with no row: the server's own words with one period
  close = await openPlayer("4870001");
  assert.equal(text(shown().querySelector(".player-card__note")), message);
  close();
  // another failure: the block with the server's words, one period, and Try again
  server.answer = { status: 503, body: { data: null, errors: [{ message: "CFBD is not answering and nothing is cached yet. Timed out" }], meta: {} } };
  close = await openPlayer("4870001", { name: "Grant Godfrey", team: "Kentucky", isUs: false, value: 5 });
  assert.equal(text(shown().querySelector(".state-block__lead")), "Could not load the card.");
  assert.equal(text(shown().querySelector(".state-block__detail")), "CFBD is not answering and nothing is cached yet. Timed out.");
  assert.equal(text(shown().querySelector(".state-block__action")), "Try again");
  assert.equal(shown().querySelector(".player-card__tabs"), null);
  server.answer = answered(playerData());
  click(shown().querySelector(".state-block__action"));
  await settle();
  assert.ok(shown().querySelector(".player-card__tabs") && clean("after Try again", shown()).includes("Darnell Brooks III"));
  close();
  server.answer = { status: 500, body: { errors: [{ message: "Already a sentence." }] } };
  close = await openPlayer("4870001", { name: "Grant Godfrey" });
  assert.equal(text(shown().querySelector(".state-block__detail")), "Already a sentence.");
  close();
  server.answer = new TypeError("Failed to fetch"); // offline
  close = await openPlayer("4870001", { name: "Grant Godfrey" });
  assert.equal(text(shown().querySelector(".state-block__detail")), "Failed to fetch.");
  close();
  // damaged answers and rows never print undefined, null or NaN
  for (const bad of [null, {}, [], "junk", 7, ...JUNK]) {
    server.answer = answered(bad);
    close = await openPlayer("4870001", { name: bad, number: bad, team: bad, position: bad, isUs: false, value: bad, detail: bad });
    clean(`answer ${String(bad)}`, shown());
    close();
    server.answer = { status: 200, body: bad };
    close = await openPlayer("4870001", { name: "Grant Godfrey", team: bad, boardLabel: bad, value: bad, detail: { YDS: bad } });
    clean(`body ${String(bad)}`, shown());
    close();
  }
  for (const bad of JUNK) {
    assert.ok(Array.isArray(rowStats(bad)));
    for (const r of rowStats({ value: bad, boardLabel: bad, detail: { YDS: bad } })) assert.ok(!RAW.test(`${r.label} ${r.value}`), `${r.label} ${r.value}`);
    assert.ok(!RAW.test(whoseNumbers({ team: bad })), whoseNumbers({ team: bad }));
    const words = slowWords({ team: bad });
    assert.ok(!RAW.test(`${words.waiting} ${words.lead}`), words.lead);
  }
  assert.equal(whoseNumbers({ team: " Kentucky " }), "Kentucky's numbers");
  assert.equal(slowWords(null).lead, "This player's numbers are still coming in from CFBD.");
  assert.equal(slowWords({ team: "" }).waiting.startsWith("Still gathering this player's numbers from CFBD."), true);
  server.restore();
};

scenarios.patientRounds = async () => {
  const { fetchPatient, FETCH_TIMEOUT_MS, SLOW_TRIES } = await import(moduleUrl("views/common.js"));
  const server = playerServer();
  errors.length = 0;
  let caught = null;
  const catcher = (error) => { caught = error; };
  // without the new options, as the matchup and national sheets call it: a round a FETCH_TIMEOUT_MS, then the AbortError
  const three = fetchPatient("/slow/a", { tries: 3 }).catch(catcher);
  await settle();
  await advance(FETCH_TIMEOUT_MS * 2);
  assert.equal(server.calls.length, 3);
  assert.equal(caught, null, "still waiting in the last round");
  await advance(FETCH_TIMEOUT_MS);
  await three;
  assert.equal(caught?.name, "AbortError", "the sheets read an AbortError as no answer in time");
  assert.equal(server.calls.length, 3);
  server.calls.length = 0;
  caught = null;
  const every = fetchPatient("/slow/b").catch(catcher);
  await settle();
  await advance(FETCH_TIMEOUT_MS * SLOW_TRIES);
  await every;
  assert.equal(server.calls.length, SLOW_TRIES, "SLOW_TRIES rounds by default");
  assert.equal(caught?.name, "AbortError");
  // current() turning false drops the wait after the round
  server.calls.length = 0;
  caught = null;
  let live = true;
  const dropped = fetchPatient("/slow/c", { current: () => live }).catch(catcher);
  await settle();
  live = false;
  await advance(FETCH_TIMEOUT_MS * 2);
  await dropped;
  assert.equal(server.calls.length, 1);
  assert.equal(caught?.name, "AbortError");
  // an answer in a later round comes back, and onSlow heard the round that ran out
  server.calls.length = 0;
  server.answer = () => (server.calls.length >= 2 ? answered({ ok: 1 }) : "hang");
  const rounds = [];
  const later = fetchPatient("/slow/d", { onSlow: (round) => rounds.push(round) });
  await settle();
  await advance(FETCH_TIMEOUT_MS);
  assert.deepEqual((await later).data, { ok: 1 });
  assert.deepEqual(rounds, [1]);
  // a server error is not a slow round: thrown at once
  server.calls.length = 0;
  caught = null;
  server.answer = { status: 503, body: { errors: [{ message: "down" }] } };
  await fetchPatient("/slow/e", { onSlow: (round) => rounds.push(round) }).catch(catcher);
  assert.equal(caught?.status, 503);
  assert.equal(server.calls.length, 1);
  // a cancel is never a slow round: thrown at once, no onSlow, never asked again
  server.calls.length = 0;
  rounds.length = 0;
  caught = null;
  server.answer = "hang";
  const stop = new AbortController();
  const cancelled = fetchPatient("/slow/f", { signal: stop.signal, onSlow: (round) => rounds.push(round) }).catch(catcher);
  await settle();
  stop.abort();
  await cancelled;
  assert.equal(caught?.name, "AbortError");
  await advance(FETCH_TIMEOUT_MS * SLOW_TRIES);
  assert.equal(server.calls.length, 1);
  assert.deepEqual(rounds, []);
  // a signal already aborted: one request, let go at once
  caught = null;
  await fetchPatient("/slow/g", { signal: stop.signal }).catch(catcher);
  assert.equal(caught?.name, "AbortError");
  assert.equal(server.calls.length, 2);
  assert.ok(server.calls[1].signal.aborted);
  // an onSlow that throws is logged and the wait goes on
  server.calls.length = 0;
  server.answer = () => (server.calls.length >= 2 ? answered({ ok: 2 }) : "hang");
  const loud = fetchPatient("/slow/h", { onSlow: () => { throw new Error("boom"); } });
  await settle();
  await advance(FETCH_TIMEOUT_MS);
  assert.deepEqual((await loud).data, { ok: 2 });
  assert.ok(errors.some((line) => line.includes("/slow/h")), errors.join("\n"));
  server.restore();
};

scenarios.gameLog = async () => {
  const { cardPropsFrom, trendValues } = await import(moduleUrl("views/player.js"));
  const { playerCard } = await import(moduleUrl("ui/player-card.js"));
  const card = playerCard({ ...cardPropsFrom(playerData()), inline: true });
  const log = card.querySelector('[aria-label="Game log"]');
  const heads = log.querySelector("thead").querySelectorAll("th").map((th) => text(th));
  assert.deepEqual(heads.slice(0, 3), ["Wk", "Opp", "Result"]);
  const rows = log.querySelector("tbody").querySelectorAll("tr");
  assert.equal(rows.length, 3);
  for (const tr of rows) assert.ok(tr.querySelectorAll("td")[1].querySelector('.sz-t--long button.team-link') && tr.querySelectorAll("td")[1].querySelector('.sz-t--short button.team-link'), "each opponent cell is a team link at every size");
  const sized = (cell, which) => text(cell.querySelector(`.sz-t--${which}`));
  assert.equal(sized(rows[0].querySelectorAll("td")[1], "long"), "at Texas State", "the latest game is first");
  assert.equal(sized(rows[0].querySelectorAll("td")[1], "short"), "at DT", "the abbreviation at small, still a link");
  assert.equal(sized(rows[2].querySelectorAll("td")[1], "long"), "vs Florida Atlantic");
  assert.equal(sized(rows[1].querySelectorAll("td")[1], "short"), "vs Campbell", "no abbreviation: the school");
  assert.ok(rows[0].querySelector(".gl-result--l"));
  assert.ok(rows[2].querySelector(".gl-result--w"));
  // box-score PCT (100.0) reads 100%, not 10000%
  assert.ok(text(log).includes("100%") && !text(log).includes("10000"));
  // Play value: numbers as numbers, the by-game row with the right at/vs and the game log's abbreviation
  const pv = card.querySelector('[aria-label="Play value"]');
  assert.ok(pv.querySelectorAll("tbody td:not(.txt)").length > 0, "numeric cells");
  assert.ok(text(pv).includes("at Texas State") && text(pv).includes("at DT"));
  // the Stats-tab sparkline: three games, latest value labelled
  const stats = card.querySelector('[aria-label="Stats"]');
  assert.equal(stats.querySelectorAll("svg.spark").length, 1);
  assert.ok(text(stats.querySelector(".player-card__trend-val")).startsWith("117"));
  assert.deepEqual(trendValues(playerData().gameLog, "receiving"), [50, 80, 117]);
  assert.deepEqual(trendValues(playerData().gameLog, "kicking"), []);
  // fewer than two games: no sparkline, the heading alone
  const one = playerData();
  one.gameLog = one.gameLog.slice(0, 1);
  const single = playerCard({ ...cardPropsFrom(one), inline: true });
  assert.equal(single.querySelector('[aria-label="Stats"]').querySelectorAll("svg.spark").length, 0);
  assert.ok(single.querySelector('[aria-label="Stats"] .player-card__h'));
  const none = playerData();
  none.gameLog = [];
  assert.equal(playerCard({ ...cardPropsFrom(none), inline: true }).querySelectorAll("svg.spark").length, 0);
  // one heading style everywhere in the card
  assert.equal(card.querySelectorAll("h4.player-card__h").length, 0);
  assert.ok(card.querySelectorAll("h3.player-card__h").length >= 4);
  clean("card", card);
};

scenarios.cardSizes = async () => {
  // tables wave 3, step 5: every table on the card sizes itself by its own box
  const { cardPropsFrom, resultMargin } = await import(moduleUrl("views/player.js"));
  const { playerCard, careerRow } = await import(moduleUrl("ui/player-card.js"));
  const labels = await import(moduleUrl("ui/stat-labels.js"));
  const marks = (ths) => ths.map((th) => (th.className.includes("st__min-large") ? "L" : th.className.includes("st__min-medium") ? "M" : ""));
  const heads = (root) => [...root.querySelector("thead").querySelectorAll("th")];
  const sized = (cell, which) => { const t = cell.querySelector(`.sz-t--${which}`); return t ? text(t) : text(cell); };
  // one size map per category, shared by the seasons and the game log
  const passing = labels.categoryColumns("passing", ["ATT", "COMPLETIONS", "INT", "PCT", "TD", "YDS", "YPA", "QBR"]);
  assert.deepEqual(passing.map((c) => [c.label, c.size]), [["Cmp", "medium"], ["Att", null], ["Comp %", null], ["Yds", null], ["Y/A", null], ["TD", null], ["INT", null], ["QBR", "large"]]);
  // the game log has its own map: four stats beside the week and the opponent on a phone, the result and the same four at
  // medium, the rest at large
  const box = labels.categoryColumns("passing", ["AVG", "C/ATT", "INT", "QBR", "TD", "YDS"], { log: true });
  assert.deepEqual(box.map((c) => [c.label, c.size]), [["C/Att", null], ["Yds", null], ["Avg", "large"], ["TD", null], ["INT", null], ["QBR", "large"]], "the game log keeps C/Att, Yds, TD and INT on a phone");
  assert.deepEqual(labels.categoryColumns("passing", ["AVG", "QBR"]).map((c) => c.size), ["medium", "large"], "the seasons' own map without { log }");
  assert.deepEqual(labels.categoryColumns("defensive", ["PD", "QB HUR", "SACKS", "SOLO", "TD", "TFL", "TOT"], { log: true }).map((c) => [c.label, c.size]), [["Tkl", null], ["Solo", "large"], ["TFL", null], ["Sacks", null], ["Hurries", "large"], ["PD", "large"], ["TD", "large"]]);
  assert.deepEqual(labels.categoryColumns("punting", ["AVG", "In 20", "LONG", "NO", "TB", "YDS"], { log: true }).map((c) => [c.label, c.size]), [["No.", null], ["Yds", "large"], ["Avg", null], ["Inside 20", null], ["Touchbacks", "large"], ["Long", "large"]]);
  const punting = labels.categoryColumns("punting", ["In 20", "LONG", "NO", "TB", "YDS", "YPP"]);
  assert.deepEqual(punting.map((c) => [c.label, c.labelMid, c.labelShort, c.size]), [["No.", null, null, null], ["Yds", null, null, "medium"], ["Avg", null, null, null], ["Inside 20", null, "In 20", null], ["Touchbacks", "TB", "TB", "large"], ["Long", null, null, "medium"]]);
  assert.deepEqual(labels.categoryColumns("defensive", ["PD", "QB HUR", "SACKS", "SOLO", "TD", "TFL", "TOT"]).map((c) => [c.label, c.size]), [["Tkl", null], ["Solo", "medium"], ["TFL", null], ["Sacks", null], ["Hurries", "medium"], ["PD", "medium"], ["TD", "large"]], "Tkl, TFL and Sacks on a phone");
  assert.deepEqual(labels.categoryColumns("kicking", ["FGA", "FGM", "LONG", "PCT", "PTS", "XPA", "XPM"]).map((c) => [c.label, c.size]), [["FGM", null], ["FGA", null], ["FG %", "medium"], ["Long", "medium"], ["XPM", "medium"], ["XPA", "medium"], ["Pts", null]]);
  assert.deepEqual(labels.categoryColumns("fumbles", ["FUM", "LOST", "REC"]).map((c) => c.size), [null, null, null]);
  for (const bad of [null, undefined, 3, {}, "nope"]) assert.ok(Array.isArray(labels.categoryColumns(bad, ["YDS"])) && labels.categoryColumns(bad, ["YDS"])[0].size === null);

  // decision 3: two seasons, so each table closes with a real Career row; the newest season first, never sorted
  const data = playerData();
  data.seasons = [
    { year: 2026, category: "receiving", stats: { LONG: 49, REC: 14, TD: 2, YDS: 246, YPR: 17.6 } },
    { year: 2025, category: "receiving", stats: { LONG: 61, REC: 20, TD: 3, YDS: 300, YPR: 15.0 } },
    { year: 2026, category: "passing", stats: { ATT: 2, COMPLETIONS: 1, PCT: 0.5, YDS: 30, YPA: 15, TD: 1, INT: 0 } },
  ];
  data.missingSeasons = [2024, "x", null];
  data.missingHistory = [2023, "y", undefined];
  const card = playerCard({ ...cardPropsFrom(data), inline: true });
  document.body.replaceChildren(card);
  clean("card with two seasons", card);
  const stats = card.querySelector('[aria-label="Stats"]');
  const tables = stats.querySelectorAll(".stat-table-wrap");
  assert.equal(tables.length, 2);
  for (const wrap of tables) assert.equal(wrap.dataset.size, "large", "a sized table");
  const receiving = tables[0];
  assert.deepEqual(heads(receiving).map((th) => text(th)), ["Year", "Rec", "Yds", "Y/R", "TD", "Long"]);
  assert.deepEqual(marks(heads(receiving)), ["", "", "", "", "", "M"], "the long waits for medium");
  assert.equal(heads(receiving).filter((th) => th.querySelector("button")).length, 0, "no sort: the Career row stays last");
  const rr = [...receiving.querySelector("tbody").querySelectorAll("tr")];
  assert.deepEqual(rr.map((tr) => sized(tr.querySelector("td"), "long")), ["2026", "2025", "Career"]);
  const career = [...rr[2].querySelectorAll("td")].map((td) => text(td));
  assert.deepEqual(career.slice(1), ["34", "546", "16.1", "5", "61"], "sums, the best long and the rate from the sums");
  assert.ok(rr[2].className.includes("is-total"));
  const passTable = tables[1];
  assert.equal(passTable.querySelectorAll("tbody tr").length, 1, "one season: no Career row repeating it");
  assert.ok(text(card.querySelector(".player-card__note")).includes("Stats for 2024 could not be loaded"), "the failed season is named");
  assert.ok(text(card.querySelector(".player-card__note")).includes("Rosters for 2023 could not be loaded, so History and the career rows may leave that season out"), "a failed earlier roster is named too");
  assert.deepEqual(careerRow([{ key: "year" }, { key: "A", sum: true }, { key: "B", max: true }, { key: "C", avg: { num: "A", den: "D" } }, { key: "D", sum: true }, { key: "E", kind: "text" }], [{ A: 2, B: 5, D: 4 }, { A: "x", B: null, D: 0 }]), { year: "Career", isTotal: true, A: 2, B: 5, C: 0.5, D: 4, E: null });

  // the game log: sized, sorting, the latest game first, the Wk head marked; the result sorts by its margin
  const log = card.querySelector('[aria-label="Game log"]');
  const recv = log.querySelector(".stat-table-wrap");
  assert.equal(recv.dataset.size, "large");
  const lh = heads(recv);
  assert.deepEqual(lh.map((th) => text(th)), ["Wk", "Opp", "Result", "Rec", "Yds", "Avg", "TD", "Long"]);
  assert.deepEqual(marks(lh), ["", "", "M", "", "", "", "", "L"], "a phone: the week, the opponent and four numbers");
  assert.ok(lh.every((th) => th.querySelector("button")), "the games sort");
  assert.equal(lh[0].getAttribute("aria-sort"), "descending");
  const weeks = () => [...recv.querySelector("tbody").querySelectorAll("tr")].map((tr) => sized(tr.querySelector("td"), "long"));
  assert.deepEqual(weeks(), ["3", "2", "1"]);
  lh[2].querySelector("button").click();
  assert.deepEqual(weeks(), ["2", "1", "3"], "the biggest win first");
  heads(recv)[0].querySelector("button").click();
  assert.deepEqual(weeks(), ["3", "2", "1"]);
  assert.equal(resultMargin("W 31-14"), 17);
  assert.equal(resultMargin("L 20-24"), -4);
  for (const bad of [null, "W", "x 1-2", 3, {}, "W 1-"]) assert.equal(resultMargin(bad), null);
  // a bowl sorts after the regular season by its place, not its words
  const bowl = playerData();
  bowl.gameLog = [...bowl.gameLog, { gameId: 499, week: 1, postseason: "Pasta Bowl", opponent: "Charlotte", homeAway: "home", result: "W 10-7", lines: [{ category: "receiving", stats: { REC: 1, YDS: 9 } }] }];
  const bowlCard = playerCard({ ...cardPropsFrom(bowl), inline: true });
  const bw = bowlCard.querySelector('[aria-label="Game log"] .stat-table-wrap');
  const bweeks = () => [...bw.querySelector("tbody").querySelectorAll("tr")].map((tr) => sized(tr.querySelector("td"), "long"));
  assert.deepEqual(bweeks(), ["Bowl", "3", "2", "1"], "a bowl's week is a word, its whole name on hover");
  const bowlWeek = bw.querySelector("tbody td");
  assert.equal(bowlWeek.querySelector(".sz-t--long span").getAttribute("title"), "Pasta Bowl");
  assert.equal(sized(bowlWeek, "short"), "Bowl");
  heads(bw)[0].querySelector("button").click();
  assert.deepEqual(bweeks(), ["1", "2", "3", "Bowl"]);
  const playoff = playerData();
  playoff.gameLog = [{ gameId: 498, week: 1, postseason: "College Football Playoff Semifinal at the Pasta Bowl", postseasonShort: "Semifinal", opponent: "Charlotte", homeAway: "away", result: "L 14-21", lines: [{ category: "receiving", stats: { REC: 2, YDS: 30 } }] }];
  const pweek = playerCard({ ...cardPropsFrom(playoff), inline: true }).querySelector('[aria-label="Game log"] tbody td');
  assert.deepEqual([sized(pweek, "long"), sized(pweek, "short")], ["Semifinal", "CFP"]);

  // Play value: the splits keep their order and shorten; PPA per play in three forms; usage sized; by game sorts
  const pv = card.querySelector('[aria-label="Play value"]');
  const [split, byGame, usage] = pv.querySelectorAll(".stat-table-wrap");
  assert.deepEqual(heads(split).map((th) => [sized(th, "long"), sized(th, "mid"), sized(th, "short")]), [["Split", "Split", "Split"], ["PPA per play", "PPA/play", "PPA"], ["Total PPA", "Total PPA", "Total"]]);
  assert.equal(heads(split).filter((th) => th.querySelector("button")).length, 0, "the splits keep their order");
  const firstCells = [...split.querySelector("tbody").querySelectorAll("tr")].map((tr) => tr.querySelector("td"));
  assert.deepEqual(firstCells.map((td) => sized(td, "short")), ["All", "Passing", "Rushing", "1st", "2nd", "3rd", "Std downs", "Pass downs"]);
  assert.equal(firstCells[3].dataset.term, "First down", "the hint keeps the long name");
  assert.ok(heads(byGame).every((th) => th.querySelector("button")) && heads(byGame)[0].getAttribute("aria-sort") === "descending");
  assert.deepEqual(heads(byGame).map((th) => sized(th, "short")), ["Wk", "Opp", "PPA", "Pass", "Rush"]);
  assert.equal(usage.dataset.size, "large");
  assert.ok(text(usage).includes("20%"), "a rate shows whole numbers (Design rules, 2026-10-21)");

  // History: newest first and sortable, the team's abbreviation (still its link) and "#" at small
  const hist = playerData();
  hist.history = [{ year: 2024, team: "Florida", teamAbbr: "FLA", classYear: "FR", position: "WR", number: 11 }, { year: 2026, team: "Florida", teamAbbr: "FLA", classYear: "JR", position: "WR", number: 1 }, { year: 2025, team: "Texas State", teamAbbr: null, classYear: "SO", position: "WR", number: 1 }];
  const hcard = playerCard({ ...cardPropsFrom(hist), inline: true });
  const hw = hcard.querySelector('[aria-label="History"] .stat-table-wrap');
  assert.equal(hw.dataset.size, "large");
  const hh = heads(hw);
  assert.deepEqual(hh.map((th) => sized(th, "short")), ["Year", "Team", "Class", "Pos", "#"]);
  assert.deepEqual(marks(hh), ["", "", "", "", ""], "nothing drops at small");
  assert.equal(hh[0].getAttribute("aria-sort"), "descending");
  const hrows = [...hw.querySelector("tbody").querySelectorAll("tr")];
  assert.deepEqual(hrows.map((tr) => sized(tr.querySelector("td"), "long")), ["2026", "2025", "2024"]);
  const team = hrows[0].querySelectorAll("td")[1];
  assert.equal(text(team.querySelector("button.team-link .sz-t--short")), "FLA");
  assert.equal(text(hrows[1].querySelectorAll("td")[1]), "Texas State", "no abbreviation: the school at every size");
  hh[0].querySelector("button").click();
  assert.deepEqual([...hw.querySelector("tbody").querySelectorAll("tr")].map((tr) => sized(tr.querySelector("td"), "long")), ["2024", "2025", "2026"]);

  // the short stat list of a player with no full card, sized
  const small = playerCard({ player: { name: "Cole Webb" }, seasonStats: [{ label: "Passing yards", value: "753" }, { label: "Cmp", value: "47" }], inline: true });
  const sw = small.querySelector('[aria-label="Stats"] .stat-table-wrap');
  assert.equal(sw.dataset.size, "large");
  assert.equal(sized(sw.querySelector("tbody td"), "short"), "Pass yds");
  // the old one-line game log shape is retired: it draws nothing, never "[object Object]"
  const old = playerCard({ player: { name: "Old" }, gameLog: [{ opponent: "Texas State", line: "5 rec" }], inline: true });
  assert.ok(clean("old shape", old).includes("Game log appears after the first game."));
};

scenarios.recruiting = async () => {
  await useTeam();
  clearCache();
  route("/api/recruiting", () => envelope(recruitingData()));
  const rec = await import(moduleUrl("views/recruiting.js"));
  // owner 2026-11-01 ("Always start with the current class, which is 2027"): the latest class opens first; the 2026 class, asked for
  const latest = await mountView(rec.createRecruitingView, {});
  assert.ok(text(latest.main.querySelector("#recruiting-class .band__title")).startsWith("2027"), "the class being recruited opens first");
  latest.view.unmount();
  const { main } = await mountView(rec.createRecruitingView, { arg: "2026:national" });
  const cls = main.querySelector("#recruiting-class");
  const head = cls.querySelector(".class-head a.rank-chip--link");
  assert.ok(head, "the class rank is the headline, a linked chip");
  assert.equal(head.getAttribute("href"), "#national=class%3A2026?team=Florida");
  assert.ok(cls.querySelector(".band__summary a.rank-chip--link"), "the summary carries the chip");
  assert.ok(cls.scrolledInto, "#recruiting=national scrolls to the class");
  const commits = cls.querySelector("table");
  const cells = commits.querySelector("tbody tr").querySelectorAll("td").map((td) => text(td));
  assert.ok(cells.includes("4-star"), cells.join("|"));
  assert.ok(cells.includes("97"), `rating as 0-100: ${cells.join("|")}`);
  assert.equal(commits.querySelectorAll("tbody a.rank-chip--link").length, 1, "only the commit with a list key links");
  // wave 3: sized; the class's national rank is its own order (the chip, a plain number at small), the position its own column
  const form = (node, which) => { const t = node.querySelector(`.sz-t--${which}`); return t ? t.textContent : text(node); };
  const marks = (ths) => ths.map((th) => (th.className.includes("st__min-large") ? "L" : th.className.includes("st__min-medium") ? "M" : ""));
  const commitWrap = cls.querySelector(".stat-table-wrap");
  assert.equal(commitWrap.dataset.size, "large");
  const ch = commits.querySelectorAll("thead th");
  assert.deepEqual(ch.map((th) => th.dataset.term), ["National rank", "Recruit", "Pos", "Stars", "Rating", "High school", "Hometown", "Ht", "Wt"]);
  assert.deepEqual(marks(ch), ["", "", "M", "", "", "L", "M", "M", "M"], "a phone keeps the order, the recruit, his stars and rating");
  assert.deepEqual([form(ch[0], "mid"), form(ch[0], "short")], ["Nat", "Nat"]);
  assert.ok(ch.every((th) => th.querySelector("button")), "the recruits sort");
  const first = commits.querySelector("tbody tr").querySelectorAll("td");
  assert.ok(first[0].querySelector(".sz-t--long .rank-chip"), "the chip at large and medium");
  assert.equal(form(first[0], "short"), "56", "a plain number at small");
  assert.equal(text(first[2]), "WR", "the position in a column of its own");
  assert.equal(first[1].querySelector("small"), null, "nothing drawn under the name");
  assert.ok(first[1].className.includes("st__person") && first[1].querySelector(".pn"), "item 6: the recruit's name steps down with the table");
  assert.deepEqual([text(first[6]), text(first[7]), text(first[8])], ["Frisco, TX", "6-1", "190"]);
  const shaped = rec.commitRows([{ name: "Jalen Smithers Jr.", position: " ", nationalRank: "9", height: 74, heightText: "6-2", weight: NaN }, null, "x"]);
  assert.equal(shaped.length, 1);
  assert.deepEqual([shaped[0].name, shaped[0].position, shaped[0].nationalRank, shaped[0].height, shaped[0].weight], ["Jalen Smithers Jr.", null, null, 74, null]);
  ch[7].querySelector("button").click();
  assert.equal(ch[7].getAttribute("aria-sort") || commits.querySelectorAll("thead th")[7].getAttribute("aria-sort"), "descending", "Ht sorts by inches, tallest first");
  const visitors = main.querySelector("#recruiting-visitors");
  const summary = text(visitors.querySelector(".band__summary"));
  assert.ok(summary.startsWith("kickoff "), summary);
  assert.ok(!summary.includes("526000600"), "never the game id");
  assert.ok(visitors.querySelector('h3.subhead button.team-link[data-team="Fresno State"]'), "the visitors' sub-heading links the team");
  // the visitors: a sized table of players that sorts, the position in its own column, the class a year
  const vt = visitors.querySelector("table");
  const vh = vt.querySelectorAll("thead th");
  assert.deepEqual(vh.map((th) => th.dataset.term), ["Recruit", "Pos", "Class", "Stars", "High school", "Hometown", "Status"]);
  assert.deepEqual(marks(vh), ["", "M", "", "", "L", "M", ""]);
  assert.ok(vh.every((th) => th.querySelector("button")), "a table of players sorts");
  const v0 = vt.querySelector("tbody tr").querySelectorAll("td");
  assert.deepEqual([pnText(v0[0]), pnText(v0[0], "last"), text(v0[1]), text(v0[2]), text(v0[6])], ["Visitor One", "One", "QB", "2027", "confirmed"]);
  // where they're from (owner 2026-10-16): a pie per class, both classes side by side, every state a slice and a chip
  const where = main.querySelector("#recruiting-where");
  assert.equal(where.querySelectorAll("table").length, 0, "no list of states any more");
  const classes = where.querySelectorAll(".where-pies__class");
  assert.equal(classes.length, 2, "the current class and the next one, together");
  assert.ok(text(classes[0].querySelector("h3")).includes("class") && text(classes[1].querySelector("h3")).includes("class"));
  const pie = classes[0].querySelector("figure.pie");
  const slices = pie.querySelectorAll(".pie__slice");
  const chips = pie.querySelectorAll(".pie__chip");
  assert.ok(slices.length >= 1 && slices.length === chips.length, "one slice and one legend chip per state");
  const { stateName } = await import(moduleUrl("us-states.js"));
  assert.deepEqual([text(chips[0].querySelector(".pie__name")), text(chips[0].querySelector(".pie__value"))], ["FL", "2 · 67%"], "the most commits first, with the share");
  assert.ok(slices[0].getAttribute("style").includes("var(--team-us)"), "our state wears our color");
  assert.ok(text(pie.querySelector(".pie__info")).startsWith(`${stateName("FL")}: 2 commits, 67%`), "the largest slice says itself");
  assert.ok(pie.querySelector("svg").getAttribute("aria-label").includes(stateName("FL")), "the pie reads as words");
  if (chips.length > 1) {
    chips[1].click();
    assert.equal(chips[1].getAttribute("aria-pressed"), "true");
    assert.ok(slices[0].classList.contains("is-dim"), "the picked state stands out");
  }
  assert.ok(text(where).includes("In-state (FL): 2 of 3 commits, 67%."));
  clean("recruiting", main);
  // the reader's order survives the redraw a class switch makes
  const yes = cls.querySelectorAll(".seg button");
  commits.querySelectorAll("thead th")[3].querySelector("button").click();
  yes[1].click();
  await settle();
  const switched = main.querySelector("#recruiting-class table");
  assert.equal(switched.querySelectorAll("thead th").find((th) => th.getAttribute("aria-sort")).dataset.term, "Stars", "the order is kept");
  localStorage.removeItem("recruiting:class"); // the tap remembered its class; the route below starts clean
  // the next class, by route: no rank yet, one commit without a state
  const next = await mountView(rec.createRecruitingView, { arg: "2027:where" });
  assert.equal(text(next.main.querySelector("#recruiting-class .band__title")), "2027 class");
  assert.ok(text(next.main.querySelector("#recruiting-where")).includes("1 commit with no home state on record."));
  assert.equal(localStorage.getItem("recruiting:class"), null, "a route year is not remembered");
  clean("recruiting 2027", next.main);
  // by-state rows with nulls and unknown states
  const rows = rec.whereRows({ byState: [null, "x", { state: null, commits: "7", stars: null, averageRating: NaN }, { state: "ZZ", commits: 2, stars: { 5: 1, 4: "x" }, averageRating: 0.9 }] });
  assert.deepEqual(rows.map((r) => r.state), ["Unknown", "ZZ"]);
  assert.equal(rows[0].commits, null);
  assert.deepEqual([rows[0].s5, rows[0].s4, rows[0].s3], [0, 0, 0], "no stars on record: zeros, never null");
  assert.deepEqual([rows[1].s5, rows[1].s4, rows[1].s3, rows[1].stateName, rows[0].stateName], [1, 0, 0, "ZZ", "Unknown"], "one count per column; a code with no name stays itself");
  assert.equal(rows[0].starMix, undefined, "the three counts are columns now, never one cell");
  for (const bad of JUNK) {
    assert.deepEqual(rec.whereRows(bad), []);
    assert.equal(rec.inStateLine(bad), "");
    assert.equal(rec.inStateLine({ inState: bad, unknownState: bad }), "");
  }
};

scenarios.damaged = async () => {
  const views = [
    ["/api/season/leaders", "views/leaders.js", "createLeadersView", leadersData],
    ["/api/roster", "views/roster.js", "createRosterView", rosterData],
    ["/api/recruiting", "views/recruiting.js", "createRecruitingView", recruitingData],
  ];
  // every field of every record replaced by junk, one kind at a time, plus whole-payload junk
  const damage = (value, bad, depth = 0) => {
    if (Array.isArray(value)) return depth > 3 ? bad : [...value.map((v) => damage(v, bad, depth + 1)), bad];
    if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).map((k) => [k, depth > 3 ? bad : damage(value[k], bad, depth + 1)]));
    return bad;
  };
  const scopes = ["team", "opponent", "conference", "national"];
  for (const [url, path, name, make] of views) {
    const mod = await import(moduleUrl(path));
    const payloads = [null, {}, [], "junk", ...JUNK.slice(0, 7).map((bad) => damage(make(), bad))];
    for (const [i, payload] of payloads.entries()) {
      for (const scope of url.includes("leaders") ? scopes : [null]) {
        clearCache();
        routes.length = 0;
        route(url, () => envelope(payload));
        if (scope) localStorage.setItem("leaders:scope", JSON.stringify(scope));
        const { main, view } = await mountView(mod[name]);
        clean(`${name} payload ${i}${scope ? ` ${scope}` : ""}`, main);
        view.unmount();
      }
    }
  }
  // the card with a damaged payload, loaded and inline
  const { cardPropsFrom } = await import(moduleUrl("views/player.js"));
  const { playerCard } = await import(moduleUrl("ui/player-card.js"));
  for (const bad of JUNK) {
    clean(`card ${String(bad)}`, playerCard({ ...cardPropsFrom(damage(playerData(), bad)), inline: true }));
    clean(`card whole ${String(bad)}`, playerCard({ ...cardPropsFrom(bad), inline: true }));
    clean(`loading ${String(bad)}`, playerCard({ player: { name: bad, number: bad, team: bad, stars: bad, rating: bad, recruitRank: bad, transfer: bad, recruit: bad }, loading: true, inline: true }));
  }
};
"""

HELPERS = r"""
const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
const clearCache = () => clearEnvelopeCache();
"""

NAMES = ["labels", "leadersChips", "leadersArrival", "leadersGrades", "leadersOtherGroup", "leadersGap", "leadersVersusPpa", "rosterTable", "cardLoading", "cardSlow", "cardClose", "cardFallback", "patientRounds", "gameLog", "cardSizes", "recruiting", "damaged"]


@needs_node
@pytest.mark.parametrize("scenario", NAMES)
def test_people_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, HELPERS + SCENARIOS, scenario, timeout=240)


def test_people_css_is_there() -> None:
    css = (ROOT / "static" / "css" / "components.css").read_text(encoding="utf-8")
    anchor = css.index("/* === PEOPLE: Leaders, Roster, Recruiting, player card === */")
    people = css[anchor : css.index("/* === PROFILES:", anchor)]
    for rule in (".leaders__scope", "tbody.stat-table__window", "tr.is-opp", ".player-card__bar", ".player-card__tabs", "min(600px, 100vw)", ".roster-filter", ".class-head"):
        assert rule in people, rule
    assert "repeat(6, minmax(0, 1fr))" in css and "border-radius: 14px" not in css.split(".depth-card {")[1].split("}")[0]
    assert ".depth-card__sort" not in css, "the hidden depth-card select is gone"
    assert ".player-card__section" not in css, "dead rules removed"


def test_page_check_has_the_people_group() -> None:
    source = (ROOT / "tools" / "page_check.py").read_text(encoding="utf-8")
    group = source[source.index('"PEOPLE": [') : source.index("],", source.index('"PEOPLE": ['))]
    for route in ("leaders", "leaders=passing:YDS:national", "roster", "recruiting", "recruiting=national"):
        assert f'"{route}"' in group, route
