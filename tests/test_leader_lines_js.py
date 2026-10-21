"""Phase 17 #17 in the fake browser: under each pair of Game program leaders, the whole line with FBS and
conference rank chips, and the line over conference games (its lead number alone at small, tables wave 2); damaged
entries draw as dashes, and nothing is drawn for a category with no stats."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

scenarios.lines = async () => {
  const { confGamesShort, confGamesText, leaderPair, leaderPairs } = await import(moduleUrl("ui/leader-lines.js"));
  const more = {
    label: "Passing yards", category: "passing", stat: "YDS",
    us: { detail: { stats: [{ stat: "YDS", value: 1204, national: { rank: 8, of: 130 }, conference: { rank: 2, of: 14, conference: "Big Pie" }, metric: "board:passing:YDS" }, { stat: "TD", value: 11, national: null, conference: { rank: "x" } }, { stat: "PCT", value: 0.652 }, null, { value: 3 }] }, conferenceGames: { stats: { YDS: 610, TD: 5, INT: 1, COMPLETIONS: 40, ATT: 60 } } },
    them: { detail: { stats: [{ stat: "YDS", value: NaN }, { stat: "INT", value: 4 }] }, conferenceGames: null },
  };
  const taps = [];
  const cat = { id: "YDS-Passing yards", label: "Passing yards", category: "passing", stat: "YDS", format: "0f", us: { name: "Al One", playerId: "41", position: "QB", value: 1204, headshotUrl: null }, them: { name: "Bo Two", playerId: 7, position: "QB", value: 900 }, more };
  const node = leaderPair(cat, { usAbbr: "SWT", themAbbr: "OPP", usTeam: "Swampwater Tech", themTeam: "Diner Tech", usConfGames: 3, themConfGames: 3, onTap: (p, side) => taps.push(`${side}:${p.name}`) });
  document.body.append(node);
  const t = text(node);
  assert.ok(!RAW.test(t), t);
  // the mock (owner 2026-10-20): the stat names on the pole, our numbers at the left hand, theirs at the right, the faces beside the pole
  assert.equal(node.style["--lpair-rows"], "6", "the title row, four stat rows and the conference line");
  assert.equal(text(node.querySelector(".lpair__title")), "Passing yards");
  assert.deepEqual(node.querySelectorAll(".lpair__label").map(text), ["Yds", "TD", "Comp %", "INT", "Conference games3 games"]);
  const us = node.querySelectorAll(".lpair__us");
  const them = node.querySelectorAll(".lpair__them");
  assert.deepEqual([us[0].style.gridRow, them[0].style.gridRow, node.querySelectorAll(".lpair__label")[0].style.gridRow], ["2", "2", "2"], "a stat's three cells share a grid row");
  assert.equal(text(us[0].querySelector(".lpair__val")), "1,204");
  const links = us[0].querySelectorAll("a.rank-chip--link");
  assert.equal(links.length, 2, "FBS and conference chips, both linked to the board's list");
  assert.equal(links[0].getAttribute("href"), "#national=board%3Apassing%3AYDS?team=Swampwater%20Tech");
  assert.equal(links[1].getAttribute("href"), "#national=board%3Apassing%3AYDS?team=Swampwater%20Tech&scope=conference");
  assert.ok(links[1].closest(".lpair__conf"), "the conference chip is marked as such");
  assert.ok(us[0].children[0].className.includes("lpair__chips") && them[0].children[0].className.includes("lpair__val"), "the chips outside the values, mirrored");
  assert.equal(text(them[0].querySelector(".lpair__val")), "\u2013", "a damaged value is a dash");
  assert.ok(!us[0].querySelector(".lead") && !us[0].querySelector(".trail"), "one side missing: nothing to compare, no edge");
  assert.equal(us[1].querySelectorAll("a.rank-chip--link").length, 0, "a damaged rank draws no chip");
  assert.equal(text(them[3].querySelector(".lpair__val")), "4");
  const conf = us[4];
  assert.ok(conf.className.includes("lpair__cell--conf"));
  assert.equal(text(conf.querySelector(".lpair__long")), "610 yds, 40/60, 5 TD, 1 int");
  assert.equal(text(conf.querySelector(".lpair__short")), "610 yds", "a phone keeps the lead number alone");
  assert.equal(text(them[4].querySelector(".lpair__val")), "\u2013");
  // the faces: a button to the card when the chart knows the player
  const who = node.querySelectorAll(".lpair__who");
  assert.equal(who.length, 2);
  assert.ok(who[0].tagName === "BUTTON" && who[0].className.includes("lpair__who--us") && who[1].className.includes("lpair__who--them"));
  assert.equal(text(who[0].querySelector(".lpair__meta")), "SWT QB");
  who[1].click();
  assert.deepEqual(taps, ["them:Bo Two"]);
  // before the whole lines arrive: the program's own line, the category's key number; an empty side says so
  const own = leaderPair({ label: "Sacks", category: "defensive", stat: "SACKS", format: "1f", us: { name: "Cy Three", value: 4.5 }, them: null }, { usAbbr: "SWT", themAbbr: "OPP" });
  assert.equal(own.style["--lpair-rows"], "2");
  assert.deepEqual(own.querySelectorAll(".lpair__label").map(text), ["Sacks"]);
  assert.equal(text(own.querySelector(".lpair__us .lpair__val")), "4.5 sacks");
  assert.equal(text(own.querySelector(".lpair__them .lpair__val")), "\u2013");
  assert.ok(text(own.querySelector(".lpair__who--them")).includes("No OPP line yet") && own.querySelector(".lpair__who--us").tagName !== "BUTTON", "no player id: not a button");
  assert.equal(leaderPairs([cat, null, "junk", {}], {}).querySelectorAll(".lpair").length, 2);
  assert.equal(confGamesShort("passing", { YDS: 610, TD: 5 }), "610 yds");
  for (const junk of [null, "x", { YDS: "x" }]) assert.equal(confGamesShort("rushing", junk), null);
  assert.equal(confGamesText("passing", null), null);
  assert.equal(confGamesText("rushing", { YDS: "x" }), null);
};

scenarios.grid = async () => {
  const { leadersGrid } = await import(moduleUrl("ui/leaders.js"));
  const detail = document.createElement("div");
  detail.textContent = "LINES";
  const grid = leadersGrid({ categories: [{ id: "a", label: "Passing yards", us: { name: "A", line: "1 yds" }, them: null, detail }, { id: "b", label: "Sacks", us: null, them: null, detail: "not a node" }], usAbbr: "SWT", themAbbr: "OPP" });
  document.body.append(grid);
  assert.equal(grid.querySelectorAll(".leader-cat__detail").length, 1);
  assert.ok(text(grid).includes("LINES"));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["lines", "grid"])
def test_leader_lines_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
