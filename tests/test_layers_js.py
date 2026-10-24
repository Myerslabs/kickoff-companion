"""Item 6, steps B, C and D (owner 2026-10-11), in the fake browser and in the source.

B. From 700 px up every side sheet and the player card start under the top bar (--layer-top, measured from the bar), and
   the top bar sits above them, so the Menu, Search and the tabs keep working; a Menu tap closes every open layer, then
   opens the drawer. The phone keeps full-screen sheets; the board (no top bar) keeps them at the top.
C. Nothing opens by itself: "Not loaded yet" is a note on the Pre-Game Program and a dot on the status pill whose card
   lists the same items; a guest's welcome is a note on the page the guest lands on. Neither shows on the board.
D. Each non-inline sheet, the player card and the menu drawer take one history entry (copying the router's state), so Back
   closes the top layer and the page stays; closing one by hand takes its entry back out; stacked layers unwind one per
   Back; a page change from a layer reuses its entry, and an entry left behind is stepped over. One Escape closes one
   layer; the drawer keeps Tab inside itself and hands focus back to the Menu button."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.fakedom import PROJECT_ROOT, needs_node, run_scenario

STATIC = PROJECT_ROOT / "static"
JS = STATIC / "js"

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object \w+\]/;
const text = (node) => (node ? node.textContent : "");
const key = (k, extra = {}) => {
  const event = Object.assign(makeEvent("keydown", { bubbles: true, cancelable: true, key: k }), extra);
  document.dispatchEvent(event);
  return event;
};
const goRoute = (id) => document.dispatchEvent(new CustomEvent("kickoff:route", { detail: { id } }));
const sheets = () => document.body.querySelectorAll(".sheet-layer");
const cards = () => document.body.querySelectorAll(".card-layer");

/** A browser's history for one page: entries with their state and address, Back and Forward that land a moment later with
 *  popstate (and hashchange when the address changes), a hash setter that pushes, and location.replace. The module's own
 *  steps are logged in nav.steps; the reader's are nav.userBack() and nav.userForward(). */
function browser(hash = "#season", state = { depth: 2, scrollY: 300 }, keepStateOnReplace = false) {
  const win = installWindow();
  const entries = [{ state, url: hash }];
  let at = 0;
  const fire = (type, extra = {}) => win.dispatchEvent({ type, ...extra, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } });
  const nav = { win, entries, steps: [], log: [], get at() { return at; } };
  const loc = {
    current: hash,
    get hash() { return this.current; },
    set hash(value) { go(value, false); },
    replace(value) { go(value, true); },
  };
  function go(value, replace) {
    const url = `#${String(value).replace(/^#/, "")}`;
    if (url === loc.current) return;
    if (replace) entries[at] = { state: keepStateOnReplace ? entries[at].state : null, url }; // WebKit keeps the entry's state on a replace, Chromium clears it
    else {
      entries.splice(at + 1);
      entries.push({ state: null, url });
      at += 1;
    }
    loc.current = url;
    nav.log.push(`${replace ? "replace" : "push"} ${url}`);
    setTimeout(() => fire("hashchange"), 0);
  }
  const step = (delta) => setTimeout(() => {
    const next = at + delta;
    if (next < 0 || next >= entries.length) return;
    const old = loc.current;
    at = next;
    loc.current = entries[at].url;
    fire("popstate", { state: entries[at].state });
    if (loc.current !== old) fire("hashchange");
  }, 0);
  const h = {
    get state() { return entries[at].state; },
    get length() { return entries.length; },
    pushState(s) { entries.splice(at + 1); entries.push({ state: s, url: loc.current }); at += 1; },
    replaceState(s) { entries[at] = { state: s, url: loc.current }; },
    back() { nav.steps.push(-1); step(-1); },
    forward() { nav.steps.push(1); step(1); },
    go(d) { nav.steps.push(d); step(d); },
  };
  nav.userBack = () => step(-1);
  nav.userForward = () => step(1);
  nav.loc = loc;
  win.location = loc;
  win.history = h;
  globalThis.history = h;
  return nav;
}

/** Let every queued history step land (each popstate may queue one more). */
async function land() {
  for (let i = 0; i < 6; i += 1) {
    await settle();
    await advance(1);
  }
  await settle();
}

async function openOne(title = "A sheet", extra = {}) {
  const { openSheet } = await import(moduleUrl("ui/remote.js"));
  return openSheet({ title, body: () => document.createElement("p"), ...extra });
}

async function openCard() {
  const { openPlayerCard } = await import(moduleUrl("ui/player-card.js"));
  return openPlayerCard({ player: { id: 7, name: "Al One", position: "QB", jersey: 7 }, loading: true });
}

scenarios.sheetBack = async () => {
  const nav = browser();
  const sheet = await openOne();
  assert.equal(nav.entries.length, 2, "one entry for the sheet");
  const state = nav.entries[1].state;
  assert.equal(state.depth, 2, "the router's depth is copied");
  assert.equal(state.scrollY, 300, "and the page's scroll memory");
  assert.ok(typeof state.layer === "string" && state.layer.length > 0);
  assert.deepEqual(state.layers, [state.layer]);
  assert.equal(nav.entries[1].url, "#season", "the same page");
  assert.ok(!document.documentElement.classList.contains("is-locked"), "item 8: the page scrolls with a sheet; only the menu locks it");
  nav.userBack();
  await land();
  assert.equal(sheets().length, 0, "Back closed the sheet");
  assert.equal(nav.loc.hash, "#season", "and the page stayed");
  assert.equal(nav.at, 0);
  assert.deepEqual(nav.steps, [], "Back already took the entry: no second step");
  assert.ok(!document.documentElement.classList.contains("is-locked"));
  assert.ok(sheet.layer && !sheet.layer.isConnected);
};

scenarios.sheetCloseByHand = async () => {
  const nav = browser();
  for (const how of ["button", "escape", "scrim", "handle"]) {
    const sheet = await openOne(`Closed by ${how}`);
    assert.equal(nav.at, 1);
    if (how === "button") sheet.layer.querySelector(".side-sheet__close").click();
    else if (how === "escape") assert.ok(key("Escape").defaultPrevented, "the sheet took the Escape");
    else if (how === "scrim") sheet.layer.querySelector(".sheet-layer__scrim").click();
    else sheet.close();
    await land();
    assert.equal(sheets().length, 0, how);
    assert.equal(nav.at, 0, `${how}: its entry went back out`);
    assert.equal(nav.loc.hash, "#season", `${how}: the page stayed`);
  }
  assert.deepEqual(nav.steps, [-1, -1, -1, -1], "one step back per close, never two");
};

scenarios.stacked = async () => {
  const nav = browser();
  await openOne("Team");
  const close = await openCard();
  assert.equal(nav.entries.length, 3, "one entry each");
  assert.deepEqual(nav.entries[2].state.layers.length, 2);
  assert.equal(close.layer.style.zIndex > sheets()[0].style.zIndex, true, "the card lies above the sheet");
  // one Escape closes only the top layer
  key("Escape");
  await land();
  assert.equal(cards().length, 0, "the card closed");
  assert.equal(sheets().length, 1, "the sheet stayed");
  assert.equal(nav.at, 1);
  await openCard();
  assert.equal(nav.at, 2);
  nav.userBack();
  await land();
  assert.equal(cards().length, 0, "the first Back closes the card");
  assert.equal(sheets().length, 1);
  assert.equal(nav.at, 1);
  nav.userBack();
  await land();
  assert.equal(sheets().length, 0, "the second the sheet");
  assert.equal(nav.at, 0);
  assert.equal(nav.loc.hash, "#season");
  assert.deepEqual(nav.steps, [-1], "only the Escape's own step");
};

scenarios.routeCloses = async () => {
  const nav = browser();
  await openOne();
  await openCard();
  goRoute("ratings");
  await land();
  assert.equal(sheets().length + cards().length, 0, "a page change closes every layer");
  assert.deepEqual(nav.steps, [], "and leaves the history to the page change");
};

scenarios.goTo = async () => {
  const nav = browser();
  const { goTo, closeLayers, openLayerCount } = await import(moduleUrl("ui/layers.js"));
  goTo("ratings");
  await land();
  assert.deepEqual(nav.log, ["push #ratings"], "no layer: an ordinary page change");
  nav.win.history.replaceState({ depth: 3 }); // the router numbers the new page
  await openOne();
  assert.equal(nav.entries.length, 3);
  goTo("#leaders");
  await land();
  assert.deepEqual(nav.log, ["push #ratings", "replace #leaders"], "from a layer: the new page takes the layer's entry");
  assert.deepEqual(nav.entries.map((e) => e.url), ["#season", "#ratings", "#leaders"], "no dead entry left behind");
  assert.equal(sheets().length, 0);
  assert.equal(openLayerCount(), 0);
  nav.userBack();
  await land();
  assert.equal(nav.loc.hash, "#ratings", "Back from the new page lands on the page the sheet was over");
  assert.equal(nav.at, 1);
  // the page already showing: the layers close and their entry goes
  await openOne();
  goTo("#ratings");
  await land();
  assert.equal(sheets().length, 0);
  assert.equal(nav.at, 1);
  assert.equal(nav.loc.hash, "#ratings");
  // closeLayers unwinds stacked layers in one step
  await openOne();
  await openCard();
  assert.equal(nav.at, 3);
  closeLayers();
  assert.equal(sheets().length + cards().length, 0, "they close at once");
  await land();
  assert.equal(nav.at, 1, "and their two entries go in one step");
  assert.deepEqual(nav.steps, [-1, -2]);
};

scenarios.goToKeepsState = async () => {
  // Safari: location.replace leaves the layer's marker on the new page's entry; the next open must not step Back over it
  const nav = browser("#season", { depth: 2, scrollY: 300 }, true);
  const { goTo, closeLayers, openLayerCount } = await import(moduleUrl("ui/layers.js"));
  await openOne();
  goTo("#newspaper");
  await land();
  assert.equal(nav.loc.hash, "#newspaper");
  assert.ok(Array.isArray(nav.entries[nav.at].state?.layers), "the entry still carries the old marker, as WebKit leaves it");
  const steps = nav.steps.length;
  closeLayers(); // what opening the menu does first
  await land();
  assert.equal(nav.steps.length, steps, "no history step: the marker names a layer that is gone");
  assert.equal(nav.loc.hash, "#newspaper", "the page stays where it is");
  await openOne();
  closeLayers();
  await land();
  assert.equal(nav.loc.hash, "#newspaper", "a layer opened and closed on the page lands back on the page");
  assert.equal(openLayerCount(), 0);
};

scenarios.deadEntry = async () => {
  const nav = browser();
  await openOne();
  nav.loc.hash = "#ratings"; // a link the layer did not catch: the new page goes on top of the sheet's entry
  nav.win.history.replaceState({ depth: 3 }); // the router numbers it
  goRoute("ratings");
  await land();
  assert.equal(sheets().length, 0);
  assert.equal(nav.entries.length, 3);
  nav.userBack(); // lands on the closed sheet's entry: stepped over, on to the page under it
  await land();
  assert.deepEqual(nav.steps, [-1]);
  assert.equal(nav.at, 0);
  assert.equal(nav.loc.hash, "#season");
  nav.userForward(); // the other way: stepped over forward, to the page after it
  await land();
  assert.deepEqual(nav.steps, [-1, 1]);
  assert.equal(nav.at, 2);
  assert.equal(nav.loc.hash, "#ratings");
};

scenarios.deferredPush = async () => {
  const nav = browser();
  const first = await openOne("Search");
  first.close(); // a result in Search: the sheet closes ...
  await settle(); // (its step back is queued now)
  const next = await openOne("Team"); // ... and the next layer opens before that step lands
  assert.equal(nav.entries.length, 2, "its entry waits for the step");
  await land();
  assert.equal(nav.at, 1, "then goes in, on the page's own entry");
  assert.equal(nav.entries[1].state.layer !== undefined, true);
  assert.ok(next.layer.isConnected, "and the new layer stays open");
  nav.userBack();
  await land();
  assert.ok(!next.layer.isConnected, "Back closes it");
  assert.equal(nav.at, 0);
  // a layer closed in the same moment another opened keeps its entry: Back steps over it
  const { openSheet } = await import(moduleUrl("ui/remote.js"));
  const a = openSheet({ title: "A", body: "a" });
  a.close();
  const b = openSheet({ title: "B", body: "b" }); // in the same tap: Search's result opening a team
  await land();
  assert.equal(nav.at, 2, "A's entry stayed under B's");
  nav.userBack();
  await land();
  assert.ok(!b.layer.isConnected);
  assert.equal(nav.at, 0, "one Back: B closed and A's empty entry stepped over");
  assert.equal(nav.loc.hash, "#season");
};

scenarios.persistAndInline = async () => {
  const nav = browser();
  const kept = await openOne("Kept", { persist: true });
  assert.equal(nav.entries.length, 1, "a sheet that outlives page changes takes no entry");
  const host = document.createElement("div");
  document.body.append(host);
  await openOne("Inline", { inline: true, mount: host });
  assert.equal(nav.entries.length, 1, "nor does the styleguide's inline sample");
  goRoute("ratings");
  assert.ok(kept.layer.isConnected, "persist keeps it over a page change");
  const { closeLayers } = await import(moduleUrl("ui/layers.js"));
  closeLayers();
  assert.ok(!kept.layer.isConnected, "the Menu closes it like every layer");
  await land();
  assert.deepEqual(nav.steps, []);
};

scenarios.leftover = async () => {
  const nav = browser("#season", { depth: 1 });
  nav.win.history.pushState({ depth: 1, layer: "layer-old-1", layers: ["layer-old-1"], layerAt: 5 }); // left by the page before a reload
  const { stepOverLeftovers } = await import(moduleUrl("ui/layers.js"));
  assert.equal(stepOverLeftovers(), true, "a reload on a layer's entry, its layer gone");
  await land();
  assert.deepEqual(nav.steps, [-1]);
  assert.equal(nav.at, 0);
  assert.equal(stepOverLeftovers(), false, "the page's own entry: nothing to do");
};

scenarios.placeLayers = async () => {
  const { placeLayers } = await import(moduleUrl("ui/layers.js"));
  const root = document.documentElement;
  assert.equal(placeLayers(), 0, "no top bar: the layers start at the top");
  assert.equal(root.style["--layer-top"], "0px");
  const bar = document.createElement("header");
  bar.className = "topbar";
  bar.getBoundingClientRect = () => ({ top: 40, bottom: 96.4, height: 56.4, left: 0, right: 820, width: 820 });
  document.body.append(bar);
  assert.equal(placeLayers(), 96, "under the bar, wherever it sits (a demo banner above it here)");
  assert.equal(root.style["--layer-top"], "96px");
  document.body.classList.add("board-mode");
  assert.equal(placeLayers(), 0, "the board hides the bar");
  document.body.classList.remove("board-mode");
  bar.getBoundingClientRect = () => ({ top: 0, bottom: NaN, height: 0 });
  assert.equal(placeLayers(), 0, "a bar with no box");
  bar.getBoundingClientRect = () => { throw new Error("detached"); };
  assert.equal(placeLayers(), 0);
};

/** The shell on the page, with a fake history under it. The Pre-Game Program is a tile of the menu's opening level, so
 *  the menu opens there (on a page inside a group it opens on that group's list: scenarios.drawerLevels). */
async function page(hash = "#program", current = "program") {
  const nav = browser(hash, { depth: 2 });
  const navigated = [];
  const { shell } = await import(moduleUrl("ui/shell.js"));
  const app = shell({ current, onNavigate: (id) => navigated.push(id), onSearch: () => {} });
  document.body.append(app.root);
  const menu = app.root.querySelector(".menu-button");
  const drawer = app.root.querySelector(".drawer");
  const open = () => drawer.hasAttribute("open");
  return { nav, app, menu, drawer, open, navigated };
}

scenarios.drawerBack = async () => {
  const { nav, menu, drawer, open } = await page();
  menu.click();
  assert.ok(open() && drawer.hasAttribute("data-modal"));
  assert.equal(menu.getAttribute("aria-expanded"), "true");
  assert.equal(nav.entries.length, 2, "the menu takes one entry");
  assert.ok(drawer.contains(document.activeElement), "focus goes into the menu");
  nav.userBack();
  await land();
  assert.ok(!open(), "Back closes the menu");
  assert.equal(nav.loc.hash, "#program", "and the page stays");
  assert.equal(document.activeElement, menu, "focus comes back to the Menu button");
  assert.ok(!document.documentElement.classList.contains("is-locked"), "the page scrolls again");
  // closed by hand: its entry goes back out
  menu.click();
  drawer.querySelector('[aria-label="Close menu"]').click();
  await land();
  assert.ok(!open());
  assert.equal(nav.at, 0);
  assert.equal(document.activeElement, menu);
  assert.deepEqual(nav.steps, [-1]);
  // a page change closes it and leaves the history to the page change
  menu.click();
  goRoute("ratings");
  assert.ok(!open(), "kickoff:route closes it");
  menu.click();
  nav.win.dispatchEvent({ type: "hashchange" });
  assert.ok(!open(), "so does any hashchange");
  // the menu button toggles it shut
  menu.click();
  assert.ok(open());
  menu.click();
  assert.ok(!open());
};

scenarios.drawerItem = async () => {
  const { nav, menu, drawer, open, navigated } = await page();
  menu.click();
  await land();
  drawer.querySelector('.drawer__item[data-entry="stats"]').click(); // the layout pass: Leaders is in the Stats group
  await land();
  const item = [...drawer.querySelectorAll(".drawer__item")].find((a) => a.getAttribute("href") === "#leaders");
  item.click();
  assert.ok(!open());
  assert.deepEqual(navigated, ["leaders"], "the app goes to the page (app.js onNavigate takes the menu's entry)");
  await land();
  assert.deepEqual(nav.steps, [], "the menu's entries are left for the new page");
  assert.equal(document.activeElement, menu, "focus is not left on a hidden item");
};

scenarios.drawerTab = async () => {
  const { menu, drawer } = await page();
  menu.click();
  const stops = [...drawer.querySelector(".drawer__panel").querySelectorAll("a, button")].filter((n) => !n.hasAttribute("hidden")); // "‹" hides on the opening level
  const first = stops[0];
  const last = stops[stops.length - 1];
  assert.equal(first.getAttribute("aria-label"), "Close menu", "the × first");
  last.focus();
  assert.ok(key("Tab").defaultPrevented);
  assert.equal(document.activeElement, first, "Tab from the last item wraps to the ×");
  assert.ok(key("Tab", { shiftKey: true }).defaultPrevented);
  assert.equal(document.activeElement, last, "Shift+Tab from the × wraps to the last item");
  stops[2].focus();
  assert.ok(!key("Tab").defaultPrevented, "inside the list the browser moves focus itself");
  document.body.focus();
  key("Tab");
  assert.equal(document.activeElement, first, "focus that got out comes back in");
  menu.click(); // closes it
  last.focus();
  assert.ok(!key("Tab").defaultPrevented, "a closed menu traps nothing");
};

scenarios.menuOverSheet = async () => {
  const { nav, menu, open } = await page();
  await openOne("Team");
  await openCard();
  assert.equal(nav.at, 2);
  menu.click();
  assert.equal(sheets().length + cards().length, 0, "the Menu closes every open layer ...");
  assert.ok(open(), "... then opens the menu");
  assert.equal(nav.at, 2, "the menu's entry waits for theirs to go");
  await land();
  assert.deepEqual(nav.steps, [-2], "both layers' entries in one step");
  assert.equal(nav.at, 1, "then the menu's own entry");
  assert.ok(open());
  nav.userBack();
  await land();
  assert.ok(!open(), "Back closes the menu");
  assert.equal(nav.at, 0);
  assert.equal(nav.loc.hash, "#program");
};

// The layout pass (owner 2026-10-22, boards 2 and 3): one level at a time. On a page inside a group the menu opens on that
// group's list with the page marked; each level below the opening one takes its own entry, so Back, Escape and "‹" go up
// one level; × closes the whole menu and gives back every entry.
scenarios.drawerLevels = async () => {
  const { nav, menu, drawer, open } = await page("#season", "season");
  menu.click();
  await land();
  assert.ok(open());
  assert.equal(drawer.querySelector(".drawer__level b").textContent, "My Teams", "Season sits in My Teams: the menu opens there");
  assert.equal(drawer.querySelector(".drawer__item.is-marked").dataset.entry, "season", "with Season marked");
  assert.equal(nav.entries.length, 3, "the menu's entry and its list's");
  assert.ok(!drawer.querySelector(".drawer__back").hasAttribute("hidden"), "‹ Menu at the head");
  nav.userBack();
  await land();
  assert.ok(open(), "Back goes up one level ...");
  assert.ok(drawer.querySelector(".drawer__tiles"), "... to the opening level");
  assert.ok(drawer.querySelector(".drawer__back").hasAttribute("hidden"));
  drawer.querySelector('.drawer__item[data-entry="game"]').click();
  await land();
  assert.equal(drawer.querySelector(".drawer__level b").textContent, "This week's game");
  assert.equal(drawer.querySelectorAll(".drawer__item--wide").length, 14, "the matchup's fourteen tables, each opening wide");
  assert.deepEqual(drawer.querySelectorAll(".drawer__item--level").map((a) => a.dataset.entry), ["ingame", "afterfinal"], "and two lists one level down");
  assert.equal(drawer.querySelectorAll(".drawer__heading").map((h) => h.textContent).join("|"), "The matchup|More");
  drawer.querySelector('.drawer__item[data-entry="ingame"]').click();
  await land();
  assert.equal(drawer.querySelectorAll(".drawer__item--wide").length, 12, "In Game's twelve panels");
  assert.equal(drawer.querySelector(".drawer__back span").textContent, "This week's game", "‹ names the list above");
  key("Escape");
  await land();
  assert.equal(drawer.querySelector(".drawer__level b").textContent, "This week's game", "Escape goes up one level");
  drawer.querySelector(".drawer__back").click();
  await land();
  assert.ok(drawer.querySelector(".drawer__tiles"), "‹ goes up one level");
  drawer.querySelector('.drawer__item[data-entry="advanced"]').click();
  await land();
  drawer.querySelector('[aria-label="Close menu"]').click();
  await land();
  assert.ok(!open(), "× closes the whole menu");
  assert.equal(nav.at, 0, "and every entry it took goes back out");
  assert.equal(nav.loc.hash, "#season");
};

scenarios.escapeOrder = async () => {
  const { app, menu, open } = await page();
  menu.click();
  await openOne("Search"); // e.g. a sheet that opened over the menu
  let event = key("Escape");
  assert.ok(event.defaultPrevented);
  assert.equal(sheets().length, 0, "the first Escape closes the sheet ...");
  assert.ok(open(), "... and only the sheet");
  key("Escape");
  assert.ok(!open(), "the next one closes the menu");
  // the status card is above everything: it goes first
  await openOne("Team");
  app.root.querySelector(".pill--button").click();
  assert.ok(document.body.querySelector(".status-card"));
  event = key("Escape");
  assert.ok(event.defaultPrevented);
  assert.equal(document.body.querySelector(".status-card"), null, "the status card closed");
  assert.equal(sheets().length, 1, "the sheet under it stayed");
  key("Escape");
  assert.equal(sheets().length, 0);
  assert.ok(!key("Escape").defaultPrevented, "nothing open: Escape is left alone");
};

scenarios.inlineDrawer = async () => {
  const nav = browser();
  const { shell } = await import(moduleUrl("ui/shell.js"));
  const sample = shell({ current: "program", inlineDrawer: true });
  document.body.append(sample.root);
  sample.openDrawer();
  const drawer = sample.root.querySelector(".drawer");
  assert.ok(drawer.hasAttribute("open"));
  assert.ok(!drawer.hasAttribute("data-modal") && drawer.getAttribute("aria-modal") === null, "a sample, not a layer");
  assert.equal(nav.entries.length, 1, "no history entry");
  assert.ok(!key("Tab").defaultPrevented, "no Tab trap on the styleguide page");
  key("Escape");
  assert.ok(drawer.hasAttribute("open"), "Escape leaves the sample alone");
  goRoute("ratings");
  assert.ok(drawer.hasAttribute("open"));
};

scenarios.notice = async () => {
  const { app } = await page();
  const pill = () => app.root.querySelector(".pill--button");
  assert.equal(pill().querySelector(".pill__notice"), null, "no notice, no dot");
  let opened = 0;
  const list = () => { const ul = document.createElement("ul"); ul.className = "readiness"; ul.append("The 2026 season load"); return ul; };
  app.setNotice({ dot: true, title: "Not loaded yet", body: list, onOpen: () => { opened += 1; app.setNotice({ dot: false, title: "Not loaded yet", body: list }); } });
  assert.ok(pill().querySelector(".pill__notice"), "a dot on the pill");
  assert.ok(pill().classList.contains("pill--notice"));
  assert.ok(/Not loaded yet/.test(pill().getAttribute("aria-label")), "and its name says why");
  pill().click();
  const card = document.body.querySelector(".status-card");
  assert.ok(card && text(card).includes("Not loaded yet") && text(card).includes("The 2026 season load"), "the card lists it");
  assert.equal(opened, 1);
  assert.equal(pill().querySelector(".pill__notice"), null, "opening the card clears the dot");
  assert.ok(text(document.body.querySelector(".status-card")).includes("The 2026 season load"), "the list stays in the card");
  app.setStatus({ kind: "stale", label: "Updated 4 min ago" });
  assert.ok(text(document.body.querySelector(".status-card")).includes("The 2026 season load"), "a new status keeps the list");
  assert.ok(!RAW.test(text(document.body.querySelector(".status-card"))));
  app.setNotice({ dot: true, title: "Not loaded yet", body: () => { throw new Error("broken"); } });
  assert.ok(!RAW.test(text(document.body.querySelector(".status-card"))), "a list that will not draw is left out");
  app.setNotice(null);
  assert.ok(!text(document.body.querySelector(".status-card")).includes("Not loaded yet"));
  assert.equal(pill().querySelector(".pill__notice"), null);
};

scenarios.readiness = async () => {
  installWindow();
  window.location = { hash: "#program" };
  window.localStorage = localStorage;
  const slot = document.createElement("div");
  slot.className = "page-notes";
  document.body.append(slot);
  const items = [
    { id: "season", title: "The 2026 season load", detail: "Not loaded", href: "#preseason" },
    { id: "costs", title: "Roster costs", detail: null, href: "https://elsewhere.example/" },
    null, "junk", { title: 5 },
  ];
  let answer = { ready: false, items, serverStartedAt: "t1" };
  route("/api/readiness", () => envelope(answer));
  const { startReadiness } = await import(moduleUrl("ui/readiness.js"));
  let notice = null;
  const page = { setNotice: (n) => { notice = n; } };
  document.body.dataset.role = "host";
  const first = await startReadiness(page);
  assert.equal(first.items.length, 2, "a bad row is skipped");
  const note = slot.querySelector(".page-note");
  assert.ok(note && !note.hasAttribute("hidden"), "listed for the To do flyout on the Pre-Game Program");
  assert.equal(note.querySelectorAll("a").length, 1, "only a link inside the app is offered");
  assert.ok(!RAW.test(text(note)));
  const { todayKey } = await import(moduleUrl("ui/readiness.js"));
  assert.equal(localStorage.getItem("kickoff.readiness.seen"), null, "listed is not seen: the note waits off the page (the layout pass, 2026-10-22)");
  const { parkNotes, takeNotes } = await import(moduleUrl("ui/page-notes.js"));
  assert.equal(takeNotes(), note, "the To do flyout takes it");
  assert.equal(localStorage.getItem("kickoff.readiness.seen"), todayKey(), "seen once the flyout shows it, for the day (owner 2026-10-13: the check is daily)");
  parkNotes();
  assert.equal(notice.dot, true);
  assert.equal(notice.title, "Not loaded yet");
  assert.ok(text(notice.body()).includes("The 2026 season load"));
  // the card opened from the dot: the dot goes, the list stays, and the check is asked again
  notice.onOpen();
  await settle();
  assert.equal(notice.dot, false);
  assert.ok(slot.querySelector(".page-note"), "the note stays until it is dismissed");
  note.querySelector(".page-note__close").click();
  assert.equal(slot.querySelector(".page-note"), null);
  assert.ok(slot.hasAttribute("hidden"));
  // once a day: a reload the same day shows neither the note nor the dot, but the card keeps the list
  slot.replaceChildren();
  const again = await startReadiness(page);
  assert.equal(again.fresh, false);
  assert.equal(slot.querySelector(".page-note"), null);
  assert.equal(notice.dot, false);
  assert.ok(text(notice.body()).includes("Roster costs"));
  // a new day: fresh again; a followed link takes the note and the dot away
  localStorage.setItem("kickoff.readiness.seen", "2000-01-01");
  await startReadiness(page);
  const fresh = slot.querySelector(".page-note");
  assert.ok(fresh && notice.dot === true);
  fresh.querySelector("a.btn").click();
  assert.equal(slot.querySelector(".page-note"), null);
  assert.equal(notice.dot, false);
  // everything loaded since the start: opening the card clears the list
  answer = { ready: true, items: [], serverStartedAt: "t2" };
  notice.onOpen();
  await settle();
  assert.equal(notice, null, "the card has nothing left to list");
  // nothing missing, a failed check, a broken answer: no note
  assert.equal(await startReadiness(page), null);
  route("/api/readiness", () => new Error("down"));
  assert.equal(await startReadiness(page), null);
  route("/api/readiness", () => envelope("junk"));
  assert.equal(await startReadiness(page), null);
  assert.equal(slot.querySelector(".page-note"), null);
};

// The layout pass (owner 2026-10-22: the To do note "dont show that unless its in its own flyout"): the Menu button counts
// the To do, a To do row tops whatever list the menu opens on, and the row opens the flyout (onTodo).
scenarios.todoMenu = async () => {
  browser("#season", { depth: 2 });
  const { shell } = await import(moduleUrl("ui/shell.js"));
  let todo = 0;
  const app = shell({ current: "season", onNavigate: () => {}, onSearch: () => {}, onTodo: () => { todo += 1; } });
  document.body.append(app.root);
  const menu = app.root.querySelector(".menu-button");
  const drawer = app.root.querySelector(".drawer");
  const badge = menu.querySelector(".menu-button__badge");
  assert.ok(badge.hasAttribute("hidden") && menu.getAttribute("aria-label") === null, "nothing to do: no count, the button's own word names it");
  document.dispatchEvent(new CustomEvent("kickoff:notes", { detail: { count: 2 } }));
  assert.ok(!badge.hasAttribute("hidden") && badge.textContent === "2", "the count on the Menu button");
  assert.equal(menu.getAttribute("aria-label"), "Menu, 2 things to do");
  menu.click();
  await land();
  const row = drawer.querySelector(".drawer__todo");
  assert.ok(row && row.parentNode.className.includes("drawer__list") && row.parentNode.childNodes[0] === row, "the To do row tops the list the menu opens on");
  assert.equal(drawer.querySelector(".drawer__level b").textContent, "My Teams", "the menu still opens on the page's own list");
  assert.ok(row.textContent.includes("2 things to look at"));
  row.click();
  await land();
  assert.equal(todo, 1, "the row opens the To do flyout");
  assert.ok(!drawer.hasAttribute("open"), "the menu closes for it");
  document.dispatchEvent(new CustomEvent("kickoff:notes", { detail: { count: 0 } }));
  assert.ok(badge.hasAttribute("hidden") && menu.getAttribute("aria-label") === null, "nothing left: no count");
  menu.click();
  await land();
  assert.equal(drawer.querySelector(".drawer__todo"), null, "and no row");
  document.dispatchEvent(new CustomEvent("kickoff:notes", { detail: { count: "x" } }));
  assert.ok(badge.hasAttribute("hidden"), "a count that is no number is nothing");
};

scenarios.pageNotes = async () => {
  window.location.hash = "#program";
  const { addNote, removeNote, noteShowing, noteCount, takeNotes, parkNotes, dismissAll, routeIdOf } = await import(moduleUrl("ui/page-notes.js"));
  const counts = [];
  document.addEventListener("kickoff:notes", (event) => counts.push(event.detail.count)); // the Menu's count follows the list
  assert.equal(addNote({ id: "x", title: "Nowhere", body: "text" }), null, "no slot on the page: no note");
  const slot = document.createElement("div");
  slot.className = "page-notes";
  slot.setAttribute("hidden", "");
  document.body.append(slot);
  for (const [hash, id] of [["#program=401", "program"], ["#team=A%20B", "team"], ["", "program"], [null, "program"], ["#national=x?y=1", "national"]]) assert.equal(routeIdOf(hash), id, String(hash));
  let shown = 0;
  let dismissed = 0;
  const note = addNote({ id: "ready", title: "Not loaded yet", body: () => { const p = document.createElement("p"); p.append("Items"); return p; }, when: (r) => r === "program", onShow: () => { shown += 1; }, onDismiss: () => { dismissed += 1; } });
  assert.ok(note && !note.hasAttribute("hidden") && !slot.hasAttribute("hidden"), "listed on the Pre-Game Program (the slot itself never shows: CSS)");
  assert.equal(shown, 0, "listed is not seen: only the To do flyout shows it (the layout pass, 2026-10-22)");
  assert.ok(noteShowing("ready") && noteCount() === 1);
  assert.equal(counts[counts.length - 1], 1);
  assert.equal(takeNotes(), slot.querySelector(".page-note"), "the flyout takes the note");
  assert.equal(shown, 1, "seen now");
  parkNotes();
  goRoute("live");
  assert.ok(note.hasAttribute("hidden") && slot.hasAttribute("hidden"), "elsewhere it waits, and the slot leaves no gap");
  assert.equal(noteCount(), 0);
  assert.equal(takeNotes(), null, "nothing listed here: nothing for the flyout");
  goRoute("board");
  assert.ok(note.hasAttribute("hidden"));
  goRoute("program");
  assert.ok(!note.hasAttribute("hidden"));
  assert.equal(shown, 1, "onShow runs once");
  slot.querySelector(".page-note__close").click(); // one close button for the whole note (Design rules, owner 2026-10-21)
  assert.equal(dismissed, 1);
  assert.equal(slot.querySelector(".page-note"), null);
  assert.ok(slot.hasAttribute("hidden"));
  assert.ok(!noteShowing("ready"));
  // the board never carries one, whatever it says
  const everywhere = addNote({ id: "all", title: "Everywhere", body: "hello", when: () => true });
  goRoute("board");
  assert.ok(everywhere.hasAttribute("hidden"), "never on the board");
  goRoute("season");
  assert.ok(!everywhere.hasAttribute("hidden"));
  // a note that leaves with the page it was seen on
  const greet = addNote({ id: "hi", title: "Welcome", body: ["one", "two"], leaveWithPage: true });
  assert.ok(!greet.hasAttribute("hidden"));
  goRoute("live");
  assert.ok(greet.isConnected, "unseen, it waits for the flyout");
  takeNotes();
  parkNotes();
  goRoute("season");
  assert.equal(greet.isConnected, false, "seen, it goes with the page it was shown on");
  assert.ok(removeNote("all"));
  assert.equal(removeNote("all"), false);
  // the flyout's Clear the list: every item listed goes, each telling its owner; one for another page waits
  let cleared = 0;
  addNote({ id: "c1", title: "One", body: "x", onDismiss: () => { cleared += 1; } });
  addNote({ id: "c2", title: "Two", body: "y", when: (r) => r === "glossary" });
  dismissAll();
  assert.equal(cleared, 1);
  assert.equal(noteCount(), 0);
  assert.ok(removeNote("c2"));
  // a body that will not draw, or a note that cannot say where it belongs
  assert.equal(addNote({ id: "bad", title: "Bad", body: () => { throw new Error("broken"); } }), null);
  const lost = addNote({ id: "lost", title: "Lost", body: "x", when: () => { throw new Error("broken"); } });
  assert.ok(lost.hasAttribute("hidden"), "hidden rather than shown everywhere");
  assert.ok(!RAW.test(text(slot)));
};
"""

