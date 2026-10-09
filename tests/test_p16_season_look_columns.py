"""Phase 16, stream SEASON, owner look G3-03: Advanced is its own band as one paired Offense | Defense table,
Trends its own band, and the profile band has no nested pseudo-bands. Phase 17 (#7, #28): the three fixed
columns became one flowing page, so this checks the bands' reading order instead."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario
from tests.test_p16_season_js import FIXTURE

SCENARIOS = r"""
const text = (node) => (node ? node.textContent : "");
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;

scenarios.columns = async () => {
  installWindow();
  const { createSeasonView } = await import(moduleUrl("views/season.js"));
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  route("/api/season/overview", () => envelope(clone(FIXTURE.season)));
  const main = document.createElement("main");
  document.body.append(main);
  const view = createSeasonView({});
  view.mount(main);
  await settle();
  // Phase 17 #7, #28: one flowing page instead of three fixed columns; the bands in reading order, the profile
  // and the advanced tables marked to span two columns on a wide page
  const page = main.querySelector(".page.season");
  assert.ok(page && page.className.includes("flow"));
  const ids = page.querySelectorAll("section.band").map((b) => b.getAttribute("id")).filter(Boolean);
  assert.deepEqual(ids.slice(0, 9), ["season-schedule", "season-profile", "season-standings", "season-polls", "season-ratings", "season-last", "season-resume", "season-trends", "season-advanced"]);
  const profile = main.querySelector("#season-profile");
  assert.equal(profile.querySelectorAll(".band").length, 0, "no band nested inside the profile band");
  assert.deepEqual(profile.querySelectorAll("h3.subhead").map(text), ["Offense", "Defense"]);
  // one paired table: the offense and defense success rates on one row, each with its linked chip
  const adv = main.querySelector("#season-advanced");
  assert.equal(adv.querySelectorAll("table").length, 1);
  const row = adv.querySelectorAll("tbody tr").find((tr) => text(tr).startsWith("Success rate"));
  assert.ok(text(row).includes("48.6%") && text(row).includes("39.1%"), text(row));
  assert.equal(row.querySelectorAll("a.rank-chip--link").length, 2);
  assert.ok(adv.querySelectorAll("tr.is-parent").map((tr) => text(tr.querySelector("td"))).includes("Tempo"), "areas are group rows");
  const oneSided = adv.querySelectorAll("tbody tr").find((tr) => text(tr).startsWith("Run rate"));
  assert.ok(text(oneSided).includes("–"), "a one-sided attribute shows a dash on the other side");
  assert.ok(!RAW.test(text(main)));
  view.unmount();
  const { pairAdvanced } = await import(moduleUrl("ui/depth2.js"));
  const pairs = pairAdvanced([
    { side: "offense", key: "offense_havoc_total", group: "Havoc", value: 0.1, label: "Havoc allowed" },
    { side: "defense", key: "defense_havoc_total", group: "Havoc", value: 0.2, label: "Havoc rate" },
    { side: "defense", key: "defense_havoc_db", group: "Havoc", value: 0.05, label: "Havoc, secondary" },
    null, { side: "both", key: "x" }, { side: "offense", key: 3 },
  ]);
  assert.deepEqual(pairs.map((p) => p.label), ["Havoc", "Havoc rate", "Havoc, secondary"]);
  assert.equal(pairs[1].off, 0.1);
  assert.equal(pairs[1].def, 0.2);
  assert.equal(pairs[2].off, undefined);
  assert.deepEqual(pairAdvanced("junk"), []);
};
"""


@pytest.fixture(scope="module")
def fixture_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("columns") / "fixture.json"
    path.write_text(json.dumps(FIXTURE), encoding="utf-8")
    return path


@needs_node
def test_the_season_columns_are_rebalanced(tmp_path: Path, fixture_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "columns", str(fixture_path))
