"""Phase 16, stream F: the shared kit the page streams build on, in the fake browser (tests/fakedom.py)
and as static checks on the stylesheets. Linked rank chips never open the row under them, the poll badge,
the stat-table hooks, the designed states, sheets that stack, swap in place and close on a route change,
the poller's instant back and skip-unchanged, the settings timeout, pull to refresh and the text size."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
CSS = (STATIC / "css" / "components.css").read_text(encoding="utf-8")
APP_CSS = (STATIC / "css" / "app.css").read_text(encoding="utf-8")
TOKENS = (STATIC / "css" / "tokens.css").read_text(encoding="utf-8")

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const clean = (label, node) => {
  const t = text(node);
  assert.ok(!RAW.test(t), `${label} printed ${JSON.stringify(t)}`);
  return t;
};
const text = (node) => (node ? node.textContent : "");
const key = (k) => { const e = makeEvent("keydown", { bubbles: true, key: k }); return e; };
Object.getPrototypeOf(document.body).scrollIntoView = function (opts) { this.scrolledInto = opts || true; };
const BAD = [null, undefined, NaN, Infinity, "", "abc", {}, [], true, 0.5, -3];

scenarios.chips = async () => {
  const { rankChip, rankChipPlaceholder, pollBadge } = await import(moduleUrl("ui/stat-table.js"));
  const { nationalHref, pollHref } = await import(moduleUrl("ui/national-link.js"));
  // plain chip: a span, quartile tone unchanged, the # apart so the digits carry the weight
  const plain = rankChip(41, 138);
  assert.equal(plain.tagName, "SPAN");
  assert.equal(plain.className, "rank-chip rank-chip--mid");
  assert.equal(text(plain), "#41");
  assert.equal(text(plain.querySelector(".rank-chip__hash")), "#");
  assert.equal(plain.getAttribute("title"), "41 of 138");
  // linked chip: an anchor with the href and a spoken name that says what opens
  const href = nationalHref("advanced:defense_explosiveness", { team: "Diner Tech" });
  const chip = rankChip(12, 138, { href, label: "Explosiveness allowed" });
  assert.equal(chip.tagName, "A");
  assert.equal(chip.getAttribute("href"), href);
  assert.equal(chip.className, "rank-chip rank-chip--top rank-chip--link");
  assert.equal(chip.getAttribute("aria-label"), "Explosiveness allowed: 12 of 138. Open the national list");
  const sec = rankChip(3, 16, { href: nationalHref("profile:ypp", { scope: "conference" }), label: "Yards per play" });
  assert.equal(sec.getAttribute("aria-label"), "Yards per play: 3 of 16. Open the conference list");
  assert.equal(text(rankChip(7, 138, { tie: true })), "T7");
  assert.equal(rankChip(7, 138, { tie: true, href }).getAttribute("aria-label"), "tied at 7 of 138. Open the national list");
  assert.equal(text(rankChip(5, 25, { ordinalPrefix: "" })), "5");
  assert.equal(rankChip(5, null).getAttribute("title"), "Rank 5");
  assert.equal(rankChip(9, 138, { href: "javascript:alert(1)" }).tagName, "SPAN", "only in-app links");
  for (const bad of [null, undefined, NaN, "12", {}, Infinity]) assert.equal(rankChip(bad, 138, { href }), null);
  const ghost = rankChipPlaceholder();
  assert.equal(ghost.getAttribute("aria-hidden"), "true");
  assert.ok(ghost.className.includes("rank-chip--placeholder"));
  // poll badge: its own square style, never a quartile tone
  const ap = pollBadge(12, "AP", { href: pollHref("AP", { team: "Diner Tech" }) });
  assert.equal(ap.tagName, "A");
  assert.equal(ap.className, "poll-badge poll-badge--link");
  assert.equal(text(ap), "AP12");
  assert.equal(ap.getAttribute("aria-label"), "AP poll: No. 12. Open the AP poll");
  assert.ok(!/rank-chip/.test(ap.className));
  const bare = pollBadge(3, "Coaches", { showPoll: false });
  assert.equal(bare.tagName, "SPAN");
  assert.equal(text(bare), "#3");
  assert.equal(pollBadge(null, "AP"), null);
  assert.equal(pollBadge("4", "AP"), null);
  clean("poll badge without a poll", pollBadge(8, null));
  // a click is offered to the page first; a listener that takes it stops the navigation
  const offers = [];
  const take = (event) => { offers.push(event.detail); event.preventDefault(); };
  document.addEventListener("kickoff:rank-link", take);
  const click = makeEvent("click", { bubbles: true });
  chip.dispatchEvent(click);
  assert.equal(offers.length, 1);
  assert.deepEqual(offers[0], { href, rank: 12, of: 138, label: "Explosiveness allowed" });
  assert.equal(click.defaultPrevented, true, "the sheet took it: no navigation");
  document.removeEventListener("kickoff:rank-link", take);
  const free = makeEvent("click", { bubbles: true });
  chip.dispatchEvent(free);
  assert.equal(free.defaultPrevented, false, "nobody took it: the link navigates");
};

scenarios.rows = async () => {
  const { statTable } = await import(moduleUrl("ui/stat-table.js"));
  const { metricLink } = await import(moduleUrl("ui/national-link.js"));
  const { teamLink } = await import(moduleUrl("ui/dom.js"));
  const taps = [];
  const rows = [
    { label: "Explosiveness allowed", value: 1.19, nationalRank: 41, nationalOf: 138, metric: "advanced:defense_explosiveness", rank: 41, of: 138, team: "Silver Dollar" },
    { label: "Havoc", value: 0.18, nationalRank: 9, nationalOf: 138, rank: 9, of: 138, team: "Diner Tech" },
  ];
  const table = statTable({
    columns: [
      { key: "label", label: "Stat", kind: "text" },
      { key: "value", label: "Value", format: "2f", rank: { key: "nationalRank", of: "nationalOf", link: metricLink({ team: "Swampwater Tech" }) } },
      { key: "rank", label: "Rk", kind: "rank", of: "of", link: metricLink() },
      { key: "team", label: "Team", kind: "text", render: (row) => teamLink(row.team) },
    ],
    rows,
    onRowTap: (row) => taps.push(row.label),
  });
  const trs = table.querySelectorAll("tbody tr");
  assert.equal(trs.length, 2);
  // the linked chip and the plain chip; a row with no metric gets no link
  const links = trs[0].querySelectorAll("a.rank-chip--link");
  assert.equal(links.length, 2);
  assert.equal(links[0].getAttribute("href"), "#national=advanced%3Adefense_explosiveness?team=Swampwater%20Tech");
  assert.equal(links[0].getAttribute("aria-label"), "Explosiveness allowed: 41 of 138. Open the national list");
  assert.equal(trs[1].querySelectorAll("a").length, 0, "no metric, no link");
  assert.equal(trs[1].querySelectorAll(".rank-chip").length, 2);
  // a chip, a team link or its keyboard never fire the row; the row itself still does
  links[0].click();
  links[1].click();
  trs[0].querySelector(".team-link").click();
  links[0].dispatchEvent(key("Enter"));
  assert.deepEqual(taps, [], "nothing inside the row opened the player card");
  const plainButton = document.createElement("button");
  trs[1].querySelector("td").append(plainButton);
  plainButton.click();
  plainButton.dispatchEvent(key("Enter"));
  assert.deepEqual(taps, [], "a control that does not stop the click is still not the row");
  trs[0].click();
  trs[1].dispatchEvent(key("Enter"));
  assert.deepEqual(taps, ["Explosiveness allowed", "Havoc"]);
};

scenarios.hooks = async () => {
  const { statTable, statTableSkeleton } = await import(moduleUrl("ui/stat-table.js"));
  const errors0 = errors.length;
  const rows = [{ name: "Swampwater Tech", rk: 1, v: 0.9379, st: 4, x: 3 }, null, "junk", { name: "Silver Dollar", rk: 2, v: "0.9", st: "4", x: 5 }];
  const table = statTable({
    columns: [
      { key: "rk", label: "Rk", kind: "rank", of: 138, stick: true },
      { key: "name", label: "Team", kind: "text", stick: true },
      { key: "v", label: "Rating", format: "rating100" },
      { key: "st", label: "Stars", format: "stars" },
      { key: "x", label: "Custom", render: (row) => (row.name === "Swampwater Tech" ? document.createTextNode("custom") : null) },
      { key: "x", label: "Broken", render: () => { throw new Error("boom"); } },
      { key: "x", label: "Placeholder", rank: { key: "missing", of: 138, placeholder: true } },
    ],
    rows,
    rowClass: (row) => (row.name === "Silver Dollar" ? "is-next" : null),
  });
  const trs = table.querySelectorAll("tbody tr");
  assert.equal(trs.length, 2, "null and junk rows are skipped, never drawn");
  const cells = trs[0].querySelectorAll("td");
  // stick: the frozen columns, the last one carries the edge; the second sits after the first
  assert.ok(cells[0].className.includes("stick") && !cells[0].className.includes("stick--edge"));
  assert.ok(cells[1].className.includes("stick--edge"));
  assert.equal(cells[1].style.left, "var(--stick-1, 0px)");
  assert.ok(table.querySelectorAll("thead th")[1].className.includes("stick"));
  assert.ok(table.className.includes("stat-table-wrap--stuck"));
  // formats: 94 in the top tier, 4 stars; a string is a dash, never a raw value
  assert.equal(text(cells[2]), "94");
  assert.ok(cells[2].className.includes("rating--top"));
  assert.equal(text(cells[3]), "4★");
  assert.equal(text(trs[1].querySelectorAll("td")[2]), "–");
  assert.equal(text(trs[1].querySelectorAll("td")[3]), "–");
  // render: its node; null is a dash; a throw falls back to the value and is logged
  assert.equal(text(cells[4]), "custom");
  assert.equal(text(trs[1].querySelectorAll("td")[4]), "–");
  assert.equal(text(cells[5]), "3");
  assert.ok(errors.length > errors0, "the broken hook was logged");
  // placeholder chip keeps the slot
  assert.ok(cells[6].querySelector(".rank-chip--placeholder"));
  assert.ok(trs[1].className.includes("is-next"));
  clean("table", table);
  // no measuring machinery is left behind in a page without layout
  assert.equal(typeof table.measure, "function");
  table.measure();
  // flow: false and a scroll box are never flow mode
  assert.ok(statTable({ columns: [{ key: "a", label: "A" }], rows: [], maxHeight: 400 }).className.includes("stat-table-wrap--box"));
  clean("empty table", statTable({ columns: [{ key: "a", label: "A" }], rows: null }));
  // the skeleton in the table's real shape: a head strip, rows, a label bar and short value bars
  const skel = statTableSkeleton(6, 5);
  const lines = skel.querySelectorAll(".skel-table__row");
  assert.equal(lines.length, 7);
  assert.ok(lines[0].className.includes("skel-table__row--head"));
  assert.equal(lines[1].querySelectorAll(".skel").length, 5);
  assert.equal(lines[1].querySelectorAll(".skel--label").length, 1);
  assert.equal(skel.getAttribute("aria-hidden"), "true");
  assert.equal(statTableSkeleton(NaN, "x").querySelectorAll(".skel-table__row").length, 5, "bad sizes fall back to 4 by 4");
  assert.equal(statTableSkeleton(3).querySelectorAll(".skel-table__row")[1].querySelectorAll(".skel").length, 4);
};

scenarios.states = async () => {
  const { band, subhead, stateBlock, backRow, jumpList } = await import(moduleUrl("ui/states.js"));
  installWindow();
  window.location = { hash: "#team=Diner%20Tech" };
  // stateBlock: designed, never raw values, whatever it is handed
  for (const bad of BAD) {
    clean(`stateBlock(${String(bad)})`, stateBlock({ lead: bad, detail: bad, action: bad, kind: bad }));
    clean(`subhead(${String(bad)})`, subhead(bad, { team: bad, side: bad }));
    clean(`backRow(${String(bad)})`, backRow({ label: bad }));
  }
  clean("stateBlock()", stateBlock());
  const empty = stateBlock({ lead: "No drives yet", detail: "Drives appear after kickoff." });
  assert.equal(text(empty.querySelector(".state-block__lead")), "No drives yet");
  assert.equal(text(empty.querySelector(".state-block__detail")), "Drives appear after kickoff.");
  assert.equal(empty.querySelector("button"), null);
  let tried = 0;
  const failed = stateBlock({ kind: "error", lead: "Could not load Ratings.", detail: "HTTP 503.", action: { label: "Try now", onClick: () => { tried += 1; } } });
  assert.ok(failed.className.includes("state-block--error"));
  assert.equal(failed.getAttribute("role"), "alert");
  failed.querySelector("button").click();
  assert.equal(tried, 1);
  // subhead: one style; a team title is that team's link
  const plain = subhead("Series history");
  assert.equal(plain.tagName, "H3");
  assert.equal(plain.className, "subhead");
  const team = subhead("Diner Tech", { team: "Diner Tech", side: "them" });
  assert.equal(team.className, "subhead subhead--them");
  assert.equal(team.querySelector(".team-link").dataset.team, "Diner Tech");
  assert.equal(subhead("Swampwater Tech", { level: 4 }).tagName, "H4");
  // backRow: back when the app came here itself, else the fallback page; never out of the app
  const row = backRow();
  const link = row.querySelector("a");
  assert.equal(text(link), "‹ Back");
  assert.equal(link.getAttribute("href"), "#season");
  link.click();
  assert.equal(window.location.hash, "#season", "no in-app history: the fallback");
  history.replaceState({ depth: 2 });
  window.location.hash = "#team=Diner%20Tech";
  backRow({ fallback: "program" }).querySelector("a").click();
  assert.equal(window.backs, 1, "in-app history: back");
  assert.equal(window.location.hash, "#team=Diner%20Tech");
  // bare band: no head, still named
  const bare = band({ id: "live-drives", title: "Drives", bare: true, body: () => document.createTextNode("body") });
  assert.equal(bare.querySelector(".band__head"), null);
  assert.equal(bare.getAttribute("aria-label"), "Drives");
  assert.ok(bare.className.includes("band--bare"));
  // jump list: the page's bands, and a folded one unfolds before the scroll
  const page = document.createElement("div");
  const a = band({ id: "program-tape", title: "Tale of the tape", foldable: true, body: () => "x" });
  const b = band({ id: "program-series", title: "Series", foldable: true, collapsed: true, body: () => "y" });
  page.append(a, b, band({ title: "No id", body: () => "z" }));
  const jump = jumpList(page);
  const button = jump.querySelector("button");
  assert.equal(jump.querySelector(".jump__panel").hasAttribute("hidden"), true);
  button.click();
  const items = jump.querySelectorAll(".jump__item");
  assert.deepEqual(items.map(text), ["Tale of the tape", "Series"]);
  const folded = (n) => n.dataset.collapsed ?? n.getAttribute("data-collapsed");
  assert.equal(folded(b), "true");
  const go = makeEvent("click", { bubbles: true });
  items[1].dispatchEvent(go);
  assert.equal(go.defaultPrevented, true, "a band id is not a route");
  assert.equal(folded(b), "false", "unfolded");
  assert.ok(b.scrolledInto, "scrolled to");
  assert.equal(jump.querySelector(".jump__panel").hasAttribute("hidden"), true, "the list closes");
  button.click();
  clean("jump list", jump);
  const none = jumpList(document.createElement("div"));
  none.querySelector("button").click();
  assert.equal(text(none.querySelector(".jump__empty")), "No sections on this page yet.");
};

scenarios.errorPanel = async () => {
  const { errorPanel } = await import(moduleUrl("views/common.js"));
  let retried = 0;
  const panel = errorPanel("Ratings", "HTTP 503", () => { retried += 1; });
  assert.ok(panel.className.includes("page"), "the single-column page, not the three-column Season grid");
  const bands = panel.querySelectorAll(".band");
  assert.equal(bands.length, 1, "one band");
  const retry = bands[0].querySelector("button");
  assert.ok(retry, "the retry sits inside the band");
  assert.equal(text(retry), "Try now");
  assert.equal(text(bands[0].querySelector(".band__title")), "Ratings");
  assert.equal(text(panel.querySelector(".state-block__lead")), "Could not load Ratings.");
  assert.equal(text(panel.querySelector(".state-block__detail")), "HTTP 503. The app tries again every 15 min.");
  retry.click();
  assert.equal(retried, 1);
  for (const bad of [null, undefined, NaN, {}]) clean(`errorPanel(${String(bad)})`, errorPanel(bad, bad, bad));
  assert.equal(errorPanel("X", "y").querySelector("button"), null, "no retry given, no button");
};

scenarios.poller = async () => {
  const { poller, clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  let data = { teams: ["Swampwater Tech", "Silver Dollar"] };
  const at = "2026-09-28T12:00:00Z";
  route("/api/ratings", () => ({ status: 200, body: { data, errors: [], meta: { fetched_at: at, stale: false } } }));
  const drawn = [];
  const rendered = [];
  document.addEventListener("kickoff:rendered", (e) => rendered.push(e.detail.url));
  const make = () => {
    let loading = 0;
    const statuses = [];
    const p = poller({
      url: "/api/ratings",
      refreshMs: 60000,
      onStatus: (s) => statuses.push(s),
      render: (env, container) => { drawn.push(env.data.teams.join(",")); container.replaceChildren(document.createTextNode(env.data.teams.join(","))); },
      renderError: (msg, container) => container.replaceChildren(document.createTextNode(`error ${msg}`)),
      renderLoading: () => { loading += 1; return document.createTextNode("loading"); },
    });
    return { p, loading: () => loading, statuses };
  };
  const main = document.createElement("main");
  document.body.append(main);
  const first = make();
  first.p.mount(main);
  assert.equal(first.loading(), 1, "a first visit shows the skeleton");
  await settle();
  assert.deepEqual(drawn, ["Swampwater Tech,Silver Dollar"]);
  assert.equal(rendered.length, 1);
  // the same data again: no rebuild
  await first.p.refresh();
  assert.deepEqual(drawn, ["Swampwater Tech,Silver Dollar"], "identical fetched_at and data: the page is not rebuilt");
  first.p.unmount();
  // instant back: the cached page at once, no skeleton, then a quiet refresh that changes nothing
  const calls0 = callsTo("/api/ratings");
  const second = make();
  main.replaceChildren();
  second.p.mount(main);
  assert.equal(second.loading(), 0, "no skeleton on the way back");
  assert.equal(text(main), "Swampwater Tech,Silver Dollar", "drawn before any fetch answered");
  assert.deepEqual(drawn, ["Swampwater Tech,Silver Dollar", "Swampwater Tech,Silver Dollar"]);
  await settle();
  assert.equal(callsTo("/api/ratings"), calls0 + 1, "still refreshed in the background");
  assert.equal(drawn.length, 2, "the background answer was the same: no second rebuild");
  // new data: drawn
  data = { teams: ["Swampwater Tech", "Georgia"] };
  await second.p.refresh();
  assert.deepEqual(drawn.slice(-1), ["Swampwater Tech,Georgia"]);
  second.p.unmount();
  assert.equal(timers.size, 0, "unmount leaves no timer");
  // a cached page older than the refresh interval is not reused
  await advance(61000);
  const third = make();
  third.p.mount(main);
  assert.equal(third.loading(), 1, "stale cache: the skeleton, then a fresh fetch");
  await settle();
  third.p.unmount();
  // a render that throws shows the error through renderError, never a blank page
  clearEnvelopeCache();
  const broken = poller({ url: "/api/ratings", refreshMs: 60000, render: () => { throw new Error("bad row"); }, renderError: (msg, c) => c.replaceChildren(document.createTextNode(`error ${msg}`)), renderLoading: () => document.createTextNode("loading") });
  broken.mount(main);
  await settle();
  assert.ok(text(main).startsWith("error The page could not be drawn"), text(main));
  broken.unmount();
};

scenarios.prefsTimeout = async () => {
  // /api/settings never answers: after 5 s the defaults apply, exactly as on an error (bug 8)
  let asked = 0;
  globalThis.fetch = (url, opts) => new Promise((resolve, reject) => {
    asked += 1;
    opts?.signal?.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
  });
  const prefs = await import(moduleUrl("prefs.js"));
  let done = false;
  prefs.loadPrefs().then(() => { done = true; });
  await advance(4900);
  assert.equal(done, false, "still waiting at 4.9 s");
  await advance(200);
  assert.equal(done, true, "gave up at 5 s");
  assert.equal(asked, 1);
  assert.equal(prefs.getPrefs().delaySeconds, 30);
  assert.equal(prefs.getPrefs().refreshMinutes, 15);
  assert.ok(/5 seconds/.test(prefs.prefsError()), prefs.prefsError());
  assert.equal(document.documentElement.dataset.theme, "dark");
  assert.equal(timers.size, 0);
};

scenarios.sheets = async () => {
  const { openSheet, closeAllSheets } = await import(moduleUrl("ui/remote.js"));
  const { openPlayerCard } = await import(moduleUrl("ui/player-card.js"));
  const html = document.documentElement;
  const layers = () => document.body.querySelectorAll(".sheet-layer");
  const closedWith = [];
  // swap title and body in place: the same layer, no scrim flash
  const one = openSheet({ title: "Drives", body: document.createTextNode("drives"), onClose: () => closedWith.push("one") });
  assert.ok(html.classList.contains("is-locked"), "the page underneath is locked");
  const layer = one.layer;
  one.setTitle("Plays");
  one.setBody(document.createTextNode("plays"));
  assert.equal(layers().length, 1);
  assert.equal(one.layer, layer);
  assert.equal(text(layer.querySelector(".side-sheet__title")), "Plays");
  assert.equal(layer.getAttribute("aria-label"), "Plays");
  assert.equal(layer.querySelector(".side-sheet__close").getAttribute("aria-label"), "Close Plays");
  assert.equal(text(layer.querySelector(".side-sheet__body")), "plays");
  const full = document.createElement("a");
  full.textContent = "Full page";
  one.setTools(full);
  assert.equal(text(layer.querySelector(".side-sheet__tools")), "Full page");
  // stacking: a sheet opened from a sheet lies above it; Escape closes the top one only
  const two = openSheet({ title: "National list", body: document.createTextNode("list"), tools: document.createTextNode("tools") });
  assert.ok(Number(two.layer.style.zIndex) > Number(one.layer.style.zIndex), "above the first");
  document.dispatchEvent(key("Escape"));
  assert.equal(layers().length, 1);
  assert.equal(layers()[0], layer);
  // a route change closes every sheet unless it asked to stay
  const kept = openSheet({ title: "Stays", body: "x", persist: true });
  document.dispatchEvent(new CustomEvent("kickoff:route", { detail: { id: "team", arg: "Swampwater Tech" } }));
  assert.deepEqual(closedWith, ["one"]);
  assert.equal(layers().length, 1, "the persistent one stays");
  kept.close();
  assert.equal(layers().length, 0);
  assert.ok(!html.classList.contains("is-locked"), "unlocked when the last layer closes");
  // the player card closes on a route change too (bug 10)
  openPlayerCard({ player: { name: "Test Player", number: 7 } });
  assert.ok(document.body.querySelector(".card-layer"));
  assert.ok(html.classList.contains("is-locked"));
  document.dispatchEvent(new CustomEvent("kickoff:route", { detail: { id: "season" } }));
  assert.equal(document.body.querySelector(".card-layer"), null);
  assert.ok(!html.classList.contains("is-locked"));
  // with motion: the closing layer slides out under another name and is gone within 250 ms
  window.matchMedia = () => ({ matches: false });
  const moving = openSheet({ title: "Moving", body: "x" });
  moving.close();
  assert.equal(layers().length, 0, "no longer a sheet the page or Escape can find");
  assert.equal(document.body.querySelectorAll(".sheet-layer-closing").length, 1);
  await advance(260);
  assert.equal(document.body.querySelectorAll(".sheet-layer-closing").length, 0, "removed after the slide");
  delete window.matchMedia;
  openSheet({ title: "a", body: "a" });
  openSheet({ title: "b", body: "b" });
  closeAllSheets();
  assert.equal(layers().length, 0);
  // a closed sheet ignores late swaps
  one.setTitle("late");
  one.setBody("late");
  one.update("late");
  assert.equal(text(layer.querySelector(".side-sheet__title")), "Plays");
};

scenarios.pull = async () => {
  const { installPullToRefresh, pullAllowed } = await import(moduleUrl("ui/pull-refresh.js"));
  installWindow({ scrollY: 0 });
  const main = document.createElement("main");
  document.body.append(main);
  const inside = (cls) => { const outer = document.createElement("div"); outer.className = cls; const inner = document.createElement("span"); outer.append(inner); main.append(outer); return inner; };
  const plain = inside("band");
  // guards
  assert.equal(pullAllowed(plain, 0), true);
  assert.equal(pullAllowed(plain, 12), false, "not at the top of the page");
  assert.equal(pullAllowed(plain, undefined), false);
  for (const cls of ["stat-table-wrap", "ticker", "remote", "sheet-layer", "card-layer", "player-card", "drawer", "plays"]) assert.equal(pullAllowed(inside(cls), 0), false, cls);
  const field = document.createElement("input");
  main.append(field);
  assert.equal(pullAllowed(field, 0), false, "a form field");
  const textNode = document.createTextNode("words");
  inside("ticker").append(textNode);
  assert.equal(pullAllowed(textNode, 0), false, "a text node inside the ticker");
  const modal = document.createElement("div");
  modal.setAttribute("data-modal", "");
  document.body.append(modal);
  assert.equal(pullAllowed(plain, 0), false, "an overlay is open");
  modal.remove();
  // the gesture
  let refreshed = 0;
  const pull = installPullToRefresh({ root: main, host: document.body, onRefresh: () => { refreshed += 1; return new Promise((resolve) => setTimeout(resolve, 500)); } });
  const line = pull.line;
  assert.ok(line.className.includes("pull-line"));
  const gesture = (target, to) => {
    target.dispatchEvent(touch("touchstart", target, 100));
    target.dispatchEvent(touch("touchmove", target, 100 + to));
    const pulling = line.className.includes("is-pulling");
    target.dispatchEvent(touch("touchend", target, 100 + to));
    return pulling;
  };
  assert.equal(gesture(plain, 30), true, "the line follows the finger");
  await settle();
  assert.equal(refreshed, 0, "a short pull does nothing");
  gesture(plain, 120);
  await settle();
  assert.equal(refreshed, 1, "a full pull refreshes");
  assert.ok(line.className.includes("is-busy"), "the line runs while the page asks");
  gesture(plain, 120);
  await settle();
  assert.equal(refreshed, 1, "one refresh at a time");
  await advance(600);
  assert.ok(!line.className.includes("is-busy"));
  assert.equal(gesture(inside("stat-table-wrap"), 200), false, "a sideways table never pulls");
  await settle();
  assert.equal(refreshed, 1);
  window.scrollY = 300;
  gesture(plain, 200);
  await settle();
  assert.equal(refreshed, 1, "not at the top");
  window.scrollY = 0;
  gesture(plain, -80);
  await settle();
  assert.equal(refreshed, 1, "a push up is a scroll");
  const keyed = pull.trigger();
  await settle(); // the refresh starts on the next tick, then its answer takes 500 ms
  await advance(600);
  assert.equal(await keyed, true);
  assert.equal(refreshed, 2, "the r key's path");
  pull.destroy();
  assert.equal(document.body.querySelector(".pull-line"), null);
  // a refresh that throws or never answers still frees the line
  const stuck = installPullToRefresh({ root: main, onRefresh: () => new Promise(() => {}) });
  const waiting = stuck.trigger();
  await advance(20100);
  assert.equal(await waiting, true);
  assert.ok(!stuck.line.className.includes("is-busy"));
  const failing = installPullToRefresh({ root: main, onRefresh: () => { throw new Error("down"); } });
  assert.equal(await failing.trigger(), true);
  assert.ok(errors.some((e) => e.includes("Pull to refresh")));
};

scenarios.textSize = async () => {
  const prefs = await import(moduleUrl("prefs.js"));
  const html = document.documentElement;
  assert.equal(prefs.textSize(), "standard");
  assert.equal(prefs.applyTextScale().scale, 1);
  assert.equal(html.style["--ui-scale"], "1");
  assert.equal(prefs.setTextSize("large").scale, 1.12);
  assert.equal(html.style["--ui-scale"], "1.12");
  assert.equal(html.dataset.textSize, "large");
  assert.equal(localStorage.getItem("ui:textSize"), '"large"');
  assert.equal(prefs.textSize(), "large");
  assert.equal(prefs.setTextSize("larger").scale, 1.25);
  assert.equal(prefs.setTextSize("huge").id, "standard", "an unknown size is Standard");
  localStorage.setItem("ui:textSize", "{broken");
  assert.equal(prefs.textSize(), "standard");
  // blocked storage (private mode): still applies, never throws
  globalThis.localStorage = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } };
  assert.equal(prefs.textSize(), "standard");
  assert.equal(prefs.setTextSize("larger").scale, 1.25);
  assert.equal(html.style["--ui-scale"], "1.25");
  assert.deepEqual(prefs.TEXT_SIZES.map((s) => Math.round(s.scale * 100)), [100, 112, 125]);
};

scenarios.domKit = async () => {
  const dom = await import(moduleUrl("ui/dom.js"));
  // flashChanges: only changed [data-k] cells, nothing on the first frame
  const frame = (pairs) => { const root = document.createElement("div"); for (const [k, v] of pairs) { const c = document.createElement("td"); c.dataset.k = k; c.textContent = v; root.append(c); } return root; };
  const before = frame([["us-pts", "14"], ["them-pts", "7"], ["q2", "7"]]);
  const after = frame([["us-pts", "21"], ["them-pts", "7"], ["q2", "7"], ["q3", "0"]]);
  assert.equal(dom.flashChanges(null, after), 0, "the first frame marks nothing");
  const snap = dom.snapshotKeys(before);
  assert.equal(snap.get("us-pts"), "14");
  assert.equal(dom.flashChanges(snap, after), 1);
  assert.deepEqual(after.querySelectorAll(".is-changed").map((n) => n.dataset.k), ["us-pts"]);
  assert.equal(dom.flashChanges(before, frame([["them-pts", "10"]]), { className: "flash" }), 1);
  // teamLogo: the dark variant on navy, the light one on the light theme, a tile when there is none
  const team = { school: "Diner Tech", abbreviation: "MISS", logo: "/media/logo/145?v=light", logoDark: "/media/logo/145?v=dark", color: "#14213D" };
  assert.equal(dom.teamLogo(team).getAttribute("src"), "/media/logo/145?v=dark");
  document.documentElement.dataset.theme = "light";
  assert.equal(dom.teamLogo(team, { size: 40 }).getAttribute("src"), "/media/logo/145?v=light");
  document.documentElement.dataset.theme = "dark";
  assert.equal(dom.teamLogo({ ...team, logoDark: null }).getAttribute("src"), "/media/logo/145?v=light", "the other variant before a tile");
  const tile = dom.teamLogo({ school: "Diner Tech", abbreviation: "MISS", color: "#14213D" });
  assert.equal(tile.tagName, "SPAN");
  assert.equal(text(tile), "MISS");
  assert.equal(tile.style["--logo-bg"], "#14213D");
  assert.equal(text(dom.teamLogo({ school: "Texas A&M" })), "TA");
  assert.equal(dom.teamLogo({ logo: "javascript:x" }).tagName, "SPAN", "only real image URLs");
  assert.equal(dom.teamLogo({ school: "Swampwater Tech", color: "red; x" }).style["--logo-bg"], undefined, "only a hex color");
  const img = dom.teamLogo(team, { lazy: false });
  assert.equal(img.getAttribute("loading"), null);
  const holder = document.createElement("div");
  holder.append(img);
  img.dispatchEvent(makeEvent("error"));
  assert.equal(text(holder), "MISS", "a broken image becomes the tile");
  for (const bad of [null, undefined, {}, "x", 7]) clean(`teamLogo(${String(bad)})`, dom.teamLogo(bad));
  // playerFace: headshot, then number, then team abbreviation, then initials; never a lone dash
  assert.equal(dom.playerFace({ headshotUrl: "/media/headshot/1.png", number: 7 }).tagName, "IMG");
  assert.equal(text(dom.playerFace({ number: 7 })), "7");
  assert.equal(text(dom.playerFace({ name: "Tre Harris" }, { abbr: "MISS", them: true })), "MISS");
  assert.ok(dom.playerFace({}, { them: true }).className.includes("number-badge--them"));
  assert.equal(text(dom.playerFace({ name: "Mason Hamilton" })), "MH");
  for (const bad of [null, undefined, {}, { number: NaN, name: null }]) {
    const t = text(dom.playerFace(bad));
    assert.ok(!RAW.test(t) && t !== "–", `playerFace printed ${JSON.stringify(t)}`);
  }
  const face = dom.playerFace({ headshotUrl: "/x.png", number: 3 }, { size: 44 });
  const slot = document.createElement("div");
  slot.append(face);
  face.dispatchEvent(makeEvent("error"));
  assert.equal(text(slot), "3");
  // scrollState / restoreScroll: the body and every table in it
  const body = document.createElement("div");
  const w1 = document.createElement("div"); w1.className = "stat-table-wrap";
  const w2 = document.createElement("div"); w2.className = "stat-table-wrap";
  body.append(w1, w2);
  body.scrollTop = 120; w1.scrollTop = 30; w2.scrollLeft = 55;
  const saved = dom.scrollState(body);
  body.scrollTop = 0; w1.scrollTop = 0; w2.scrollLeft = 0;
  dom.restoreScroll(body, saved);
  assert.deepEqual([body.scrollTop, w1.scrollTop, w2.scrollLeft], [120, 30, 55]);
  dom.restoreScroll(body, null);
  dom.restoreScroll(null, saved);
  // the page lock follows the open layers
  const layer = document.createElement("div");
  layer.setAttribute("data-modal", "");
  document.body.append(layer);
  dom.syncPageLock();
  assert.ok(document.documentElement.classList.contains("is-locked"));
  layer.remove();
  dom.syncPageLock();
  assert.ok(!document.documentElement.classList.contains("is-locked"));
  // el sets custom properties through setProperty
  assert.equal(dom.el("div", { style: { "--x": "4px", width: "2px" } }).style["--x"], "4px");
};
"""

