"""The menu and page order (owner 2026-10-10), in the fake browser and as static checks: the Injury Report page (one band per
game, newest first, the older ones folded, a missing report leading to the notes), the Setup page, the Pre-Game Program's
sixteen bands in his order with players to watch never repeating a leader, the Big screen button on In Game, First time
setup in Settings, and the page check holding every page to the new names."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.fakedom import needs_node, run_scenario

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "static" / "js"

INJURIES = {
    "season": 2026,
    "team": {"school": "Swampwater Tech"},
    "isUs": True,
    "counts": {"games": 5, "reports": 2},
    "games": [
        {"gameId": 5, "week": 5, "homeAway": "home", "completed": False, "next": True, "date": "2026-10-03T19:00:00Z", "opponent": {"school": "Lake Effect"}, "notes": True, "reported": True, "source": "Conference report", "updatedAt": "2026-10-01", "rows": [{"name": "Zed Out", "position": "WR", "status": "Out", "note": "Knee"}, {"name": "Al Maybe", "position": "LB", "status": "Questionable", "note": None}], "unassigned": [{"name": "Who Knows", "position": "OL", "status": "Probable", "note": "hand"}]},
        {"gameId": 4, "week": 4, "homeAway": "away", "completed": True, "opponent": {"school": "Diner Tech"}, "notes": False, "reported": False, "rows": [], "unassigned": []},
        {"gameId": 3, "week": 3, "homeAway": "home", "completed": True, "opponent": {"school": "Silver Dollar"}, "notes": True, "error": "3.json is not valid JSON", "reported": False, "rows": [], "unassigned": []},
        {"gameId": 2, "week": 2, "homeAway": "neutral", "label": "Kickoff Classic", "completed": True, "opponent": {"school": "Gravel State"}, "notes": True, "reported": True, "rows": [], "unassigned": []},
        {"gameId": 1, "week": 1, "homeAway": "home", "completed": True, "opponent": None, "notes": True, "reported": True, "rows": [None, "junk", {"name": "Old Hurt", "status": "Doubtful"}], "unassigned": None},
    ],
}

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object Object\]/;
const text = (node) => (node ? node.textContent : "");
const clean = (label, node) => {
  const t = text(node);
  assert.ok(!RAW.test(t), `${label} printed ${JSON.stringify(t.match(/.{0,60}(undefined|null|NaN|Infinity|\[object Object\]).{0,60}/)?.[0])}`);
  return t;
};

scenarios.injuries = async () => {
  installWindow();
  const { clearEnvelopeCache } = await import(moduleUrl("views/common.js"));
  clearEnvelopeCache();
  route("/api/injuries", () => envelope(INJURIES));
  const { createInjuriesView, gameTitle, countsLine } = await import(moduleUrl("views/injuries.js"));
  const main = document.createElement("main");
  document.body.append(main);
  const view = createInjuriesView({});
  view.mount(main);
  await settle();
  const t = clean("injuries", main);
  const bands = [...main.querySelectorAll("section.band")];
  assert.deepEqual(bands.map((b) => b.getAttribute("id")), ["injuries-5", "injuries-3", "injuries-2", "injuries-1"], "newest first; a played game with no report is in the line at the foot (the layout pass, 2026-10-22)");
  assert.equal(main.querySelector(".chips-row"), null, "no strip of week chips over the page");
  assert.ok(text(bands[0].querySelector(".band__head")).includes("Next: Week 5 vs Lake Effect"));
  assert.ok(text(bands[0]).includes("1 out, 1 questionable"));
  assert.ok(text(bands[0]).includes("Zed Out") && text(bands[0]).includes("Team not named in the report") && text(bands[0]).includes("Who Knows"));
  assert.deepEqual(bands.map((b) => b.getAttribute("data-collapsed")), ["false", "false", "false", "true"], "the next game and the last two shown open, the rest folded");
  const quiet = main.querySelector(".injuries-quiet");
  assert.ok(quiet && text(quiet).startsWith("No report for one played game") && quiet.querySelector('a[href="#program=4"]'), "a played game with no report: one line, its link to the program");
  assert.ok(text(bands[1]).includes("could not be read"), "an unreadable notes file keeps its band and says so");
  assert.ok(text(bands[2].querySelector(".band__head")).includes("Kickoff Classic vs Gravel State"));
  assert.ok(text(bands[2]).includes("Nobody from Swampwater Tech on the report"));
  assert.ok(text(bands[3]).includes("Old Hurt"), "a bad row is skipped, a good one kept");
  assert.ok(t.includes("Newest week first"));
  view.unmount();
  assert.equal(gameTitle({ week: 7, homeAway: "away", opponent: { school: "Lake Effect" } }), "Week 7 at Lake Effect");
  assert.equal(gameTitle(null), "Game vs the opponent");
  assert.equal(countsLine([{ status: "Out" }, { status: "out" }, { status: "Probable" }, { status: "Not reported" }]), "2 out, 1 probable, 1 other");
  assert.equal(countsLine([]), "nobody listed");
  const { quietLine } = await import(moduleUrl("views/injuries.js"));
  assert.equal(quietLine([]), null);
  assert.equal(quietLine(null), null);
  const two = quietLine([{ gameId: 7, week: 7, homeAway: "away", opponent: { school: "Lake Effect" } }, { gameId: "bad id", week: 6, opponent: null }]);
  assert.ok(text(two).includes("2 played games") && two.querySelectorAll("a").length === 1 && text(two).includes("Week 6 vs the opponent"), text(two));
  // a broken answer never breaks the page
  clearEnvelopeCache();
  route("/api/injuries", () => envelope({ games: "x", team: null }));
  const again = createInjuriesView({});
  again.mount(main);
  await settle();
  assert.ok(clean("empty injuries", main).includes("No games on the schedule yet."));
  again.unmount();
};

scenarios.setup = async () => {
  installWindow();
  const { createSetupPageView, SETUP_LINKS } = await import(moduleUrl("views/setup-page.js"));
  const main = document.createElement("main");
  document.body.append(main);
  createSetupPageView({}).mount(main);
  const links = [...main.querySelectorAll("a.setup-link")];
  assert.deepEqual(links.map((a) => a.getAttribute("href")), ["/demo", "#archive", "#review", "#radio"]);
  assert.deepEqual(SETUP_LINKS.map((l) => l.label), ["Demo", "Archive", "Season in review", "Radio"]);
  assert.ok(clean("setup", main).includes("First time setup, above"), "the Setup links sit under First time setup in the Profile's Setup flyout (board 7, 2026-10-22)");
  assert.ok(main.querySelector("#settings-setup"), "the band the Profile shows");
};

scenarios.leaders = async () => {
  // the mock (owner 2026-10-20): a leader carries his value for the row on the pole; the headlines fit their row
  const { fitHeadlines, programLeader } = await import(moduleUrl("views/program.js"));
  const lead = programLeader({ player: "Al One", playerId: "41", position: "QB", value: 1204 }, { format: "0f", stat: "YDS" });
  assert.deepEqual([lead.name, lead.playerId, lead.value, lead.line.hero], ["Al One", "41", 1204, "1,204 yds"]);
  assert.equal(programLeader({ player: "Bo", value: "x" }).value, null, "a damaged value is null, never a string");
  assert.equal(programLeader(null), null);
  fitHeadlines(null);
  fitHeadlines(document.createElement("div"));
  const body = document.createElement("div");
  const list = document.createElement("ul");
  list.className = "news";
  for (let i = 0; i < 3; i += 1) {
    const li = document.createElement("li");
    li.hidden = true;
    list.append(li);
  }
  body.append(list);
  fitHeadlines(body);
  assert.ok([...list.children].every((li) => !li.hidden), "a body that sizes itself hides nothing");
};
"""


