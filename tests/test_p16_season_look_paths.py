"""Phase 16, stream SEASON, owner look GX-06 (restrained): the AP rank path in the Polls band (72 x 20, inverted,
gaps for unranked weeks) and Swampwater Tech's Elo line in the team header. Dropping the commit drops this file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario
from tests.test_p16_season_js import FIXTURE

SCENARIOS = r"""
const text = (node) => (node ? node.textContent : "");
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;

scenarios.paths = async () => {
  const { rankPath, rankY, eloLine } = await import(moduleUrl("ui/sparkline.js"));
  // inverted: #1 at the top, #25 at the bottom, clamped
  assert.ok(rankY(1) < rankY(12) && rankY(12) < rankY(25));
  assert.equal(rankY(40), rankY(25));
  assert.equal(rankY(null), null);
  // gaps: an unranked week breaks the line instead of dropping it to the bottom
  const gapped = rankPath([3, 5, null, 8, 7]);
  const svg = gapped.querySelector("svg");
  assert.equal(svg.querySelectorAll("path").length, 2, "two runs of ranked weeks, two lines");
  assert.equal(gapped.getAttribute("aria-label"), "AP rank by week: 3, 5, unranked, 8, 7");
  for (const d of svg.querySelectorAll("path").map((p) => p.getAttribute("d"))) assert.ok(!RAW.test(d), d);
  // a lone ranked week between gaps is a point; the latest ranked week carries the end dot
  const lone = rankPath([null, 12, null, null]);
  assert.equal(lone.querySelectorAll("path").length, 0);
  assert.equal(lone.querySelectorAll("circle.rankpath__pt").length, 1);
  assert.equal(lone.querySelectorAll("circle.rankpath__dot").length, 1);
  for (const bad of [null, undefined, [], [null, null], "3,4", [0, -2, NaN], [{}]]) assert.equal(rankPath(bad), null, JSON.stringify(bad));
  // Elo: the first pregame rating, then every postgame rating, and today's value
  const elo = eloLine({ current: 1669, points: [{ pre: 1562, post: 1658 }, { pre: 1658, post: 1669 }, null] });
  assert.equal(text(elo.querySelector(".elo-line__val")), "1669");
  assert.ok(elo.querySelector("svg path"));
  assert.equal(elo.getAttribute("title"), "Elo by game: 1562, 1658, 1669");
  assert.equal(text(eloLine({ current: 1500, points: [] })), "1500");
  for (const bad of [null, {}, { current: "x", points: "y" }, { points: [{ pre: NaN }] }]) assert.equal(eloLine(bad), null);
};

scenarios.wired = async () => {
  installWindow();
  const { createSeasonView } = await import(moduleUrl("views/season.js"));
  const { createTeamView } = await import(moduleUrl("views/team.js"));
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  route("/api/season/overview", () => envelope(clone(FIXTURE.season)));
  const ours = clone(FIXTURE.ours);
  ours.team.eloPath = { current: 1669, points: [{ pre: 1562, post: 1658 }, { pre: 1658, post: 1669 }] };
  route("/api/team/Swampwater%20Tech", () => envelope(ours));
  const main = document.createElement("main");
  document.body.append(main);
  const season = createSeasonView({});
  season.mount(main);
  await settle();
  const paths = main.querySelectorAll("#season-polls .rankpath-wrap");
  assert.equal(paths.length, 3);
  assert.ok(text(main.querySelector("#season-polls .poll-caption")).includes("AP Top 25, week 4"));
  assert.ok(!RAW.test(text(main)));
  season.unmount();
  const team = createTeamView({ school: "Swampwater Tech" });
  team.mount(main);
  await settle();
  const elo = main.querySelector(".team-head__facts a.team-head__elo");
  assert.equal(elo.getAttribute("href"), "#ratings=elo?team=Swampwater%20Tech");
  assert.equal(text(elo.querySelector(".elo-line__val")), "1669");
  team.unmount();
};
"""


@pytest.fixture(scope="module")
def fixture_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("paths") / "fixture.json"
    path.write_text(json.dumps(FIXTURE), encoding="utf-8")
    return path


@needs_node
@pytest.mark.parametrize("scenario", ["paths", "wired"])
def test_rank_paths_and_the_elo_line(tmp_path: Path, fixture_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario, str(fixture_path))