NAMES = ["chips", "rows", "hooks", "states", "errorPanel", "poller", "prefsTimeout", "sheets", "pull", "textSize", "domKit"]


@needs_node
@pytest.mark.parametrize("scenario", NAMES)
def test_kit_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


# --- static checks on the stylesheets and the tools ------------------------------------------------------------


def blocks_outside_hover_media(css: str) -> list[str]:
    """Every rule with :hover that is not inside an @media (hover: hover) block."""
    found = []
    depth = 0
    hover_depth = None
    token = re.compile(r"@media[^{]*\{|\{|\}")
    pos = 0
    for match in token.finditer(css):
        chunk = css[pos:match.start()]
        pos = match.end()
        piece = match.group(0)
        if piece.startswith("@media"):
            depth += 1
            if "hover: hover" in piece.replace("hover:hover", "hover: hover") and hover_depth is None:
                hover_depth = depth
            continue
        if piece == "{":
            if ":hover" in chunk and hover_depth is None:
                found.append(chunk.strip()[-120:])
            depth += 1
        else:
            if hover_depth is not None and depth == hover_depth:
                hover_depth = None
            depth -= 1
    return found


@pytest.mark.parametrize("name", ["components.css", "app.css", "styleguide.css", "tokens.css"])
def test_no_hover_outside_the_hover_media_query(name: str) -> None:
    css = (STATIC / "css" / name).read_text(encoding="utf-8")
    assert blocks_outside_hover_media(css) == []