@needs_node
@pytest.mark.parametrize("name", ["injuries", "setup", "leaders"])
def test_menu_pages_in_a_fake_browser(tmp_path: Path, name: str) -> None:
    run_scenario(tmp_path, SCENARIOS.replace("envelope(INJURIES)", f"envelope({json.dumps(INJURIES)})"), name)


def test_the_programs_bands_in_the_owners_order() -> None:
    src = (JS / "views" / "program.js").read_text(encoding="utf-8")
    body = src.split("function sections(data", 1)[1].split("\n}\n", 1)[0]
    listed = re.findall(r"(\w+Band)\(", body.split("const listed = [", 1)[1].split("];", 1)[0])
    # the mock (owner 2026-10-20): the notes beside the headlines, the recruits beside the availability report, common
    # opponents over the radio beside last season, the two schools and the series last
    assert listed == ["notesBand", "headlinesBand", "tapeBand", "visitorsBand", "availabilityBand", "leadersBand", "recruitingBand", "lineupsBand", "advancedBand", "tendenciesBand", "ppaBand", "commonBand", "radioBand", "lastSeasonBand", "twoSchoolsBand", "seriesBand"]
    assert "const unplaced = [matchup(data)]" in body, "the matchup card was not on his canvas: it follows the order"
    assert "watchBand" not in src and "pickerBand" not in src, "players to watch and prior weeks' programs are gone"


def test_in_game_settings_and_page_check() -> None:
    live = (JS / "views" / "live.js").read_text(encoding="utf-8")
    assert "stageTools({ delayLabel: shortDelayLabel()" in live, "the five tools sit in the panel row (wave F5)"
    stage = (JS / "ui" / "stage.js").read_text(encoding="utf-8")
    assert 'el("a", { class: "remote__btn remote__btn--tool", href: boardHref }, "Big screen")' in stage
    settings = (JS / "views" / "settings.js").read_text(encoding="utf-8")
    assert 'row("First time setup", el("a", { class: "btn", href: "/setup" }, "Open")' in settings
    from tools import page_check

    assert "injuries" in page_check.ROUTES and "setup" in page_check.ROUTES
    assert page_check.OLD_NAMES.search("Open the Live sheet") and page_check.OLD_NAMES.search("the Game program")
    assert not page_check.OLD_NAMES.search("the In Game sheet and the Pre-Game Program")
    # tables wave 2 (2026-10-10): any object printed as text fails the check, the board's "[object HTMLElement]" too
    assert page_check.BAD.search("[object HTMLElement],[object HTMLElement]") and page_check.BAD.search("[object Object]")
    assert not page_check.BAD.search("an objective look at the Nullarbor")
