"""The Profile in the fake browser (Phase 17 #31's rows, the layout pass's board 7, owner 2026-10-22: "Put the Tier 2 Key
info in about and help. Change Start and Server to Server Settings. Everything else is good."). Who and what at the top
with four facts that open their sections; the four game-day settings on the page; every section a tile saying what is set
now and opening its settings in the wide flyout, one row per setting with its help, switches for on/off settings, a green
saved line; #profile=radio (and the old #settings=radio) opening that section; a failed load still draws."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const flush = async () => { for (let i = 0; i < 8; i += 1) await new Promise((resolve) => setImmediate(resolve)); };
Object.getPrototypeOf(document.body).scrollIntoView = function (opts) { this.scrolledInto = opts || true; };

const PREFS = { delaySeconds: 30, hints: true, autoStart: false, theme: "dark", refreshMinutes: 5, keepScreenOn: "gameday", openBrowser: "manual", tickerMode: "national", announcer: true };
const META = { radioSources: [{ id: "env-1", name: "Station 101.5", kind: "link", url: "https://example.com", origin: "env" }], autoStart: { supported: true, method: "a Startup shortcut", enabled: false }, notes: { commandFound: false }, plan: { tierName: "Tier 2", likedAllowed: true, used: 412, monthlyLimit: 30000, remaining: 29588 }, about: { version: "0.24.0" }, server: { team: "Swampwater Tech", dataDir: "C:/data", logDir: "C:/logs" }, teamSet: {} };

async function mounted(arg = null) {
  const { createSettingsView } = await import(moduleUrl("views/settings.js"));
  const main = document.createElement("main");
  document.body.append(main);
  const view = createSettingsView({ arg });
  await view.mount(main);
  await flush();
  return { main, view };
}

scenarios.settings = async () => {
  installWindow();
  route("/api/settings", () => envelope({ prefs: PREFS, ...META })); // the meta sits beside the prefs, as /api/settings answers
  route("/api/host", () => envelope({ pinSet: true, isHost: true, serverComputer: true }));
  route("/api/invite", () => envelope({ url: "http://kickoff.local:8642/", copyUrl: null, warnings: [] }));
  route("/api/readiness", () => envelope({ ready: false, items: [{ id: "season", title: "The 2026 season load", detail: "Not loaded", href: "#preseason" }] }));
  route("/api/board/screens", () => envelope({ screens: [], serverComputer: true, browser: true }));
  route("/api/claude-schedule", () => envelope({ enabled: false, commandFound: false, next: [], recent: [] }));
  route("/api/updates", () => envelope({ enabled: true, current: "0.24.0", latest: "0.24.0", newer: false }));
  const { main, view } = await mounted();
  const page = main.querySelector(".profile-page");
  assert.ok(page, "the Profile page");
  const t = text(page);
  assert.ok(!RAW.test(t), t.slice(0, 400));
  // who and what: the team, the role, four facts
  assert.ok(text(page.querySelector(".profile-hello")).includes("Host"));
  const facts = page.querySelectorAll(".profile-fact").map(text);
  assert.equal(facts.length, 4);
  assert.ok(facts[0].includes("Tier 2") && facts[0].includes("412 of 30,000 calls"), facts[0]);
  assert.ok(facts[1].includes("0.24.0"));
  assert.ok(facts[2].includes("kickoff.local") && facts[2].includes("port 8642"), facts[2]);
  assert.ok(facts[3].includes("PIN set"), facts[3]);
  // the four game-day settings on the page
  const quick = page.querySelectorAll(".profile-quick__row").map((r) => text(r.querySelector(".profile-quick__label b")));
  assert.deepEqual(quick, ["Spoiler delay", "Theme", "Keep the screen on", "Text size"]);
  page.querySelectorAll(".profile-seg").find((g) => g.getAttribute("aria-label") === "Theme").querySelectorAll("button")[1].click();
  await flush();
  assert.ok(text(main.querySelector(".setting__saved")).includes("Theme saved"), "a tap on Light saves the theme: " + text(main.querySelector(".setting__saved")));
  // the ten tiles, in the board's order, each saying what is set now
  const tiles = main.querySelectorAll(".profile-tile");
  assert.deepEqual(tiles.map((x) => text(x.querySelector("b"))), ["Game day", "Trivia", "Display", "Your teams", "Friends and the big screen", "Radio stations", "Claude and loading data", "Server Settings", "About and help", "Setup"]);
  const line = (id) => text(main.querySelector(`.profile-tile[data-section="${id}"] small`));
  assert.ok(line("gameday").includes("Station 101.5") && line("gameday").includes("every FBS game"), line("gameday"));
  assert.ok(line("about").includes("Tier 2 key") && line("about").includes("412 of 30,000"), "the key and the plan in About and help: " + line("about"));
  assert.ok(!line("teams").includes("Tier"), "Your teams has the teams only");
  assert.ok(line("claude").includes("1 load missing") && main.querySelector('.profile-tile[data-section="claude"]').className.includes("profile-tile--warn"), "gold while something is not loaded");
  // a tile opens its section in the wide flyout, one row per setting with its help
  main.querySelector('.profile-tile[data-section="display"]').click();
  await flush();
  const sheet = document.querySelector(".profile-sheet");
  assert.ok(sheet && sheet.className.includes("side-sheet--wide"), "the wide flyout");
  const rows = sheet.querySelectorAll(".setting__label").map((l) => text(l.childNodes[0]));
  assert.deepEqual(rows, ["Theme", "Text size", "Stat hints", "Color-blind friendly colors", "Spoiler mode", "Page refresh"]);
  assert.ok(sheet.querySelector(".setting__label small"), "each setting explains itself");
  const hints = sheet.querySelector('input[aria-label="Stat hints"]');
  assert.equal(hints.getAttribute("role"), "switch");
  // Game day takes the announcer; Server Settings is Start and the server without the setup and Claude Code
  main.querySelector('.profile-tile[data-section="gameday"]').click();
  await flush();
  assert.deepEqual(document.querySelector(".profile-sheet").querySelectorAll(".setting__label").map((l) => text(l.childNodes[0])), ["Spoiler delay", "Keep the screen on", "Radio source", "Announcer", "Score ticker"]);
  main.querySelector('.profile-tile[data-section="server"]').click();
  await flush();
  const server = document.querySelector(".profile-sheet").querySelectorAll(".setting__label").map((l) => text(l.childNodes[0]));
  assert.ok(server.includes("Start at login") && !server.includes("First time setup") && !server.includes("Claude Code"), server.join(", "));
  assert.equal(document.querySelectorAll(".profile-sheet").length, 1, "one section open at a time");
  main.querySelector('.profile-tile[data-section="about"]').click();
  await flush();
  const about = text(document.querySelector(".profile-sheet"));
  assert.ok(about.includes("Your CFBD plan") && about.includes("The key can be replaced from the server computer") && about.includes("C:/data"), "About and help: the key and plan, the folders");
  view.unmount();
  assert.equal(document.querySelector(".profile-sheet"), null, "leaving the page closes the flyout");

  // #settings=radio, from the radio's "Add it in Settings", opens Radio stations; an old name leads to its new home
  const radio = await mounted("radio");
  assert.ok(text(document.querySelector(".profile-sheet")).includes("How to add your team's station"));
  radio.view.unmount();
  const start = await mounted("start");
  assert.ok(text(document.querySelector(".profile-sheet")).includes("Start at login"), "the old Start and the server is Server Settings");
  start.view.unmount();
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["settings"])
def test_settings_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