def test_the_hover_checker_catches_a_bare_hover() -> None:
    assert blocks_outside_hover_media(".a:hover { color: red; }") == [".a:hover"]
    assert blocks_outside_hover_media("@media (hover: hover) { .a:hover { color: red; } }\n.b { x: y; }") == []
    assert blocks_outside_hover_media("@media (max-width: 9px) { .a:hover { color: red; } }") == [".a:hover"]


def test_field_belongs_to_the_drive_bar_only() -> None:
    assert len(re.findall(r"(?m)^\.field\s*\{", CSS)) == 1
    assert re.search(r"(?m)^\.form-field\s*\{", CSS)
    assert 'class: "field"' in (STATIC / "js" / "ui" / "drive-bar.js").read_text(encoding="utf-8")


def test_remote_bar_offsets_by_the_dock_height() -> None:
    remote = re.search(r"(?m)^\.remote\s*\{([^}]*)\}", CSS)
    assert remote and "bottom: var(--dock-h, 0px)" in remote.group(1)


def test_the_stacked_spread_rule_is_scoped_to_seasons_middle_column() -> None:
    assert ".season__guide .spread--2" in APP_CSS
    assert not re.search(r"(?m)^\s*\.season \.spread--2", APP_CSS)
    season = (STATIC / "js" / "views" / "season.js").read_text(encoding="utf-8")
    assert season.count('class: "season__guide"') == 1


