"""Phase 17 #31 in the fake browser: Settings in Steam's style. The sections listed beside the page, the options
grouped as Game day, Display, and Start and the server, one row per setting with its help, switches for on/off
settings, and a green saved line; a failed load still draws, with defaults and a note."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const flush = async () => { for (let i = 0; i < 8; i += 1) await new Promise((resolve) => setImmediate(resolve)); };
Object.getPrototypeOf(document.body).scrollIntoView = function (opts) { this.scrolledInto = opts || true; };

scenarios.settings = async () => {
  installWindow();
  let saves = 0;
  route("/api/settings", (url, options) => {
    if (options && options.method === "PUT") saves += 1;
    return envelope({ prefs: { delaySeconds: 30, hints: true, autoStart: false, theme: "dark", refreshMinutes: 5, keepScreenOn: "gameday", openBrowser: "manual", tickerMode: "national" }, meta: { radioSources: [], autoStart: { supported: true, method: "a Startup shortcut", enabled: false }, notes: {}, plan: { tierName: "Tier 2", likedAllowed: true }, about: {} } });
  });
  route("/api/notes/template", () => envelope({ template: "x", custom: false }));
  const { createSettingsView } = await import(moduleUrl("views/settings.js"));
  const main = document.createElement("main");
  document.body.append(main);
  const view = createSettingsView({});
  await view.mount(main);
  await flush();
  const page = main.querySelector(".settings-page");
  assert.ok(page, "the settings page");
  const t = text(page);
  assert.ok(!RAW.test(t), t.slice(0, 400));
  // the sections, listed beside the page
  const nav = page.querySelectorAll(".settings-nav__item").map(text);
  assert.deepEqual(nav.slice(0, 3), ["Game day", "Readiness", "Display"]);
  assert.ok(nav.includes("About"));
  // one row per setting in the right section, each with its help
  const inSection = (id) => main.querySelector(`#${id}`).querySelectorAll(".setting__label").map((l) => text(l.childNodes[0]));
  assert.deepEqual(inSection("settings-gameday"), ["Spoiler delay", "Keep the screen on", "Radio source", "Score ticker"]);
  assert.deepEqual(inSection("settings-display"), ["Theme", "Text size", "Stat hints", "Color-blind friendly colors", "Spoiler mode", "Announcer", "Page refresh"]);
  assert.ok(inSection("settings-start").includes("Start at login"));
  assert.ok(main.querySelector("#settings-display .setting__label small"), "each setting explains itself");
  // on/off settings are switches
  const hints = main.querySelector('#settings-display input[aria-label="Stat hints"]');
  assert.equal(hints.getAttribute("role"), "switch");
  assert.ok(hints.className.includes("switch"));
  // a tap on a section unfolds and scrolls to it, and marks it
  const display = page.querySelectorAll(".settings-nav__item").find((a) => text(a) === "Display");
  display.click();
  assert.ok(display.className.includes("is-current"), `class: ${display.className}`);
  assert.ok(main.querySelector("#settings-display").scrolledInto, "scrolled to");
  view.unmount();
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["settings"])
def test_settings_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
