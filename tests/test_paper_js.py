"""FEAT-14 wave 3 in the fake browser (the owner's boards of 2026-10-27): the paper in one scroll (the masthead and the
week chips; the front page's lead beside the rail, three stories, the game of the week; page 2; page 3 and on; the Top 25
at the back), the earlier weeks folded and opened in place, our final as the lead, an older server's answer, and the
reader; nothing that repeats the tabs; no undefined, null or NaN on screen. The layout is the server's own rule
(app/services/paper_layout.py), built here from made-up stories."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.paper_layout import layout
from tests.fakedom import needs_node, run_scenario


def team(school: str, abbr: str, rank: int | None, points: int | None = None, color: str = "#336699") -> dict:
    return {"school": school, "abbreviation": abbr, "mascot": "Things", "rank": rank, "color": color, "altColor": "#ffffff", "record": {"wins": 5, "losses": 1}, "conferenceRecord": {"wins": 3, "losses": 1}, "points": points, "lineScores": None, "logo": None, "logoDark": None}


def game(gid: int, status: str, away: dict, home: dict, *, headline: dict | None = None, us: bool = False) -> dict:
    return {"gameId": gid, "week": 9, "seasonType": "regular", "kickoff": "2026-10-31T19:30:00Z", "startTimeTbd": False, "neutralSite": False, "conferenceGame": True, "conference": "SEC", "venue": "A Stadium", "status": status, "period": 2 if status == "live" else None, "clock": "7:02" if status == "live" else None, "isUs": us, "away": away, "home": home, "headline": headline}


MATCHUPS = [
    game(1, "final", team("Miami", "MIA", 1, 52), team("North Carolina", "UNC", None, 23), headline={"text": "No. 1 Miami rolls"}),
    game(2, "pre", team("Arizona", "ARIZ", 22), team("Texas Tech", "TTU", 13), headline={"text": "Wildcats at Red Raiders"}),
    game(3, "pre", team("Florida", "FLA", 17), team("Georgia", "UGA", 3), us=True, headline={"text": "Florida meets No. 3 Georgia"}),
    game(4, "live", team("Ohio State", "OSU", 2, 14), team("USC", "USC", None, 10)),
]


def story(n: int, *, copied: bool = False, photo: bool = False, topic: str = "game", url: str | None = None) -> dict:
    sid = f"{n:016x}"
    return {
        "id": sid, "title": f"Gators story number {n}", "url": url or f"https://site.example.invalid/{n}", "source": "Florida Athletics" if copied else "On3", "publishedAt": "2026-10-27T15:00:00Z",
        "topic": topic, "players": [], "copied": copied, "photo": f"/media/paper/{sid}.jpg" if photo else None, "cutline": "A caption." if photo else None, "credit": "A Photographer" if photo else None,
        "opening": ["The first paragraph.", "The second paragraph."] if copied else [], "words": 500 if copied else 0, "author": "Pat Writer" if copied else None,
    }


ROWS = [story(1, copied=True, photo=True), story(2, copied=True, photo=True, topic="coach"), story(3, topic="coach"), story(4, copied=True), story(5, copied=True, topic="rankings"),
        *[story(n, topic="recruiting") for n in range(6, 30)], story(30, url="javascript:alert(1)")]
LAYOUT = layout(ROWS, coach="Jon Sumrall")
LAYOUT["front"]["quote"] = {"text": "We will be ready.", "who": "Jon Sumrall", "storyId": ROWS[0]["id"], "publishedAt": "2026-10-26T15:00:00Z"}

PAPER = {
    "season": 2026,
    "today": "2026-10-27",
    "feeds": {"team": {"name": "Florida Athletics", "status": "ok"}},
    "editions": [{"key": "week-8", "label": "Week 8", "saved": True}, {"key": "week-9", "label": "Week 9", "current": True}],
    "folded": [
        {"key": "week-8", "week": 8, "label": "Week 8", "weekOf": "2026-10-19", "opponent": None, "homeAway": None, "final": None, "won": None, "record": "5-2", "lead": "A Long Wait, A Big Moment For Jones", "bye": True},
        {"key": "week-7", "week": 7, "label": "Week 7", "weekOf": "2026-10-12", "opponent": "Texas", "homeAway": "away", "final": "Florida 27, Texas 24", "won": True, "record": "5-2", "lead": "Florida 27, Texas 24", "bye": False},
        "junk", {"key": "../x"},
    ],
    "edition": {"key": "week-9", "season": 2026, "label": "Week 9", "week": 9, "headlines": ROWS, "matchups": MATCHUPS, "offThisWeek": [], "layout": LAYOUT, "current": True},
}
KEPT = {"season": 2026, "today": "2026-10-27", "edition": {"key": "week-8", "season": 2026, "label": "Week 8", "week": 8, "headlines": ROWS[:6], "matchups": MATCHUPS[:2], "offThisWeek": [{"school": "Florida"}], "layout": layout(ROWS[:6]), "current": False, "frozen": True}}
STORY = {
    "id": ROWS[1]["id"], "title": "Gators story number 2", "source": "Florida Athletics", "author": "Scott Carter", "publishedAt": "2026-10-26T21:30:00Z", "url": "https://floridagators.example.invalid/news/x",
    "host": "floridagators.example.invalid", "paragraphs": ["GAINESVILLE, Fla. — The first paragraph.", "The second.", "The third."], "photo": f"/media/paper/{ROWS[1]['id']}.jpg", "cutline": "A caption.", "credit": "A Photographer",
    "words": 900, "readMinutes": 4, "copiedAt": "2026-10-26T21:40:00Z",
    "paper": {"key": "week-9", "label": "Week 9", "position": 2, "count": 30, "section": "The coach and the team", "prev": {"id": ROWS[0]["id"], "title": "Gators story number 1", "copied": True}, "next": {"id": ROWS[2]["id"], "title": "Gators story number 3", "copied": False, "url": "https://site.example.invalid/3", "source": "On3"}, "related": [{"id": ROWS[2]["id"], "title": "Gators story number 3", "source": "On3", "copied": False, "url": "https://site.example.invalid/3"}, {"id": ROWS[3]["id"], "title": "Gators story number 4", "source": "Florida Athletics", "copied": True}]},
}

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");

async function mounted(paper, data, opts = {}) {
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  route("/api/newspaper", (url) => envelope(clone(String(url).includes("edition=week-8") ? FIX.kept : data)));
  const main = document.createElement("main");
  document.body.append(main);
  const view = paper.createNewspaperView(opts);
  view.mount(main);
  await settle();
  return { main, view };
}

let FIX = null;

scenarios.paper = async () => {
  installWindow();
  FIX = JSON.parse(readFileSync(process.argv[4], "utf8"));
  const { setIdentity } = await import(moduleUrl("identity.js"));
  setIdentity({ school: "Florida", mascot: "Gators", label: "FLA", name: "Gators" });
  const paper = await import(moduleUrl("views/newspaper.js"));
  // the masthead's name: steady within a week, a different one some other week, from the team's own names
  assert.equal(paper.mastheadName(2026, 6), paper.mastheadName(2026, 6));
  const names = new Set([1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((w) => paper.mastheadName(2026, w)));
  assert.ok(names.size >= 3 && [...names].every((n) => n.includes("Gators") || n.includes("Florida")));
  assert.equal(paper.agateName("Appalachian State"), "Appalachian St.");
  assert.equal(paper.agateName(null), "–");
  const g = (id, a, h, extra = {}) => ({ gameId: id, away: { rank: a }, home: { rank: h }, ...extra });
  assert.equal(paper.gameOfWeek([g(1, 1, null), g(2, 2, 20), g(3, 9, 13), g(5, null, 12, { isUs: true })]).gameId, 2);
  assert.equal(paper.gameOfWeek(null), null);

  const { main, view } = await mounted(paper, FIX.paper);
  const t = text(main);
  assert.ok(!RAW.test(t), t.slice(0, 400));
  assert.equal(text(main.querySelector(".np-mast__name")), paper.mastheadName(2026, 9));
  assert.ok(text(main.querySelector(".np-mast__line")).includes(`${FIX.paper.edition.layout.count} stories so far`));
  // the week chips: this week, then each earlier week by its number
  const chips = main.querySelectorAll(".np-weeks .np-chip").map(text);
  assert.deepEqual(chips, ["Week 9", "8", "7"]);
  // the lead beside the rail: a copied story with its photo, its text in two legs, the way to the whole story
  const lead = main.querySelector(".np-lead");
  assert.equal(text(lead.querySelector(".np-head--lead")), "Gators story number 1");
  assert.equal(lead.querySelector(".np-head--lead a").getAttribute("href"), `#story=${FIX.rows[0].id}`);
  assert.ok(lead.querySelector(".np-pic--lead img").getAttribute("src").startsWith("/media/paper/"));
  assert.equal(lead.querySelectorAll(".np-legs p").length, 2);
  assert.ok(text(lead.querySelector(".np-byline")).includes("By Pat Writer"));
  assert.ok(text(lead).includes("The whole story ›"));
  const rail = main.querySelector(".np-rail");
  assert.ok(rail.querySelectorAll(".np-inside").length >= 2, "Inside today: page 2's stories and the rest");
  assert.ok(text(rail).includes("By the numbers") && text(rail).includes("Florida's record, No. 17"));
  assert.ok(text(rail.querySelector(".np-quote")).includes("We will be ready."));
  // three stories of two columns: the middle leads with its head, a headline-only story has an Also brief
  const cells = main.querySelectorAll(".np-row")[1].querySelectorAll(".np-story");
  assert.equal(cells.length, 3);
  assert.ok(cells[1].childNodes[0].className.includes("np-kicker"), "head first in the middle");
  assert.ok(cells.some((c) => c.querySelector(".np-also")), "an Also brief under the headline-only story");
  assert.ok(cells.some((c) => text(c).includes("Read it at On3 ›")));
  // the game of the week, the logos facing; page 2; page 3 and on; the Top 25 at the back
  assert.ok(text(main.querySelector(".np-game")).includes("Wildcats at Red Raiders"));
  const folios = main.querySelectorAll(".np-folio").map((f) => text(f.querySelector(".np-folio__page")));
  assert.equal(folios[0], "Page 2");
  assert.ok(folios.includes("Page 3"));
  assert.ok(main.querySelectorAll(".np-column .np-standing").length >= 2, "page 3's sections");
  assert.equal(main.querySelectorAll(".np-agate").length, 0, "the Top 25's Saturday left the paper for the Top 25 page (wave 3, 2026-11-01)");
  // nothing repeats the tabs or the menu (his marks), and no script address anywhere
  const hrefs = main.querySelectorAll("a").map((a) => a.getAttribute("href") || "");
  assert.ok(!hrefs.some((h) => h === "#live" || h.startsWith("#program") || h === "#top25" || h.startsWith("javascript")), hrefs.join(" "));
  // the earlier weeks, folded: a tap opens Week 8 in place (its finals, our bye), and it stays open through a refresh
  const folds = main.querySelectorAll(".np-fold");
  assert.equal(folds.length, 2);
  assert.ok(text(folds[0]).includes("A Long Wait, A Big Moment For Jones") && text(folds[0]).includes("Bye week") && text(folds[0]).includes("5-2"));
  folds[0].click();
  await settle();
  assert.equal(folds[0].getAttribute("aria-expanded"), "true");
  const body = main.querySelector("#np-weekbody-week-8");
  assert.ok(body && !text(body).includes("the week's finals"), "the kept week opens in place; its Top 25 finals agate left the paper for the Top 25 page (wave 3, 2026-11-01)");
  await view.refresh();
  await settle();
  assert.equal(main.querySelector(".np-fold").getAttribute("aria-expanded"), "true", "an open week stays open through the minute's refresh");
  view.unmount();

  // our final with the recap: its headline is the lead's banner, the player of the game in the deck, hidden in spoiler mode
  const done = clone(FIX.paper);
  const ourGame = done.edition.matchups[2];
  Object.assign(ourGame, { status: "final", headline: { text: "Florida stuns No. 3 Georgia, 31-28" } });
  ourGame.away.points = 31;
  ourGame.home.points = 28;
  done.recap = { gameId: 3, opponent: "Georgia", final: { usScore: 31, themScore: 28 }, record: { wins: 6, losses: 2, ties: 0 }, playerOfGame: { name: "Tramell Jones Jr.", isUs: true }, keyStats: [{ label: "Turnovers", format: "0f", us: 0, them: 2 }] };
  const fin = await mounted(paper, done);
  const banner = fin.main.querySelector(".np-head--lead");
  assert.equal(text(banner), "Florida stuns No. 3 Georgia, 31-28");
  assert.ok(banner.className.includes("paper-head--final"));
  assert.ok(text(fin.main.querySelector(".np-kicker")).includes("Game week · Final"));
  assert.ok(text(fin.main.querySelector(".np-lead .np-byline")).includes("Tramell Jones Jr. is the player of the game"));
  assert.ok(!RAW.test(text(fin.main)));
  fin.view.unmount();

  // an older answer with no layout: the headlines still read, as briefs
  const older = clone(FIX.paper);
  delete older.edition.layout;
  delete older.folded;
  const old = await mounted(paper, older);
  assert.ok(text(old.main).includes("Gators story number 7") && !RAW.test(text(old.main)));
  old.view.unmount();

  // laid out by Claude Code (wave 4): said on the masthead, its numbers in the rail, a drawing where a story had no picture
  const edited = clone(FIX.paper);
  edited.edition.layout.by = "Claude Code";
  edited.edition.layout.front.numbers = [{ big: "100", words: "seasons of the annual game", storyId: FIX.rows[0].id }];
  edited.edition.layout.front.row[1].picture = { kind: "drawn", src: `/media/paper-art/${FIX.rows[2].id}.svg`, cutline: "A drawing of the stadium.", credit: "Illustration: Claude Code" };
  const ed = await mounted(paper, edited);
  assert.ok(text(ed.main.querySelector(".np-mast__line")).includes("laid out by Claude Code"));
  assert.ok(text(ed.main.querySelector(".np-rail")).includes("seasons of the annual game"));
  const drawn = ed.main.querySelector(".np-pic--drawn img");
  assert.ok(drawn && drawn.getAttribute("src").startsWith("/media/paper-art/"));
  assert.ok(text(ed.main).includes("A drawing of the stadium. Illustration: Claude Code") && !text(ed.main).includes("Photo: Illustration"));
  ed.view.unmount();

  // a week with no stories yet: said, not blank
  const empty = clone(FIX.paper);
  empty.edition.layout = { front: {}, page2: null, more: [], order: [], count: 0 };
  const none = await mounted(paper, empty);
  assert.ok(text(none.main).includes("No stories from the team's feeds yet this week"));
  none.view.unmount();
};

scenarios.reader = async () => {
  installWindow();
  FIX = JSON.parse(readFileSync(process.argv[4], "utf8"));
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  const reader = await import(moduleUrl("views/reader.js"));
  clearEnvelopeCache();
  const sid = FIX.story.id;
  route(`/api/paper/story/${sid}`, () => envelope(clone(FIX.story)));
  const main = document.createElement("main");
  document.body.append(main);
  const view = reader.createReaderView({ id: sid });
  view.mount(main);
  await settle();
  const t = text(main);
  assert.ok(!RAW.test(t), t.slice(0, 300));
  assert.equal(text(main.querySelector("h1")), "Gators story number 2");
  assert.ok(text(main.querySelector(".np-reader__byline")).includes("By Scott Carter") && t.includes("4 min read"));
  assert.equal(main.querySelectorAll(".np-reader__body p").length, 3);
  assert.ok(main.querySelector(".np-reader__photo img").getAttribute("src").startsWith("/media/paper/"));
  assert.ok(text(main.querySelector(".np-reader__photo figcaption")).includes("Photo: A Photographer"));
  assert.ok(text(main.querySelector(".np-reader__where")).includes("Story 2 of 30"));
  const steps = main.querySelectorAll(".np-reader__bar a.btn").map((a) => a.getAttribute("href"));
  assert.ok(steps.includes(`#story=${FIX.rows[0].id}`) && steps.includes("https://site.example.invalid/3"), steps.join(" "));
  assert.ok(t.includes("Read it at floridagators.example.invalid ↗"));
  assert.ok(text(main.querySelector(".np-card--next")).includes("Next in the paper") && text(main.querySelector(".np-card--next")).includes("Gators story number 3"));
  assert.equal(main.querySelectorAll(".np-related .np-brief").length, 2);
  view.unmount();

  // a story that stayed headline only, and a bad id
  clearEnvelopeCache();
  route("/api/paper/story/0000000000000001", () => ({ status: 404, body: { data: null, errors: [{ message: "the site refuses automated readers (HTTP 402)" }], meta: {} } }));
  const refused = reader.createReaderView({ id: "0000000000000001" });
  const main2 = document.createElement("main");
  document.body.append(main2);
  refused.mount(main2);
  await settle();
  assert.ok(text(main2).includes("402") && main2.querySelector('a[href="#newspaper"]'));
  refused.unmount();
  const bad = reader.createReaderView({ id: "../etc" });
  const main3 = document.createElement("main");
  bad.mount(main3);
  assert.ok(text(main3).includes("That story is not on this server."));
};
"""


@pytest.fixture(scope="module")
def fixture_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("paper") / "paper.json"
    path.write_text(json.dumps({"paper": PAPER, "kept": KEPT, "story": STORY, "rows": ROWS}), encoding="utf-8")
    return path


@needs_node
@pytest.mark.parametrize("scenario", ["paper", "reader"])
def test_newspaper_in_a_fake_browser(tmp_path: Path, fixture_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario, str(fixture_path))