def test_type_tokens_follow_the_text_size() -> None:
    tokens = dict(re.findall(r"(?m)^\s*(--text-[\w-]+):\s*([^;]+);", TOKENS))
    assert {"--text-body", "--text-stat", "--text-label", "--text-caption", "--text-display", "--text-h1", "--text-chip"} <= set(tokens)
    for name, value in tokens.items():
        match = re.fullmatch(r"calc\((\d+)px \* var\(--ui-scale\)\)", value.strip())
        assert match, f"{name}: {value} does not scale"
    assert int(re.fullmatch(r"calc\((\d+)px.*", tokens["--text-body"]).group(1)) == 16
    assert re.search(r"--ui-scale:\s*1;", TOKENS)
    assert "accent-color: var(--team-accent)" in TOKENS
    assert "--sticky-top: var(--topbar)" in TOKENS
    assert "scroll-padding-top: calc(var(--sticky-top) + var(--gap))" in TOKENS
    assert "-webkit-tap-highlight-color: transparent" in TOKENS
    assert re.search(r"html\.is-locked\s*\{\s*overflow: hidden;", TOKENS)


def test_the_kit_css_is_there() -> None:
    for selector in (".rank-chip--link::after", ".poll-badge {", ".stat-table-wrap--fits", ".stat-table .stick", ".stat-table-wrap--more",
                     ".skel-table__row", ".state-block", ".subhead", ".page {", ".back-row__link", ".jump__panel", ".team-logo--mono",
                     ".pull-line", ".sheet-layer-closing", ".card-layer-closing", ".drawer.is-closing", "@keyframes skel-pulse", ".is-changed"):
        assert selector in CSS, selector
    assert "shimmer" not in CSS
    assert re.search(r"\.seg button \{\s*min-height: var\(--tap\);", CSS)
    assert re.search(r"\.setting__select, \.setting__text \{ min-height: var\(--tap\);", CSS)
    assert re.search(r"@keyframes cell-flash \{ from \{ background-color: var\(--flash\); \}", CSS)


