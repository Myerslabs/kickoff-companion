"""Phase 16, stream SEASON, owner look GX-14 (restrained): the 280px SP+ offense vs defense scatter inside the SP+
band on Ratings, at 1100px and wider only, labels on Swampwater Tech and the next opponent only, a tap opens the team.
Dropping the commit drops this file."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario
from tests.test_p16_season_js import FIXTURE

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "css" / "components.css").read_text(encoding="utf-8")

SCENARIOS = r"""
const text = (node) => (node ? node.textContent : "");
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;

scenarios.scatter = async () => {
  const { spScatter, scatterScale } = await import(moduleUrl("ui/scatter.js"));
  const rows = [
    { team: "Swampwater Tech", off: 33.4, def: 14.5 },
    { team: "Silver Dollar", off: 30.0, def: 20.0 },
    { team: "Georgia", off: 40.8, def: 12.1 },
    { team: "Kent State", off: 10.0, def: 40.0 },
    { team: "Broken", off: "x", def: 3 }, null, { team: "", off: 1, def: 1 }, { team: "NaN U", off: NaN, def: 2 },
  ];
  // the scale: best offense at the right edge, best defense (fewest points) at the top edge
  const s = scatterScale(rows, { size: 280, pad: 14 });
  assert.equal(s.x(10), 14);
  assert.equal(s.x(40.8), 266);
  assert.equal(s.y(12.1), 14, "the best defense is at the top");
  assert.equal(s.y(40), 266);
  assert.deepEqual(s.domain, { off: [10, 40.8], def: [12.1, 40] });
  assert.equal(scatterScale([{ team: "A", off: 1, def: 1 }]), null, "one team is not a chart");
  const fig = spScatter(rows, { us: "Swampwater Tech", next: "Silver Dollar" });
  const labels = fig.querySelectorAll("text.scatter__label").map(text);
  assert.deepEqual(labels, ["Silver Dollar", "Swampwater Tech"], "labels only on the next opponent and Swampwater Tech (drawn last, on top)");
  assert.equal(fig.querySelectorAll("circle.scatter__hit").length, 4, "every valid team is a target; bad rows are skipped");
  assert.equal(fig.querySelectorAll("circle.scatter__dot--us").length, 1);
  assert.equal(fig.querySelectorAll("circle.scatter__ring").length, 1);
  for (const c of fig.querySelectorAll("circle")) for (const a of ["cx", "cy"]) assert.ok(!RAW.test(c.getAttribute(a)), `${a}=${c.getAttribute(a)}`);
  assert.ok(!RAW.test(text(fig)));
  // a tap opens that team through the same event every team name uses
  const opened = [];
  document.addEventListener("kickoff:team", (e) => opened.push(e.detail));
  fig.querySelectorAll("circle.scatter__hit").find((c) => c.getAttribute("data-team") === "Georgia").click();
  assert.deepEqual(opened, ["Georgia"]);
  // no next opponent, or a next opponent that is Swampwater Tech: one label
  assert.deepEqual(spScatter(rows, { us: "Swampwater Tech", next: "Swampwater Tech" }).querySelectorAll("text.scatter__label").map(text), ["Swampwater Tech"]);
  for (const bad of [null, [], "x", [{ team: "A", off: 1, def: 1 }]]) assert.equal(spScatter(bad), null);
};

scenarios.onRatings = async () => {
  installWindow();
  localStorage.setItem("kickoff:next-opponent", JSON.stringify({ school: "Silver Dollar" }));
  const { createRatingsView } = await import(moduleUrl("views/ratings.js"));
  route("/api/ratings", () => envelope(clone(FIXTURE.ratings)));
  const main = document.createElement("main");
  document.body.append(main);
  const view = createRatingsView({});
  view.mount(main);
  await settle();
  const fig = main.querySelector("#ratings-sp figure.scatter");
  assert.ok(fig, "the scatter sits inside the SP+ band");
  assert.deepEqual(fig.querySelectorAll("text.scatter__label").map(text), ["Silver Dollar", "Swampwater Tech"]);
  view.unmount();
};
"""


@pytest.fixture(scope="module")
def fixture_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("scatter") / "fixture.json"
    path.write_text(json.dumps(FIXTURE), encoding="utf-8")
    return path


@needs_node
@pytest.mark.parametrize("scenario", ["scatter", "onRatings"])
def test_the_sp_scatter(tmp_path: Path, fixture_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario, str(fixture_path))


def test_the_scatter_shows_only_at_1100_and_wider() -> None:
    assert re.search(r"(?m)^\.scatter \{ display: none;", CSS)
    wide = CSS.split("@media (min-width: 1100px) {\n  .ratings__sp", 1)
    assert len(wide) == 2 and ".scatter { display: grid;" in wide[1].split("}\n}", 1)[0]
