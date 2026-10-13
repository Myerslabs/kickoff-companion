"""Queue item 11 in the fake browser (mock approved 2026-10-13): the Top 25 page. Every game with an AP Top 25 team as a
compact Pre-Game Program cover (the same facts as the cover, no headlines), the live score with its quarter and clock, a
final without anyone's Won or Lost, Off this week, the spoiler-delay line; the tab after Season and every page in the
menu (owner 2026-10-13: "everything should always be accessible from the menu")."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario
from tests.test_paper_js import MATCHUPS

ROOT = Path(__file__).resolve().parents[1]

TOP25 = {
    "season": 2026, "week": 8, "seasonType": "regular", "label": "Week 8", "poll": {"name": "AP Top 25", "week": 8, "teams": 25},
    "delaySeconds": 30, "weather": "cfbd",
    "games": [{**g, "weather": {"tempF": 57.2, "windMph": 10.6, "windDir": "ESE", "sky": None, "indoors": False}} for g in MATCHUPS] + [{"junk": True}],
    "offThisWeek": [{"school": "Crab Cake", "rank": 5}, {"school": "Seagull Shores", "rank": 10}, None],
    "counts": {"live": 2, "pre": 1, "final": 2}, "note": None, "parts": {},
}

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

async function mounted(data) {
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  route("/api/top25", () => envelope(clone(data)));
  const { createTop25View } = await import(moduleUrl("views/top25.js"));
  const main = document.createElement("main");
  document.body.append(main);
  const view = createTop25View({});
  view.mount(main);
  await settle();
  return { main, view };
}

scenarios.top25 = async () => {
  installWindow();
  const fixture = JSON.parse(readFileSync(process.argv[4], "utf8"));
  const { setIdentity } = await import(moduleUrl("identity.js"));
  setIdentity({ school: "Swampwater Tech", mascot: "Mudpuppies", label: "SWT", name: "Mudpuppies" });
  const { main, view } = await mounted(fixture);
  const t = text(main);
  assert.ok(!RAW.test(t), t.slice(0, 400));
  assert.equal(text(main.querySelector(".top25-head__title")), "AP Top 25, Week 8");
  assert.ok(text(main.querySelector(".top25-head__line")).includes("AP poll, week 8") && text(main.querySelector(".top25-head__line")).includes("5 games with a ranked team"));
  assert.ok(text(main.querySelector(".top25-head__counts")).includes("2 live"));
  assert.ok(text(main.querySelector(".top25-head__delay")).includes("30 s behind the broadcast"));
  // one compact cover a game, in the server's order; the junk row is skipped
  const cards = main.querySelectorAll(".top25-card");
  assert.equal(cards.length, 5);
  for (const card of cards) {
    assert.ok(card.className.includes("cover--compact"));
    assert.equal(card.querySelectorAll(".cover__nav").length, 0, "no arrows on a card");
    assert.equal(card.querySelectorAll(".cover__actions").length, 0, "no buttons on a card");
    assert.ok(!text(card).includes("SP+"), "no SP+ chip on a card");
    assert.ok(card.querySelectorAll(".cover__name").every((n) => n.dataset.oneline === "1"));
  }
  assert.equal(cards[0].getAttribute("aria-label"), "Saddle Sore at Prairie Fire");
  // a final: the score and "Final, 2 overtimes", never one side's Won or Lost; its score opens the box score
  assert.ok(text(cards[0].querySelector(".cover__middle")).includes("Final, 2 overtimes"));
  assert.ok(!/\bWon\b|\bLost\b/.test(text(cards[0])));
  assert.equal(cards[0].querySelector("a.cover__middle--link").getAttribute("href"), "#box=1");
  // a live game: the score with its quarter and clock, Live in the kicker
  assert.ok(text(cards[1].querySelector(".cover__middle")).includes("SNOW 2") && text(cards[1].querySelector(".cover__middle")).includes("2nd quarter, 7:02"));
  assert.ok(text(cards[1].querySelector(".cover__kicker")).includes("Live"));
  // ours: Our game in the kicker, the middle opens In Game
  assert.ok(cards[3].className.includes("top25-card--us") && text(cards[3].querySelector(".cover__kicker")).includes("Our game"));
  assert.equal(cards[3].querySelector("a.cover__middle--link").getAttribute("href"), "#live");
  // the cover's facts: the line by abbreviation, the head coaches, the weather, the win probability in both colors
  assert.ok(text(cards[2]).includes("EMBR -3.5") && text(cards[2]).includes("A Coach"));
  assert.ok(text(cards[2].querySelector(".top25-weather")).includes("57°F") && text(cards[2].querySelector(".top25-weather")).includes("wind 11 mph ESE"));
  assert.ok(cards[2].querySelector(".cover__wpbar--teams"));
  // no headlines on this page (owner)
  assert.ok(!t.includes("brew the coffee") && !t.includes("grumbling"));
  // off this week: a line, no card
  const off = main.querySelector(".top25-off");
  assert.ok(text(off).includes("Off this week") && text(off).includes("No. 5 Crab Cake") && text(off).includes("Seagull Shores"));
  view.unmount();

  // no poll yet: the note, no cards
  const empty = clone(fixture);
  empty.games = [];
  empty.offThisWeek = [];
  empty.note = "No AP poll yet this season.";
  empty.delaySeconds = 0;
  empty.weather = "none";
  const second = await mounted(empty);
  const t2 = text(second.main);
  assert.ok(t2.includes("No AP poll yet this season.") && t2.includes("no spoiler delay") && t2.includes("Tier 1 key") && !RAW.test(t2), t2.slice(0, 400));
  assert.equal(second.main.querySelectorAll(".top25-card").length, 0);
  second.view.unmount();
};

scenarios.tabs = async () => {
  const { VIEWS, MENU } = await import(moduleUrl("ui/shell.js"));
  assert.deepEqual(VIEWS.map((v) => v.id), ["newspaper", "program", "live", "season", "top25"], "Top 25 right after Season (owner)");
  const views = MENU.find((g) => g.group === "Views").items.map((i) => i.id);
  for (const v of VIEWS) assert.ok(views.includes(v.id), `${v.id} in the menu's Views`);
};
"""

