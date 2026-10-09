"""Phase 16, stream NV, in the fake browser (tests/fakedom.py): the national list view and side sheet
render damaged payloads without undefined/null/NaN, ties read T, player lists keep the top 100, a gap
row and every Mudpuppy in a second tbody, poll lists use the poll badge and link to the Season polls, the
delegated handler opens a stacked sheet instead of navigating (an Biscuit Belt chip opens the conference list),
and 'Full page' is the #national route. Also: the GX-04 bar and percentile math, the matchup sheet over
a damaged payload, search's pending cue and <mark>, the glossary's folding groups and list links, and
every glossary 'National list' link names a list the server knows."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from app.services.national import resolve
from tests.fakedom import NODE, STATIC_JS, needs_node, run_scenario

SEASON = 2026

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const clean = (label, node) => {
  const t = text(node);
  assert.ok(!RAW.test(t), `${label} printed ${JSON.stringify(t.slice(0, 400))}`);
  return t;
};
const rowsIn = (tbody) => tbody.childNodes.filter((n) => n.tagName === "TR");

function teamList(extra = {}) {
  const rows = [
    { rank: 1, tied: false, team: "Georgia", conference: "Biscuit Belt", value: 8.8, isUs: false, isFocus: false, isNext: false },
    { rank: 2, tied: true, team: "Diner Tech", conference: "Biscuit Belt", value: 8.1, isUs: false, isFocus: true, isNext: true },
    { rank: 2, tied: true, team: "Swampwater Tech", conference: "Biscuit Belt", value: 8.1, isUs: true, isFocus: false, isNext: false },
    { rank: 4, tied: false, team: null, conference: null, value: null },
    { rank: 5, tied: false, team: "Ghost", conference: undefined, value: NaN, isUs: "yes" },
    null, "junk", 7,
  ];
  return {
    metric: "profile:ypp", family: "profile", key: "ypp", label: "Yards per play", format: "1f", higherIsBetter: true,
    valueLabel: "Yards per play", season: 2026, year: 2026, years: [2026, 2025], scope: "national", scopes: ["national", "conference"],
    conference: null, unit: "team", population: "FBS teams", rankSource: "local", tiesShare: true, of: 138, unranked: 2,
    rows, beyond: [], cut: null, shown: 5, us: { team: "Swampwater Tech", rank: 2, value: 8.1, of: 138 }, focus: { team: "Diner Tech", rank: 2, value: 8.1 },
    next: "Diner Tech", note: null, parts: { stats: { status: "ok" } }, ...extra,
  };
}

function playerList() {
  const rows = Array.from({ length: 100 }, (_, i) => ({ rank: i + 1, tied: false, playerId: String(i), player: `Player ${i + 1}`, position: "QB", team: i === 3 ? "Diner Tech" : "Team", conference: "X", value: 4000 - i * 10, isUs: false, isFocus: false, isNext: i === 3 }));
  const beyond = [
    { rank: 131, tied: true, playerId: "g1", player: "Mudpuppy One", position: "WR", team: "Swampwater Tech", value: 700, isUs: true },
    { rank: 131, tied: true, playerId: "g2", player: "Mudpuppy Two", position: null, team: "Swampwater Tech", value: 700, isUs: true },
    { rank: 400, playerId: "g3", player: null, team: "Swampwater Tech", value: null, isUs: true },
  ];
  return { ...teamList(), metric: "board:passing:YDS", family: "board", key: "passing:YDS", label: "Passing yards", format: "0f", unit: "player", years: [2026], rows, beyond, cut: 100, of: 358, population: "FBS players", us: { team: "Swampwater Tech", rank: 131, value: 700, of: 358, player: "Mudpuppy One", playerId: "g1" }, focus: null };
}

function pollList() {
  const rows = [
    { rank: 1, tied: false, team: "Georgia", conference: "Biscuit Belt", value: 1500, firstPlaceVotes: 50 },
    { rank: 12, tied: false, team: "Swampwater Tech", conference: "Biscuit Belt", value: 700, firstPlaceVotes: null, isUs: true },
  ];
  return { ...teamList(), metric: "poll:AP", family: "poll", key: "AP", label: "AP Top 25", format: "0f", valueLabel: "Points", scopes: ["national"], years: [2026], rankSource: "cfbd", population: "The AP Top 25", rows, of: 25, unranked: null, note: "Week 5 (regular season).", us: { team: "Swampwater Tech", rank: 12, value: 700, of: 25 }, focus: null };
}

scenarios.view = async () => {
  installWindow();
  const { createNationalView } = await import(moduleUrl("views/national.js"));
  route("/api/national/profile%3Aypp", () => envelope(teamList()));
  const statuses = [];
  const view = createNationalView({ onStatus: (s) => statuses.push(s), arg: "profile:ypp", params: { team: "Diner Tech" } });
  const host = document.createElement("main");
  document.body.append(host);
  view.mount(host);
  assert.ok(host.querySelector(".skel-table"), "a table-shaped skeleton while loading");
  await advance(50);
  const page = host.querySelector(".nat-page");
  assert.ok(page && page.querySelector(".back-row"), "a Back row on the page");
  const all = clean("view", host);
  assert.ok(all.includes("Swampwater Tech T2 of 138 · Diner Tech T2 of 138 · ties share a rank · FBS teams"), all.slice(0, 300));
  const th = host.querySelector(".nat-summary th");
  assert.equal(th.getAttribute("scope"), "row");
  assert.equal(text(th), "Yards per play");
  assert.ok(calls.some((u) => u === "/api/national/profile%3Aypp?team=Diner%20Tech"), calls.join(" "));
  const body = host.querySelector(".nat .stat-table tbody");
  const trs = rowsIn(body);
  assert.equal(trs.length, 5, "junk rows are dropped, the rest drawn");
  assert.equal(text(trs[1].querySelector(".rank-chip")), "T2");
  assert.ok(trs[1].className.includes("is-focus") && trs[1].className.includes("is-next"));
  assert.ok(text(trs[1]).includes("Next"));
  assert.ok(trs[2].className.includes("is-us"));
  assert.equal(host.querySelectorAll(".rank-chip--link").length, 0, "chips inside the list do not link");
  assert.ok(text(trs[3]).includes("–"), "a missing team and value are dashes");
  // switches: All FBS / Biscuit Belt and this season / last season, as links on the full page
  const segs = host.querySelectorAll(".nat-seg");
  assert.equal(segs.length, 2);
  assert.equal(text(segs[0]), "All FBSBiscuit Belt");
  segs[0].querySelectorAll("button")[1].click();
  assert.equal(window.location.hash, "#national=profile%3Aypp?team=Diner%20Tech&scope=conference");
  segs[1].querySelectorAll("button")[1].click();
  assert.equal(window.location.hash, "#national=profile%3Aypp?team=Diner%20Tech&year=2025");
  view.unmount();
};

scenarios.viewStates = async () => {
  installWindow();
  const { createNationalView } = await import(moduleUrl("views/national.js"));
  const host = document.createElement("main");
  document.body.append(host);
  // empty with a reason
  route("/api/national/profile%3Appg", () => envelope({ ...teamList(), rows: [], beyond: [], of: null, us: { team: "Swampwater Tech", rank: null, value: null, of: null }, focus: null, note: "Points need every FBS game." }));
  let view = createNationalView({ arg: "profile:ppg", params: {} });
  view.mount(host);
  await advance(50);
  assert.ok(clean("empty", host).includes("Points need every FBS game."));
  assert.ok(host.querySelector(".state-block"));
  view.unmount();
  // a part failed and nothing came: a designed error with Try now
  route("/api/national/rating%3Asp", () => envelope({ ...teamList(), rows: [], beyond: [], of: null, us: {}, focus: null, parts: { sp: { status: "error", error: "CFBD unavailable" } } }));
  view = createNationalView({ arg: "rating:sp", params: {} });
  view.mount(host);
  await advance(50);
  assert.ok(host.querySelector(".state-block--error") && clean("part error", host).includes("CFBD unavailable"));
  view.unmount();
  // stale: the list with its age
  route("/api/national/profile%3Aypg", () => ({ status: 200, body: { data: teamList({ metric: "profile:ypg" }), errors: [], meta: { fetched_at: new Date(now - 3 * 3600 * 1000).toISOString(), stale: true, source: "cache" } } }));
  view = createNationalView({ arg: "profile:ypg", params: {} });
  view.mount(host);
  await advance(50);
  assert.ok(host.querySelector(".band__foot--stale") && clean("stale", host).includes("Updated 3.0 h ago"));
  view.unmount();
  // the server refuses: an error panel with the reason, never a blank page
  route("/api/national/profile%3Anope", () => ({ status: 404, body: { data: null, errors: [{ code: "not_found", message: "No national list with that name." }], meta: {} } }));
  view = createNationalView({ arg: "profile:nope", params: {} });
  view.mount(host);
  await advance(50);
  assert.ok(clean("404", host).includes("No national list with that name"));
  view.unmount();
  // a malformed metric never fetches
  const before = calls.length;
  view = createNationalView({ arg: "not a metric", params: {} });
  view.mount(host);
  await advance(50);
  assert.equal(calls.length, before);
  assert.ok(clean("bad metric", host).includes("no national list with that name"));
};

scenarios.players = async () => {
  const { nationalListBody } = await import(moduleUrl("ui/national-sheet.js"));
  const node = nationalListBody({ data: playerList() });
  document.body.append(node);
  clean("players", node);
  const tbodies = node.querySelector(".stat-table").childNodes.filter((n) => n.tagName === "TBODY");
  assert.equal(tbodies.length, 3, "top 100, the gap, the Mudpuppies");
  assert.equal(rowsIn(tbodies[0]).length, 100);
  assert.ok(tbodies[1].className.includes("nat-gap"));
  assert.equal(text(tbodies[1]), "Top 100 of 358 shown · Swampwater Tech below the cut");
  assert.ok(tbodies[2].className.includes("nat-beyond"));
  const ours = rowsIn(tbodies[2]);
  assert.equal(ours.length, 3);
  assert.ok(ours.every((tr) => tr.className.includes("is-us")));
  assert.equal(text(ours[0].querySelector(".rank-chip")), "T131");
  assert.ok(text(ours[0]).includes("Mudpuppy One") && text(ours[0]).includes("WR · Swampwater Tech"));
  assert.ok(clean("summary", node.querySelector(".nat-summary")).includes("Swampwater Tech: Mudpuppy One T131 of 358"));
  assert.ok(text(rowsIn(tbodies[0])[3]).includes("Next"), "the next opponent's player is marked");
};

scenarios.poll = async () => {
  const { nationalListBody, openNationalSheet } = await import(moduleUrl("ui/national-sheet.js"));
  const node = nationalListBody({ data: pollList() });
  clean("poll", node);
  assert.equal(node.querySelectorAll(".rank-chip").length, 0, "no quartile chip on a poll");
  const badges = node.querySelectorAll(".poll-badge");
  assert.equal(badges.length, 2);
  assert.equal(text(badges[1]), "#12");
  assert.equal(node.querySelectorAll(".nat-seg").length, 0, "a poll has no conference or season switch");
  assert.ok(text(node).includes("Week 5 (regular season)."));
  route("/api/national/poll%3AAP", () => envelope(pollList()));
  const sheet = openNationalSheet({ metric: "poll:AP" });
  await advance(50);
  assert.equal(sheet.layer.querySelector(".nat-full").getAttribute("href"), "#season=polls%3AAP");
  assert.equal(text(sheet.layer.querySelector(".side-sheet__title")), "AP Top 25");
  sheet.close();
};

scenarios.sheet = async () => {
  const { installNationalLinks } = await import(moduleUrl("ui/national-sheet.js"));
  const { rankChip, pollBadge, statTable } = await import(moduleUrl("ui/stat-table.js"));
  const { nationalHref, pollHref } = await import(moduleUrl("ui/national-link.js"));
  assert.equal(installNationalLinks(document), true);
  assert.equal(installNationalLinks(document), false, "installed once");
  route("/api/national/", (url) => envelope(teamList({ scope: url.includes("scope=conference") ? "conference" : "national", conference: url.includes("scope=conference") ? "Biscuit Belt" : null })));
  // a chip inside a tappable row: the sheet opens, the row does not, the link does not navigate
  let tapped = 0;
  const table = statTable({ columns: [{ key: "label", label: "Stat", kind: "text" }, { key: "value", label: "Value", rank: { key: "rank", of: "of", link: (r) => nationalHref("profile:ypp", { team: "Diner Tech" }) } }], rows: [{ label: "Yards per play", value: 8.1, rank: 2, of: 138 }], onRowTap: () => { tapped += 1; } });
  document.body.append(table);
  const chip = table.querySelector("a.rank-chip--link");
  const click = makeEvent("click", { bubbles: true, cancelable: true });
  chip.dispatchEvent(click);
  assert.equal(tapped, 0);
  assert.ok(click.defaultPrevented, "the sheet took the click");
  await advance(50);
  let layers = document.body.querySelectorAll(".sheet-layer");
  assert.equal(layers.length, 1);
  const sheet = layers[0];
  assert.ok(sheet.querySelector(".nat-sheet"));
  assert.equal(text(sheet.querySelector(".side-sheet__title")), "Yards per play");
  assert.equal(sheet.querySelector(".nat-full").getAttribute("href"), "#national=profile%3Aypp?team=Diner%20Tech");
  assert.ok(calls.includes("/api/national/profile%3Aypp?team=Diner%20Tech"));
  clean("sheet", sheet);
  await advance(40); // two frames after the draw
  assert.ok(sheet.querySelector("tr.nat-arrived"), "the tapped team's row is marked on arrival");
  // the conference switch reloads in place
  sheet.querySelectorAll(".nat-seg")[0].querySelectorAll("button")[1].click();
  await advance(50);
  assert.ok(calls.includes("/api/national/profile%3Aypp?team=Diner%20Tech&scope=conference"));
  assert.equal(text(sheet.querySelector(".side-sheet__title")), "Yards per play, Biscuit Belt");
  assert.equal(sheet.querySelector(".nat-full").getAttribute("href"), "#national=profile%3Aypp?team=Diner%20Tech&scope=conference");
  // an Biscuit Belt chip opens the conference list, stacked above the open sheet
  const sec = rankChip(3, 16, { href: nationalHref("profile:ypp", { scope: "conference" }), label: "Yards per play" });
  sheet.append(sec);
  sec.dispatchEvent(makeEvent("click", { bubbles: true, cancelable: true }));
  await advance(50);
  layers = document.body.querySelectorAll(".sheet-layer");
  assert.equal(layers.length, 2);
  assert.ok(Number(layers[1].style.zIndex) > Number(layers[0].style.zIndex));
  assert.ok(calls.includes("/api/national/profile%3Aypp?scope=conference"));
  // a poll badge opens its poll list
  const badge = pollBadge(12, "AP", { href: pollHref("AP Top 25", { team: "Swampwater Tech" }) });
  document.body.append(badge);
  badge.dispatchEvent(makeEvent("click", { bubbles: true, cancelable: true }));
  await advance(50);
  assert.ok(calls.includes("/api/national/poll%3AAP?team=Swampwater%20Tech"));
  // a plain list link (glossary) goes through the delegated click handler
  const { listLink } = await import(moduleUrl("ui/national-sheet.js"));
  const link = listLink("rating:sp", { label: "SP+" });
  assert.equal(link.getAttribute("href"), "#national=rating%3Asp");
  assert.equal(text(link), "National list ›");
  document.body.append(link);
  const plain = makeEvent("click", { bubbles: true, cancelable: true });
  link.dispatchEvent(plain);
  assert.ok(plain.defaultPrevented);
  await advance(50);
  assert.ok(calls.includes("/api/national/rating%3Asp"));
  // a ratings-page chip is not a list link: it navigates as before
  const ratings = rankChip(4, 138, { href: "#ratings=sp" });
  document.body.append(ratings);
  const nav = makeEvent("click", { bubbles: true, cancelable: true });
  ratings.dispatchEvent(nav);
  assert.equal(nav.defaultPrevented, false);
  assert.equal(listLink("not a metric"), null);
  // Full page is a plain link: the route change closes every sheet
  document.dispatchEvent(new CustomEvent("kickoff:route", { detail: { id: "national", arg: "profile:ypp" } }));
  assert.equal(document.body.querySelectorAll(".sheet-layer").length, 0);
};

scenarios.sheetErrors = async () => {
  const { openNationalSheet } = await import(moduleUrl("ui/national-sheet.js"));
  assert.equal(openNationalSheet({ metric: "bad" }), null);
  assert.equal(openNationalSheet("#season"), null);
  route("/api/national/profile%3Aypp", () => ({ status: 503, body: { data: null, errors: [{ code: "upstream_unavailable", message: "CFBD is not answering and nothing is cached" }], meta: {} } }));
  const sheet = openNationalSheet("#national=profile%3Aypp");
  await advance(50);
  const t = clean("503", sheet.layer);
  assert.ok(t.includes("Could not load this list.") && t.includes("CFBD is not answering"));
  let retried = 0;
  route("/api/national/profile%3Aypp", () => { retried += 1; return envelope(teamList()); });
  sheet.layer.querySelector(".state-block__action").click();
  await advance(50);
  assert.equal(retried, 1);
  assert.ok(sheet.layer.querySelector(".nat .stat-table"));
  sheet.close();
  route("/api/national/profile%3Axx", () => ({ status: 404, body: { errors: [{ message: "No national list with that name." }] } }));
  const missing = openNationalSheet({ metric: "profile:xx" });
  await advance(50);
  assert.ok(clean("404", missing.layer).includes("There is no such list."));
  assert.equal(missing.layer.querySelector(".state-block__action"), null);
  missing.close();
  route("/api/national/profile%3Ayy", () => new Error("offline"));
  const offline = openNationalSheet({ metric: "profile:yy" });
  await advance(50);
  assert.ok(clean("offline", offline.layer).includes("offline"));
  offline.close();
};

scenarios.titles = async () => {
  const { listTitle, summaryText } = await import(moduleUrl("ui/national-sheet.js"));
  assert.equal(listTitle({ label: "Recruit rank", family: "recruit", key: "2026", year: 2026, season: 2026 }), "Recruit rank, 2026 class");
  assert.equal(listTitle({ label: "Yards per play", year: 2025, season: 2026 }), "Yards per play, 2025");
  assert.equal(listTitle({ label: "Blue-chip ratio", scope: "conference", conference: "Biscuit Belt", year: 2026, season: 2026 }), "Blue-chip ratio, Biscuit Belt");
  assert.equal(listTitle(null), "National list");
  for (const bad of [null, undefined, 7, "x", [], { us: null, focus: 7, rows: "x", of: NaN, population: {} }]) assert.ok(!RAW.test(summaryText(bad)), String(bad));
  assert.equal(summaryText({ us: { team: "Swampwater Tech", rank: null }, rows: [{ team: "Georgia", rank: 1 }], population: "FBS teams", rankSource: "cfbd", family: "rating" }), "Swampwater Tech not ranked · CFBD's ranking · FBS teams");
  assert.equal(summaryText({ us: { team: "Swampwater Tech", rank: null }, rows: [], population: "FBS teams" }), "FBS teams", "no rows: no rank claimed");
};

scenarios.bars = async () => {
  const { barCell, barScale, distributionStrip, median, percentile, pctlText } = await import(moduleUrl("ui/national-bars.js"));
  const { nationalListBody } = await import(moduleUrl("ui/national-sheet.js"));
  // percentile: the share of the list ranked below; ties share it; junk is null
  assert.equal(percentile(1, 138), 100);
  assert.equal(percentile(138, 138), 0);
  assert.equal(percentile(41, 138), 71);
  assert.equal(percentile(2, 3), 50);
  for (const [r, o] of [[null, 138], [5, null], [0, 138], [139, 138], [1, 1], [NaN, 5], ["3", 5]]) assert.equal(percentile(r, o), null, `${r}/${o}`);
  assert.equal(pctlText(88), "88th");
  assert.equal(pctlText(1), "1st");
  assert.equal(pctlText(null), "–");
  assert.equal(median([3, 1, 2]), 2);
  assert.equal(median([4, 1, 3, 2, null, NaN, "9"]), 2.5);
  assert.equal(median([]), null);
  // the scale: worst to best; lower-is-better reversed; missing values have no bar
  const up = barScale([10, 20, 30, null, NaN], { higher: true });
  assert.equal(up.frac(30), 1);
  assert.equal(up.frac(10), 0);
  assert.equal(up.frac(20), 0.5);
  assert.equal(up.frac(null), null);
  assert.equal(up.median, 20);
  assert.equal(up.medianFrac, 0.5);
  const down = barScale([10, 20, 30], { higher: false });
  assert.equal(down.frac(10), 1, "the lowest is the best when lower is better");
  assert.equal(down.frac(30), 0);
  const zero = barScale([400, 800], { zero: true });
  assert.equal(zero.lo, 0);
  assert.equal(zero.frac(400), 0.5);
  assert.equal(zero.medianFrac, null, "no median tick on a top-N list");
  assert.equal(barScale([5, 5]).frac(5), 1, "one value everywhere: full bars");
  assert.equal(barScale([null, "x", NaN]), null);
  assert.equal(barScale("junk"), null);
  // the cell: Swampwater Tech orange, the next opponent --opp, a dash and no bar without a value
  const us = barCell({ value: 20, isUs: true }, { scale: up, format: "1f" });
  assert.equal(us.className, "nat-bar nat-bar--us");
  assert.equal(us.style["--bar"], "50%");
  assert.equal(us.style["--mid"], "50%");
  assert.equal(text(us), "20.0");
  assert.equal(barCell({ value: 30, isNext: true }, { scale: up, format: "0f" }).className, "nat-bar nat-bar--next");
  const none = barCell({ value: null }, { scale: up, format: "1f" });
  assert.equal(none.className, "nat-bar nat-bar--none");
  assert.equal(text(none), "–");
  assert.equal(text(barCell(null, {})), "–");
  // the strip: every team a tick, Swampwater Tech's labelled, ends and median named; never on player or poll lists
  const data = teamList();
  const strip = distributionStrip({ ...data, rows: [...data.rows, { rank: 6, team: "Kansas", value: 5.0 }] }, barScale([8.8, 8.1, 8.1, 5.0]));
  clean("strip", strip);
  assert.ok(strip.querySelector(".nat-strip__tick--us") && text(strip.querySelector(".nat-strip__label")) === "Swampwater Tech 8.1");
  assert.ok(strip.querySelector(".nat-strip__tick--next"));
  assert.equal(strip.querySelectorAll(".nat-strip__tick").length, 4);
  assert.ok(strip.getAttribute("aria-label").includes("best Georgia 8.8"));
  assert.equal(distributionStrip(playerList(), barScale([1, 2, 3])), null);
  assert.equal(distributionStrip(pollList(), barScale([1, 2, 3])), null);
  assert.equal(distributionStrip({ rows: [{ value: 1 }, { value: 2 }] }, barScale([1, 2])), null, "fewer than three values");
  // wired into the list: a Pctl column, bars in the value cells, the strip above a team list
  const list = nationalListBody({ data: { ...data, rows: [...data.rows, { rank: 6, team: "Kansas", conference: "Big 12", value: 5.0 }] } });
  clean("list with bars", list);
  const heads = list.querySelectorAll("thead th").map((th) => text(th));
  assert.deepEqual(heads, ["FBS rank", "Team", "Value", "Pctl"]);
  assert.ok(list.querySelector(".nat-strip"));
  assert.ok(list.querySelectorAll(".nat-bar").length >= 5);
  const players = nationalListBody({ data: playerList() });
  assert.equal(players.querySelector(".nat-strip"), null);
  assert.ok(players.querySelector(".nat-beyond .nat-bar--us"), "the Mudpuppies below the cut get bars too");
  const polls = nationalListBody({ data: pollList() });
  assert.ok(!polls.querySelectorAll("thead th").map((th) => text(th)).includes("Pctl"), "no percentile of a top 25");
};

function matchupData() {
  return {
    season: 2026,
    away: { school: "Diner Tech", abbreviation: "MISS", mascot: "Rebels", conference: "Biscuit Belt", isUs: false, record: { wins: 3, losses: 0, ties: 0 }, conferenceRecord: { wins: 1, losses: 0 }, apRank: 8, coachesRank: 9, cfpRank: null, sp: { rating: 15.2, rank: 20 }, talent: { talent: 886.2, rank: 14, of: 138 }, form: [{ result: "W", points: 31, opponentPoints: 10, opponent: "Kentucky", homeAway: "away" }], logo: null },
    home: { school: "Swampwater Tech", abbreviation: "SWT", isUs: true, record: { wins: 3, losses: 0 }, sp: { rating: 19.4, rank: 13 }, talent: { talent: 891, rank: 10, of: 138 }, form: [] },
    rows: [
      { group: "Per game", side: "offense", label: "Yards per play", key: "ypp", metric: "profile:ypp", format: "1f", higherIsBetter: true, of: 138, away: { value: 6.4, rank: 57 }, home: { value: 8.0, rank: 5 } },
      { group: "Per game", side: "defense", label: "Yards allowed per play", key: "ypp_d", metric: "profile:ypp_d", format: "1f", higherIsBetter: false, of: 138, away: { value: 5.6, rank: 80 }, home: { value: 4.5, rank: 20 } },
    ],
    game: { status: "scheduled", kickoff: "2026-09-26T23:30:00Z", startTimeTbd: false, venue: "Swampwater Tech Memorial Stadium", neutralSite: false, homePoints: null, awayPoints: null },
    pollWeek: 5,
    parts: { stats: { status: "ok" } },
  };
}

scenarios.matchup = async () => {
  const { matchupBody, openMatchupSheet } = await import(moduleUrl("ui/matchup-sheet.js"));
  const good = matchupBody({ data: matchupData(), meta: {} });
  clean("matchup", good);
  const table = good.querySelector(".mx-table");
  assert.ok(table && table.className.includes("tt"), "the two-team table pattern");
  const chips = good.querySelectorAll(".mx-table a.rank-chip--link");
  assert.equal(chips.length, 4);
  // final pass: we sit first whenever we are in the game (here we are the home team)
  assert.equal(chips[0].getAttribute("href"), "#national=profile%3Aypp?team=Swampwater%20Tech");
  assert.equal(chips[1].getAttribute("href"), "#national=profile%3Aypp?team=Diner%20Tech");
  assert.deepEqual([...table.querySelectorAll("thead th")].map(text), ["This season", "SWT", "Edge", "MISS"]);
  assert.deepEqual([...table.querySelectorAll("tbody tr.tt__group")].map(text), ["Per game"], "the server's groups, in order");
  const cells = table.querySelectorAll("tbody tr:not(.tt__group)")[1].querySelectorAll("td");
  assert.ok(cells[1].className.includes("lead") && cells[3].className.includes("trail") && cells[3].className.includes("tt__them"), "the better number is bright; lower is better on defense rows");
  assert.ok(text(cells[1]).includes("4.5") && text(cells[1]).includes("#20"), text(cells[1]));
  assert.ok(cells[2].querySelector(".tug__bar--us"), "the tug bar leans our way");
  assert.ok(text(good.querySelector(".mx-at")) === "vs" && good.querySelector(".mx-team").className.includes("mx-team--us"), "we are first and host the game");
  assert.ok(!good.className.includes("mx--neutral"));
  assert.ok(good.querySelector(".mx-team--us"));
  assert.ok(text(good).includes("Kickoff"));
  assert.ok(good.querySelectorAll(".poll-badge--link").length === 2);
  assert.ok(good.querySelector(".mx-team a.rank-chip--link[href=\"#national=rating%3Asp?team=Diner%20Tech\"]"));
  // a damaged payload: dashes and designed blocks, never raw words
  const bad = matchupData();
  bad.away.record = { wins: "3" };
  bad.away.sp = { rating: NaN, rank: "x" };
  bad.away.talent = null;
  bad.away.form = [{ result: "W", points: null, opponent: null }, "junk", { result: "Q" }, null];
  bad.away.mascot = null;
  bad.home.conference = undefined;
  bad.home.form = "nope";
  bad.rows = [bad.rows[0], { label: null, away: null, home: { value: NaN, rank: Infinity }, format: {} }, "junk", 7, { group: 7, metric: "bad key", away: { value: "x" } }];
  bad.game = { status: "final", awayPoints: null, homePoints: 3, venue: null };
  bad.parts = { stats: { status: "error", error: "CFBD unavailable" }, sp: null };
  const damaged = matchupBody({ data: bad, meta: { stale: true, fetched_at: new Date(now - 7200 * 1000).toISOString() } });
  const t = clean("damaged matchup", damaged);
  assert.ok(t.includes("Part of this sheet did not load") && t.includes("Updated 2.0 h ago"));
  assert.equal(damaged.querySelectorAll(".mx-table tbody tr:not(.tt__group)").length, 3, "junk rows dropped, the rest drawn");
  // two other teams: the away team first, "at", and the bars in their own colors
  const others = matchupData();
  others.home.isUs = false;
  others.away.color = "#ff8800";
  others.home.color = "#44aaff";
  const theirs = matchupBody({ data: others, meta: {} });
  assert.ok(theirs.className.includes("mx--neutral") && text(theirs.querySelector(".mx-at")) === "at");
  assert.equal(theirs.style["--team-us"], "#ff8800");
  assert.equal(theirs.style["--opp"], "#44aaff");
  assert.equal(text(theirs.querySelector(".mx-table thead th.us")), "MISS");
  for (const payload of [null, {}, { data: null }, { data: { away: null, home: { school: "Swampwater Tech" }, parts: { teams: { status: "error", error: "down" } } } }, { data: { away: { school: "x".repeat(80) }, home: { school: "Swampwater Tech" } } }]) {
    const node = matchupBody(payload, { onRetry: () => {} });
    clean("empty matchup", node);
    assert.ok(node.className.includes("state-block--error"));
  }
  const none = matchupBody({ data: { ...matchupData(), rows: [] } });
  assert.ok(clean("no rows", none).includes("No season stats for these teams yet."));
  // the sheet: one fetch, the title, a 404 without a retry
  assert.equal(openMatchupSheet({ away: "Diner Tech" }), null);
  assert.equal(openMatchupSheet({ away: "", home: "Swampwater Tech" }), null);
  route("/api/matchup", (url) => (url.includes("Nowhere") ? { status: 404, body: { errors: [{ message: "No FBS team called Nowhere." }] } } : envelope(matchupData())));
  const sheet = openMatchupSheet({ away: "Diner Tech", home: "Swampwater Tech" });
  assert.equal(text(sheet.layer.querySelector(".side-sheet__title")), "Diner Tech at Swampwater Tech");
  await advance(50);
  assert.ok(calls.includes("/api/matchup?away=Diner%20Tech&home=Swampwater%20Tech"));
  assert.ok(sheet.layer.querySelector(".mx-table"));
  sheet.close();
  const missing = openMatchupSheet({ away: "Nowhere", home: "Swampwater Tech" });
  await advance(50);
  const m = clean("404 matchup", missing.layer);
  assert.ok(m.includes("There is no such matchup.") && m.includes("No FBS team called Nowhere."));
  assert.equal(missing.layer.querySelector(".state-block__action"), null);
  missing.close();
};

scenarios.search = async () => {
  const { openSearch, marked } = await import(moduleUrl("views/search.js"));
  // <mark> around every match of the query's words, never on a dash
  const m = document.createElement("span");
  m.append(marked("Diner Tech Cooks", "tech diner"));
  assert.equal(m.querySelectorAll("mark").length, 2);
  assert.equal(m.querySelectorAll("mark").map((x) => text(x)).join("|"), "Diner|Tech");
  assert.equal(marked(null, "ole"), "–");
  assert.equal(marked("Swampwater Tech", ""), "Swampwater Tech");
  assert.equal(marked("Swampwater Tech", "x"), "Swampwater Tech", "one letter marks nothing");
  route("/api/search", () => envelope({
    teams: [{ school: "Diner Tech", mascot: "Cooks", conference: "Pancake Athletic", abbreviation: "DT", logo: null, isFavorite: true }, { school: "Old Mill State", mascot: null, conference: null, abbreviation: null }],
    players: [
      { playerId: "1", name: "Ole Player", position: "QB", team: "Diner Tech", number: 7, canOpen: true, current: true },
      { playerId: "2", name: "Olen Former", position: null, team: "Somewhere", number: null, canOpen: false, current: false, toYear: 2023 },
      { playerId: "3", name: "Old Fcs", team: "FCS U", canOpen: false, current: true },
      null, "junk",
    ],
    opponent: "Diner Tech",
  }));
  const close = openSearch();
  const layer = document.body.querySelector(".sheet-layer");
  const input = layer.querySelector(".search__input");
  const results = layer.querySelector(".search__results");
  input.value = "ol";
  input.dispatchEvent(makeEvent("keydown", { key: "Enter" }));
  assert.equal(results.getAttribute("aria-busy"), "true", "pending while the request runs");
  assert.ok(results.className.includes("is-pending"));
  await advance(10);
  assert.equal(results.getAttribute("aria-busy"), null);
  assert.ok(!results.className.includes("is-pending"));
  const t = clean("search", results);
  assert.ok(!t.includes("Card"), "no jargon");
  const tags = results.querySelectorAll(".tag").map((x) => text(x));
  assert.deepEqual(tags, ["Former", "Not FBS"]);
  assert.equal(results.querySelectorAll("button.search__item .search__go").length, 3, "a chevron on every openable row");
  assert.equal(results.querySelectorAll(".search__item--quiet .search__go").map((x) => text(x)).join(""), "", "never on a row that opens nothing");
  assert.ok(results.querySelector(".search__star") && results.querySelector(".search__item--fav"));
  assert.ok(results.querySelectorAll("mark").length >= 4);
  assert.ok(results.querySelector(".team-logo"), "the logo tile when there is no logo URL");
  // a failed search says so, and the dimming ends
  route("/api/search", () => new Error("offline"));
  input.value = "fl";
  input.dispatchEvent(makeEvent("keydown", { key: "Enter" }));
  await advance(10);
  assert.ok(clean("failed search", results).includes("Search failed: offline"));
  assert.equal(results.getAttribute("aria-busy"), null);
  // Phase 17 #8: an empty box explains search and offers examples; a near miss offers "Did you mean"
  input.value = "";
  input.dispatchEvent(makeEvent("input"));
  await advance(300);
  const help = clean("search help", results);
  assert.ok(help.includes("Find a team or a player.") && help.includes("jersey number") && help.includes("Search every player"), help);
  assert.ok(results.querySelectorAll(".search__try-btn").length >= 1);
  let asked = null;
  route("/api/search", (url) => {
    asked = url;
    return envelope({ teams: [], players: [], suggest: ["Ole Player", "", null, 5], opponent: "Diner Tech" });
  });
  results.querySelector(".search__try-btn").click();
  await advance(10);
  assert.ok(asked && asked.includes("q="), "an example runs a search");
  const did = results.querySelectorAll(".search__try-btn").map((x) => text(x));
  assert.deepEqual(did, ["Ole Player"], "only real names are offered");
  assert.ok(text(results).includes("Did you mean"));
  results.querySelector(".search__try-btn").click();
  assert.equal(input.value, "Ole Player", "a suggestion fills the box and searches");
  close();
};

scenarios.glossary = async () => {
  installWindow();
  const folded = (b) => b.dataset.collapsed ?? b.getAttribute("data-collapsed");
  document.getElementById = (id) => document.querySelector(`#${id}`);
  Object.getPrototypeOf(document.body).scrollIntoView = function () { this.scrolled = true; };
  const { GLOSSARY } = await import(moduleUrl("glossary-data.js"));
  const { createGlossaryView, groupId } = await import(moduleUrl("views/glossary.js"));
  localStorage.setItem(`band:${groupId("Defense")}`, "true"); // the reader folded Defense earlier
  const host = document.createElement("main");
  document.body.append(host);
  let view = createGlossaryView({});
  view.mount(host);
  clean("glossary", host);
  const groups = host.querySelectorAll(".gloss-groups section.band");
  assert.ok(groups.length >= 9 && groups.every((b) => b.className.includes("band--foldable")), "every group band folds");
  const defense = host.querySelector(`#${groupId("Defense")}`);
  assert.equal(folded(defense), "true", "the remembered fold holds");
  const intro = host.querySelector("#glossary-search");
  const jumps = intro.querySelectorAll(".band__body .gloss__jump a");
  assert.ok(jumps.length >= 9 && intro.querySelector(".band__head .gloss__jump") === null, "jump links in the body, not the head");
  jumps.find((a) => text(a) === "Defense").click();
  assert.equal(folded(defense), "false", "a jump unfolds its group");
  assert.ok(defense.scrolled);
  const withList = GLOSSARY.filter((e) => typeof e.metric === "string");
  assert.equal(host.querySelectorAll(".gloss__entry a.national-link").length, withList.length);
  const sp = host.querySelector("#gloss-sp-plus a.national-link");
  assert.equal(sp.getAttribute("href"), "#national=rating%3Asp");
  view.unmount();
  // a search marks the matches and never hides one inside a folded group
  localStorage.setItem(`band:${groupId("Defense")}`, "true");
  view = createGlossaryView({});
  view.mount(host);
  const input = host.querySelector(".gloss__search");
  input.value = "havoc";
  input.dispatchEvent(makeEvent("input"));
  const found = host.querySelector(`#${groupId("Defense")}`);
  assert.equal(folded(found), "false");
  assert.equal(localStorage.getItem(`band:${groupId("Defense")}`), "true", "the search does not change the remembered fold");
  assert.ok(host.querySelectorAll(".gloss mark").length >= 3);
  input.value = "zzzz";
  input.dispatchEvent(makeEvent("input"));
  assert.ok(clean("no match", host).includes('Nothing matches "zzzz"'));
  view.unmount();
  // #glossary=<id> opens the entry's group even when folded
  view = createGlossaryView({ focusId: "havoc" });
  view.mount(host);
  assert.equal(folded(host.querySelector(`#${groupId("Defense")}`)), "false");
  assert.ok(host.querySelector("#gloss-havoc").className.includes("is-focus"));
};
"""

