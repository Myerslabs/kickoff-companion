"""Queue item 11 in the fake browser (mock approved 2026-10-13): the Top 25 page. Every game with an AP Top 25 team as a
compact Pre-Game Program cover (the same facts as the cover, no headlines), the live score with its quarter and clock, a
final without anyone's Won or Lost, Off this week, the spoiler-delay line; the tab after Season and every page in the
menu (owner 2026-10-13: "everything should always be accessible from the menu"). The layout pass, board 6 (owner
2026-10-22): the score alone in the middle, the rows level, "Head coach" over the name, the weather and the tools in the
last row, "In poll order" in the header."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]


# the ranked games of a week (the old Newspaper test's, kept here when the paper's test moved to FEAT-14's layout)
def team(school: str, abbr: str, rank: int | None, points: int | None = None, lines: list[int] | None = None, color: str = "#336699") -> dict:
    return {"school": school, "abbreviation": abbr, "mascot": "Things", "rank": rank, "apRank": rank, "color": color, "altColor": "#ffffff", "record": {"wins": 5, "losses": 1}, "conferenceRecord": {"wins": 3, "losses": 1}, "points": points, "lineScores": lines, "headCoach": "A Coach", "form": []}


def game(gid: int, status: str, away: dict, home: dict, *, headline: dict | None = None, us: bool = False, **extra) -> dict:
    return {
        "gameId": gid, "week": 8, "seasonType": "regular", "bowl": None, "kickoff": "2026-10-24T19:30:00Z", "startTimeTbd": False, "neutralSite": False,
        "conferenceGame": True, "conference": "Big 12", "venue": "Iowa State Stadium", "tv": "Snack Sports", "status": status, "detail": "Q2 7:02" if status == "live" else None,
        "period": 2 if status == "live" else None, "clock": "7:02" if status == "live" else None, "isUs": us, "href": "#live" if us else f"#box={gid}",
        "away": away, "home": home, "line": {"spread": -3.5, "formatted": "Iowa State -3.5", "short": "ISU -3.5", "overUnder": 58.5, "pickem": False},
        "homeWinProbability": 0.61, "weather": None, "headline": headline, **extra,
    }


MATCHUPS = [
    game(1, "final", team("West Virginia", "WVU", 2, 54, [6, 10, 0, 24, 7, 7]), team("Iowa State", "ISU", 20, 47, [3, 14, 13, 10, 7, 0]), headline={"kind": "overtime", "kicker": "Overtime", "text": "No. 2 West Virginia outlasts No. 20 Iowa State, 54-47, in 2 overtimes"}),
    game(2, "live", team("Mississippi State", "MSST", 6, 2), team("Purdue", "PUR", 18, 0)),
    game(3, "pre", team("UCLA", "UCLA", 9), team("Michigan State", "MSU", None), headline={"kind": "preLate", "kicker": "Late show", "text": "No. 9 UCLA visits Michigan State, 10:30 PM kickoff; brew the coffee"}),
    game(4, "live", team("Florida", "FLA", None), team("Texas", "TEX", 12), us=True),
    game(5, "final", team("North Texas", "UNT", None, 19), team("Memphis", "MEM", 25, 3), headline={"kind": "finalUpset", "kicker": "Upset", "text": "North Texas sends No. 25 Memphis home grumbling, 19-3"}),
]

TOP25 = {
    "season": 2026, "week": 8, "seasonType": "regular", "label": "Week 8", "poll": {"name": "AP Top 25", "week": 8, "teams": 25},
    "delaySeconds": 30, "weather": "cfbd",
    "games": [{**g, "weather": {"tempF": 57.2, "windMph": 10.6, "windDir": "ESE", "sky": None, "indoors": False}} for g in MATCHUPS] + [{"junk": True}],
    "offThisWeek": [{"school": "SMU", "rank": 5}, {"school": "Florida State", "rank": 10}, None],
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
  setIdentity({ school: "Florida", mascot: "Gators", label: "FLA", name: "Gators" });
  const { main, view } = await mounted(fixture);
  const t = text(main);
  assert.ok(!RAW.test(t), t.slice(0, 400));
  assert.equal(text(main.querySelector(".top25-head__title")), "AP Top 25, Week 8");
  assert.ok(text(main.querySelector(".top25-head__line")).includes("AP poll, week 8") && text(main.querySelector(".top25-head__line")).includes("5 games with a ranked team"));
  assert.ok(text(main.querySelector(".top25-head__line")).startsWith("In poll order"), "board 6: the header says how the cards run");
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
    // board 6: a long name wraps (never fitted down to the abbreviation); both sides keep the same rows, an unranked
    // team its empty AP row and a team with no games its empty last five, so the rows stay level
    assert.ok(card.querySelectorAll(".cover__name").every((n) => n.dataset.oneline !== "1"));
    for (const side of card.querySelectorAll(".cover__side")) {
      assert.equal(side.querySelectorAll(".cover__ap").length, 1);
      assert.equal(side.querySelectorAll(".form-guide").length, 1);
    }
    assert.equal(card.querySelectorAll(".top25-coach").length, 2, "Head coach over each name");
    assert.ok(card.querySelectorAll(".top25-coach").every((c) => text(c).startsWith("Head coach")));
    // the last row: the weather at the left, Matchup at the right
    const row = card.querySelector(".cover__foot-row");
    assert.ok(row && row.querySelector(".top25-weather") && row.querySelector(".top25-card__matchup"));
    // the when in two lines: the day and time, then the stadium and the TV
    assert.ok(card.querySelector(".cover__when-day") && card.querySelector(".cover__when-place"));
  }
  assert.equal(cards[0].getAttribute("aria-label"), "West Virginia at Iowa State");
  // a final: the points alone (the sides say who is who), "Final · 2 OT", never one side's Won or Lost; its score opens
  // the box score; the abbreviations stay in the score's label
  const finalScore = cards[0].querySelector(".cover__score");
  assert.equal(text(finalScore), "54 · 47");
  assert.equal(finalScore.getAttribute("aria-label"), "Final: WVU 54, ISU 47");
  assert.ok(text(cards[0].querySelector(".cover__middle")).includes("Final · 2 OT"));
  assert.ok(!/\bWon\b|\bLost\b/.test(text(cards[0])));
  assert.equal(cards[0].querySelector("a.cover__middle--link").getAttribute("href"), "#box=1");
  // a live game: the score with its quarter and clock, Live in the kicker
  assert.equal(text(cards[1].querySelector(".cover__score")), "2 · 0");
  assert.ok(text(cards[1].querySelector(".cover__middle")).includes("Q2 · 7:02"), text(cards[1].querySelector(".cover__middle")));
  assert.ok(text(cards[1].querySelector(".cover__kicker")).includes("Live"));
  // ours: Our game in the kicker, the middle opens In Game
  assert.ok(cards[3].className.includes("top25-card--us") && text(cards[3].querySelector(".cover__kicker")).includes("Our game"));
  assert.equal(cards[3].querySelector("a.cover__middle--link").getAttribute("href"), "#live");
  // the cover's facts: the line by abbreviation, the head coaches, the weather, the win probability in both colors
  assert.ok(text(cards[2]).includes("ISU -3.5") && text(cards[2]).includes("A Coach") && text(cards[2]).includes("O/U"));
  assert.ok(text(cards[2].querySelector(".top25-weather")).includes("57°F") && text(cards[2].querySelector(".top25-weather")).includes("wind 11 mph ESE"));
  assert.ok(cards[2].querySelector(".cover__wpbar--teams"));
  // no headlines on this page (owner)
  assert.ok(!t.includes("brew the coffee") && !t.includes("grumbling"));
  // off this week: a line, no card
  const off = main.querySelector(".top25-off");
  assert.ok(text(off).includes("Off this week") && text(off).includes("No. 5 SMU") && text(off).includes("Florida State"));
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
  assert.ok(!text(second.main.querySelector(".top25-head__line")).includes("In poll order"), "no cards, no order to state");
  second.view.unmount();

  // the quarter and the clock under a live score, and a final's overtimes, short enough for the card's middle
  const { clockText, overtimes } = await import(moduleUrl("views/top25.js"));
  assert.equal(clockText({ period: 2, clock: "7:02" }), "Q2 · 7:02");
  assert.equal(clockText({ period: 5, clock: null }), "OT");
  assert.equal(clockText({ period: 6 }), "2OT");
  assert.equal(clockText({ period: null, detail: "Halftime" }), "Halftime");
  assert.equal(clockText({ period: "2", clock: "1:00" }), "Under way", "a period as text is no period");
  assert.equal(clockText({}), "Under way");
  assert.equal(overtimes({ home: { lineScores: [1, 2, 3, 4, 5] }, away: { lineScores: [1, 2, 3, 4, 5] } }), "OT");
  assert.equal(overtimes({ home: { lineScores: [1, 2, 3, 4, 5, 6] }, away: null }), "2 OT");
  assert.equal(overtimes({ home: { lineScores: [1, 2, 3, 4] }, away: { lineScores: "x" } }), null);
  assert.equal(overtimes({}), null);
};

scenarios.filters = async () => {
  // post-freeze Wave 3: upsets marked (ENH-5) and the counts as filters (ENH-6)
  installWindow();
  const fixture = JSON.parse(readFileSync(process.argv[4], "utf8"));
  const { setIdentity } = await import(moduleUrl("identity.js"));
  setIdentity({ school: "Florida", mascot: "Gators", label: "FLA", name: "Gators" });
  const { main, view } = await mounted(fixture);
  const cards = () => main.querySelectorAll(".top25-card");
  assert.equal(cards().length, 5);
  const upset = cards().filter((c) => c.className.includes("top25-card--upset"));
  assert.equal(upset.length, 2, "two upsets marked");
  assert.equal(text(upset.find((c) => c.className.includes("top25-card--upset-final")).querySelector(".top25-upset")), "Upset");
  assert.equal(text(upset.find((c) => c.className.includes("top25-card--upset-live")).querySelector(".top25-upset")), "Upset alert");
  const pills = () => main.querySelectorAll(".top25-head__counts button");
  assert.deepEqual(pills().map((b) => text(b)), ["All", "2 live", "1 to come", "2 final", "2 upsets"]);
  assert.equal(pills()[0].getAttribute("aria-pressed"), "true", "every game shows at first");
  pills().find((b) => text(b) === "2 live").click();
  await settle();
  assert.equal(cards().length, 2, "the live games alone");
  assert.ok(cards().every((c) => c.className.includes("top25-card--live")));
  assert.equal(pills().find((b) => text(b) === "2 live").getAttribute("aria-pressed"), "true");
  pills().find((b) => text(b) === "2 upsets").click();
  await settle();
  assert.equal(cards().length, 2, "the upsets alone");
  pills().find((b) => text(b) === "2 upsets").click();
  await settle();
  assert.equal(cards().length, 5, "a second tap shows every game again");
  pills().find((b) => text(b) === "2 final").click();
  await view.refresh();
  await settle();
  assert.equal(cards().length, 2, "the filter lasts across the minute's refresh");
  pills()[0].click();
  await settle();
  assert.equal(cards().length, 5);
  view.unmount();
};

scenarios.tabs = async () => {
  const { VIEWS, TABS, MENU } = await import(moduleUrl("ui/shell.js"));
  const { findPath } = await import(moduleUrl("ui/menu-tree.js"));
  assert.deepEqual(VIEWS.map((v) => v.id), ["newspaper", "program", "live", "season", "top25"], "Top 25 right after Season (owner)");
  assert.deepEqual(TABS.map((v) => v.id), ["newspaper", "program", "live"], "the layout pass (owner 2026-10-22): three tabs; Season and Top 25 in the menu only");
  for (const v of VIEWS) assert.ok(findPath(MENU, (entry) => entry.page === v.id), `${v.id} in the menu`);
  assert.deepEqual(findPath(MENU, (entry) => entry.page === "top25"), ["national", "top25"], "Top 25 under National: one row that opens the page, the picks a band on it (ENH-46, 2026-11-10)");
  assert.deepEqual(findPath(MENU, (entry) => entry.page === "season"), ["teams", "season"], "Season under My Teams: one row that opens the page (ENH-46, 2026-11-10)");
};
"""

