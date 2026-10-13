"""Queue items 10 to 12 in the fake browser (mock approved 2026-10-13): the Newspaper to the owner's whiteboard. The
masthead with this week's name and the edition arrows; our lead story beside the top-ranked game; the player feature and
the coach's story (headlines only); then rows mixing stories and ranked games by rank, a headline before kickoff and
after the final only; an earlier edition, a missing one and an old server's answer; no undefined, null or NaN on screen."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario


def team(school: str, abbr: str, rank: int | None, points: int | None = None, lines: list[int] | None = None, color: str = "#336699") -> dict:
    return {"school": school, "abbreviation": abbr, "mascot": "Things", "rank": rank, "apRank": rank, "color": color, "altColor": "#ffffff", "record": {"wins": 5, "losses": 1}, "conferenceRecord": {"wins": 3, "losses": 1}, "points": points, "lineScores": lines, "headCoach": "A Coach", "form": []}


def game(gid: int, status: str, away: dict, home: dict, *, headline: dict | None = None, us: bool = False, **extra) -> dict:
    return {
        "gameId": gid, "week": 8, "seasonType": "regular", "bowl": None, "kickoff": "2026-10-24T19:30:00Z", "startTimeTbd": False, "neutralSite": False,
        "conferenceGame": True, "conference": "Big Casserole", "venue": "Prairie Fire Stadium", "tv": "Snack Sports", "status": status, "detail": "Q2 7:02" if status == "live" else None,
        "period": 2 if status == "live" else None, "clock": "7:02" if status == "live" else None, "isUs": us, "href": "#live" if us else f"#box={gid}",
        "away": away, "home": home, "line": {"spread": -3.5, "formatted": "Prairie Fire -3.5", "short": "EMBR -3.5", "overUnder": 58.5, "pickem": False},
        "homeWinProbability": 0.61, "weather": None, "headline": headline, **extra,
    }


MATCHUPS = [
    game(1, "final", team("Saddle Sore", "SADL", 2, 54, [6, 10, 0, 24, 7, 7]), team("Prairie Fire", "EMBR", 20, 47, [3, 14, 13, 10, 7, 0]), headline={"kind": "overtime", "kicker": "Overtime", "text": "No. 2 Saddle Sore outlasts No. 20 Prairie Fire, 54-47, in 2 overtimes"}),
    game(2, "live", team("Snowdrift State", "SNOW", 6, 2), team("Hayloft", "HAY", 18, 0)),
    game(3, "pre", team("Rust Belt", "RVT", 9), team("Tater Tot Tech", "TOT", None), headline={"kind": "preLate", "kicker": "Late show", "text": "No. 9 Rust Belt visits Tater Tot Tech, 10:30 PM kickoff; brew the coffee"}),
    game(4, "live", team("Swampwater Tech", "SWT", None), team("Bluegrass Bottoms", "BLUE", 12), us=True),
    game(5, "final", team("Loon Lake", "LOON", None, 19), team("Snowmobile Tech", "SLED", 25, 3), headline={"kind": "finalUpset", "kicker": "Upset", "text": "Loon Lake sends No. 25 Snowmobile Tech home grumbling, 19-3"}),
]


def story(title: str, topic: str, hours: int, players: list | None = None, url: str = "https://example.com/s") -> dict:
    return {"title": title, "url": url, "source": "Campus Daily", "publishedAt": f"2026-10-24T{max(0, 20 - hours):02d}:00:00Z", "topic": topic, "players": players or []}


HEADLINES = [
    story("Gameday: Swampwater Tech visits Bluegrass Bottoms", "stadium", 1),
    story("Jadan Quillfeather has the offense humming", "game", 2, [{"playerId": "11", "name": "Jadan Quillfeather", "team": "Swampwater Tech"}]),
    story("Head coach on the Banjos: they are fast", "coach", 3),
    story("Storms in the forecast", "weather", 4, url="javascript:alert(1)"),
    story("Thursday practice ran loud", "practice", 5),
    {"title": None}, "junk",
]

PAPER = {
    "season": 2026,
    "today": "2026-10-24",
    "feeds": {"espn": {"name": "ESPN", "status": "ok", "count": 3, "betting": 1}},
    "weeks": [{"key": "4", "gameId": 4, "week": 8, "label": "Week 8 · at Bluegrass Bottoms", "opponent": "Bluegrass Bottoms", "homeAway": "away", "kickoff": "2026-10-24T23:00:00Z", "headlines": HEADLINES[:2]}],
    "editions": [
        {"key": "week-7", "label": "Week 7", "opponent": "Catfish Bend", "homeAway": "home", "saved": True, "frozen": True, "current": False},
        {"key": "week-8", "label": "Week 8", "opponent": None, "homeAway": None, "saved": True, "frozen": False, "current": True},
    ],
    "edition": {"key": "week-8", "season": 2026, "label": "Week 8", "week": 8, "seasonType": "regular", "gameId": 4, "opponent": "Bluegrass Bottoms", "homeAway": "away", "date": "2026-10-24T23:00:00Z", "headlines": HEADLINES, "matchups": MATCHUPS, "offThisWeek": [], "frozen": False, "current": True},
    "parts": {},
}

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

async function mounted(paper, data, opts = {}) {
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  route("/api/newspaper", () => envelope(clone(data)));
  const main = document.createElement("main");
  document.body.append(main);
  const view = paper.createNewspaperView(opts);
  view.mount(main);
  await settle();
  return { main, view };
}

scenarios.paper = async () => {
  installWindow();
  const fixture = JSON.parse(readFileSync(process.argv[4], "utf8"));
  const { setIdentity } = await import(moduleUrl("identity.js"));
  setIdentity({ school: "Swampwater Tech", mascot: "Mudpuppies", label: "SWT", name: "Mudpuppies" });
  const paper = await import(moduleUrl("views/newspaper.js"));
  // the masthead: steady within a week, a different name for some other week, from the team's own names
  assert.equal(paper.mastheadName(2026, 6), paper.mastheadName(2026, 6));
  const names = new Set([1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((w) => paper.mastheadName(2026, w)));
  assert.ok(names.size >= 3 && [...names].every((n) => n.includes("Mudpuppies") || n.includes("Swampwater Tech")));
  assert.ok(paper.mastheadName(null, null, null).startsWith("The "));
  // the stories for the boxes: the player feature names one of ours, the coach's story is about the coach (headlines only)
  const picked = paper.pickStories(fixture.edition.headlines, "Swampwater Tech");
  assert.equal(picked.lead.title, "Gameday: Swampwater Tech visits Bluegrass Bottoms");
  assert.equal(picked.player.title, "Jadan Quillfeather has the offense humming");
  assert.equal(picked.coach.topic, "coach");
  assert.deepEqual(picked.rest.map((h) => h.topic), ["weather", "practice"]);
  assert.deepEqual(paper.pickStories(null), { lead: null, player: null, coach: null, rest: [] });
  // the rows after the first two: a matchup and a story switching sides, then whatever is left, two a row
  const rows = paper.paperRows([{ t: 1 }, { t: 2 }], [{ m: 1 }, { m: 2 }, { m: 3 }, { m: 4 }]);
  assert.deepEqual(rows.map((r) => r.map(([k]) => k).join("")), ["MA", "AM", "MM"]);
  assert.deepEqual(paper.paperRows([], []), []);
  assert.deepEqual(paper.paperRows([{ t: 1 }], []).map((r) => r.length), [1]);

  const { main, view } = await mounted(paper, fixture);
  const t = text(main);
  assert.ok(!RAW.test(t), t.slice(0, 400));
  assert.equal(text(main.querySelector(".paper-mast__name")), paper.mastheadName(2026, 8));
  const line = text(main.querySelector(".paper-mast__line"));
  assert.ok(line.includes("Week 8 edition") && line.includes("at Bluegrass Bottoms"), line);
  const prev = main.querySelector("a.paper-mast__nav--prev");
  assert.equal(prev.getAttribute("href"), "#newspaper=week-7");
  assert.ok(text(prev).includes("Week 7 edition") && text(prev).includes("vs Catfish Bend"));
  assert.ok(main.querySelector(".paper-mast__nav--next").className.includes("is-off"), "this week's paper has no later edition");
  // row 1: our lead beside the top-ranked game, two helmets in their teams' colors
  const rowA = main.querySelector(".paper-row--a");
  assert.equal(text(rowA.querySelector(".paper-lead .paper-head--lead")), "Gameday: Swampwater Tech visits Bluegrass Bottoms");
  assert.ok(rowA.querySelector(".paper-lead canvas.px-fill--stadium"));
  const top = rowA.querySelector(".paper-match--big");
  assert.equal(top.querySelectorAll("canvas.px-fill--helmet").length, 2);
  assert.ok(text(top).includes("54-47") && text(top.querySelector(".paper-score")).includes("Final, 2 overtimes"));
  assert.ok(top.querySelector(".paper-qline"), "a finished top game shows its score by quarter");
  assert.equal(top.querySelector(".paper-head a").getAttribute("href"), "#box=1");
  assert.ok(top.querySelector(".paper-head--final"), "a final's headline is hidden in spoiler mode");
  // row 2: the player feature and the coach's story, each a headline linking out
  const rowB = main.querySelector(".paper-row--b");
  const player = rowB.querySelector(".paper-feat--player");
  assert.ok(text(player).includes("Player feature") && player.querySelector("canvas.px-fill--player"));
  assert.equal(player.querySelector(".paper-head a").getAttribute("href"), "https://example.com/s");
  assert.ok(text(rowB.querySelector(".paper-feat--coach")).includes("From the coach") && rowB.querySelector("canvas.px-fill--coach"));
  // the rest: the other four games and the two other stories, in rows of two; a bad link is plain text
  const rest = main.querySelectorAll(".paper-row--rest");
  assert.equal(rest.flatMap((r) => r.querySelectorAll(".paper-match--half")).length, 4);
  assert.equal(rest.flatMap((r) => r.querySelectorAll(".paper-art")).length, 2);
  assert.ok(!main.querySelectorAll("a").some((a) => (a.getAttribute("href") || "").startsWith("javascript")));
  // a live game: no headline, the score, the quarter and the clock; ours links to In Game, the others to their box score
  const live = main.querySelectorAll(".paper-match--live");
  assert.equal(live.length, 2);
  for (const box of live) assert.equal(box.querySelector(".paper-head"), null, "no funny headline while a game is on");
  assert.ok(text(live[0]).includes("SNOW 2") && text(live[0]).includes("2nd quarter, 7:02 left"));
  assert.equal(main.querySelector(".paper-match--us .paper-status").getAttribute("href"), "#live");
  assert.ok(text(main.querySelector(".paper-match--us")).includes("Our game"));
  // a game to come: its headline, its kickoff, the line and the win probability
  const pre = main.querySelector(".paper-match--pre");
  assert.ok(text(pre).includes("brew the coffee") && text(pre).includes("EMBR -3.5") && pre.querySelector(".paper-wp"));
  view.unmount();

  // an earlier edition, as the paper printed it (rebuilt from the headlines: no matchups)
  const old = clone(fixture);
  old.edition = { key: "week-7", season: 2026, label: "Week 7", week: 7, opponent: "Catfish Bend", homeAway: "home", date: "2026-10-17T19:30:00Z", headlines: fixture.edition.headlines.slice(0, 2), matchups: [], current: false, rebuilt: true, frozen: true };
  const second = await mounted(paper, old, { edition: "week-7" });
  const t2 = text(second.main);
  assert.ok(!RAW.test(t2) && t2.includes("Week 7 edition, as the paper printed it"), t2.slice(0, 300));
  assert.equal(second.main.querySelector(".paper-back a").getAttribute("href"), "#newspaper");
  assert.ok(second.main.querySelector(".paper-row--a.paper-row--one"), "no matchup: the lead takes the row");
  assert.equal(second.main.querySelector("a.paper-mast__nav--next").getAttribute("href"), "#newspaper");
  second.view.unmount();

  // a kept edition with a game the season never finished: "Not played", no score, no headline
  const kept = clone(old);
  kept.edition.rebuilt = false;
  kept.edition.matchups = [{ ...fixture.edition.matchups[1], status: "unplayed", detail: "Not played", headline: null }];
  const keptView = await mounted(paper, kept, { edition: "week-7" });
  const k = text(keptView.main.querySelector(".paper-match"));
  assert.ok(k.includes("Not played") && k.includes("was not played") && !k.includes("SNOW 2"), k);
  assert.equal(keptView.main.querySelector(".paper-match .paper-head"), null);
  keptView.view.unmount();

  // a week the season has no paper for
  const none = clone(fixture);
  none.edition = null;
  const third = await mounted(paper, none, { edition: "week-2" });
  assert.ok(text(third.main).includes("No paper was kept for week 2") && third.main.querySelector('a[href="#newspaper"]'));
  third.view.unmount();

  // a server from before items 10-12 sends no edition: this week's headlines, no matchups
  const older = clone(fixture);
  delete older.edition;
  delete older.editions;
  const fourth = await mounted(paper, older);
  assert.ok(text(fourth.main).includes("Jadan Quillfeather has the offense humming") && !RAW.test(text(fourth.main)));
  fourth.view.unmount();
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
