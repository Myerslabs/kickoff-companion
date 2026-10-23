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
  // board 9: three weeks and two finished games, no game ids: the lengths disagree, so the columns are the trends' own weeks
  // and opponents, with no result and no filled dot (never a guess)
  assert.equal(main.querySelectorAll("#season-trends .tgrid__game").length, 3);
  assert.equal(main.querySelectorAll("#season-trends .tgrid__dot.is-win").length, 0);
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
  const finished = data.schedule.filter((g) => g.completed === true);
  const heads = main.querySelectorAll("#season-trends .tgrid__game");
  assert.equal(heads.length, 2, "one column a finished game");
  assert.deepEqual(heads.map((h) => text(h.querySelector(".tgrid__chip"))), finished.map((g) => g.opponent.abbreviation || g.opponent.school.slice(0, 4).toUpperCase()), "headed by the opponent");
  assert.ok(heads.every((h) => h.querySelector(".tgrid__chip").style.background), "in the opponent's colors");
  const row = [...main.querySelectorAll("#season-trends .tgrid__row")].find((r) => text(r).startsWith("Points allowed"));
  const dots = row.querySelectorAll(".tgrid__dot");
  assert.deepEqual(dots.map((d) => d.className.includes("is-win")), finished.map((g) => g.result === "W"), "points allowed: a filled dot for a win, a hollow one for a loss");
  assert.deepEqual(row.querySelectorAll(".tgrid__val").map(text), ["21", "20"], "the value under each game");
  assert.ok(text(main).includes("a filled dot is a win"));
  again.unmount();
  // with the game ids the columns follow them, whatever the lengths
  const ids = clone(FIXTURE.season);
  ids.trends.gameIds = [finished[1].gameId];
  ids.trends.weeks = [2];
  ids.trends.points = [10];
  route("/api/season/overview", () => envelope(ids));
  clearEnvelopeCache();
  const third = createSeasonView({});
  third.mount(main);
  await settle();
  const only = main.querySelectorAll("#season-trends .tgrid__game");
  assert.equal(only.length, 1);
  assert.ok(text(only[0]).includes(`${finished[1].usPoints}-${finished[1].themPoints}`), "the game's score under its opponent");
  third.unmount();
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