# Pages reached from inside another page rather than from the menu: a team (any team name), a box score (any game), a
# national list (any rank chip), the radio (the Pre-Game Program's radio band; the menu's Radio tile opens the stations),
# and the Profile's two older addresses (#settings and #setup open the Profile, which the menu holds).
CONTEXT_ROUTES = {"team", "box", "national", "radio", "settings", "setup", "myteams", "story", "band", "blame", "picks", "compare"}  # compare: two players side by side, from the player card only (batch 3, owner 2026-11-16, "Card only, two"); blame: the old Circle of Blame address, My Team's wheel now (wave 3, 2026-11-01);  # myteams: the old address, the Season page now (board 9); story: the Newspaper's reader (FEAT-14); band: a band's own page, the flyout's Own page (owner 2026-10-28)


@pytest.fixture(scope="module")
def fixture_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("top25") / "top25.json"
    path.write_text(json.dumps(TOP25), encoding="utf-8")
    return path


@needs_node
def test_the_top25_page_in_a_fake_browser(tmp_path: Path, fixture_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "top25", str(fixture_path))


@needs_node
def test_upsets_and_the_count_filters(tmp_path: Path) -> None:
    data = json.loads(json.dumps(TOP25))
    data["games"][0]["upset"] = "final"  # No. 20 beat No. 2 in the fixture's terms: marked as the server would
    data["games"][1]["upset"] = "live"
    data["counts"]["upset"] = 2
    path = tmp_path / "top25-upsets.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    run_scenario(tmp_path, SCENARIOS, "filters", str(path))


