"""Compare two players (batch 3, owner 2026-11-16; a viewer's feedback of 2026-10-31, "Compare players side by side please").

His picks: from the player card, two players, bio and recruiting, season stats. The page reads the two cards'
own answers (/api/players/<id>), so the server side is the card's; these check the wiring and that two players of two
teams both answer in the league. The page itself is drawn by the Node page tests on GitHub."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.fakedom import needs_node, run_scenario
from tests.test_any_team import OTHER, lclient  # noqa: F401 - the league client fixture

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "static" / "js"


def test_the_route_the_card_and_the_picker_are_wired():
    app = (JS / "app.js").read_text(encoding="utf-8")
    assert re.search(r"compare: \(opts, arg, focus, params\) => createCompareView\(", app), "#compare=<id>,<id> is a page"
    assert '"compare"' in app.split("const NO_TAB")[1].split(";")[0], "the comparison belongs to no tab"
    card = (JS / "ui" / "player-card.js").read_text(encoding="utf-8")
    assert "player-card__compare" in card and "onCompare" in card
    player = (JS / "views" / "player.js").read_text(encoding="utf-8")
    assert "openComparePick({ first:" in player, "the card's Compare opens the picker with this player first"
    view = (JS / "views" / "compare.js").read_text(encoding="utf-8")
    for part in ("Bio and recruiting", "season"):
        assert part in view
    assert "pffOn" not in view, "Kickoff Companion has no film grades"
    assert "gameLog" not in view, "game by game was not picked"


def test_two_players_of_two_teams_both_answer(lclient: TestClient):  # noqa: F811
    ours = lclient.get("/api/roster").json()["data"]["players"]
    theirs = lclient.get(f"/api/roster?team={OTHER}").json()["data"]["players"]
    a = next(p for p in ours if p.get("position") == "QB")
    b = next(p for p in theirs if p.get("position") == "QB")
    pid = lambda p: p.get("id") or p.get("playerId")  # noqa: E731
    first = lclient.get(f"/api/players/{pid(a)}")
    second = lclient.get(f"/api/players/{pid(b)}?team={OTHER}")
    assert first.status_code == 200 and second.status_code == 200, (first.text[:200], second.text[:200])
    for answer in (first.json()["data"], second.json()["data"]):
        assert answer["player"]["name"] and isinstance(answer["seasons"], list)
        assert "pffOn" not in answer


def test_the_team_line_draws_the_teams_logo_not_a_dash() -> None:
    """The review (owner 2026-11-19): a stray dash stood before each team's name, the player passed where a team belongs."""
    page = (Path(__file__).resolve().parents[1] / "static" / "js" / "views" / "compare.js").read_text(encoding="utf-8")
    assert "teamLogo(p," not in page
    assert "abbreviation: str(p.teamAbbr)" in page and "logo: p.logo, logoDark: p.logoDark" in page


SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object \w+\]/;
const text = (node) => (node ? node.textContent : "");

const QB = {
  playerId: "101",
  player: { id: 101, name: "Avery Stone", lastName: "Stone", team: "Florida", teamAbbr: "FLA", position: "QB", classYear: "Junior", number: 12, height: 75, weight: 215, hometown: "Ocala, FL", stars: 4 },
  seasons: [
    { year: 2026, category: "passing", stats: { YDS: 2100, TD: 18, INT: 4 } },
    { year: 2026, category: "rushing", stats: { CAR: 40, YDS: 150 } },
    { year: 2025, category: "passing", stats: { YDS: 900 } },
    null, "junk",
  ],
};
// no team in his answer: the page keeps the team it arrived with (?tb=)
const WR = {
  playerId: "202",
  player: { id: 202, name: "Jordan Reed", lastName: "Reed", position: "WR", classYear: "Senior", number: null, height: null, weight: "junk" },
  seasons: [{ year: 2026, category: "rushing", stats: { CAR: 3, YDS: 22 } }, { year: 2026, category: "receiving", stats: { REC: 40, YDS: 600, TD: 5 } }],
};

async function draw(arg, params, answers) {
  const { createCompareView } = await import(moduleUrl("views/compare.js"));
  for (const [id, answer] of Object.entries(answers || {})) route(`/api/players/${id}`, answer);
  const main = document.createElement("main");
  document.body.append(main);
  const statuses = [];
  const view = createCompareView({ arg, params, onStatus: (s) => statuses.push(s) });
  view.mount(main);
  await settle();
  await settle();
  return { main, view, statuses };
}

function outsideHidden(node) {
  for (let n = node; n; n = n.parentNode) if (typeof n.getAttribute === "function" && n.getAttribute("aria-hidden") === "true") return false;
  return true;
}

