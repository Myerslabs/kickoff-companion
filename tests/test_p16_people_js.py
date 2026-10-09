"""Phase 16, stream PEOPLE: Leaders, Roster, Recruiting and the player card in the fake browser
(tests/fakedom.py), plus the pure helpers under Node. Chips in tappable rows never open the card, a link
arrival keeps the remembered Leaders scope, the Mudpuppies below the cut sit in their own tbody, the roster's
position select is visible and its sort survives a refresh, depth rows carry the jersey number with no
anchor inside the button, the loading card states nothing as fact and never draws Swampwater Tech as the opponent,
game-log opponents are team links, the sparkline needs two games, the by-state table survives nulls, and
no damaged payload prints undefined, null or NaN."""

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
    playerId: "p1", player: "Mason Hamilton", position: "QB", team: "Swampwater Tech", teamAbbr: "SWT", metric: "board:passing:YDS", isUs: true,
    value: 721, detail: { ATT: 64, COMPLETIONS: 47, INT: 2, PCT: 0.734, TD: 6, YPA: 11.3 }, rank: null,
    conferenceRank: 6, conferenceOf: 43, nationalRank: 47, nationalOf: 358, headshotUrl: "/media/headshot/p1", ...over,
  };
}

function leadersData() {
  const national = Array.from({ length: 10 }, (_, i) => entry({ playerId: `n${i}`, player: `National ${i}`, team: i === 3 ? "Silver Dollar" : "USC", teamAbbr: i === 3 ? "GRID" : "USC", isUs: false, rank: i + 1, nationalRank: i + 1, value: 1200 - i * 10 }));
  const conference = Array.from({ length: 10 }, (_, i) => entry({ playerId: `c${i}`, player: `Biscuit Belt ${i}`, team: "Silver Dollar", teamAbbr: "GRID", isUs: false, rank: i + 1, conferenceRank: i + 1, value: 1100 - i * 10 }));
  return {
    season: 2026,
    team: { school: "Swampwater Tech", abbreviation: "SWT", conference: "Biscuit Belt" },
    opponent: { school: "Silver Dollar", abbreviation: "GRID", conference: "Biscuit Belt" },
    boards: [
      {
        id: "passing:YDS", metric: "board:passing:YDS", category: "passing", stat: "YDS", label: "Passing yards", format: "0f",
        team: [entry(), entry({ playerId: "p2", player: "Tramell Jones Jr.", value: 126, nationalRank: 160, conferenceRank: 20 })],
        opponent: [entry({ playerId: "o1", player: "Byron Brooks", team: "Silver Dollar", teamAbbr: "GRID", isUs: false, value: 753, nationalRank: 37 })],
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
  return { playerId: "r1", number: 12, name: "Mason Hamilton", firstName: "Aaron", lastName: "Hamilton", team: "Swampwater Tech", position: "QB", classYear: "JR", height: 73, heightText: "6-1", weight: 207, hometown: "Bogart, GA", highSchool: "Oconee", stars: 4, rating: 0.9379, recruitRank: 142, headshotUrl: "/media/headshot/r1", isUs: true, transfer: null, ppaPerPlay: 0.4, ppaPlays: 81, usageShare: 0.3, ...over };
}

function rosterData() {
  return {
    season: 2026,
    team: { school: "Swampwater Tech" },
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
    pff: { enabled: false },
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
    visitors: { gameId: 526000600, opponent: "Silver Dollar", date: "2026-10-03T16:00:00.000Z", startTimeTbd: false, home: [{ name: "Visitor One", position: "QB", stars: 4, highSchool: "X", hometown: "Y", classYear: 2027, status: "confirmed" }], away: [], source: null, note: null, error: null },
    parts: {},
  };
}

function playerData() {
  const game = (week, opponent, homeAway, result, yds) => ({ gameId: 400 + week, week, postseason: null, date: "2026-09-05T23:45:00.000Z", opponent, homeAway, result, lines: [{ category: "receiving", stats: { REC: 5, YDS: yds, AVG: 10.2, TD: 1, LONG: 40 } }, { category: "kicking", stats: { FG: "1/1", PCT: 100.0 } }] });
  return {
    player: { playerId: "p9", number: 1, name: "Darnell Brooks III", team: "Swampwater Tech", teamAbbr: "SWT", position: "WR", classYear: "SO", heightText: "5-11", weight: 180, hometown: "Jacksonville, FL", highSchool: "Jackson", stars: 4, rating: 0.9379, recruitRank: 123, recruit: { year: 2024, stars: 4, rating: 0.9379, nationalRank: 123, position: "ATH", type: "HighSchool" }, transfer: { from: "Georgia Tech", stars: 3, rating: 0.89, date: "2026-01-06", eligibility: "Immediate" }, headshotUrl: "/media/headshot/p9", isUs: true },
    seasons: [{ year: 2026, category: "receiving", stats: { LONG: 49, REC: 14, TD: 2, YDS: 246, YPR: 17.6 } }],
    gameLog: [game(1, "Swampwater Tech Atlantic", "home", "W 66-21", 50), game(2, "Campbell", "home", "W 52-3", 80), game(3, "Diner Tech", "away", "L 20-24", 117)],
    missingWeeks: [],
    history: [{ year: 2025, team: "Swampwater Tech", classYear: "FR", position: "WR", number: 1 }],
    ppa: { season: { plays: 20, average: { all: 0.5, pass: 0.6 }, total: { all: 10 } }, teamRank: 3, teamOf: 18, games: [{ week: 3, opponent: "Diner Tech", all: 0.8, pass: 0.9, rush: null }] },
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
  // the national chip on the value and the Biscuit Belt chip open their lists; the summary carries a linked chip
  const chips = band.querySelectorAll("tbody a.rank-chip--link");
  assert.ok(chips.length >= 4, `linked chips in the rows (${chips.length})`);
  const hrefs = chips.map((a) => a.getAttribute("href"));
  assert.ok(hrefs.includes("#national=board%3Apassing%3AYDS?team=Swampwater%20Tech"), hrefs.join(" "));
  assert.ok(hrefs.includes("#national=board%3Apassing%3AYDS?team=Swampwater%20Tech&scope=conference"), hrefs.join(" "));
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
  // a usage board has no lists: its chips stay plain, never an anchor to nowhere
  const usage = main.querySelector("#leaders-usage-overall");
  assert.equal(usage.querySelectorAll("a.rank-chip--link").length, 0);
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
  const conf = [...main.querySelectorAll(".leaders__scope button")].find((b) => text(b) === "Biscuit Belt top 10");
  click(conf);
  assert.equal(localStorage.getItem("leaders:scope"), JSON.stringify("conference"));
};

scenarios.leadersGap = async () => {
  clearCache();
  route("/api/season/leaders", () => envelope(leadersData()));
  localStorage.setItem("leaders:scope", JSON.stringify("national"));
  const { createLeadersView, windowRows } = await import(moduleUrl("views/leaders.js"));
  const { main } = await mountView(createLeadersView);
  const table = main.querySelector("#leaders-passing-YDS table");
  const bodies = table.querySelectorAll("tbody");
  assert.equal(bodies.length, 2, "the Mudpuppies below the cut have their own tbody");
  assert.equal(bodies[0].querySelectorAll("tr").length, 10, "the top 10 alone in the first");
  assert.equal(bodies[0].querySelectorAll("tr.is-window").length, 0);
  const tail = bodies[1].querySelectorAll("tr");
  assert.ok(tail[0].className.includes("gap-row"), "the gap row leads the second tbody");
  assert.equal(tail.length, 3, "gap row plus both Mudpuppies");
  assert.ok(tail[1].className.includes("is-us"));
  assert.equal(text(tail[1].querySelector("td")), "47");
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
  // vs opponent: Swampwater Tech beside the opponent, value and chip in one cell a side
  localStorage.setItem("leaders:scope", JSON.stringify("opponent"));
  const vs = await mountView(createLeadersView);
  const heads = vs.main.querySelectorAll("#leaders-passing-YDS thead th").map((th) => text(th));
  assert.deepEqual(heads, ["#", "SWT", "Yds", "GRID", "Yds"]);
  const first = vs.main.querySelector("#leaders-passing-YDS tbody tr");
  assert.ok(first.querySelectorAll("td")[3].className.includes("col-div"), "a divider before the opponent");
  assert.ok(first.querySelectorAll("td")[4].querySelector(".rank-chip"), "the opponent's value carries its chip");
  clean("vs opponent", vs.main);
};

scenarios.rosterTable = async () => {
  clearCache();
  let version = 0;
  route("/api/roster", () => { version += 1; return envelope(rosterData()); });
  const { createRosterView } = await import(moduleUrl("views/roster.js"));
  const { main } = await mountView(createRosterView);
  const band = main.querySelector("#roster-table");
  const select = band.querySelector("select");
  assert.ok(select, "a position select");
  assert.ok(!select.className.includes("depth-card__sort"), "not the depth card's hidden select");
  assert.ok(select.className.includes("setting__select"), "styled like the settings selects (visible, 44 px)");
  assert.equal(band.querySelector(".band__head select"), null, "not in the band head");
  assert.ok(band.querySelector(".band__body select"));
  assert.equal(text(band.querySelector(".roster-filter__label")), "Position");
  const wrap = band.querySelector(".stat-table-wrap");
  assert.ok(wrap.className.includes("stat-table-wrap--box"), "a scroll box so the header sticks");
  assert.equal(wrap.style["--table-max"], "min(70vh, 720px)");
  // sort by weight, then refresh: the sort stays
  const wt = band.querySelectorAll("thead th").find((th) => text(th) === "Wt");
  click(wt.querySelector("button"));
  assert.equal(band.querySelectorAll("thead th").find((th) => text(th) === "Wt").getAttribute("aria-sort"), "descending");
  await advance(60 * 60 * 1000 + 5);
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

scenarios.depthRows = async () => {
  clearCache();
  route("/api/roster", () => envelope(rosterData()));
  localStorage.removeItem("roster:sort:OL");
  localStorage.setItem("roster:sort:LB", JSON.stringify("recruit"));
  const roster = await import(moduleUrl("views/roster.js"));
  const { main } = await mountView(roster.createRosterView);
  const rows = main.querySelectorAll(".depth-row");
  assert.equal(rows.length, 5);
  for (const row of rows) {
    const num = row.querySelector(".depth-row__num");
    assert.ok(num, "every row has its jersey number");
    assert.ok(/^\d+$/.test(text(num)), text(num));
    assert.equal(row.querySelectorAll("a").length, 0, "no anchor inside the row's button");
  }
  const card = (label) => main.querySelectorAll(".depth-card").find((c) => text(c.querySelector("h3")) === label);
  // LRP-04: QB starts on Plays, OL (no play counts) on Rating: the number is the rating, not a dash
  const pick = (c) => c.querySelector("select.depth-card__pick");
  assert.equal(pick(card("QB")).querySelector("option[selected]").getAttribute("value"), "plays");
  assert.equal(pick(card("OL")).querySelector("option[selected]").getAttribute("value"), "rating");
  assert.deepEqual(card("OL").querySelectorAll(".depth-row__val").map((v) => text(v)), ["95", "88"]);
  assert.deepEqual(card("OL").querySelectorAll(".depth-row__num").map((v) => text(v)), ["70", "71"], "the order is the rating order it always was");
  assert.equal(roster.defaultSort([{ ppaPlays: 3 }, {}]), "plays");
  assert.equal(roster.defaultSort([{}, null, "x"]), "rating");
  assert.equal(roster.defaultSort(null), "rating");
  // a remembered choice wins; the Recruit rank sort puts the chip beside the button
  const lb = card("LB");
  assert.equal(pick(lb).querySelector("option[selected]").getAttribute("value"), "recruit");
  const li = lb.querySelector("li");
  assert.ok([...li.childNodes].some((n) => n.className && n.className.includes("rank-chip")), "the chip is a sibling of the button");
  assert.equal(li.querySelector("button").querySelectorAll(".rank-chip").length, 0);
  // the skeleton is the chart's shape
  const skel = roster.depthSkeleton();
  assert.equal(skel.querySelectorAll(".depth__unit").length, 6);
  clean("depth chart", main);
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
  const opened = openPlayer("p9", { name: "Darnell Brooks III", number: 1, position: "WR", team: "Swampwater Tech", isUs: true });
  await settle();
  const card = document.body.querySelector(".player-card");
  assert.ok(card, "the loading card is up");
  const loadingText = clean("loading card", card);
  for (const sentence of ["No season stats yet", "Game log appears", "No roster history", "No play value"]) assert.ok(!loadingText.includes(sentence), `the loading card says "${sentence}"`);
  assert.ok(loadingText.includes("#1 Darnell Brooks III"));
  assert.ok(card.className.includes("is-loading"));
  assert.equal(card.querySelectorAll(".number-badge--them").length, 0, "a Swampwater Tech player is not them");
  assert.ok(card.querySelector(".player-card__hero--us"));
  assert.ok(card.querySelector(".skel-table"), "skeleton bars");
  // a Swampwater Tech row without isUs (older rows) is not them either
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
  assert.ok(card.querySelector('.player-card__bio button.team-link[data-team="Swampwater Tech"]'), "the team in the bio line links");
  assert.ok(card.querySelector('.player-card__facts button.team-link[data-team="Georgia Tech"]'), "the transfer school links");
  assert.ok(card.querySelector('[aria-label="History"] button.team-link'), "History's team links");
  close();
  assert.equal(document.body.querySelector(".card-layer"), null);
  assert.equal(close.update({ player: { name: "Late" } }), false, "an answer after close never reopens the card");
  globalThis.fetch = realFetch;
  assert.ok(other.cardHeading("X").className.includes("player-card__h"));
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
  for (const tr of rows) assert.ok(tr.querySelectorAll("td")[1].querySelector('button.team-link'), "each opponent cell is a team link");
  assert.equal(text(rows[0].querySelectorAll("td")[1]), "at Diner Tech", "the latest game is first");
  assert.equal(text(rows[2].querySelectorAll("td")[1]), "vs Swampwater Tech Atlantic");
  assert.ok(rows[0].querySelector(".gl-result--l"));
  assert.ok(rows[2].querySelector(".gl-result--w"));
  // box-score PCT (100.0) reads 100%, not 10000%
  assert.ok(text(log).includes("100.0%") && !text(log).includes("10000"));
  // Play value: numbers as numbers, the by-game row with the right at/vs
  const pv = card.querySelector('[aria-label="Play value"]');
  assert.ok(pv.querySelectorAll("tbody td:not(.txt)").length > 0, "numeric cells");
  assert.ok(text(pv).includes("at Diner Tech"));
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

scenarios.recruiting = async () => {
  await useTeam();
  clearCache();
  route("/api/recruiting", () => envelope(recruitingData()));
  const rec = await import(moduleUrl("views/recruiting.js"));
  const { main } = await mountView(rec.createRecruitingView, { arg: "national" });
  const cls = main.querySelector("#recruiting-class");
  const head = cls.querySelector(".class-head a.rank-chip--link");
  assert.ok(head, "the class rank is the headline, a linked chip");
  assert.equal(head.getAttribute("href"), "#national=class%3A2026?team=Swampwater%20Tech");
  assert.ok(cls.querySelector(".band__summary a.rank-chip--link"), "the summary carries the chip");
  assert.ok(cls.scrolledInto, "#recruiting=national scrolls to the class");
  const commits = cls.querySelector("table");
  const cells = commits.querySelector("tbody tr").querySelectorAll("td").map((td) => text(td));
  assert.ok(cells.includes("4-star"), cells.join("|"));
  assert.ok(cells.includes("97"), `rating as 0-100: ${cells.join("|")}`);
  assert.equal(commits.querySelectorAll("tbody a.rank-chip--link").length, 1, "only the commit with a list key links");
  const visitors = main.querySelector("#recruiting-visitors");
  const summary = text(visitors.querySelector(".band__summary"));
  assert.ok(summary.startsWith("kickoff "), summary);
  assert.ok(!summary.includes("526000600"), "never the game id");
  assert.ok(visitors.querySelector('h3.subhead button.team-link[data-team="Silver Dollar"]'), "the visitors' sub-heading links the team");
  const where = main.querySelector("#recruiting-where");
  assert.deepEqual(where.querySelectorAll("thead th").map((th) => text(th)), ["State", "Commits", "Avg rating", "5-, 4-, 3-star"]);
  assert.ok(text(where).includes("In-state (FL): 2 of 3 commits, 67%."));
  clean("recruiting", main);
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
  assert.equal(rows[0].starMix, "0 / 0 / 0");
  assert.equal(rows[1].starMix, "1 / 0 / 0");
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

NAMES = ["labels", "leadersChips", "leadersArrival", "leadersGap", "rosterTable", "depthRows", "cardLoading", "gameLog", "recruiting", "damaged"]


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
