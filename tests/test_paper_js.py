"""Phase 17 #26 in the fake browser: the Newspaper as a newspaper page. The weekly masthead (steady within a week,
from the team's names), this week open with its lead story and columns, earlier weeks folded, a pixel picture
on every story, and an old server's payload (no weeks) still drawn; no undefined, null or NaN on screen."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

PAPER = {
    "season": 2026,
    "today": "2026-10-07",
    "gameDay": False,
    "slateDay": False,
    "slate": [],
    "slateNote": "The slate shows on Saturdays in the season. Headlines are here every day.",
    "nextGame": {"gameId": 3, "date": "2026-10-10T16:45:00Z", "opponent": "Diner Tech"},
    "news": [{"title": "Old digest story", "url": "https://example.com/a", "source": "ESPN", "publishedAt": "2026-10-07T10:00:00Z"}],
    "feeds": {"espn": {"name": "ESPN", "status": "ok", "count": 3, "betting": 1}},
    "weeks": [
        {"key": "3", "gameId": 3, "week": 6, "label": "Week 6 · vs Diner Tech", "opponent": "Diner Tech", "homeAway": "home", "kickoff": "2026-10-10T16:45:00Z", "headlines": [
            {"title": "Three questions before Diner Tech", "url": "https://example.com/1", "source": "ESPN", "publishedAt": "2026-10-07T10:00:00Z", "topic": "game", "players": []},
            {"title": "Quillfeather is the key", "url": "https://example.com/2", "source": "Gazette", "publishedAt": "2026-10-06T10:00:00Z", "topic": "game", "players": [{"playerId": "11", "name": "Jadan Quillfeather", "team": "Swampwater Tech"}]},
            {"title": "Storms in the forecast", "url": "javascript:alert(1)", "source": None, "publishedAt": None, "topic": "weather", "players": None},
        ]},
        {"key": "2", "gameId": 2, "week": 5, "label": "Week 5 · at Silver Dollar", "opponent": "Silver Dollar", "homeAway": "away", "kickoff": "2026-10-03T19:30:00Z", "headlines": [
            {"title": "Silver Dollar recap", "url": "https://example.com/3", "source": "ESPN", "publishedAt": "2026-10-04T10:00:00Z", "topic": "nonsense", "players": []},
        ]},
        None, "junk",
    ],
    "parts": {},
}

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

scenarios.paper = async () => {
  installWindow();
  const fixture = JSON.parse(readFileSync(process.argv[4], "utf8"));
  const { setIdentity } = await import(moduleUrl("identity.js"));
  setIdentity({ school: "Swampwater Tech", mascot: "Mudpuppies", label: "SWT", name: "Mudpuppies" });
  const paper = await import(moduleUrl("views/newspaper.js"));
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  // the masthead: steady within a week, a different name for some other week, from the team's own names
  const a = paper.mastheadName(2026, 6);
  assert.equal(a, paper.mastheadName(2026, 6));
  const names = new Set([1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((w) => paper.mastheadName(2026, w)));
  assert.ok(names.size >= 3, [...names].join(" | "));
  assert.ok([...names].every((n) => n.includes("Mudpuppies") || n.includes("Swampwater Tech")));
  assert.ok(paper.mastheadName(null, null, null).startsWith("The "));
  clearEnvelopeCache();
  route("/api/newspaper", () => envelope(clone(fixture)));
  const main = document.createElement("main");
  document.body.append(main);
  const view = paper.createNewspaperView({});
  view.mount(main);
  await settle();
  const t = text(main);
  assert.ok(!RAW.test(t), t.slice(0, 400));
  assert.equal(text(main.querySelector(".paper-mast__name")), paper.mastheadName(2026, 6));
  assert.ok(text(main.querySelector(".paper-mast__line")).includes("Week 6 · vs Diner Tech edition"));
  // this week open: its newest story leads, the rest in the columns; a bad link is plain text
  const week = main.querySelector("#paper-week-3");
  assert.equal(week.getAttribute("data-collapsed"), "false");
  assert.equal(text(week.querySelector(".paper-lead__head")), "Three questions before Diner Tech");
  assert.equal(week.querySelectorAll(".paper-cols .paper-story").length, 2);
  assert.ok(!week.querySelectorAll("a").some((a) => (a.getAttribute("href") || "").startsWith("javascript")));
  // a picture on every story, the lead's bigger; a story naming a player is labeled with the player
  assert.equal(week.querySelectorAll("canvas.px-pic").length, 3);
  assert.ok(week.querySelector("canvas.px-pic--lead"));
  assert.ok(week.querySelectorAll("canvas.px-pic").some((c) => (c.getAttribute("aria-label") || "").includes("Jadan Quillfeather")));
  // earlier weeks folded under their heading
  assert.ok(text(main).includes("Earlier weeks"));
  assert.equal(main.querySelector("#paper-week-2").getAttribute("data-collapsed"), "true");
  view.unmount();
  // an old server sends no weeks: the old digest
  clearEnvelopeCache();
  const old = clone(fixture);
  delete old.weeks;
  route("/api/newspaper", () => envelope(old));
  const main2 = document.createElement("main");
  document.body.append(main2);
  const view2 = paper.createNewspaperView({});
  view2.mount(main2);
  await settle();
  assert.ok(text(main2).includes("Old digest story") && !RAW.test(text(main2)));
  view2.unmount();
};
"""


@pytest.fixture(scope="module")
def fixture_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("paper") / "paper.json"
    path.write_text(json.dumps(PAPER), encoding="utf-8")
    return path


@needs_node
def test_newspaper_in_a_fake_browser(tmp_path: Path, fixture_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "paper", str(fixture_path))