# Pages reached from inside another page rather than from the menu: a team (any team name), a box score (any game), a
# national list (any rank chip), the board (In Game's Big screen button), the Archive and Season in review (the Setup page,
# which the menu holds), the radio (the Pre-Game Program's radio band).
CONTEXT_ROUTES = {"team", "box", "national", "board", "archive", "review", "radio"}


@pytest.fixture(scope="module")
def fixture_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("top25") / "top25.json"
    path.write_text(json.dumps(TOP25), encoding="utf-8")
    return path


@needs_node
def test_the_top25_page_in_a_fake_browser(tmp_path: Path, fixture_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "top25", str(fixture_path))


@needs_node
def test_the_top25_tab_sits_after_season(tmp_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "tabs")


def test_every_page_is_in_the_menu() -> None:
    """Owner 2026-10-13: "everything should always be accessible from the menu". Every page the router builds is a menu
    item, or a page reached from inside one (CONTEXT_ROUTES, each named with where it is reached from)."""
    app = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    shell = (ROOT / "static" / "js" / "ui" / "shell.js").read_text(encoding="utf-8")
    built = re.search(r"const BUILT = \{(.*?)\n\};", app, re.S)
    assert built, "app.js BUILT"
    routes = set(re.findall(r"^\s{2}(\w+): \(", built.group(1), re.M))
    assert {"newspaper", "top25", "season", "settings"} <= routes
    menu = set(re.findall(r'\{ id: "(\w+)"', shell))
    missing = sorted(routes - menu - CONTEXT_ROUTES)
    assert not missing, f"pages the menu cannot reach: {missing}"
