"""Queue items 10 to 12 in the fake browser (mock approved 2026-10-13), laid out as a newspaper's front page since the
layout pass (owner 2026-10-22, board 5): the masthead with this week's name and the edition arrows; the skybox; our game
as the dominant story with a banner headline, the deck and the press box; the game of the week beside "By the numbers";
the player feature, the coach's story and every ranked game in one line of agate; the briefs; an earlier edition, a
missing one and an old server's answer; no undefined, null or NaN on screen."""

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
  // a school in a line of agate: shortened the way a newspaper does, never cut (his 2)
  assert.equal(paper.agateName("Dust Devil State"), "Dust Devil St.");
  assert.equal(paper.agateName("Moonpie Mountain"), "Moonpie Mtn.");
  assert.equal(paper.agateName("Red Clay"), "Red Clay", "a short name stays whole");
  assert.equal(paper.agateName(null), "–");
  // the game of the week (the layout pass, 2026-10-22): the matchups come in AP poll order, so No. 1 against an unranked
  // team leads them; the game drawn large is still the best pair of ranked teams, else the first game not ours
  const g = (id, a, h, extra = {}) => ({ gameId: id, away: { rank: a }, home: { rank: h }, ...extra });
  const week = [g(1, 1, null), g(2, 2, 20), g(3, 6, 18), g(4, 9, 13), g(5, null, 12, { isUs: true })];
  assert.equal(paper.gameOfWeek(week).gameId, 2, "No. 2 against No. 20 (22) over No. 9 against No. 13 (22, the better rank wins)");
  assert.equal(paper.gameOfWeek([g(1, 1, null), g(5, 3, 4, { isUs: true }), g(6, null, 7)]).gameId, 1, "no other ranked pair: the first game not ours");
  assert.equal(paper.gameOfWeek([g(5, 3, 4, { isUs: true })]), null);
  assert.equal(paper.gameOfWeek(null), null);
  assert.equal(paper.gameOfWeek([null, "x", g(8, "2", 3), g(9, 5, 6)]).gameId, 9, "a malformed rank is no rank");

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
  // the lead (board 5): our game under way, its score as the banner, the stadium, the press box with the way into In Game
  const lead = main.querySelector(".front-lead");
  assert.ok(text(lead.querySelector(".paper-kicker")).includes("Game week · Live"));
  const liveBanner = lead.querySelector(".front-banner--live .paper-status");
  assert.equal(liveBanner.getAttribute("href"), "#live", "our game opens In Game");
  assert.ok(text(liveBanner).includes("2nd quarter, 7:02 left"), text(liveBanner));
  assert.ok(lead.querySelector("canvas.px-fill--stadium"));
  assert.ok(text(lead.querySelector(".front-col")).includes("From the press box"));
  assert.ok(text(lead.querySelector(".front-deck")).includes("Prairie Fire Stadium"), "the deck before the final: when and where");
  // the game of the week: the top-ranked other game across two columns, two helmets in their teams' colors
  const top = main.querySelector(".front-tier--two .front-span2 .paper-match--big");
  assert.equal(top.querySelectorAll("canvas.px-fill--helmet").length, 2);
  assert.ok(text(top).includes("54-47") && text(top.querySelector(".paper-score")).includes("Final, 2 overtimes"));
  assert.ok(top.querySelector(".paper-qline"), "a finished top game shows its score by quarter");
  assert.equal(top.querySelector(".paper-head a").getAttribute("href"), "#box=1");
  assert.ok(top.querySelector(".paper-head--final"), "a final's headline is hidden in spoiler mode");
  // beside it, by the numbers: before the final, the two teams' records and the over/under
  const nums = main.querySelectorAll(".front-tier--two .front-rail .front-num");
  assert.ok(nums.length >= 2 && text(nums[0]).includes("5-1"), text(main.querySelector(".front-numbers")));
  // the next tier: the player feature and the coach's story (headlines linking out), then the rail's scoreboard
  const player = main.querySelector(".front-tier--three .front-mod--player .paper-feat--player");
  assert.ok(text(player).includes("Player feature") && player.querySelector("canvas.px-fill--player"));
  assert.equal(player.querySelector(".paper-head a").getAttribute("href"), "https://example.com/s");
  const coach = main.querySelector(".front-tier--three .front-mod--coach .paper-feat--coach");
  assert.ok(text(coach).includes("From the coach") && coach.querySelector("canvas.px-fill--coach"));
  // every ranked game one line of agate (his 1: the Top 25 compact): the winner first after a final, the quarter while live,
  // the kickoff before, ours marked; the full cards a tap away on the Top 25 page
  const agate = main.querySelectorAll(".front-agate__row");
  assert.equal(agate.length, 5);
  assert.ok(text(agate[0]).startsWith("2 Saddle Sore 54, 20 Prairie Fire 47") && text(agate[0]).endsWith("2OT"), text(agate[0]));
  assert.ok(text(agate[1]).includes("6 Snowdrift St. 2, 18 Hayloft 0") && text(agate[1]).endsWith("Q2"), text(agate[1]));
  assert.ok(text(agate[2]).startsWith("9 Rust Belt at Tater Tot Tech"), text(agate[2]));
  assert.ok(agate[3].className.includes("is-us"));
  assert.equal(main.querySelector(".front-scores .front-refer").getAttribute("href"), "#top25");
  // the briefs at the foot: the other stories, and the feed's lead (our game leads the page); a bad link is plain text
  const briefs = main.querySelectorAll(".front-briefs .front-brief").map(text);
  assert.ok(briefs.some((b) => b.includes("Storms in the forecast")) && briefs.some((b) => b.includes("Gameday: Swampwater Tech visits")), briefs.join(" | "));
  assert.ok(!main.querySelectorAll("a").some((a) => (a.getAttribute("href") || "").startsWith("javascript")));
  view.unmount();

  // after our final, with the recap: the paper's own headline as the banner, the player of the game and the record in the
  // deck, the turning point and the key stats in the press box, the key stats by the numbers, the skybox's refers
  const done = clone(fixture);
  const ourGame = done.edition.matchups[3];
  Object.assign(ourGame, { status: "final", detail: "Final", period: null, clock: null, headline: { kind: "final", text: "Swampwater Tech takes down No. 12 Bluegrass Bottoms, 40-34" } });
  ourGame.away.points = 40;
  ourGame.home.points = 34;
  done.rankedWeek = { counts: { live: 1, pre: 1, final: 3 } };
  done.recap = { gameId: 4, opponent: "Bluegrass Bottoms", final: { usScore: 40, themScore: 34, result: "W" }, record: { wins: 5, losses: 2, ties: 0 }, playerOfGame: { name: "Keegan Crawford", position: "QB", isUs: true, value: 19.7 }, turningPoint: { period: 4, clock: { minutes: 4, seconds: 55 }, usScore: 40, themScore: 34, usWpBefore: 0.6487, usWpAfter: 0.9219 }, keyStats: [{ label: "Turnovers", format: "0f", us: 0, them: 3 }, { label: "Third-down rate", format: "pct", us: 0.214, them: 0.4 }, null], next: { opponent: "Front Porch State", homeAway: "home", date: "2026-10-31T19:30:00Z" } };
  const fin = await mounted(paper, done);
  const ft = text(fin.main);
  assert.ok(!RAW.test(ft), ft.slice(0, 400));
  const banner = fin.main.querySelector(".front-banner");
  assert.equal(text(banner), "Swampwater Tech takes down No. 12 Bluegrass Bottoms, 40-34");
  assert.ok(banner.className.includes("paper-head--final"), "a final's banner is hidden in spoiler mode");
  const deck = text(fin.main.querySelector(".front-deck"));
  assert.ok(deck.includes("Keegan Crawford is the player of the game") && deck.includes("moves to 5-2"), deck);
  const press = text(fin.main.querySelector(".front-col"));
  assert.ok(press.includes("4:55 left in the 4th quarter") && press.includes("65% to 92%") && press.includes("Turnovers: SWT 0, BLUE 3") && press.includes("21%") && press.includes("Next: Front Porch State at home"), press);
  assert.ok(fin.main.querySelector('.front-col a[href="#program=4"]'), "the way into the Post-Game Program");
  assert.equal(text(fin.main.querySelector(".front-numbers .front-num b")), "0", "the key stats by the numbers");
  const sky = fin.main.querySelectorAll(".front-sky__item").map(text);
  assert.ok(sky[0].includes("Next up") && sky[0].includes("Front Porch State") && sky[1].includes("3 final, 1 live, 1 to come") && sky[2].includes("5-2"), sky.join(" | "));
  assert.ok(text(fin.main.querySelector(".front-agate .is-us")).startsWith("Swampwater Tech 40, 12 Bluegrass Bottoms 34"));
  fin.view.unmount();

  // an earlier edition, as the paper printed it (rebuilt from the headlines: no matchups)
  const old = clone(fixture);
  old.edition = { key: "week-7", season: 2026, label: "Week 7", week: 7, opponent: "Catfish Bend", homeAway: "home", date: "2026-10-17T19:30:00Z", headlines: fixture.edition.headlines.slice(0, 2), matchups: [], current: false, rebuilt: true, frozen: true };
  const second = await mounted(paper, old, { edition: "week-7" });
  const t2 = text(second.main);
  assert.ok(!RAW.test(t2) && t2.includes("Week 7 edition, as the paper printed it"), t2.slice(0, 300));
  assert.equal(second.main.querySelector(".paper-back a").getAttribute("href"), "#newspaper");
  assert.equal(text(second.main.querySelector(".front-banner a")), "Gameday: Swampwater Tech visits Bluegrass Bottoms", "no matchup: the feed's lead story leads");
  assert.equal(second.main.querySelector(".front-tier--two"), null, "no game of the week and nothing to number");
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
