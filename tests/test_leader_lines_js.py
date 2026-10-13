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
  const { leaderLines, confGamesShort, confGamesText } = await import(moduleUrl("ui/leader-lines.js"));
  const cat = {
    label: "Passing yards", category: "passing", stat: "YDS",
    us: { detail: { stats: [{ stat: "YDS", value: 1204, national: { rank: 8, of: 130 }, conference: { rank: 2, of: 14, conference: "Big Pie" }, metric: "board:passing:YDS" }, { stat: "TD", value: 11, national: null, conference: { rank: "x" } }, { stat: "PCT", value: 0.652 }, null, { value: 3 }] }, conferenceGames: { stats: { YDS: 610, TD: 5, INT: 1, COMPLETIONS: 40, ATT: 60 } } },
    them: { detail: { stats: [{ stat: "YDS", value: NaN }, { stat: "INT", value: 4 }] }, conferenceGames: null },
  };
  const node = leaderLines(cat, { usAbbr: "SWT", themAbbr: "OPP", usTeam: "Swampwater Tech", themTeam: "Diner Tech", usConfGames: 3, themConfGames: 3 });
  document.body.append(node);
  const t = text(node);
  assert.ok(!RAW.test(t), t);
  assert.ok(node.querySelector("table").className.includes("tt--tug"), "the shared two-team table with the tug bar");
  // 2026-10-10: the chips in their own headed columns; the one-row head (medium, small) and the large head's second row
  const shown = (cell, form) => { const t = cell.querySelector(`.tt__t--${form}`); return t ? t.textContent + [...cell.querySelectorAll("small")].map((s) => s.textContent).join("") : text(cell); };
  // centered (2026-10-10): the stat over its bar in the middle column, the teams mirrored around it, one center line down the band
  assert.ok(node.querySelector("table").className.includes("tt--centered"));
  assert.deepEqual([...node.querySelectorAll("thead tr.tt__head--one th")].map((th) => shown(th, "short")), ["FBS", "SWT", "Season", "OPP"], "the opponent's rows carry no rank: no chip columns on that side");
  assert.deepEqual([...node.querySelectorAll("thead tr.tt__head--a th")].map((th) => shown(th, "long")), ["Swampwater Tech", "Season", "Diner Tech"]);
  assert.deepEqual([...node.querySelectorAll("thead tr.tt__head--b th")].map(text), ["FBS rank", "Big Pie rank", "", ""], "our conference's own name heads our conference column");
  const rows = node.querySelectorAll("tbody tr");
  assert.ok(rows.every((r) => !r.querySelector("td.tt__label") && r.querySelector("td.tt__mid .tug")), "no label column: the stat sits over its bar");
  assert.deepEqual(rows.map((r) => shown(r.querySelector("td.tt__mid .tt__mid-words"), "long")), ["Yds", "TD", "Comp %", "INT", "Conference games3 games"]);
  assert.deepEqual(rows.map((r) => shown(r.querySelector("td.tt__mid .tt__mid-words"), "short")), ["Yds", "TD", "Comp %", "INT", "Conf games3 games"]);
  assert.deepEqual([...rows[0].querySelectorAll("td")].map((td) => td.className.split(" ")[0]), ["tt__rank", "tt__rank", "num", "tt__tug", "num"], "our chips and value, the middle, their value");
  const links = rows[0].querySelectorAll("a.rank-chip--link");
  assert.equal(links.length, 2, "FBS and conference chips, both linked to the board's list");
  assert.equal(links[0].getAttribute("href"), "#national=board%3Apassing%3AYDS?team=Swampwater%20Tech", "the national chip outside");
  assert.equal(links[1].getAttribute("href"), "#national=board%3Apassing%3AYDS?team=Swampwater%20Tech&scope=conference", "the conference chip in its own column, next in");
  assert.ok(links[0].closest("td").className.includes("tt__rank--natl") && links[1].closest("td").className.includes("tt__rank--conf"));
  assert.ok(!rows[0].querySelector("td.lead") && !rows[0].querySelector("td.trail"), "one side missing: nothing to compare, no edge");
  assert.equal(rows[1].querySelectorAll("a.rank-chip--link").length, 0, "a damaged rank draws no chip");
  assert.ok(rows[1].querySelector("td.tt__rank--conf .tt__norank") && !rows[1].querySelector("td.tt__rank--conf .rank-chip"), "a dash in the chip's place, never a blank square");
  assert.ok(text(rows[4]).includes("610 yds") && text(rows[4]).includes("40/60") && text(rows[4]).includes("5 TD"));
  assert.ok(rows[4].className.includes("lines__conf"));
  // wave 2: the conference-game line's lead number alone at small, so a phone's table keeps its width
  const confCell = rows[4].querySelector("td.tt__cell.tt__us");
  assert.deepEqual([text(confCell.querySelector(".tt__t--short")), confCell.querySelector(".tt__t--long").className.includes("tt__t--mid")], ["610 yds", true]);
  assert.ok(text(confCell.querySelector(".tt__t--long")).includes("40/60"), "the whole line at large and medium");
  assert.equal(confGamesShort("passing", { YDS: 610, TD: 5 }), "610 yds");
  for (const junk of [null, "x", { YDS: "x" }]) assert.equal(confGamesShort("rushing", junk), null);
  assert.equal(confGamesText("passing", null), null);
  assert.equal(confGamesText("rushing", { YDS: "x" }), null);
  assert.equal(leaderLines({ category: "passing", us: {}, them: null }), null);
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