SCENARIO_NAMES = [
    "sheetBack", "sheetCloseByHand", "stacked", "routeCloses", "goTo", "goToKeepsState", "deadEntry", "deferredPush", "persistAndInline", "leftover",
    "placeLayers", "drawerBack", "drawerItem", "drawerTab", "menuOverSheet", "escapeOrder", "drawerLevels", "inlineDrawer", "notice", "readiness", "pageNotes", "todoMenu",
]


@needs_node
@pytest.mark.parametrize("scenario", SCENARIO_NAMES)
def test_layers_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def _css() -> str:
    return (STATIC / "css" / "components.css").read_text(encoding="utf-8")


def test_layers_start_under_the_top_bar_from_700_px():
    """B: the sheets, the card and their scrims (the layer boxes) start at --layer-top from 700 px up; the top bar sits above
    every layer z-index layerZ can hand out (46 to 59), the drawer above the bar; the board keeps its layers at 0 and the
    styleguide's inline sample is left alone. Below 700 px nothing changes (full-screen sheets)."""
    css = _css()
    block = re.search(r"@media \(min-width: 700px\) \{\n  \.topbar \{ z-index: (\d+); \}\n  \.drawer \{ z-index: (\d+); \}\n(.*?)\n\}", css, flags=re.S)
    assert block, "the item 6 block"
    bar, drawer = int(block.group(1)), int(block.group(2))
    dom = (JS / "ui" / "dom.js").read_text(encoding="utf-8")
    top_layer = int(re.search(r"Math\.min\((\d+), 46 \+ open\)", dom).group(1))
    assert bar > top_layer, "the Menu stays above the highest sheet"
    assert drawer > bar, "the menu drawer lies above the sheets (it starts under the top bar: the layout pass, board 2)"
    assert ".drawer { top: var(--layer-top, var(--topbar)); }" in block.group(3)
    body = block.group(3)
    assert ".sheet-layer:not(.sheet-layer--inline), .sheet-layer-closing, .card-layer, .card-layer-closing { top: var(--layer-top, var(--topbar)); }" in body
    assert "body.board-mode :is(.sheet-layer, .sheet-layer-closing, .card-layer, .card-layer-closing) { top: 0; }" in body
    # the rule comes after the base layer rules it overrides
    assert css.index(".sheet-layer-closing, .card-layer-closing { position: fixed; inset: 0;") < css.index(block.group(0))
    assert "body.board-mode .page-notes" in css, "notes never on the board"
    assert ".page-notes[hidden], .page-note[hidden] { display: none; }" in css


