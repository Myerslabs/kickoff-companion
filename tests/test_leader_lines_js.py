"""Phase 17 #17 in the fake browser: under each pair of Game program leaders, the whole line with FBS and
conference rank chips, and the line over conference games; damaged entries draw as dashes, and nothing is drawn
for a category with no stats."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

scenarios.lines = async () => {
  const { leaderLines, confGamesText } = await import(moduleUrl("ui/leader-lines.js"));
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
  assert.deepEqual([...node.querySelectorAll("thead th")].map(text), ["Season", "SWT", "Edge", "OPP"]);
  const rows = node.querySelectorAll("tbody tr");
  assert.deepEqual(rows.map((r) => text(r.querySelector("td.tt__label"))), ["Yds", "TD", "Comp %", "INT", "Conference games3 games"]);
  const links = rows[0].querySelectorAll("a.rank-chip--link");
  assert.equal(links.length, 2, "FBS and conference chips, both linked to the board's list");
  assert.equal(links[0].getAttribute("href"), "#national=board%3Apassing%3AYDS?team=Swampwater%20Tech&scope=conference", "the conference chip sits outside with the tug bar");
  assert.equal(links[1].getAttribute("href"), "#national=board%3Apassing%3AYDS?team=Swampwater%20Tech");
  assert.ok(rows[0].querySelector(".tt__conf small") && text(rows[0].querySelector(".tt__conf")).includes("Conf"));
  assert.ok(!rows[0].querySelector("td.lead") && !rows[0].querySelector("td.trail"), "one side missing: nothing to compare, no edge");
  assert.equal(rows[1].querySelectorAll("a.rank-chip--link").length, 0, "a damaged rank draws no chip");
  assert.equal(rows[1].querySelectorAll(".tt__conf").length, 0);
  assert.ok(text(rows[4]).includes("610 yds") && text(rows[4]).includes("40/60") && text(rows[4]).includes("5 TD"));
  assert.ok(rows[4].className.includes("lines__conf"));
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