NAMES = ["view", "viewStates", "players", "poll", "sheet", "sheetErrors", "titles", "bars", "matchup", "search", "glossary"]


@needs_node
@pytest.mark.parametrize("scenario", NAMES)
def test_national_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_app_registers_the_route_and_the_handler() -> None:
    app = (STATIC_JS / "app.js").read_text(encoding="utf-8")
    assert "national: (opts, arg, focus, params) => createNationalView({ ...opts, arg, params })" in app
    assert "installNationalLinks(document)" in app
    assert 'national: ["National list"' not in app, "the placeholder is gone"


DUMP = "const m = await import(process.argv[1]); console.log(JSON.stringify(m.GLOSSARY.map((e) => [e.id, e.metric ?? null])));"


@needs_node
def test_every_glossary_list_link_names_a_registry_metric() -> None:
    done = subprocess.run([NODE, "--input-type=module", "-e", DUMP, (STATIC_JS / "glossary-data.js").resolve().as_uri()], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    entries = json.loads(done.stdout)
    linked = [(entry_id, metric) for entry_id, metric in entries if metric is not None]
    assert len(linked) >= 40
    for entry_id, metric in linked:
        assert resolve(metric, SEASON) is not None, (entry_id, metric)


def test_glossary_has_the_labels_other_streams_introduce() -> None:
    """LRP-06 short column names, the Live edge column and key-play badges, NV's own list columns."""
    source = (STATIC_JS / "glossary-data.js").read_text(encoding="utf-8")
    for label in ("Cmp", "Att", "Y/A", "Car", "Y/C", "Rec", "Y/R", "Tkl", "Hurries", "No", "Inside 20", "Touchbacks", "Nat", "Edge to", "Pctl", "1st", "TD", "TO", "Big play", "Sack", "4th down", "Flag 15", "Recruit rank", "Blue-chip ratio", "Returning passing usage"):
        assert f'"{label}"' in source, label
