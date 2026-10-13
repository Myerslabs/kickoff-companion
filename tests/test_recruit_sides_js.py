"""Phase 17 #24, #36 in the fake browser: the talent band's star strips split into offense and defense for each
team in one table, with a fallback to the one strip for an older server, and nothing drawn when neither team has counts.
Tables wave 2 (owner 2026-10-10): each team's table is a sized stat table (ours left, theirs right, never a sideways
scroll): every star level at large, the 2- and 1-star columns gone below large and the signee count at small."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const form = (cell, which) => { const t = cell.querySelector(`.sz-t--${which}`); return t ? t.textContent : text(cell); }; // a sized table's words

scenarios.sides = async () => {
  const { starsPair } = await import(moduleUrl("views/program.js"));
  const { applyStatSize } = await import(moduleUrl("ui/stat-table.js"));
  const counts = { 5: 1, 4: 3, 3: 10, 2: 2, 1: 0 };
  const us = { sides: { offense: { counts, average: 3.4, signees: 16 }, defense: { counts: { 5: null, 4: "x" }, average: null, signees: 1 }, apart: { athlete: 2 } } };
  const them = { stars: { counts, average: 3.1 } };
  const pair = starsPair(us, them, "SWT", "OPP");
  document.body.append(pair);
  const t = text(pair);
  assert.ok(!RAW.test(t), t);
  const wraps = pair.querySelectorAll(".stat-table-wrap");
  assert.equal(wraps.length, 2, "one table a team, side by side");
  assert.ok(wraps.every((w) => w.dataset.size === "large" && typeof w.measure === "function"), "each sized by its own box");
  assert.ok(pair.querySelector(".stars-split__team--us") && pair.querySelector(".stars-split__team--them"), "ours at the left hand, theirs at the right");
  // the visible line over each table, and the same words for a screen reader
  assert.deepEqual(pair.querySelectorAll(".stars-split__caption").map(text), ["SWT signees by stars, last four classes", "OPP signees by stars, last four classes"]);
  assert.ok(text(pair.querySelectorAll("caption")[0]).startsWith("SWT") && text(pair.querySelectorAll("caption")[1]).startsWith("OPP"));
  // the heads: the star levels at every size, Avg at small, the 2- and 1-star columns at large only
  const heads = wraps[0].querySelectorAll("thead th");
  assert.deepEqual(heads.map((th) => form(th, "long")), ["Unit", "5-star", "4-star", "3-star", "2-star", "1-star", "Avg stars"]);
  assert.deepEqual(heads.map((th) => form(th, "short")), ["Unit", "5-star", "4-star", "3-star", "2-star", "1-star", "Avg"]);
  assert.deepEqual(heads.map((th) => (th.className.includes("st__min-large") ? "l" : th.className.includes("st__min-medium") ? "m" : "")), ["", "", "", "", "l", "l", ""]);
  assert.ok(!heads.some((th) => th.querySelector("button")), "a table of units does not sort");
  // a row per side; theirs, from an older answer, has no split, so one row for all
  const rows = pair.querySelectorAll("tbody tr");
  assert.deepEqual(rows.map((r) => form(r.querySelector("td"), "long")), ["Offense16 signees", "Defense1 signee", "All"]);
  assert.deepEqual(rows.map((r) => form(r.querySelector("td"), "short")), ["Off", "Def", "All"], "the unit's short word at small, never the group title's");
  assert.deepEqual(rows[0].querySelectorAll("td").slice(1).map(text), ["1", "3", "10", "2", "0", "3.40"]);
  assert.ok(rows[0].querySelectorAll("td")[1].querySelector(".stars-split__hot") && rows[0].querySelectorAll("td")[2].querySelector(".stars-split__hot") && !rows[0].querySelectorAll("td")[3].querySelector(".stars-split__hot"), "the blue chips stand out");
  assert.deepEqual(rows[1].querySelectorAll("td").slice(1).map(text), ["0", "0", "0", "0", "0", "–"], "a missing or damaged count is a zero, no average a dash");
  assert.ok(rows[0].className.includes("is-us") && rows[2].className.includes("is-next"));
  applyStatSize(wraps[0], "small");
  assert.equal(wraps[0].dataset.size, "small");
  const old = starsPair({ stars: { counts } }, them, "SWT", "OPP");
  assert.equal(old.querySelectorAll(".starstrip").length, 2, "an older server: one strip a team");
  assert.equal(starsPair({}, { sides: { offense: { counts: null } } }, "A", "B"), null);
  assert.equal(starsPair(null, undefined, "A", "B"), null);
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["sides"])
def test_recruit_sides_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
