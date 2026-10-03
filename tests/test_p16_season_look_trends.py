"""Phase 16, stream SEASON, owner look G3-12 part 2: W/L dots and a dashed season-average line on the trend
sparklines. Dots align by index on the unfiltered arrays (a game whose box score did not load keeps its place),
and nothing is drawn when the results and the values disagree in length. Dropping the commit drops this file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario
from tests.test_p16_season_js import FIXTURE

SCENARIOS = r"""
const text = (node) => (node ? node.textContent : "");
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;

scenarios.marks = async () => {
  const { sparkline, trendRow } = await import(moduleUrl("ui/sparkline.js"));
  // a skipped game (null) keeps its result's place: the second drawn point is game three, a loss
  const svg = sparkline({ values: [24, null, 17, 31], results: ["W", "W", "L", "W"], avg: 24 });
  assert.deepEqual(svg.querySelectorAll("circle.spark__res").map((c) => c.getAttribute("class")), ["spark__res spark__res--w", "spark__res spark__res--l", "spark__res spark__res--w"]);
  assert.equal(svg.querySelectorAll("line.spark__avg").length, 1);
  assert.equal(svg.querySelectorAll("circle.spark__dot").length, 0, "the result dots replace the end dot");
  // lengths that disagree: no dots at all, the plain end dot instead
  const off = sparkline({ values: [24, 17, 31], results: ["W", "L"] });
  assert.equal(off.querySelectorAll("circle.spark__res").length, 0);
  assert.equal(off.querySelectorAll("circle.spark__dot").length, 1);
  // junk results and averages draw nothing odd
  const junk = sparkline({ values: [1, 2], results: [{}, "X"], avg: NaN });
  assert.equal(junk.querySelectorAll("circle.spark__res").length, 0);
  assert.equal(junk.querySelectorAll("line").length, 0);
  for (const c of svg.querySelectorAll("circle, line")) for (const a of ["cx", "cy", "y1", "y2"]) assert.ok(!RAW.test(c.getAttribute(a) ?? ""), a);
  assert.ok(!RAW.test(text(trendRow({ label: "Points", values: [3, null], results: ["W", "L"] }))));
};

scenarios.wired = async () => {
  installWindow();
  const { createSeasonView } = await import(moduleUrl("views/season.js"));
  route("/api/season/overview", () => envelope(clone(FIXTURE.season)));
  const main = document.createElement("main");
  document.body.append(main);
  const view = createSeasonView({});
  view.mount(main);
  await settle();
  // three weeks and two finished games: the lengths disagree, so no dots (never a guess)
  assert.equal(main.querySelectorAll("circle.spark__res").length, 0);
  view.unmount();
  const data = clone(FIXTURE.season);
  data.trends.weeks = [1, 2];
  data.trends.pointsAllowed = [21, 20];
  route("/api/season/overview", () => envelope(data));
  const again = createSeasonView({});
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  again.mount(main);
  await settle();
  const dots = main.querySelectorAll(".trend circle.spark__res");
  assert.deepEqual(dots.map((c) => c.getAttribute("class").split("--")[1]), ["w", "l"], "points allowed: a win, then the loss");
  assert.ok(text(main).includes("Filled dot a win"));
  again.unmount();
};
"""


@pytest.fixture(scope="module")
def fixture_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("trends") / "fixture.json"
    path.write_text(json.dumps(FIXTURE), encoding="utf-8")
    return path


@needs_node
@pytest.mark.parametrize("scenario", ["marks", "wired"])
def test_trend_marks(tmp_path: Path, fixture_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario, str(fixture_path))
