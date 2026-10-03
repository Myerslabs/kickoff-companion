"""Phase 16, stream SEASON, owner look G3-10 part B: 20px self-hosted logos (16px under 700px) before the team names
in Standings, Polls, the schedule rail, the Ratings Team column and Road ahead. A team without a logo URL gets its
name alone. Dropping the commit drops this file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario
from tests.test_p16_season_js import FIXTURE

SCENARIOS = r"""
const text = (node) => (node ? node.textContent : "");
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;

scenarios.logos = async () => {
  installWindow();
  const { logoLink } = await import(moduleUrl("ui/team-page.js"));
  const withLogo = logoLink("Silver Dollar", { logo: "/media/logo/2", logoDark: "/media/logo/2?v=dark", abbreviation: "GRID" });
  assert.equal(withLogo.className, "tl");
  assert.equal(withLogo.querySelector("img").getAttribute("src"), "/media/logo/2?v=dark", "the dark variant on navy");
  assert.equal(withLogo.querySelector("button.team-link").dataset.team, "Silver Dollar");
  const bare = logoLink("Kent State", { logo: "javascript:alert(1)" });
  assert.equal(bare.className, "tl tl--bare");
  assert.equal(bare.querySelectorAll("img, .team-logo").length, 0, "no URL, no mark");
  assert.equal(text(logoLink(null, {})), "–");
  const { createSeasonView } = await import(moduleUrl("views/season.js"));
  const { createRatingsView } = await import(moduleUrl("views/ratings.js"));
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  const overview = clone(FIXTURE.season);
  overview.standings.forEach((row, i) => { row.logo = `/media/logo/${i}`; row.logoDark = `/media/logo/${i}?v=dark`; });
  route("/api/season/overview", () => envelope(overview));
  const main = document.createElement("main");
  document.body.append(main);
  const season = createSeasonView({});
  season.mount(main);
  await settle();
  assert.ok(main.querySelectorAll("#season-schedule .sched__opp img.tl__logo").length === 3, "every schedule row");
  assert.ok(main.querySelectorAll("#season-standings .tl img").length === 3, "every standings row");
  assert.ok(main.querySelectorAll("#season-road .tl img").length === 1, "road ahead borrows the schedule's logos");
  assert.equal(main.querySelectorAll("#season-polls .tl--bare").length, 3, "poll rows without logo URLs keep the name alone");
  assert.ok(!RAW.test(text(main)));
  season.unmount();
  const data = clone(FIXTURE.ratings);
  data.rows[12].logo = "/media/logo/57";
  route("/api/ratings", () => envelope(data));
  const ratings = createRatingsView({});
  ratings.mount(main);
  await settle();
  assert.equal(main.querySelectorAll("#ratings-sp .tl img").length, 1, "only the row the server gave a logo");
  ratings.unmount();
  assert.ok(!errors.some((e) => /could not draw a cell/.test(e)), errors.join("\n"));
};
"""


@pytest.fixture(scope="module")
def fixture_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("logos") / "fixture.json"
    path.write_text(json.dumps(FIXTURE), encoding="utf-8")
    return path


@needs_node
def test_logos_in_the_team_columns(tmp_path: Path, fixture_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "logos", str(fixture_path))