def test_the_router_keeps_the_page_for_a_layers_entry():
    """D in app.js: a popstate onto the same route (a layer's entry) neither changes the page nor waits for a scroll to put
    back; the tabs and menu items go through goTo (a layer's entry is reused) or close the layers for the page showing."""
    app = (JS / "app.js").read_text(encoding="utf-8")
    assert 'import { closeLayers, goTo, installLayerHistory, stepOverLeftovers } from "./ui/layers.js";' in app
    pop = app[app.index('window.addEventListener("popstate", () => {'): app.index('window.addEventListener("hashchange", () => {')]
    assert "routeKey(" in pop and "=== currentKey) return;" in pop and pop.index("return;") < pop.index("restore = { pending: true };")
    nav = app[app.index("onNavigate: (id) => {"): app.index("onSearch:")]
    assert "goTo(id)" in nav and "closeLayers();" in nav
    assert '!document.querySelector(".drawer[open]")' in app, '"/" does not open Search behind the open menu'
    start = app[app.index("installLayerHistory();"):]
    assert start.index("installLayerHistory();") < start.index("if (initial) show(initial);") < start.index("stepOverLeftovers();")


def test_nothing_opens_by_itself():
    """C: the readiness list and the guest welcome never open a sheet; the router no longer opens one on a timer."""
    app = (JS / "app.js").read_text(encoding="utf-8")
    assert "maybeShowReadiness" not in app
    assert "startReadiness(page)" in app and "Promise.all([guestKnown, drawn]).then(askReadiness);" in app
    readiness = (JS / "ui" / "readiness.js").read_text(encoding="utf-8")
    assert "openSheet" not in readiness and "when: () => true, // every page (the board never" in readiness  # the Prompts phase: every page, once a day
    guest = (JS / "ui" / "guest.js").read_text(encoding="utf-8")
    welcome = guest[guest.index("async function welcomeGuest()"): guest.index("export async function startGuestMode()")]
    assert "openSheet" not in welcome and "addNote(" in welcome and 'route !== "board"' in welcome and "leaveWithPage: true" in welcome
    assert "setTimeout(() => welcomeGuest()" not in guest
    from tools import page_check

    assert ".page-notes button, .page-notes a[href]" in page_check.RULES_JS, "the page check holds the notes to the 44 px rule"
    assert "document.querySelector('.page-notes'), document.querySelector('main')" in page_check.RULES_JS, "and to the 13 px floor"