def test_each_stream_has_its_anchor_at_the_end_of_components_css() -> None:
    anchors = re.findall(r"/\* === (\w+):", CSS)
    assert anchors == ["NV", "SEASON", "PROGRAM", "PEOPLE", "PROFILES", "SCORES", "LIVE", "DS"]
    assert CSS.rstrip().endswith("=== */"), "the anchors close the file"


def test_page_check_groups_and_size_flag() -> None:
    from tools import page_check

    assert list(page_check.ROUTE_GROUPS) == ["F", "NV", "SEASON", "PROGRAM", "PEOPLE", "PROFILES", "SCORES", "LIVE", "DS", "MYTEAMS"]  # MYTEAMS: public release Phase 5b
    assert page_check.ROUTES == list(dict.fromkeys(r for g in page_check.ROUTE_GROUPS.values() for r in g))
    assert {"season", "program", "live", "ratings", "team={US}"} <= set(page_check.ROUTES)
    # public release Phase 2: routes name the made-up league's teams and games through placeholders
    assert page_check.fill("team={US}&x={OPP}", {"US": "A%20B", "OPP": "C"}) == "team=A%20B&x=C"
    assert page_check.parse_size("820x1180") == (820, 1180)
    assert page_check.parse_size(" 1180X820 ") == (1180, 820)
    for bad in ("", "820", "wide", "8x8"):
        with pytest.raises(argparse.ArgumentTypeError):
            page_check.parse_size(bad)
    assert page_check.routes_for(None, None) == page_check.ROUTES
    assert page_check.routes_for(["F"], None) == page_check.ROUTE_GROUPS["F"]
    assert page_check.routes_for(["F"], ["live"]) == ["live"]
    with pytest.raises(SystemExit):
        page_check.routes_for(["NOPE"], None)
