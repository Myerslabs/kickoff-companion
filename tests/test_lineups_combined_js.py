"""Phase 19: lineups and depth in one view, and the experience of the starters by unit."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

const slot = (unit, name, players) => ({ unit, slot: name, players });
const p = (name, classYear, extra = {}) => ({ name, classYear, ...extra });
const lineups = {
  us: { team: "Home U", slots: [
    slot("Offense", "QB", [p("Q One", "JR", { number: 1, playerId: "11", chips: ["917 passing yards"] }), p("Q Two", "FR"), p("Q Three", "RS SO")]),
    slot("Offense", "LT", [p("L One", "SR", { number: 70 })]),
    slot("Defense", "DE", [p("D One", "GR"), p("D Two", "SO")]),
  ] },
  them: { team: "Away U", slots: [
    slot("Defense", "DE", [p("E One", "FR"), p("E Two", "FR")]),
    slot("Offense", "QB", [p("R One", "SO")]),
  ] },
};
const us = { school: "Home U", abbreviation: "HU" };
const them = { school: "Away U", abbreviation: "AU" };

scenarios.classes = async () => {
  const { classNumber } = await import(moduleUrl("ui/lineups_combined.js"));
  assert.deepEqual(["FR", "so", "JR", "SR", "GR", "RS SO", "rs fr", "", null, "XX", 5].map(classNumber), [1, 2, 3, 4, 4, 2, 1, null, null, null, null]);
};

scenarios.block = async () => {
  const { lineupBlock, experienceBlock } = await import(moduleUrl("ui/lineups_combined.js"));
  const opened = [];
  const node = lineupBlock({ lineups, us, them, availability: [{ name: "Q Two", status: "Questionable", note: "ankle" }], onPlayer: (row) => opened.push(row.playerId) });
  document.body.append(node);
  const t = text(node);
  assert.ok(!RAW.test(t), t.slice(0, 500));
  // the starter and the depth behind him in ONE row
  assert.ok(t.includes("Q One") && t.includes("917 passing yards"));
  assert.ok(t.includes("Q Two (FR), questionable, Q Three (RS SO)"), "the rest of the chart, in order, with the report's status: " + t.slice(0, 900));
  assert.ok(t.includes("Then, in order"));
  assert.ok(t.includes("Home U offense") && t.includes("Away U defense"), "our offense beside their defense");
  // a tap on a starter with an id opens him
  node.querySelectorAll("tbody tr").find((r) => text(r).includes("Q One")).click();
  assert.deepEqual(opened, ["11"]);
  // the experience table: starters by class, average class
  const exp = experienceBlock({ lineups, us, them });
  const rows = exp.querySelectorAll("tbody tr").map((r) => r.querySelectorAll("td, th").map(text));
  const home = rows.find((r) => r[0] === "HU offense");
  assert.deepEqual(home.slice(1), ["2", "0", "0", "1", "1", "3.5"].map((v, i) => (i === 0 ? v : v)), "two starters: a junior and a senior, average 3.5");
  const away = rows.find((r) => r[0] === "AU defense");
  assert.deepEqual(away.slice(1, 3), ["1", "1"]);
  assert.equal(rows.find((r) => r[0] === "HU defense")[6], "4.0", "a fifth-year defender counts as a senior");
  assert.equal(experienceBlock({ lineups: { us: { slots: [slot("Offense", "QB", [p("No Class", "")])] } }, us, them }), null, "no classes named: no table");
  assert.equal(experienceBlock({}), null);
};

scenarios.empty = async () => {
  const { lineupBlock } = await import(moduleUrl("ui/lineups_combined.js"));
  const t = text(lineupBlock({}));
  assert.ok(t.includes("No lineups for this game yet") && !RAW.test(t));
  for (const bad of [{ lineups: null }, { lineups: { us: { slots: "x" } }, us: null, them: undefined, availability: "x", onPlayer: 3 }]) {
    assert.ok(!RAW.test(text(lineupBlock(bad))));
  }
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["classes", "block", "empty"])
def test_combined_lineups_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)