scenarios.both = async () => {
  installWindow();
  const { main, view, statuses } = await draw("101,202", { ta: "Florida", tb: "Texas State" }, { 101: envelope(clone(QB)), 202: envelope(clone(WR)) });
  assert.ok(calls.includes("/api/players/101?team=Florida") && calls.includes("/api/players/202?team=Texas%20State"), calls.join(" "));
  const heads = main.querySelectorAll(".compare__head .compare__who");
  assert.equal(heads.length, 2, "both heads");
  assert.ok(pnText(heads[0]).includes("Avery Stone") || text(heads[0]).includes("Avery Stone"), text(heads[0]));
  assert.ok(text(heads[1]).includes("Jordan Reed"), text(heads[1]));
  assert.ok(!text(heads[1]).includes("#"), "no number: no '#'");
  assert.ok(!RAW.test(text(main)), text(main));
  const swap = main.querySelector("a.compare__swap");
  assert.ok(swap, "the swap is drawn");
  assert.ok(outsideHidden(swap), "a screen reader reaches the swap");
  assert.equal(swap.getAttribute("aria-label"), "Swap sides");
  assert.equal(swap.getAttribute("href"), "#compare=202,101?ta=Texas%20State&tb=Florida", "an answer with no team keeps the team the page arrived with");
  assert.equal(main.querySelectorAll(".compare__change").length, 2, "Change on each side");
  assert.ok(main.querySelector("#compare-bio") && main.querySelector("#compare-stats"));
  assert.equal(statuses[statuses.length - 1].kind, "ok");
  view.unmount();
};

scenarios.oneFails = async () => {
  installWindow();
  const broken = { status: 500, body: { data: null, errors: [{ message: "The roster did not load" }] } };
  const { main, view, statuses } = await draw("101,202", { ta: "Florida", tb: "Texas State" }, { 101: envelope(clone(QB)), 202: broken });
  assert.ok(!RAW.test(text(main)), text(main));
  const failed = main.querySelector(".compare__who--b.compare__who--failed");
  assert.ok(failed, "the failed side says so");
  assert.ok(text(failed).includes("The roster did not load"), text(failed));
  assert.ok(failed.querySelector("button.compare__change"), "the failed side keeps its Change");
  assert.ok(failed.querySelector("button.compare__retry"), "and a Try again");
  const good = main.querySelector(".compare__who--a");
  assert.ok(good && !good.className.includes("compare__who--failed") && text(good).includes("Avery Stone"), "the other side draws");
  assert.ok(main.querySelector("#compare-bio") && main.querySelector("#compare-stats"), "the bands still draw for the side that loaded");
  assert.ok(main.querySelector("a.compare__swap"), "the swap stays");
  assert.equal(statuses[statuses.length - 1].kind, "error");
  failed.querySelector("button.compare__change").click();
  await settle();
  const layer = document.body.querySelector(".sheet-layer");
  assert.ok(layer, "Change opens the picker");
  assert.ok(text(layer).includes("Avery Stone"), "the side that stays is the one that loaded");
  view.unmount();
};

scenarios.noLine = async () => {
  installWindow();
  const old = clone(WR);
  old.player.team = "Texas State";
  old.seasons = [{ year: 2025, category: "receiving", stats: { REC: 12, YDS: 150 } }];
  const { main, view } = await draw("101,202", {}, { 101: envelope(clone(QB)), 202: envelope(old) });
  const stats = main.querySelector("#compare-stats");
  assert.ok(text(stats).includes("Jordan Reed: no 2026 line."), text(stats));
  assert.ok(!RAW.test(text(main)), text(main));
  view.unmount();
};

scenarios.hint = async () => {
  installWindow();
  for (const arg of ["101,101", "101", "abc,<b>", "", "1,2,3"]) {
    const { main, view } = await draw(arg, {}, {});
    assert.ok(text(main).includes("The address names no two players"), `${arg}: ${text(main)}`);
    assert.equal(main.querySelector(".compare__head"), null, arg);
    assert.ok(!RAW.test(text(main)), text(main));
    view.unmount();
    main.remove();
  }
  assert.equal(calls.filter((u) => u.startsWith("/api/players/")).length, 0, "nothing asked of the server");
};
"""

NAMES = ["both", "oneFails", "noLine", "hint"]


@needs_node
@pytest.mark.parametrize("scenario", NAMES)
def test_the_comparison_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_the_review_of_2026_11_19_holds() -> None:
    """The swap reachable on a phone and outside aria-hidden; each side drawn on its own."""
    view = (JS / "views" / "compare.js").read_text(encoding="utf-8")
    assert "Promise.all([fetchPatient" not in view, "one failed player no longer fails the page"
    assert '"compare__vs", "aria-hidden"' not in view
    css = (ROOT / "static" / "css" / "components.css").read_text(encoding="utf-8")
    assert ".compare__vs { display: none; }" not in css, "the swap stays at 390 px"
    pick = (JS / "ui" / "compare-pick.js").read_text(encoding="utf-8")
    assert "isNum(p.number)" in pick
