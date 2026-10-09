"""Phase 17 #4, #6, #39 in the fake browser: the big headers' Wikipedia links (drawn as searches, then pointed at the
pages the server found; a failed answer keeps the searches), the Team page chip, the wind-on-kicks line in two looks,
and the band a section chip leads to flashing on every press."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const flush = async () => { for (let i = 0; i < 6; i += 1) await new Promise((resolve) => setImmediate(resolve)); };

scenarios.links = async () => {
  const asked = [];
  globalThis.fetch = async (url) => {
    asked.push(String(url));
    return { ok: true, status: 200, json: async () => ({ data: { teams: { "Home U": { football: "https://en.wikipedia.org/wiki/Home_U_football", school: "https://en.wikipedia.org/wiki/Home_University", resolved: true }, "Away State": { football: "https://evil.example/x", school: null } }, venues: { "Pie Bowl": { stadium: "https://en.wikipedia.org/wiki/Pie_Bowl" } } } }) };
  };
  const { wikiLink, teamPageChip, fillWiki, searchUrl } = await import(moduleUrl("ui/wiki-links.js"));
  const root = document.createElement("div");
  root.append(wikiLink("football", { team: "Home U" }, "LOGO"), wikiLink("school", { team: "Home U" }, "Home U"), wikiLink("school", { team: "Away State" }, "Away State"), wikiLink("stadium", { venue: "Pie Bowl" }, "Pie Bowl"), wikiLink("school", { team: null }, "nobody"), teamPageChip("Home U"));
  document.body.append(root);
  const links = root.querySelectorAll("a.wiki-link");
  assert.equal(links.length, 4, "no team, no link");
  assert.equal(links[2].getAttribute("href"), searchUrl("Away State university"), "a search first");
  assert.equal(links[0].getAttribute("target"), "_blank");
  await fillWiki(root);
  assert.equal(asked.length, 1);
  assert.ok(asked[0].startsWith("/api/wiki?team=Home+U&team=Away+State&venue=Pie+Bowl"), asked[0]);
  assert.equal(links[0].getAttribute("href"), "https://en.wikipedia.org/wiki/Home_U_football");
  assert.equal(links[1].getAttribute("href"), "https://en.wikipedia.org/wiki/Home_University");
  assert.equal(links[2].getAttribute("href"), searchUrl("Away State university"), "an answer off Wikipedia is not followed");
  assert.equal(links[3].getAttribute("href"), "https://en.wikipedia.org/wiki/Pie_Bowl");
  const chip = root.querySelector(".team-page-chip");
  assert.equal(chip.getAttribute("href"), "#team=Home%20U");
  assert.equal(teamPageChip(""), null);
  await fillWiki(root);
  assert.equal(asked.length, 1, "one request a page load for the same teams");
};

scenarios.failed = async () => {
  globalThis.fetch = async () => ({ ok: false, status: 500, json: async () => ({ errors: [{ message: "down" }] }) });
  const { wikiLink, fillWiki, searchUrl } = await import(moduleUrl("ui/wiki-links.js"));
  const root = document.createElement("div");
  root.append(wikiLink("football", { team: "Lone U" }, "L"));
  await fillWiki(root);
  assert.equal(root.querySelector("a").getAttribute("href"), searchUrl("Lone U football"));
};

scenarios.wind = async () => {
  const { kickWind, kickWindLevel, WINDY_MPH } = await import(moduleUrl("ui/wind.js"));
  assert.equal(WINDY_MPH, 15);
  assert.deepEqual([kickWindLevel(14.9), kickWindLevel(15), kickWindLevel(30, true), kickWindLevel(null), kickWindLevel(NaN), kickWindLevel(-3)], ["calm", "windy", "indoors", null, null, null]);
  const calm = kickWind({ windMph: 7 });
  const windy = kickWind({ windMph: 21 });
  const inside = kickWind({ windMph: null, indoors: true });
  document.body.append(calm, windy, inside);
  assert.equal(text(calm), "Wind won't affect kicks");
  assert.equal(text(windy), "Wind will affect kicks");
  assert.ok(windy.className.includes("kick-wind--windy") && text(inside).includes("Indoors"));
  assert.equal(kickWind({}), null);
  const { weatherRow } = await import(moduleUrl("ui/matchup-card.js"));
  const row = weatherRow({ tempF: 61, windMph: 18, sky: "Clear" });
  assert.ok(!RAW.test(text(row)) && text(row).includes("Wind will affect kicks"));
};

scenarios.flash = async () => {
  const { band, revealBand, FLASH_MS } = await import(moduleUrl("ui/states.js"));
  Object.getPrototypeOf(document.body).scrollIntoView = function () {};
  const b = band({ id: "x", title: "Series", body: () => document.createElement("div") });
  document.body.append(b);
  revealBand(b);
  assert.ok(b.className.includes("band--flash"));
  await advance(FLASH_MS + 10);
  assert.ok(!b.className.includes("band--flash"));
  revealBand(b);
  revealBand(b);
  assert.ok(b.className.includes("band--flash"), "every press flashes again");
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["links", "failed", "wind", "flash"])
def test_wiki_wind_and_flash_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