@needs_node
def test_the_top25_tab_sits_after_season(tmp_path: Path) -> None:
    run_scenario(tmp_path, SCENARIOS, "tabs")


def test_every_page_is_in_the_menu() -> None:
    """Owner 2026-10-13: "everything should always be accessible from the menu". Every page the router builds is a menu
    item, or a page reached from inside one (CONTEXT_ROUTES, each named with where it is reached from)."""
    app = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    tree = (ROOT / "static" / "js" / "ui" / "menu-tree.js").read_text(encoding="utf-8")  # the menu's tree (the layout pass, 2026-10-22)
    built = re.search(r"const BUILT = \{(.*?)\n\};", app, re.S)
    assert built, "app.js BUILT"
    routes = set(re.findall(r"^\s{2}(\w+): \(", built.group(1), re.M))
    assert {"newspaper", "top25", "season", "settings", "profile"} <= routes
    # a row written pageRow("<page>") opens that page of the catalog, at the catalog's address (ENH-46, 2026-11-10)
    catalog = (ROOT / "static" / "js" / "ui" / "band-catalog.js").read_text(encoding="utf-8")
    rows = set(re.findall(r'pageRow\("([\w-]+)"', tree))
    assert {"season", "newspaper", "top25", "program", "live", "stats-passing"} <= rows
    addresses = {key.strip('"'): route for key, route in re.findall(r'^  ("?[\w-]+"?): \{[^\n]*?route: "(\w+)', catalog, re.M)}
    addresses |= {key: route for key, route in re.findall(r'^  (\w+): \{\n(?:    [^\n]*\n)*?    route: "(\w+)', catalog, re.M)}
    unknown = sorted(rows - set(addresses))
    assert not unknown, f"rows of pages the catalog does not name: {unknown}"
    menu = set(re.findall(r'page: "(\w+)"', tree)) | {addresses[row] for row in rows}
    missing = sorted(routes - menu - CONTEXT_ROUTES)
    assert not missing, f"pages the menu cannot reach: {missing}"