def test_every_layer_holds_its_entry():
    """D: the sheets, the card and the drawer each take an entry and release it; a layer's Escape gives way to one marked
    handled (the hint card and the status card above it), and the hint card marks its own."""
    remote = (JS / "ui" / "remote.js").read_text(encoding="utf-8")
    assert "release = holdLayer((why) => close(why), { history: !persist });" in remote
    assert 'if (!persist) close("route");' in remote and "sheetAnchor(placeLayers())" in remote
    card = (JS / "ui" / "player-card.js").read_text(encoding="utf-8")
    assert "release = holdLayer((why) => close(why));" in card and 'const onRoute = () => close("route");' in card
    for src in (remote, card):
        assert 'event.key === "Escape" && !event.defaultPrevented && isTopLayer(layer)' in src
    shell = (JS / "ui" / "shell.js").read_text(encoding="utf-8")
    assert "releaseDrawer = holdLayer((why) => closeDrawer(why));" in shell
    assert '!document.querySelector(".sheet-layer[data-modal], .card-layer[data-modal]")' in shell
    hints = (JS / "ui" / "hints.js").read_text(encoding="utf-8")
    assert "if (card) event.preventDefault();" in hints
    team = (JS / "views" / "team.js").read_text(encoding="utf-8")
    assert "goTo(`team=${encodeURIComponent(usSchool())}`);" in team, "our team from a sheet takes the sheet's entry"
