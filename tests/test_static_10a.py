"""Phase 10a front end (Saturday readiness). Every JavaScript module parses under Node, the stale
"Biscuit Belt and Top 25" wording is gone, and the Live sheet runs in a small fake browser under Node
against a state derived from the recorded live document (tests/fixtures/cfbd/live_plays.json):
the wake lock, the stream watchdog and fallback poll, frames that cannot be parsed or drawn, the
feed-health pill (contracts C1, C2), CFBD's success rate (C3), side sheets that follow the game,
the persistent ticker, the delay slider, the opening rule, and the archive's null guards.

No network: the harness scripts fetch, EventSource, the wake lock, and the clock itself."""

from __future__ import annotations

import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.cfbd.models import GamePlayerStats, GameTeamStats, LiveGame, parse_one, parse_records
from app.live.events import box_events, events_from_live
from app.live.state import derive_state
from tests.conftest import fixture_payload
from tests.fakedom import FAKEDOM_JS, RUNNER_JS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_JS = PROJECT_ROOT / "static" / "js"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")

# The files this phase's front-end work owns; the stale wording must not come back in any of them.
OWNED = [
    "views/live.js",
    "app.js",
    "ui/remote.js",
    "ui/delay-slider.js",
    "ui/ticker.js",
    "ui/wp-chart.js",
    "ui/stat-table.js",
    "ui/play-log.js",
    "ui/strip.js",
    "views/archive.js",
]
SCENARIOS = ["pure", "components", "live", "ticker", "pregame", "oldserver", "silentstart", "archive", "gameinfo", "held", "finalnote", "board"]


@needs_node
def test_every_javascript_module_passes_node_check(tmp_path: Path):
    modules = sorted(STATIC_JS.rglob("*.js"))
    assert len(modules) >= 28

    def check(module):
        # .mjs so Node reads it as the ES module the browser loads; eight at a time (faster tests, 2026-10-13)
        target = tmp_path / (module.relative_to(STATIC_JS).as_posix().replace("/", "__")[:-3] + ".mjs")
        target.write_text(module.read_text(encoding="utf-8"), encoding="utf-8")
        result = subprocess.run([NODE, "--check", str(target)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        return module, result

    with ThreadPoolExecutor(max_workers=8) as pool:
        for module, result in pool.map(check, modules):
            assert result.returncode == 0, f"{module.relative_to(PROJECT_ROOT)}: {result.stderr[:400]}"


def test_stale_labels_are_gone():
    live = (STATIC_JS / "views" / "live.js").read_text(encoding="utf-8")
    for stale in ("Biscuit Belt and Top 25", "No Biscuit Belt or Top 25 games", "Biscuit Belt, Top 25", "opens by itself 30 minutes before kickoff"):
        assert stale not in live, stale
    for name in OWNED:
        source = (STATIC_JS / name).read_text(encoding="utf-8")
        assert "Biscuit Belt and Top 25" not in source and "Biscuit Belt, Top 25" not in source and "Biscuit Belt or Top 25" not in source, name
    # the ticker carries every FBS game; Phase 17 #25: the sheet no longer promises to open itself
    # wave F5 (owner 2026-10-20): the ticker has no "FBS scores" label; only the My teams one names itself
    assert "every FBS game" in live and "No FBS games" in live and '"My teams"' in live
    assert "opens by itself" not in live and "1 hour before kickoff" not in live


def test_success_rate_row_is_not_repeated_in_the_feed_table():
    # final pass: the feed rows are one shared list (ui/team-stats.js FEED_ROWS) drawn by In Game and the Archive; wave 2
    # (2026-10-10): one builder on the two-team kit, feedEfficiencyTable, whose rows are FEED_ROWS
    live = (STATIC_JS / "views" / "live.js").read_text(encoding="utf-8")
    start = live.index("function feedStatsTable")
    body = live[start : live.index("function wpBlock")]
    assert "feedEfficiencyTable(" in body and '"Success rate"' not in body
    source = (STATIC_JS / "ui" / "team-stats.js").read_text(encoding="utf-8")
    builder = source[source.index("export function feedStatRows") : source.index("export function feedEfficiencyTable")]
    assert "FEED_ROWS.map(" in builder and '"Success rate"' not in builder
    rows = source[source.index("export const FEED_ROWS") : source.index("];", source.index("export const FEED_ROWS"))]
    assert '"Success rate"' not in rows
    assert '"Standard downs"' in rows and '"Passing downs"' in rows and '"PPA per play"' in rows and '"Scoring chances"' in rows


def live_state() -> dict:
    """The recorded live document (Silver Dollar at home, Swampwater Tech away) plus the box polls, through the engine's own state builder."""
    game = parse_one(LiveGame, fixture_payload("live_plays"), context="test")
    assert game is not None
    received = datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc)
    events = events_from_live(game, received)
    teams = parse_records(GameTeamStats, fixture_payload("games_teams"), context="test").records
    players = parse_records(GamePlayerStats, fixture_payload("games_players"), context="test").records
    events += box_events(game.id, teams, players, received)
    for seq, event in enumerate(events, start=1):
        event.seq = seq
    state = derive_state(events, game_id=game.id, home="Silver Dollar", away="Swampwater Tech", mode="live")
    assert state["plays"] and state["box"].get("Swampwater Tech") and state["box"].get("Silver Dollar") and state["playerStats"]
    return state


@pytest.fixture(scope="module")
def harness(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    folder = tmp_path_factory.mktemp("live-harness")
    script = folder / "harness.mjs"
    script.write_text(HARNESS, encoding="utf-8")
    fixture = folder / "state.json"
    fixture.write_text(json.dumps(live_state()), encoding="utf-8")
    return script, fixture


@needs_node
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_live_sheet_in_a_fake_browser(harness: tuple[Path, Path], scenario: str):
    script, fixture = harness
    result = subprocess.run([NODE, str(script), str(STATIC_JS), scenario, str(fixture)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert result.returncode == 0, result.stdout[-6000:] + result.stderr[-2000:]
    assert f"ok {scenario}" in result.stdout


# --- the harness ---------------------------------------------------------------------------------

HARNESS = FAKEDOM_JS + r"""// --- shared data ----------------------------------------------------------------------------------

const KICKOFF = "2026-09-26T19:30:00+00:00";
const PROGRAM = {
  game: { id: 526001015, kickoff: KICKOFF, homeIsUs: false, venue: "Vaught-Hemingway Stadium", tv: "ESPN" },
  us: { school: "Swampwater Tech", abbreviation: "SWT" },
  them: { school: "Diner Tech", abbreviation: "MISS" },
  line: {},
  pregame: { homeWinProbability: 0.6, usWinProbability: 0.4 },
  notes: { present: false, availability: [] },
  weather: { available: false, error: "No forecast yet" },
  edges: [],
};
const feed = (state, extra = {}) => ({ state, lastSuccessAt: null, lastNewEventAt: null, consecutiveFailures: 0, lastError: null, staleSeconds: null, checkedAt: new Date(now).toISOString(), ...extra });
const WINDOW_OPEN = { gameId: 526001015, kickoff: KICKOFF, opensAt: "2026-09-26T19:00:00+00:00", closesAt: "2026-09-27T00:30:00+00:00", open: true, liveView: true, liveViewAt: "2026-09-26T18:30:00+00:00" };
const game = (away, home, awayPts, homePts, status = "live") => ({ away: { school: away, abbr: away.slice(0, 4).toUpperCase(), points: awayPts, rank: null }, home: { school: home, abbr: home.slice(0, 4).toUpperCase(), points: homePts, rank: 5 }, status, detail: status === "final" ? "Final" : "Q2 8:12", isUs: false });
const TICKER = { source: "scoreboard", games: [game("Alabama", "Georgia", 7, 10), game("Texas", "Oklahoma", 21, 14, "final")] };

/** The fixture state as an in-progress frame, with CFBD's team success rate (contract C3) and a judged last play. */
function liveFrame(overrides = {}) {
  const s = clone(FIXTURE);
  s.status = "in_progress";
  for (const team of ["Swampwater Tech", "Silver Dollar"]) {
    s.box[team].successCounts = null;
    s.box[team].successRate = team === "Swampwater Tech" ? 0.375 : 0.388;
  }
  const scrimmage = s.plays.find((p) => p.offense === "Swampwater Tech" && /Rush|Pass/.test(p.playType || "")) || s.plays[0];
  s.lastPlay = { ...scrimmage, success: true };
  return Object.assign(s, overrides);
}

function withNewPlay(frame, text) {
  const s = clone(frame);
  const newest = { ...s.plays[0], id: `harness-${text}`, offense: "Swampwater Tech", defense: "Silver Dollar", text, flags: [], success: true };
  s.plays = [newest, ...s.plays];
  s.counts = { ...s.counts, plays: s.counts.plays + 1 };
  return s;
}

async function mountLive({ status, ticker = TICKER, program = PROGRAM } = {}) {
  route("/api/program/next", () => {
    const answer = typeof program === "function" ? program() : program;
    return answer instanceof Error ? answer : envelope(answer);
  });
  route("/api/live/status", () => envelope(typeof status === "function" ? status() : status));
  route("/api/ticker", () => envelope(typeof ticker === "function" ? ticker() : ticker));
  route("/api/settings", () => envelope({ prefs: {} }));
  const { createLiveView } = await import(moduleUrl("views/live.js"));
  const statuses = [];
  const view = createLiveView({ onStatus: (s) => statuses.push(s) });
  const container = document.createElement("main");
  document.body.append(container);
  await view.mount(container);
  await settle();
  const shell = () => statuses[statuses.length - 1]?.label;
  const stripPill = () => container.querySelector(".strip .pill")?.textContent; // Phase 17 #29: always none
  return { view, container, statuses, shell, stripPill };
}

const text = (node) => (node ? node.textContent : "");
// a sized table's label or head holds its long, middle and short words (ui/sizes.js); the long one is the name
const longWords = (node) => text(node ? node.querySelector(".tt__t--long, .sz-t--long") || node : null);
const layer = () => document.body.querySelector(".sheet-layer");
const sheetBody = () => document.body.querySelector(".sheet-layer .side-sheet__body");
const remoteButton = (container, id) => container.querySelector(`.remote__btn[data-id="${id}"]`);
// wave F5: the five tools are buttons at the end of the panel row, told apart by their words
const toolButton = (container, label) => container.querySelectorAll(".remote .remote__btn--tool").find((b) => text(b) === label);
const sheetTitle = () => text(document.body.querySelector(".sheet-layer .side-sheet__title"));
const RAW = /\b(undefined|NaN|null)\b/;
/** The named parts under a root in document order (the first class of each; a found part is not searched inside). */
function partsOf(root, names) {
  const found = [];
  const walk = (node) => {
    for (const child of node.childNodes || []) {
      const first = String(child.className || "").split(" ")[0];
      if (names.includes(first)) found.push(first);
      else walk(child);
    }
  };
  walk(root);
  return found;
}

// --- scenarios ------------------------------------------------------------------------------------

const scenarios = {};

// Public release Phase 7b: the TV crew and both staffs, the shot chart, the hint when missing. Wave F5 (owner 2026-10-20):
// the game line left the page for the Notes sheet (your notes, the program notes, the schemes, then the line), and the
// chart shows the passes over the line of scrimmage and the runs under it at once, with no switch.
scenarios.gameinfo = async () => {
  const withCrew = clone(PROGRAM);
  withCrew.weather = { available: true, tempF: 71.6, windMph: 8, dome: false };
  withCrew.notes = {
    present: true, availability: [],
    broadcast: { network: "ABC", playByPlay: "Pat Caller", analyst: "Sam Color", sideline: ["Lee Field", null, 7], source: "network release" },
    coaches: { us: { headCoach: "Head Us", offensiveCoordinator: "Oc Us", defensiveCoordinator: null }, them: { headCoach: "Head Them" } },
    schemes: { offense: "Spread", defense: "4-2-5", opponent: { offense: "Pro style", defense: null } },
  };
  route("/api/gamenotes/", () => envelope({ notes: [] }));
  const status = { mode: "live", window: WINDOW_OPEN, feed: feed("ok") };
  const { view, container } = await mountLive({ status, program: withCrew });
  latest().emit("hello", { delaySeconds: 30, mode: "live", gameId: 526000600, feed: feed("ok") });
  const frame = liveFrame({ possession: "Swampwater Tech" });
  latest().emit("state", frame);
  await settle();
  assert.equal(container.querySelector(".game-info"), null, "no game line on the page: In Game is one screen");
  assert.ok(container.querySelector(".live-dock .live-dock__line .strip"), "the layout pass (owner 2026-10-22): the score line sits in the dock at the bottom");
  assert.equal(container.querySelector(".stage-essentials"), null, "no essentials: the line carries the last play and the percentage on every screen");
  toolButton(container, "Notes").click();
  await settle();
  assert.equal(sheetTitle(), "Notes");
  const notes = sheetBody().querySelector(".notes-sheet");
  assert.ok(notes, "the Notes sheet");
  const order = notes.childNodes.map((n) => n.className || "");
  assert.ok(order[0].includes("gamenotes"), `your own notes first: ${order.join(" | ")}`);
  assert.ok(text(notes).includes("No notes from the host for this game yet."), text(notes).slice(0, 200));
  const schemes = notes.querySelectorAll(".notes-sheet__scheme").map(text);
  assert.equal(schemes.length, 2, "a scheme line for each side");
  assert.equal(schemes[0], "SWT Spread offense, 4-2-5 defense");
  assert.ok(schemes[1].endsWith(" Pro style offense") && !schemes[1].includes("defense"), schemes[1]);
  const info = text(notes.querySelector(".game-info"));
  assert.ok(info.includes("Vaught-Hemingway Stadium") && info.includes("72°F, wind 8 mph"), info);
  assert.ok(info.includes("ABC: Pat Caller, Sam Color, Lee Field (sideline)"), info);
  assert.ok(info.includes("SWT HC Head Us · OC Oc Us") && info.includes("HC Head Them") && !info.includes("DC"), info);
  assert.ok(!info.includes("Add "), "nothing missing, no hint");
  assert.equal(notes.childNodes[notes.childNodes.length - 1], notes.querySelector(".game-info"), "the game line last");
  assert.ok(!RAW.test(text(notes)), text(notes));
  document.body.querySelector(".side-sheet__head button").click();
  assert.equal(layer(), null);
  const chart = container.querySelector("#live-chart");
  assert.equal(chart.querySelector(".band__head"), null, "no title bar (owner 2026-10-22)");
  assert.equal(text(chart.querySelector(".shot-endzone .shot-endzone__team")), "SWT offense", "the end zone names the offense on the field");
  assert.ok(chart.querySelector(".shot-endzone--us"), "in our color");
  assert.match(text(chart.querySelector(".shot-endzone__counts")), /^\d+ passes, \d+ runs(, \d+ sacks?)?$/, "the counts ride in the end zone: no room for a note on one screen");
  const field = chart.querySelector(".shot-field--both");
  assert.ok(field && field.querySelector(".shot-field__los"), "passes over the line of scrimmage, runs under it");
  assert.equal(field.querySelectorAll(".shot-cell").length, 9, "six pass zones and three run lanes");
  assert.equal(field.querySelectorAll(".shot-row--runs").length, 1, "one row of runs");
  assert.equal(field.querySelectorAll(".shot-row--runs .shot-cell").length, 3, "three run lanes");
  assert.equal(chart.querySelector(".shot-chart__seg"), null, "no Passes and Runs switch");
  assert.ok(!text(chart).includes("Success is CFBD"), "the counts only, on one screen");
  assert.ok(!RAW.test(text(chart)), text(chart));
  latest().emit("state", frame);
  assert.ok(container.querySelector("#live-chart .shot-field--both"), "both across frames");
  // the chart follows the offense on the field (owner 2026-10-22), and keeps it through a kickoff or a break
  latest().emit("state", liveFrame({ possession: "Silver Dollar" }));
  await settle();
  assert.equal(text(container.querySelector("#live-chart .shot-endzone__team")), "SIL offense", "their ball, their chart");
  assert.ok(container.querySelector("#live-chart .shot-endzone--them"), "in their color");
  latest().emit("state", liveFrame({ possession: null }));
  await settle();
  assert.equal(text(container.querySelector("#live-chart .shot-endzone__team")), "SIL offense", "no one has the ball: the last offense stays");
  view.unmount();

  // no crew and no staffs in the notes: a quiet hint where to add them; no program notes: where to add those
  document.body.replaceChildren();
  const bare = await mountLive({ status, program: PROGRAM });
  latest().emit("hello", { delaySeconds: 30, mode: "live", gameId: 526000600, feed: feed("ok") });
  const empty = liveFrame();
  empty.shotChart = { "Swampwater Tech": { passes: { "deep-left": { attempts: "x" }, "short-left": null }, runs: "junk", unzoned: null, sacks: NaN } };
  latest().emit("state", empty);
  await settle();
  toolButton(bare.container, "Notes").click();
  await settle();
  const plain = sheetBody().querySelector(".notes-sheet");
  assert.ok(text(plain).includes("No program notes for this game yet."), text(plain).slice(0, 200));
  assert.equal(plain.querySelectorAll(".notes-sheet__scheme").length, 0, "no schemes, no scheme lines");
  const hint = text(plain.querySelector(".game-info"));
  assert.ok(hint.includes("on ESPN") && hint.includes("Add the TV crew and the coaches with the notes prompt on the Pre-Game Program."), hint);
  document.body.querySelector(".side-sheet__head button").click();
  assert.ok(!RAW.test(text(bare.container.querySelector("#live-chart"))), "a damaged chart draws dashes");
  bare.view.unmount();
};

scenarios.pure = async () => {
  const live = await import(moduleUrl("views/live.js"));
  const app = await import(moduleUrl("app.js"));
  assert.equal(live.readFeed(null), null);
  assert.equal(live.readFeed({ state: "sideways" }), null);
  assert.equal(live.readFeed("ok"), null);
  assert.deepEqual(live.readFeed({ state: "stale", staleSeconds: 61, consecutiveFailures: "x", lastError: "  timeout  " }), { state: "stale", staleSeconds: 61, consecutiveFailures: 0, lastError: "timeout", lastSuccessAt: null });
  assert.equal(live.readFeed({ state: "ok", staleSeconds: -4 }).staleSeconds, null);
  assert.equal(live.staleLabel(50), "Stale 50 s, CFBD not answering");
  assert.equal(live.staleLabel(119.4), "Stale 119 s, CFBD not answering");
  assert.equal(live.staleLabel(120), "Stale 2 min, CFBD not answering");
  assert.equal(live.staleLabel(3599), "Stale 59 min, CFBD not answering");
  assert.equal(live.staleLabel(null), "Stale, CFBD not answering");
  assert.equal(live.staleLabel(NaN), "Stale, CFBD not answering");
  const pill = (facts) => live.livePill(facts);
  assert.deepEqual(pill({ delay: 45 }), { kind: "delayed", label: "Delayed 45 s" });
  assert.deepEqual(pill({ delay: 0 }), { kind: "live", label: "Live" });
  assert.deepEqual(pill({ delay: 45, streamDown: true }), { kind: "offline", label: "Offline" });
  assert.deepEqual(pill({ delay: 45, streamDown: true, polled: true }), { kind: "stale", label: "Polling, stream down" });
  assert.deepEqual(pill({ delay: 45, displayError: true, streamDown: true }), { kind: "stale", label: "Display error" });
  assert.deepEqual(pill({ pregame: true }), { kind: "quiet", label: "Pregame" });
  assert.deepEqual(pill({ pregame: true, statusDown: true }), { kind: "offline", label: "Offline" });
  assert.deepEqual(pill({ delay: 45, feed: { state: "stale", staleSeconds: 40 }, feedAge: 15 }), { kind: "stale", label: "Stale 55 s, CFBD not answering" });
  assert.deepEqual(pill({ delay: 45, feed: { state: "stale", staleSeconds: null } }), { kind: "stale", label: "Stale, CFBD not answering" });
  assert.deepEqual(pill({ delay: 45, feed: { state: "no_live_key" } }), { kind: "offline", label: "No live feed on this key" });
  assert.deepEqual(pill({ delay: 45, feed: { state: "waiting" } }), { kind: "quiet", label: "Waiting for CFBD" });
  assert.deepEqual(pill({ delay: 45, feed: { state: "ok" } }), { kind: "delayed", label: "Delayed 45 s" });
  assert.deepEqual(pill({ delay: 45, feed: { state: "idle" } }), { kind: "delayed", label: "Delayed 45 s" });
  assert.deepEqual(pill({ delay: 45, final: true, feed: { state: "stale", staleSeconds: 300 } }), { kind: "live", label: "Final" });
  assert.equal(live.clampDelay(47), 45);
  assert.equal(live.clampDelay(-10), 0);
  assert.equal(live.clampDelay(500), 120);
  assert.equal(live.clampDelay("30"), null);
  // Phase 17 #25: the LIVE marker follows the server's inProgress, never the hour-before view, never a replay
  assert.equal(app.gameIsLive({ mode: "live", window: { open: true, liveView: true, inProgress: true } }), true);
  assert.equal(app.gameIsLive({ mode: "live", window: { open: true, liveView: true, inProgress: false } }), false);
  assert.equal(app.gameIsLive({ mode: "replay", window: { inProgress: true } }), false);
  assert.equal(app.gameIsLive({ window: { inProgress: "yes" } }), false);
  assert.equal(app.gameIsLive({ window: null }), false);
  assert.equal(app.gameIsLive(null), false);
};

scenarios.components = async () => {
  const { statTable } = await import(moduleUrl("ui/stat-table.js"));
  const { playLog } = await import(moduleUrl("ui/play-log.js"));
  const { openSheet, remoteBar } = await import(moduleUrl("ui/remote.js"));
  const { delaySlider } = await import(moduleUrl("ui/delay-slider.js"));
  const { strip } = await import(moduleUrl("ui/strip.js"));
  const { ticker } = await import(moduleUrl("ui/ticker.js"));
  const { successRow } = await import(moduleUrl("ui/wp-chart.js"));

  // statTable: initial sort, onSort, getSort; the old call shape still works.
  const sorts = [];
  const columns = [{ key: "name", label: "Name", kind: "text" }, { key: "yds", label: "Yds" }, { key: "td", label: "TD" }];
  const rows = [{ name: "A", yds: 10, td: 2 }, { name: "B", yds: 30, td: 0 }];
  const table = statTable({ columns, rows, sort: { key: "td", dir: "ascending" }, onSort: (s) => sorts.push(s) });
  assert.deepEqual(table.getSort(), { key: "td", dir: "ascending" });
  assert.equal(text(table.querySelector('th[aria-sort="ascending"]')), "TD");
  assert.equal(text(table.querySelector("tbody tr td")), "B");
  table.querySelectorAll("th button")[1].click();
  assert.deepEqual(sorts, [{ key: "yds", dir: "descending" }]);
  assert.deepEqual(table.getSort(), { key: "yds", dir: "descending" });
  assert.equal(statTable({ columns, rows }).getSort(), null);
  assert.equal(statTable({ columns, rows, sort: { key: "yds", dir: "sideways" } }).getSort().dir, "descending");

  // playLog: initial filter, onFilter, getFilter, junk records skipped.
  const us = { name: "Swampwater Tech", abbr: "SWT" };
  const them = { name: "Silver Dollar", abbr: "GRID" };
  const plays = [{ id: "1", offense: "Swampwater Tech", text: "run" }, null, "junk", { id: "2", offense: "Silver Dollar", text: "pass" }];
  const filters = [];
  const log = playLog({ plays, us, them, filter: "them", onFilter: (id) => filters.push(id) });
  assert.equal(log.getFilter(), "them");
  assert.equal(log.querySelectorAll(".plays li.play").length, 1);
  assert.equal(text(log.querySelector('.seg button[aria-pressed="true"]')), "GRID");
  log.querySelector('.seg button[data-filter="all"]').click();
  assert.deepEqual(filters, ["all"]);
  assert.equal(log.querySelectorAll(".plays li.play").length, 2);
  assert.equal(playLog({ plays, us, them, filter: "bogus" }).getFilter(), "all");
  assert.equal(playLog({ plays: "not a list", us, them }).querySelectorAll(".plays li.play").length, 0);
  const kick = playLog({ plays: [{ id: "k", offense: "Swampwater Tech", down: 0, distance: 0, yardsToGoal: 65, text: "Kickoff" }], us, them });
  assert.ok(!text(kick).includes("0th"), "a kickoff has no down to show");

  // openSheet: update keeps the body's scroll and the tables' scroll; close runs once.
  let closes = 0;
  const handle = openSheet({ title: "Plays", body: () => [statTable({ columns, rows }), el("p", "one")], onClose: () => { closes += 1; } });
  const body = handle.layer.querySelector(".side-sheet__body");
  body.scrollTop = 300;
  body.querySelector(".stat-table-wrap").scrollLeft = 40;
  handle.update(() => [statTable({ columns, rows }), el("p", "two")]);
  assert.equal(body.scrollTop, 300);
  assert.equal(body.querySelector(".stat-table-wrap").scrollLeft, 40);
  assert.ok(text(body).includes("two") && !text(body).includes("one"));
  assert.throws(() => handle.update(() => { throw new Error("bad body"); }));
  assert.ok(text(body).includes("two"), "a failed update keeps the old body");
  handle.close();
  handle.close();
  assert.equal(closes, 1);
  assert.equal(layer(), null);
  handle.update(() => el("p", "after close"));

  // remoteBar: setHint leaves an unchanged hint alone.
  const bar = remoteBar({ items: [{ id: "a", label: "A", hint: "one" }] });
  const small = bar.querySelector("small");
  bar.setHint("a", "two");
  assert.equal(text(small), "two");
  bar.setHint("missing", "x");

  // delaySlider: dragging says nothing until release; nudges settle after 400 ms; no-ops say nothing.
  const changes = [];
  const slider = delaySlider({ value: 30, onChange: (v) => changes.push(v) });
  const range = slider.querySelector('input[type="range"]');
  range.value = "45";
  range.dispatchEvent(makeEvent("input"));
  assert.deepEqual(changes, []);
  assert.equal(text(slider.querySelector(".delay__value")), "45 s");
  range.dispatchEvent(makeEvent("change"));
  assert.deepEqual(changes, [45]);
  range.dispatchEvent(makeEvent("change"));
  assert.deepEqual(changes, [45], "a release on the same value is not a change");
  const plus = slider.querySelector('button[aria-label="5 seconds more"]');
  const minus = slider.querySelector('button[aria-label="5 seconds less"]');
  plus.click();
  await advance(100);
  plus.click();
  await advance(399);
  assert.deepEqual(changes, [45]);
  await advance(1);
  assert.deepEqual(changes, [45, 55]);
  plus.click();
  minus.click();
  await advance(500);
  assert.deepEqual(changes, [45, 55], "a nudge back to the same value is not a change");
  plus.click();
  slider.flush();
  assert.deepEqual(changes, [45, 55, 60]);
  range.value = "abc";
  range.dispatchEvent(makeEvent("change"));
  assert.equal(text(slider.querySelector(".delay__value")), "60 s");
  slider.setDelay(90);
  assert.deepEqual(changes, [45, 55, 60]);

  // strip: setPill swaps the pill in place and ignores a repeat.
  const s = strip({ us: { abbr: "SWT", points: 7 }, them: { abbr: "GRID", points: 3 }, status: "live", period: 2, clock: "5:00", pill: { kind: "delayed", label: "Delayed 30 s" } });
  const first = s.querySelector(".pill");
  s.setPill({ kind: "delayed", label: "Delayed 30 s" });
  assert.equal(s.querySelector(".pill"), first);
  s.setPill({ kind: "stale", label: "Stale 50 s, CFBD not answering" });
  assert.equal(s.querySelectorAll(".pill").length, 1);
  assert.equal(text(s.querySelector(".pill--stale")), "Stale 50 s, CFBD not answering");
  s.setPill(null);
  assert.equal(s.querySelector(".pill"), null);
  s.setPill({ kind: "live", label: "Live" });
  assert.equal(text(s.querySelector(".strip__right .pill")), "Live");

  // ticker: setGames swaps the games inside the running track; destroy lets go of the observer.
  const before = timers.size;
  const games = () => t.querySelectorAll(".ticker__half:not(.ticker__half--clone) .ticker__game").length;
  const t = ticker({ games: [TICKER.games[0], null, "junk"], id: "harness", label: "FBS scores" });
  assert.equal(games(), 1);
  const observer = observers[observers.length - 1];
  const track = t.querySelector(".ticker__track");
  assert.equal(observer.disconnected, false);
  t.setGames([...TICKER.games, game("Utah", "BYU", 0, 0)], "FBS scores, every 5 min");
  assert.equal(games(), 3);
  assert.equal(t.querySelector(".ticker__track"), track, "the same track keeps crawling");
  assert.equal(observer.disconnected, false);
  assert.equal(text(t.querySelector(".ticker__label")), "FBS scores, every 5 min");
  assert.equal(t.getAttribute("aria-label"), "FBS scores, every 5 min");
  t.setGames([]);
  assert.equal(observer.disconnected, true, "no games, no observer");
  assert.ok(text(t).includes("No other games right now."));
  t.setGames([TICKER.games[1]]);
  assert.equal(games(), 1);
  const second = observers[observers.length - 1];
  assert.notEqual(second, observer);
  t.destroy();
  assert.equal(second.disconnected, true);
  await advance(2000);
  assert.equal(timers.size, before, "no crawl checks left behind");
  const empty = ticker({ games: [], id: "empty" });
  empty.setGames("not a list");
  empty.destroy();

  // successRow: CFBD's rate with no counts, a source label, and nothing undefined.
  const row = successRow({ play: { text: "Run for 6", down: 1, distance: 10, yardsGained: 6, success: true }, offenseAbbr: "SWT", us: { abbr: "SWT", rate: 0.375, counts: null }, them: { abbr: "GRID", rate: null, counts: null }, source: "CFBD" });
  assert.equal(text(row.querySelector(".success__source")), "Success rate, CFBD");
  assert.equal(text(row.querySelector(".success__rate--us")), "SWT 38%");
  assert.equal(text(row.querySelector(".success__rate--them")), "GRID –");
  assert.ok(!/\b(undefined|NaN|null)\b/.test(text(row)));
  const old = successRow({ play: null, us: null, them: undefined });
  assert.equal(old.querySelector(".success__source"), null);
  assert.ok(text(old).includes("No scrimmage play yet."));
  const counted = successRow({ play: null, us: { abbr: "SWT", rate: 0.5, counts: { successes: 3, judged: 6 } } });
  assert.equal(text(counted.querySelector(".success__rate--us small")), "3 of 6");
};

function el(tag, content) {
  const node = document.createElement(tag);
  node.append(content);
  return node;
}

scenarios.live = async () => {
  const status = { mode: "live", window: WINDOW_OPEN, feed: feed("waiting") };
  const { view, container, shell, stripPill } = await mountLive({ status });
  assert.equal(sources.length, 1, "the window is open, so the stream connects at mount");
  assert.ok(latest().url.includes("delay=30"));
  assert.equal(shell(), "Waiting for CFBD");

  latest().emit("hello", { delaySeconds: 30, mode: "live", gameId: 526000600, feed: feed("ok") });
  status.feed = feed("ok");
  assert.equal(shell(), "Delayed 30 s");

  const frame1 = liveFrame();
  latest().emit("state", frame1);
  await settle();
  assert.equal(shell(), "Delayed 30 s");
  assert.equal(shell(), "Delayed 30 s");
  assert.equal(wake.requests, 1, "the screen is held awake on a live frame");
  const tickerNode = container.querySelector(".live-ticker .ticker");
  assert.ok(tickerNode, "the ticker is on the page");
  assert.equal(text(tickerNode.querySelector(".ticker__label")), "", "wave F5: no label on the national ticker");

  // wave F5 (owner 2026-10-20): In Game on one screen. The layout pass (owner 2026-10-22): the stage (the short box score
  // side by side, then the last five plays, Score by quarter with the drive lines, and the shot chart, no title bars), then
  // the dock at the bottom: the score line (the percentage and the last play at its right), the ticker, the panel row.
  const frame = container.querySelector(".live-frame");
  assert.ok(frame, "the frame");
  assert.deepEqual(partsOf(frame, ["strip", "stage-essentials", "stage", "live-ticker", "remote"]), ["stage", "strip", "live-ticker", "remote"], "in order: the stage, then the score line, the ticker and the panel row");
  assert.deepEqual(partsOf(frame.querySelector(".live-dock"), ["strip", "live-ticker", "remote"]), ["strip", "live-ticker", "remote"], "the three in the dock");
  assert.ok(container.querySelector(".remote").className.includes("remote--stage"), "the panel row of the stage kind");
  const extras = container.querySelector(".strip .strip__right .strip__extras");
  assert.ok(extras, "the strip's right side carries the extras");
  assert.match(text(extras.querySelector(".strip__wp .strip__wp-pct")), /^\d+%$/, "the win probability as a percentage");
  assert.ok(text(extras.querySelector(".strip__wp")).includes("SWT to win"), text(extras));
  assert.equal(text(extras.querySelector(".strip__last .strip__last-label")), "Last play");
  const lastWords = text(extras.querySelector(".strip__last .strip__last-words"));
  assert.ok(lastWords.includes("SWT") && /Q\d \d+:\d\d$/.test(lastWords), lastWords);
  assert.ok(["strip__last-who", "strip__last-ppa", "strip__last-when"].every((c) => extras.querySelector(`.${c}`)), "each part the line may drop is its own span");
  assert.equal(text(container.querySelector(".live-dock__play .live-dock__play-words")), lastWords, "the phone's moment in the ticker's place says the same play");
  const stage = container.querySelector(".stage");
  assert.deepEqual(stage.querySelectorAll(".band").map((b) => b.getAttribute("id")), ["live-box", "live-plays", "live-score", "live-chart"], "the four cells");
  assert.equal(stage.querySelectorAll(".band__head").length, 0, "no title bars (owner 2026-10-22)");
  const halves = stage.querySelectorAll("#live-box .stage-box__half");
  assert.equal(halves.length, 2, "both teams' box scores side by side");
  assert.equal(stage.querySelectorAll(".stage-step").length, 0, "nothing steps: the short box holds still");
  assert.deepEqual(halves.map((h) => text(h.querySelector(".stage-box__abbr"))), ["SWT", "SIL"], "each half headed by its team, at its first table's head");
  for (const h of halves) {
    const tables = h.querySelectorAll(".stat-table");
    const caps = { Passing: 1, Rushing: 2, Receiving: 3 };
    assert.ok(tables.length >= 2 && tables.length <= 3, `passing, rushing and receiving only: ${tables.length}`);
    for (const t of tables) {
      const head = text(t.querySelector("thead th")).replace(/^(SWT|SIL)/, "");
      const cap = Object.entries(caps).find(([name]) => head.includes(name));
      assert.ok(cap, `a short box category: ${head}`);
      assert.ok(t.querySelectorAll("tbody tr").length <= cap[1], `${cap[0]}: the top ${cap[1]}`);
      assert.ok(!t.querySelectorAll("thead th").some((th) => text(th).includes("QBR")), "no QBR in the short box");
      assert.equal(t.querySelectorAll("thead th button").length, 0, "the short box never re-sorts");
    }
    const rushYards = h.querySelectorAll(".stat-table")[1]?.querySelectorAll("tbody tr").map((tr) => Number(text(tr.children[2])));
    assert.ok(!rushYards || rushYards.every((y, i) => i === 0 || rushYards[i - 1] >= y), `the leaders by yards: ${rushYards}`);
  }
  const plays = stage.querySelectorAll("#live-plays ol.stage-plays li.stage-play");
  assert.equal(plays.length, 5, "the last five plays");
  assert.ok(plays.every((p) => text(p.querySelector(".stage-play__clock")) && text(p.querySelector(".stage-play__side")) && text(p.querySelector(".stage-play__words"))), "clock, side and words on every play");
  assert.equal(String(plays[0].dataset.play), String(frame1.plays[0].id), "newest first");
  assert.equal(stage.querySelectorAll("#live-score .qline__row").length, 2, "Score by quarter, both teams");
  assert.equal(stage.querySelectorAll("#live-score .stage-drives .stage-drives__row").length, 4, "the four drive lines");
  assert.ok(stage.querySelector("#live-chart .shot-field--both") && !stage.querySelector("#live-chart .shot-chart__seg"), "passes and runs at once, no switch");
  for (const id of ["live-wp", "live-stats", "live-leaders"]) assert.equal(container.querySelector(`#${id}`), null, `${id} left the page for a panel`);
  assert.equal(container.querySelector(".game-info"), null, "the game line left the page for the Notes sheet");
  assert.equal(container.querySelector(".live-tools"), null, "no tools row: the tools sit in the panel row");
  const row = container.querySelector(".remote");
  assert.deepEqual(row.querySelectorAll(".remote__btn[data-id]").map((b) => b.dataset.id), ["box", "drives", "splits", "plays", "situation", "edges", "weather", "visitors", "injuries", "lineups", "scores", "value"], "the twelve panels");
  assert.deepEqual(row.querySelectorAll(".remote__btn--tool").map(text), ["Delay 30 s", "Radio", "Notes", "Invite", "Big screen"], "then the five tools");
  const bigScreen = row.querySelectorAll(".remote__btn--tool")[4];
  assert.ok(bigScreen.tagName === "A" && bigScreen.getAttribute("href") === "#board", "the Big screen is a link");
  assert.ok(row.querySelectorAll(".remote__btn").slice(-5).every((b) => b.className.includes("remote__btn--tool")), "the tools at the row's end");
  assert.deepEqual(row.querySelectorAll(".remote__tools .remote__btn--tool").map(text), ["Delay 30 s", "Radio", "Notes", "Invite", "Big screen"], "pinned at the right end (owner 2026-10-22), the panels sliding beside them");
  assert.ok(!RAW.test(text(container)), "no raw value on the live sheet");

  // F9: CFBD's rate, the source label, the summary only for a judged play, no Success rate row in the feed table. Wave F5:
  // the win probability and the success row sit in the Situation panel, Team stats in the Box score panel.
  remoteButton(container, "situation").click();
  assert.equal(sheetTitle(), "Situation");
  assert.deepEqual(sheetBody().querySelectorAll(".band").map((b) => text(b.querySelector(".band__title"))), ["Situation", "Win probability"], "the situation grid, then the chart");
  assert.equal(text(sheetBody().querySelector("#live-wp .band__summary")), "Last play: success");
  assert.equal(text(sheetBody().querySelector("#live-wp .success__source")), "Success rate, CFBD");
  assert.equal(text(sheetBody().querySelector("#live-wp .success__rate--us")), "SWT 38%");
  assert.ok(sheetBody().querySelector("#live-wp .wp__svg"), "the win probability chart in the panel");
  latest().emit("state", liveFrame({ lastPlay: { ...frame1.lastPlay, success: null } }));
  assert.equal(sheetBody().querySelector("#live-wp .band__summary"), null, "no verdict, no summary");
  remoteButton(container, "box").click();
  assert.equal(sheetTitle(), "Box score");
  // wave 2 (2026-10-10): Team stats is the sized two-team kit, its label cell holding the long, middle and short names
  const statCells = sheetBody().querySelectorAll("#live-stats td.txt").map(longWords);
  assert.equal(statCells.filter((t) => t === "Success rate").length, 1, "one success-rate row: the team table's, not the feed table's");
  assert.ok(statCells.includes("Standard downs") && statCells.includes("Passing downs"));
  assert.deepEqual(sheetBody().querySelectorAll(".band").map((b) => text(b.querySelector(".band__title"))), ["Team stats", "Swampwater Tech", "Silver Dollar"], "Team stats first, then each team's box");
  document.body.querySelector(".side-sheet__head button").click();
  assert.equal(layer(), null);
  assert.equal(container.querySelector(".live-ticker .ticker"), tickerNode, "the ticker survives a frame");
  assert.ok(!RAW.test(text(container)), "no raw value on the live sheet");

  // F5: an open Plays sheet follows the game with its filter and scroll.
  const bar = container.querySelector(".remote");
  remoteButton(container, "plays").click();
  assert.ok(layer(), "the sheet opened");
  const openLayer = layer();
  assert.equal(remoteButton(container, "plays").getAttribute("aria-pressed"), "true");
  sheetBody().querySelector('.seg button[data-filter="us"]').click();
  assert.equal(sheetBody().querySelectorAll(".plays li.play--them").length, 0);
  sheetBody().scrollTop = 250;
  const frame2 = withNewPlay(liveFrame(), "Harness new play");
  latest().emit("state", frame2);
  assert.equal(layer(), openLayer, "the same sheet, not a new one");
  assert.ok(text(sheetBody()).includes("Harness new play"), "the open sheet shows the new play");
  assert.equal(sheetBody().querySelector('.seg button[data-filter="us"]').getAttribute("aria-pressed"), "true");
  assert.equal(sheetBody().querySelectorAll(".plays li.play--them").length, 0, "the filter survived");
  assert.equal(sheetBody().scrollTop, 250, "the scroll survived");
  assert.equal(container.querySelector(".remote"), bar, "the remote bar is built once");
  assert.equal(remoteButton(container, "plays").getAttribute("aria-pressed"), "true");
  assert.equal(text(remoteButton(container, "plays").querySelector("small")), `${frame2.counts.plays} plays`);
  assert.match(text(remoteButton(container, "scores").querySelector("small")), /^(\d+ live|every FBS game)$/); // Phase 16 wave 3 (L-14): the count of live games when there are some

  // The box score keeps the reader's sort.
  document.body.querySelector(".side-sheet__head button").click();
  assert.equal(layer(), null);
  assert.equal(remoteButton(container, "plays").getAttribute("aria-pressed"), "false");
  remoteButton(container, "box").click();
  const rushing = () => sheetBody().querySelectorAll(".stat-table").find((t) => text(t.querySelector("thead")).startsWith("Rushing"));
  rushing().querySelectorAll("th button").find((b) => longWords(b) === "Carries").click(); // wave 2: the whole head, Car at medium and small
  assert.equal(longWords(rushing().querySelector("th[aria-sort]")), "Carries");
  latest().emit("state", withNewPlay(frame2, "Another play"));
  assert.equal(longWords(rushing().querySelector("th[aria-sort]")), "Carries", "the sort survived a frame");

  // wave 2, step 3 (2026-10-10): every panel's tables size themselves; the two-team ones are the kit with the tug bar
  assert.ok(sheetBody().querySelectorAll(".stat-table-wrap").every((w) => w.dataset.size === "large" && typeof w.measure === "function"), "the box score's tables are sized");
  remoteButton(container, "situation").click();
  const sit = sheetBody().querySelector(".tt-wrap");
  assert.ok(sit && sit.querySelector("table").className.includes("tt--tug"), "Situation is the Team stats kit with the bar");
  assert.deepEqual(sit.querySelectorAll("tr.tt__head--a th").map(longWords), ["Situation", "Swampwater Tech", "Edge", "Silver Dollar"]);
  assert.equal(sit.querySelectorAll("tbody tr").length, 8);
  remoteButton(container, "drives").click();
  const driveTable = sheetBody().querySelector(".tt-wrap");
  assert.ok(driveTable && longWords(driveTable.querySelector("tr.tt__head--a th")) === "Drives", "the drive summary on the kit");
  assert.equal(driveTable.querySelectorAll("tbody tr").length, 7);
  assert.ok(sheetBody().querySelector(".drives, ul"), "the drive list under it");
  remoteButton(container, "splits").click();
  const splitWraps = sheetBody().querySelectorAll(".stat-table-wrap");
  assert.equal(splitWraps.length, 4, "each team's quarters and its situations");
  assert.ok(splitWraps.every((w) => w.dataset.size === "large"));
  assert.ok(text(sheetBody()).includes("PPA per play (no TD plays)") && text(sheetBody()).includes("Run success"));
  remoteButton(container, "box").click(); // wave F5: Team stats in the Box score panel
  assert.deepEqual(sheetBody().querySelector("#live-stats .tt-wrap").querySelectorAll("tr.tt__head--a th").map(longWords), ["Statistic", "Swampwater Tech", "Edge", "Silver Dollar"], "Team stats: the schools head it at large");
  assert.equal(sheetBody().querySelectorAll("#live-stats .tt-wrap").length, 2, "Team stats and the feed's efficiency, both on the kit");
  assert.ok(!RAW.test(text(sheetBody())), "no raw value in a panel");

  // Static panels are not rebuilt: Visitors fetches once.
  route("/api/recruiting", () => envelope({ visitors: { home: [{ name: "Five Star", position: "QB", stars: 5, highSchool: "IMG", status: "Committed" }], away: [], opponent: "Silver Dollar" } }));
  remoteButton(container, "visitors").click();
  await settle();
  assert.ok(text(sheetBody()).includes("Five Star"));
  for (const label of ["p1", "p2", "p3"]) latest().emit("state", withNewPlay(frame2, label));
  await settle();
  assert.equal(callsTo("/api/recruiting"), 1, "no refetch per play");
  assert.ok(text(sheetBody()).includes("Five Star"));
  document.body.querySelector(".side-sheet__head button").click();

  // F4: the feed health from pings drives both pills.
  latest().emit("ping", { feed: feed("stale", { staleSeconds: 50 }), serverTime: new Date(now).toISOString() });
  assert.equal(shell(), "Stale 50 s, CFBD not answering");
  assert.equal(shell(), "Stale 50 s, CFBD not answering");
  latest().emit("ping", { feed: feed("stale", { staleSeconds: 130 }), serverTime: new Date(now).toISOString() });
  assert.equal(shell(), "Stale 2 min, CFBD not answering");
  latest().emit("ping", { feed: feed("no_live_key"), serverTime: new Date(now).toISOString() });
  assert.equal(shell(), "No live feed on this key");
  latest().emit("ping", { feed: feed("ok"), serverTime: new Date(now).toISOString() });
  assert.equal(shell(), "Delayed 30 s");
  assert.equal(shell(), "Delayed 30 s");

  // F3: a bad frame is dropped; a frame that cannot be drawn keeps the last good screen.
  const stripBefore = container.querySelector(".strip");
  const warnCount = warnings.length;
  latest().emit("state", "{not json");
  assert.equal(warnings.length, warnCount + 1);
  assert.equal(container.querySelector(".strip"), stripBefore);
  globalThis.__failTag = "section";
  latest().emit("state", withNewPlay(frame2, "Unlucky"));
  globalThis.__failTag = null;
  assert.ok(errors.some((e) => e.includes("could not be drawn")));
  assert.equal(container.querySelector(".strip"), stripBefore, "the last good screen stays");
  assert.equal(shell(), "Display error");
  assert.equal(shell(), "Display error");
  latest().emit("state", withNewPlay(frame2, "Recovered"));
  assert.notEqual(container.querySelector(".strip"), stripBefore);
  assert.equal(shell(), "Delayed 30 s");
  assert.equal(shell(), "Delayed 30 s");

  // F3: an open side panel that cannot be redrawn keeps its last good body and never holds back
  // the strip or the score; the pill says Display error until the panel draws again or closes.
  remoteButton(container, "plays").click();
  const playsLayer = layer();
  assert.ok(text(sheetBody()).includes("Recovered"));
  const stripGood = container.querySelector(".strip");
  const errorCount = errors.length;
  globalThis.__failTag = "ul"; // only the play log builds a list
  latest().emit("state", withNewPlay(liveFrame({ homeScore: 99, awayScore: 98 }), "Hidden play"));
  globalThis.__failTag = null;
  assert.equal(errors.length, errorCount + 1);
  assert.ok(errors[errors.length - 1].includes("the Plays panel could not be redrawn"), errors[errors.length - 1]);
  assert.notEqual(container.querySelector(".strip"), stripGood, "the strip still follows the game");
  assert.ok(text(container.querySelector(".strip")).includes("99") && text(container.querySelector(".strip")).includes("98"), text(container.querySelector(".strip")));
  assert.equal(layer(), playsLayer, "the same sheet stays open");
  assert.ok(text(sheetBody()).includes("Recovered") && !text(sheetBody()).includes("Hidden play"), "the panel keeps its last good body");
  assert.equal(shell(), "Display error");
  assert.equal(shell(), "Display error");
  latest().emit("state", withNewPlay(frame2, "Drawn again"));
  assert.ok(text(sheetBody()).includes("Drawn again"), "the next good frame redraws the panel");
  assert.equal(shell(), "Delayed 30 s");
  assert.equal(shell(), "Delayed 30 s");
  globalThis.__failTag = "ul";
  latest().emit("state", withNewPlay(frame2, "Hidden again"));
  globalThis.__failTag = null;
  assert.equal(shell(), "Display error");
  document.body.querySelector(".side-sheet__head button").click();
  assert.equal(layer(), null);
  assert.equal(shell(), "Delayed 30 s", "closing the panel clears its Display error");
  assert.equal(shell(), "Delayed 30 s");

  // F2: the watchdog reopens a silent stream.
  const silent = latest();
  await advance(45000);
  assert.equal(silent.readyState, 2, "the silent stream was closed");
  assert.notEqual(latest(), silent, "and a new one opened");

  // F2: a dropped stream falls back to polling, and the next hello clears it.
  route("/api/live/state", () => envelope(withNewPlay(frame2, "Polled")));
  latest().emit("hello", { delaySeconds: 30, mode: "live", gameId: 526000600, feed: feed("ok") });
  latest().fail(false);
  assert.equal(shell(), "Offline");
  assert.equal(shell(), "Offline");
  await advance(15000);
  assert.equal(callsTo("/api/live/state"), 1);
  assert.equal(shell(), "Polling, stream down");
  assert.equal(shell(), "Polling, stream down");
  latest().emit("hello", { delaySeconds: 30, mode: "live", gameId: 526000600, feed: feed("ok") });
  assert.equal(shell(), "Delayed 30 s");
  latest().emit("state", frame2);
  await advance(30000);
  assert.equal(callsTo("/api/live/state"), 1, "the fallback poll stopped");
  assert.equal(container.querySelector(".live-ticker .ticker"), tickerNode, "the ticker reloaded with the same games and kept its node");

  // F2: a closed stream reconnects when the page is shown, and the backoff retry does not double it.
  const count = sources.length;
  latest().fail(true);
  document.dispatchEvent(makeEvent("visibilitychange"));
  assert.equal(sources.length, count + 1);
  await advance(6000);
  assert.equal(sources.length, count + 1, "the pending retry was cancelled by the reconnect");
  latest().emit("hello", { delaySeconds: 30, mode: "live", gameId: 526000600, feed: feed("ok") });

  // F1: the wake lock is asked for again after the system releases it.
  const requests = wake.requests;
  await wake.sentinels[wake.sentinels.length - 1].release();
  latest().emit("state", frame2);
  await settle();
  assert.equal(wake.requests, requests + 1, "a new frame asks again");
  await wake.sentinels[wake.sentinels.length - 1].release();
  document.dispatchEvent(makeEvent("visibilitychange"));
  await settle();
  assert.equal(wake.requests, requests + 2, "showing the page asks again");
  latest().emit("state", frame2);
  await settle();
  assert.equal(wake.requests, requests + 2, "a held lock is not asked for twice");

  // F7: the delay changes on release, nudges settle, and no change means no reconnect. Public release Phase 7b:
  // the slider lives in a side panel the Delay button opens, so it takes no room on the sheet. Wave F5: the Delay button
  // is the first tool in the panel row, and its words are short.
  assert.equal(container.querySelector('input[type="range"]'), null, "no slider on the sheet itself");
  const delayButton = container.querySelector(".remote .remote__delay");
  assert.equal(delayButton, toolButton(container, "Delay 30 s"));
  assert.equal(text(delayButton), "Delay 30 s");
  delayButton.click();
  assert.equal(sheetTitle(), "Spoiler delay");
  const range = document.body.querySelector('.sheet-layer input[type="range"]');
  const sliderNode = document.body.querySelector(".sheet-layer .delay");
  assert.ok(text(document.body.querySelector(".sheet-layer")).includes("Sync to my TV"), "the sync lives in the same panel");
  const before = sources.length;
  range.value = "45";
  range.dispatchEvent(makeEvent("input"));
  assert.equal(sources.length, before, "dragging does not reconnect");
  range.dispatchEvent(makeEvent("change"));
  assert.equal(sources.length, before + 1);
  assert.ok(latest().url.includes("delay=45"));
  assert.equal(shell(), "Delayed 45 s");
  assert.equal(shell(), "Delayed 45 s");
  assert.equal(text(delayButton), "Delay 45 s", "the button says the delay");
  latest().emit("hello", { delaySeconds: 45, mode: "live", gameId: 526000600, feed: feed("ok") });
  latest().emit("state", frame2);
  assert.equal(document.body.querySelector(".sheet-layer .delay"), sliderNode, "the slider is not rebuilt by a frame");
  const plus = document.body.querySelector('.sheet-layer button[aria-label="5 seconds more"]');
  const minus = document.body.querySelector('.sheet-layer button[aria-label="5 seconds less"]');
  plus.click();
  await advance(100);
  plus.click();
  await advance(100);
  plus.click();
  assert.equal(sources.length, before + 1);
  await advance(400);
  assert.equal(sources.length, before + 2);
  assert.ok(latest().url.includes("delay=60"));
  latest().emit("hello", { delaySeconds: 60, mode: "live", gameId: 526000600, feed: feed("ok") });
  plus.click();
  minus.click();
  await advance(500);
  assert.equal(sources.length, before + 2, "a nudge back to the same value does not reconnect");

  // The final: the wake lock goes, the pill says Final.
  latest().emit("state", liveFrame({ status: "final" }));
  await settle();
  assert.equal(wake.sentinels[wake.sentinels.length - 1].released, true);
  assert.equal(shell(), "Final");
  assert.equal(shell(), "Final");

  // Unmount leaves nothing behind: no sheet, no stream, no observer, no timer.
  remoteButton(container, "box").click();
  assert.ok(layer());
  view.unmount();
  assert.equal(layer(), null);
  assert.equal(latest().readyState, 2);
  assert.ok(observers.every((o) => o.disconnected), "every ticker observer is disconnected");
  assert.equal(timers.size, 0, `timers left after unmount: ${timers.size}`);
  assert.equal(errors.length, 3, errors.join("\n")); // the three injected faults, nothing else
};

scenarios.ticker = async () => {
  let ticker = clone(TICKER);
  const status = { mode: "live", window: WINDOW_OPEN, feed: feed("ok") };
  const { view, container } = await mountLive({ status, ticker: () => ticker });
  latest().emit("hello", { delaySeconds: 30, mode: "live", gameId: 526000600, feed: feed("ok") });
  latest().emit("state", liveFrame());
  const first = container.querySelector(".live-ticker .ticker");
  const firstObserver = observers[observers.length - 1];
  remoteButton(container, "scores").click();
  assert.ok(text(sheetBody()).includes("Alabama"));
  ticker = { source: "games", games: [...TICKER.games, game("Swampwater Tech State", "Miami", 3, 0)] };
  for (let i = 0; i < 4; i += 1) {
    await advance(15000);
    latest().emit("ping", { feed: feed("ok"), serverTime: new Date(now).toISOString() });
  }
  const second = container.querySelector(".live-ticker .ticker");
  assert.equal(second, first, "new games go into the same ticker, so the crawl carries on");
  assert.equal(firstObserver.disconnected, false, "the running line keeps its observer");
  assert.equal(second.querySelectorAll(".ticker__half:not(.ticker__half--clone) .ticker__game").length, 3);
  assert.equal(text(second.querySelector(".ticker__label")), "", "wave F5 (owner 2026-10-20): the national ticker has no label, whatever its source");
  assert.ok(text(sheetBody()).includes("Swampwater Tech State"), "the open Scores sheet follows the ticker");
  assert.ok(!text(container).includes("Biscuit Belt") && !text(document.body).includes("Top 25"));
  // the My teams ticker still names itself, with the schedule's cadence when the scores come from it
  ticker = { source: "games", mode: "mine", refreshMinutes: 20, games: [game("Swampwater Tech State", "Miami", 3, 0)] };
  for (let i = 0; i < 4; i += 1) {
    await advance(15000);
    latest().emit("ping", { feed: feed("ok"), serverTime: new Date(now).toISOString() });
  }
  assert.equal(container.querySelector(".live-ticker .ticker"), first, "the same ticker still");
  assert.equal(text(first.querySelector(".ticker__label")), "My teams, every 20 min");
  assert.equal(first.getAttribute("aria-label"), "My teams, every 20 min");
  assert.ok(text(sheetBody()).includes("Your primary and secondary teams' games"), "the Scores sheet says whose games these are");
  view.unmount();
  assert.equal(timers.size, 0);
};

scenarios.pregame = async () => {
  const status = { mode: "idle", window: { ...WINDOW_OPEN, open: false, liveView: false }, feed: feed("idle") };
  const { view, container, shell } = await mountLive({ status });
  assert.equal(sources.length, 0);
  assert.equal(shell(), "Pregame");
  const page = text(container);
  assert.ok(!/(undefined|NaN|null)/.test(page), page);
  // Phase 17 #25: before kickoff the sheet is the game sheet with dashes, never a promise to open itself. Wave F5 (owner
  // 2026-10-20): the stage, every cell waiting; the kickoff on the strip, the delay on its button (the line that said so
  // under the sheet is the board's foot now)
  assert.ok(!page.includes("opens by itself") && !page.includes("1 hour before"), page);
  assert.ok(text(container.querySelector(".strip")).includes("Kickoff"), "the strip shows the kickoff");
  assert.ok(text(container.querySelector(".strip .strip__wp")).includes("40%") && text(container.querySelector(".strip .strip__wp")).includes("at kickoff"), "the pregame number, marked as such");
  assert.equal(container.querySelector(".strip .strip__last"), null, "no last play before the game");
  assert.deepEqual(container.querySelectorAll(".stage .band").map((b) => b.getAttribute("id")), ["live-box", "live-plays", "live-score", "live-chart"], "the stage, waiting");
  assert.ok(page.includes("The box score fills in with the first pass or run.") && page.includes("Plays appear after kickoff.") && page.includes("The shot chart fills in with the first pass or run."), page);
  assert.ok(container.querySelector(".live-ticker .ticker"));
  assert.ok(container.querySelector(".remote"), "the remote bar is there before kickoff too");
  assert.equal(text(container.querySelector(".remote .remote__delay")), "Delay 30 s", "the delay on its button");
  container.querySelector(".remote .remote__delay").click();  // public release Phase 7b: the slider opens in a side panel
  const slider = document.body.querySelector(".sheet-layer .delay");
  const range = slider.querySelector('input[type="range"]');
  range.value = "45";
  range.dispatchEvent(makeEvent("change"));
  assert.equal(sources.length, 0, "no stream before the window");
  assert.equal(text(container.querySelector(".remote .remote__delay")), "Delay 45 s", "the button follows the slider");
  container.querySelector(".remote button").click(); // a side panel opens on the empty sheet without an error
  assert.ok(document.body.querySelector(".sheet-layer"));
  assert.equal(shell(), "Pregame");
  assert.equal(document.body.querySelector(".sheet-layer .delay"), slider);
  status.window = WINDOW_OPEN;
  status.feed = feed("waiting");
  await advance(60000);
  assert.equal(sources.length, 1, "the window opened: the stream connects");
  assert.ok(latest().url.includes("delay=45"));
  assert.equal(shell(), "Waiting for CFBD");
  latest().emit("hello", { delaySeconds: 45, mode: "live", gameId: 526001015, feed: feed("ok") });
  assert.equal(shell(), "Delayed 45 s");
  view.unmount();
  assert.equal(timers.size, 0);

  // The program failing at first is retried every minute.
  document.body.replaceChildren();
  let program = new Error("HTTP 503");
  const second = await mountLive({ status: { mode: "idle", window: null }, program: () => program });
  assert.ok(text(second.container).includes("tries again every minute"));
  program = PROGRAM;
  await advance(60000);
  assert.ok(text(second.container.querySelector(".strip")).includes("Kickoff") && second.container.querySelector(".stage"), "the program arrived: the stage, waiting");
  second.view.unmount();
};

// Owner 2026-10-10: In Game keeps our last final until noon the day after the game. A fresh open (a reload, another device,
// the board) draws it from /api/live/final at its own delay with that game's own program and no stream; it lets go when the
// hold ends; a game under way takes the sheet over.
scenarios.held = async () => {
  const finalState = liveFrame({ status: "final" });
  const GID = finalState.gameId;
  const HELD = { gameId: GID, home: "Diner Tech", away: "Swampwater Tech", kickoff: KICKOFF, finalAt: "2026-09-26T22:55:00Z", until: "2026-09-27T16:00:00Z", released: true };
  finalState.held = { until: HELD.until, finalAt: HELD.finalAt, kickoff: HELD.kickoff };
  let answer = { held: HELD, waiting: true };
  route("/api/live/final", () => envelope(answer));
  route(`/api/program/${GID}`, () => envelope({ ...PROGRAM, game: { ...PROGRAM.game, gameId: GID } }));
  route(`/api/games/${GID}/analytics`, () => envelope({ winProbability: { available: false }, ppa: { available: false } }));
  const status = { mode: "idle", window: { ...WINDOW_OPEN, gameId: 526001099, open: false, liveView: false }, held: HELD, feed: feed("idle") };
  const { view, container, shell } = await mountLive({ status });
  assert.equal(sources.length, 0, "a held final opens no stream");
  // this device is still behind the final: it asks again every few seconds and never draws it early
  assert.equal(callsTo("/api/live/final"), 1);
  answer = finalState;
  await advance(5000);
  assert.equal(callsTo("/api/live/final"), 2);
  const page = text(container);
  assert.ok(!/(undefined|NaN|null)/.test(page), page);
  assert.ok(shell().startsWith("Final"), shell());
  assert.ok(shell().includes("·"), "the held final carries its date");
  assert.equal(text(container.querySelector(".strip .strip__final")), "Final");
  assert.ok(container.querySelector("#live-box .stage-box__half .stat-table-wrap"), "the final box on the stage");
  // the final's own line (the Archive link, "In Game shows this final until") is scenarios.finalnote
  assert.ok(callsTo(`/api/program/${GID}`) >= 1, "the held game's own program, not next week's");
  assert.ok(callsTo(`/api/games/${GID}/analytics`) >= 1, "the post-game numbers of that game");
  // the hold ends (noon the day after the game): the next game's pregame sheet
  status.held = null;
  await advance(60000);
  assert.equal(shell(), "Pregame");
  assert.ok(text(container.querySelector(".strip")).includes("Kickoff") && !container.querySelector(".strip .strip__final"), "the next game's kickoff on the strip, no final");
  view.unmount();
  assert.equal(timers.size, 0, "nothing left running");

  // a game under way takes over a held sheet
  document.body.replaceChildren();
  answer = finalState;
  const status2 = { mode: "idle", window: { ...WINDOW_OPEN, gameId: 526001099, open: false, liveView: false }, held: HELD, feed: feed("idle") };
  const second = await mountLive({ status: status2 });
  assert.ok(second.shell().startsWith("Final"));
  const before = sources.length;
  status2.window = { ...WINDOW_OPEN, gameId: 526001099, open: true };
  status2.held = HELD;
  await advance(60000);
  assert.equal(sources.length, before + 1, "the next game's stream connects");
  latest().emit("hello", { delaySeconds: 30, mode: "live", gameId: 526001099, feed: feed("waiting") });
  assert.ok(!second.shell().startsWith("Final"), second.shell());
  second.view.unmount();

  // review 2026-10-10: a sheet still mid-game on the held game (a restart cut its stream before the final) reaches the held
  // final through /api/live/final, never stays on its last frame; waking it again asks for the final, never a stream
  document.body.replaceChildren();
  const status3 = { mode: "live", window: { ...WINDOW_OPEN }, feed: feed("ok") };
  const third = await mountLive({ status: status3 });
  latest().emit("state", liveFrame({ gameId: GID }));
  assert.ok(!third.shell().startsWith("Final"));
  status3.window = { ...WINDOW_OPEN, gameId: 526001099, open: false, liveView: false };
  status3.mode = "idle";
  status3.held = HELD;
  answer = finalState;
  const asked = callsTo("/api/live/final");
  await advance(60000);
  assert.ok(callsTo("/api/live/final") > asked, "the held final is fetched for the stuck sheet");
  assert.ok(third.shell().startsWith("Final"), third.shell());
  const streams = sources.length;
  document.visibilityState = "visible";
  document.dispatchEvent(makeEvent("visibilitychange"));
  await settle();
  assert.equal(sources.length, streams, "waking a held final opens no stream");
  third.view.unmount();
};

// Owner 2026-10-10: after the final, In Game said when it was played, linked the whole game in the Archive and the next
// game's program, and said until when it shows this final (finalNote). Wave F5 rebuilt In Game as one screen and that line
// went with the sheet's bottom: liveParts gives it to the board's foot only (boardNote), and the tablet shows nothing of
// it. Left failing on purpose (2026-10-20): a suspected omission of the rebuild, for the owner to rule on; the board's
// copy is checked in scenarios.board.
scenarios.finalnote = async () => {
  const finalState = liveFrame({ status: "final" });
  const GID = finalState.gameId;
  finalState.held = { until: "2026-09-27T16:00:00Z", finalAt: "2026-09-26T22:55:00Z", kickoff: KICKOFF };
  route(`/api/games/${GID}/analytics`, () => envelope({ winProbability: { available: false }, ppa: { available: false } }));
  const status = { mode: "live", window: WINDOW_OPEN, feed: feed("ok") };
  const { view, container, shell } = await mountLive({ status });
  latest().emit("hello", { delaySeconds: 30, mode: "live", gameId: GID, feed: feed("ok") });
  latest().emit("state", finalState);
  await settle();
  assert.ok(shell().startsWith("Final"), shell());
  const note = container.querySelector(".final-note");
  const link = container.querySelector(`a[href="#archive=${GID}"]`);
  assert.ok(note && link && text(link).includes("Archive") && text(note).includes("In Game shows this final until"), `the final's line on In Game (the whole game in the Archive, the next game's program, until when the final stays): ${note ? text(note) : "no .final-note on the page; the frame holds " + partsOf(container.querySelector(".live-frame"), ["strip", "stage", "live-ticker", "remote"]).join(", ")}`);
  view.unmount();
};

scenarios.oldserver = async () => {
  const status = { mode: "live", window: { gameId: 526001015, kickoff: KICKOFF, opensAt: KICKOFF, closesAt: KICKOFF, open: true } };
  const { view, container, shell, stripPill } = await mountLive({ status });
  assert.equal(shell(), "Delayed 30 s", "no feed block: the pill works as before");
  assert.equal(stripPill(), undefined, "Phase 17 #29: one pill, in the top bar; the strip carries none");
  latest().emit("hello", { delaySeconds: 30, mode: "live", gameId: 526000600 });
  const frame = clone(FIXTURE);
  frame.status = "in_progress";
  frame.box["Swampwater Tech"].successCounts = { successes: 29, judged: 75 };
  frame.box["Swampwater Tech"].successRate = 0.387;
  frame.lastPlay = { ...frame.plays[1], success: false };
  latest().emit("state", frame);
  assert.equal(shell(), "Delayed 30 s");
  remoteButton(container, "situation").click(); // wave F5: the success row sits in the Situation panel
  assert.equal(text(sheetBody().querySelector("#live-wp .success__source")), "Success rate, play log");
  assert.equal(text(sheetBody().querySelector("#live-wp .success__rate--us small")), "29 of 75");
  assert.equal(text(sheetBody().querySelector("#live-wp .band__summary")), "Last play: failed");
  document.body.querySelector(".side-sheet__head button").click();
  const first = latest();
  await advance(120000);
  assert.equal(latest(), first, "no pings from this server, so no watchdog reconnects");
  view.unmount();
};

scenarios.silentstart = async () => {
  // A Phase 10a server (its status carries the feed block) whose first stream opens and never says hello.
  const status = { mode: "live", window: WINDOW_OPEN, feed: feed("ok") };
  const { view } = await mountLive({ status });
  assert.equal(sources.length, 1);
  const first = latest();
  await advance(45000);
  assert.equal(first.readyState, 2, "the silent first stream was closed");
  assert.equal(sources.length, 2, "and a new one opened");
  // Once a stream says hello, its hello decides: one without the feed block means no pings to wait for.
  latest().emit("hello", { delaySeconds: 30, mode: "live", gameId: 526001015 });
  const second = latest();
  await advance(130000);
  assert.equal(latest(), second, "the status check does not turn the watchdog back on over the hello");
  view.unmount();
  assert.equal(timers.size, 0);

  // A server from before Phase 10a (no feed block anywhere) keeps today's behaviour: no watchdog.
  document.body.replaceChildren();
  const old = await mountLive({ status: { mode: "live", window: { gameId: 526001015, kickoff: KICKOFF, opensAt: KICKOFF, closesAt: KICKOFF, open: true } } });
  const quiet = latest();
  assert.equal(sources.length, 3);
  await advance(130000);
  assert.equal(latest(), quiet, "no pings from this server, so a quiet stream is left alone");
  old.view.unmount();
  assert.equal(timers.size, 0);
};

scenarios.board = async () => {
  // The game-day board (freeze wave F5, owner 2026-10-20: "the big screen should mirror the tablet's exactly"): In Game's
  // own frame without the chrome: the strip with its extras, the stage, the ticker, then a foot in place of the panel row
  // with the radio, the delay line (or the final's) and the QR. No panel buttons, no menu, nothing remembered on the device.
  route("/api/program/next", () => envelope(PROGRAM));
  route("/api/live/status", () => envelope({ mode: "live", window: WINDOW_OPEN, feed: feed("ok") }));
  route("/api/ticker", () => envelope(TICKER));
  route("/api/settings", () => envelope({ prefs: {} }));
  const { createLiveView } = await import(moduleUrl("views/live.js"));
  const view = createLiveView({ board: true });
  const container = document.createElement("main");
  document.body.append(container);
  await view.mount(container);
  await settle();
  latest().emit("hello", { delaySeconds: 30, mode: "live", gameId: 526000600, feed: feed("ok") });
  const frame1 = liveFrame();
  latest().emit("state", frame1);
  await settle();
  const tv = container.querySelector(".tv");
  assert.ok(tv && tv.className.includes("live-frame") && !tv.className.includes("tv--empty"), `In Game's frame: ${tv && tv.className}`);
  assert.ok(!/\[object \w+\]|\b(undefined|NaN|null)\b/.test(text(tv)), text(tv).slice(0, 300));
  assert.deepEqual(partsOf(tv, ["strip", "stage-essentials", "stage", "live-ticker", "remote", "tv__foot"]), ["stage", "strip", "live-ticker", "tv__foot"], "the stage, then the score line, the ticker and the foot; no panel row");
  const dockEl = tv.querySelector(".live-dock");
  assert.equal(dockEl.childNodes[dockEl.childNodes.length - 1].className, "tv__foot", "the foot last, in the dock");
  // the strip with the percentage and the last play
  const extras = tv.querySelector(".strip .strip__extras");
  assert.ok(extras && extras.querySelector(".strip__wp") && extras.querySelector(".strip__last"), "the strip's extras");
  assert.match(text(extras.querySelector(".strip__wp-pct")), /^\d+%$/);
  // the stage: In Game's four cells, both teams' box score side by side
  assert.deepEqual(tv.querySelectorAll(".stage .band").map((b) => b.getAttribute("id")), ["live-box", "live-plays", "live-score", "live-chart"]);
  const halves = tv.querySelectorAll("#live-box .stage-box__half");
  assert.equal(halves.length, 2, "both teams' box score, each its half");
  assert.ok(halves.every((h) => h.querySelectorAll(".stat-table-wrap").length >= 2 && !h.querySelector(".stage-step")), "each half its short box, holding still");
  assert.equal(tv.querySelectorAll("#live-plays li.stage-play").length, 5, "the last five plays");
  assert.ok(tv.querySelector("#live-score .qline__row") && tv.querySelectorAll("#live-score .stage-drives__row").length === 4, "Score by quarter with the drive lines is on the board now: In Game mirrored");
  const chart = tv.querySelector("#live-chart");
  assert.ok(chart.querySelector(".shot-field--both") && chart.querySelectorAll(".shot-row--runs .shot-cell").length === 3, "the passes over the line of scrimmage and the runs under it, one chart");
  assert.equal(chart.querySelector(".shot-chart__seg"), null, "no Passes and Runs switch");
  assert.ok(!text(chart).includes("Success is CFBD"), "the counts only, on a TV");
  assert.ok(tv.querySelectorAll(".stat-table-wrap").every((w) => ["large", "medium", "small"].includes(w.dataset.size)), "every table sized");
  // nothing of the old board, and nothing that lives in a panel
  for (const sel of [".tv__main", ".tv__cell--wp", ".tv__cell--panel", ".tv__menu", ".tv__menu-btn", ".board-panel", ".tv__bar--strip", ".tv__bar--ticker", ".remote", ".remote__btn", ".live-tools", ".game-info", "#live-wp", "#live-stats", "#live-leaders"]) assert.equal(container.querySelector(sel), null, `${sel} is not on the board`);
  assert.equal(layer(), null, "no sheet on the board");
  assert.equal(localStorage.getItem("kickoff.board.panel"), null, "nothing remembered on the device");
  // the foot: the radio and QR cells the board view fills, and the delay line between them
  const foot = tv.querySelector(".tv__foot");
  assert.deepEqual(foot.childNodes.map((n) => n.className), ["tv__radio", "tv__note", "tv__qr"]);
  assert.ok(text(foot.querySelector(".tv__note")).includes("30 s behind the broadcast"), "the spoiler-delay line");
  assert.equal(text(foot.querySelector(".tv__note .tv__delay")), "30 s");
  // nothing steps any more (owner 2026-10-22: "the box currently moves around a lot"); a frame keeps the frame
  assert.ok(![...timers.values()].some((t) => t.every === 2200), "no stepping timer");
  await advance(2500);
  latest().emit("state", withNewPlay(frame1, "Board play"));
  await settle();
  assert.equal(container.querySelector(".tv"), tv, "the frame is built once");
  assert.equal(String(tv.querySelector("#live-plays li.stage-play").dataset.play), "harness-Board play", "the new play leads the list");
  // after the final the foot carries the final's line: the Archive link and the next game's program
  route("/api/games/", () => envelope({ winProbability: { available: false }, ppa: { available: false } }));
  const finalState = liveFrame({ status: "final" });
  finalState.held = { until: "2026-09-27T16:00:00Z", finalAt: "2026-09-26T22:55:00Z", kickoff: KICKOFF };
  latest().emit("state", finalState);
  await settle();
  const note = foot.querySelector(".tv__note .final-note");
  assert.ok(note && note.querySelector(`a[href="#archive=${finalState.gameId}"]`) && text(note).includes("the next game's program") && text(note).includes("In Game shows this final until"), `the final's line in the foot: ${text(foot)}`);
  assert.ok(!/\[object \w+\]|\b(undefined|NaN|null)\b/.test(text(tv)), text(tv).slice(0, 300));
  view.unmount();
  assert.equal(timers.size, 0, `timers left after unmount: ${timers.size} ${[...timers.values()].map((t) => `${t.every}:${String(t.fn).slice(0, 60)}`).join(" | ")}`);

  // before kickoff the board is the pregame stage with the kickoff line in its foot; with no game at all it is empty
  document.body.replaceChildren();
  route("/api/live/status", () => envelope({ mode: "idle", window: { ...WINDOW_OPEN, open: false, liveView: false }, feed: feed("idle") }));
  const early = createLiveView({ board: true });
  const main = document.createElement("main");
  document.body.append(main);
  await early.mount(main);
  await settle();
  const pre = main.querySelector(".tv");
  assert.ok(pre && !pre.className.includes("tv--empty"), "a game ahead: the stage, waiting");
  assert.ok(text(pre.querySelector(".strip")).includes("Kickoff") && pre.querySelector("#live-box") && pre.querySelector("#live-chart"));
  assert.ok(text(pre.querySelector(".tv__foot .tv__note")).includes("The sheet fills in as the game is played, 30 s behind the broadcast"), text(pre.querySelector(".tv__foot")));
  assert.equal(sources.length, 1, "no stream before the window");
  early.unmount();
  assert.equal(timers.size, 0);
  document.body.replaceChildren();
  route("/api/program/next", () => envelope({ game: null }));
  const none = createLiveView({ board: true });
  const empty = document.createElement("main");
  document.body.append(empty);
  await none.mount(empty);
  await settle();
  assert.ok(empty.querySelector(".tv").className.includes("tv--empty"), "no game of ours ahead: the empty board");
  assert.ok(text(empty).includes("No game of ours is on the schedule ahead"));
  assert.equal(empty.querySelector(".tv .strip"), null);
  none.unmount();
  assert.equal(timers.size, 0);
};

scenarios.archive = async () => {
  const { createArchiveView } = await import(moduleUrl("views/archive.js"));
  const state = liveFrame({ status: "final" });
  const good = { gameId: 526000600, week: 4, home: "Silver Dollar", away: "Swampwater Tech", homeIsUs: false, opponent: "Silver Dollar", usScore: 44, themScore: 39, kickoff: KICKOFF, savedAt: KICKOFF, state, winProbability: { available: false, note: "Not posted." }, ppa: { available: false }, final: { available: false }, notes: { present: false } };
  const junk = { gameId: 1, homeIsUs: "maybe", state: { drives: "x", plays: { a: 1 }, box: "zz", boxScore: [1], counts: "q", feedStats: 3 }, notes: { availability: "x", sources: "y", present: true }, ppa: { available: true, players: { us: "x", them: [null] }, teams: 4 }, winProbability: { available: true, series: "no" }, final: { players: 5 } };
  for (const [id, data] of [["526000600", good], ["1", junk]]) {
    route(`/api/archive/${id}`, () => envelope(data));
    const view = createArchiveView({ gameId: id, onStatus: () => {} });
    const container = document.createElement("main");
    document.body.replaceChildren(container);
    view.mount(container);
    await settle();
    const page = text(container);
    assert.ok(page.includes("Team stats"), `archive ${id} drew the game: ${page.slice(0, 200)}`);
    const raw = page.match(/.{0,80}\b(undefined|NaN|null)\b.{0,40}/);
    assert.equal(raw, null, `archive ${id} shows a raw value: ${raw && raw[0]}`);
    if (data === good) {
      const cells = container.querySelectorAll("#archive-stats td.txt").map(longWords); // wave 2: both tables on the sized kit
      assert.ok(cells.includes("PPA per play"), "the feed table is drawn"); // final pass: the Season tables' name
      assert.equal(cells.filter((t) => t === "Success rate").length, 1, "one success-rate row: the team table's, not the feed table's");
    }
    view.unmount();
  }
  // tables wave 3: each team's play value is In Game's two-team table with the tug bar (the defense's rows say allowed), the
  // school and mascot over each side at large as on Team stats; the players' tables give the position its own column
  const valued = { ...good, us: { school: "Swampwater Tech", abbreviation: "SWT", mascot: "Mudcats" }, them: { school: "Silver Dollar", abbreviation: "SD", mascot: "Dealers" }, ppa: { available: true, teams: { us: { offense: { overall: 0.21, passing: 0.3, rushing: 0.1 }, defense: { overall: 0.05, passing: "x", rushing: null } }, them: { offense: { overall: -0.1 }, defense: "x" } }, players: { us: [{ playerId: "7", name: "Avery Passer", position: "QB", all: 0.4, pass: 0.5, rush: null }, null], them: [] } } };
  route("/api/archive/526000601", () => envelope(valued));
  const one = createArchiveView({ gameId: "526000601", onStatus: () => {} });
  const page = document.createElement("main");
  document.body.replaceChildren(page);
  one.mount(page);
  await settle();
  assert.ok(!/\b(undefined|NaN|null)\b/.test(text(page)), text(page).slice(0, 300));
  const value = page.querySelector("#archive-ppa .tt-wrap");
  assert.ok(value && value.querySelector("td.tt__tug .tug"), "the play value table is the kit with the tug bar");
  assert.deepEqual(value.querySelectorAll(".tt__team").map(longWords), ["Swampwater Tech Mudcats", "Silver Dollar Dealers"]);
  assert.ok(value.querySelectorAll("td.tt__label, td.tt__mid, td.txt").map(longWords).includes("Defense allowed, overall"), "the defense's rows say allowed");
  assert.deepEqual(page.querySelectorAll("#archive-stats .tt__team").slice(0, 2).map(longWords), ["Swampwater Tech Mudcats", "Silver Dollar Dealers"], "Team stats wear the mascot heads too");
  const players = page.querySelector("#archive-ppa .twocol .stat-table-wrap");
  assert.deepEqual(players.querySelectorAll("thead th").map(longWords), ["Player", "Pos", "PPA per play", "PPA per pass", "PPA per rush"]);
  one.unmount();
  // the list sizes itself: the week and plays from medium, the win probability's source at large; newest first
  route("/api/archive", () => envelope({ games: [
    null, "x",
    { gameId: 5, away: "Swampwater Tech", home: "Silver Dollar", awayAbbr: "SWT", homeAbbr: "SD", usScore: 1, themScore: 0, kickoff: "2026-09-05T23:00:00Z", week: 2, plays: 150, hasWinProbability: true },
    { gameId: 6, away: "Diner Tech", home: "Swampwater Tech", awayAbbr: null, usScore: 10, themScore: 24, kickoff: "2026-09-19T23:00:00Z", week: 4, hasWinProbability: false },
    { gameId: 7, home: 4, away: null, kickoff: 9, usScore: "x" },
  ], skipped: 1 }));
  const list = createArchiveView({ onStatus: () => {} });
  const container = document.createElement("main");
  document.body.replaceChildren(container);
  list.mount(container);
  await settle();
  assert.ok(text(container).includes("3 games this app watched"));
  assert.ok(!/\b(undefined|NaN|null)\b/.test(text(container)), text(container));
  const wrap = container.querySelector("#archive-list .stat-table-wrap");
  assert.equal(wrap.dataset.size, "large");
  const formOf = (node, which) => text(node.querySelector(`.sz-t--${which}`) || node);
  const heads = wrap.querySelectorAll("thead th");
  assert.deepEqual(heads.map((th) => formOf(th, "long")), ["Date", "Week", "Game", "Result", "Plays", "Win probability"]);
  assert.deepEqual(heads.map((th) => formOf(th, "mid")), ["Date", "Wk", "Game", "Result", "Plays", "Win prob."]);
  const size = (th) => ["st__min-medium", "st__min-large"].find((c) => String(th.getAttribute("class") || "").includes(c)) || "";
  assert.deepEqual(heads.map(size), ["", "st__min-medium", "", "", "st__min-medium", "st__min-large"]);
  assert.equal(heads[0].getAttribute("aria-sort"), "descending", "the newest first");
  const ids = () => wrap.querySelectorAll("tbody tr").map((tr) => text(tr.querySelectorAll("td")[3]));
  assert.deepEqual(ids(), ["L 10-24", "W 1-0", "\u2013"], "by kickoff, a game without one last");
  const rowOf = (i) => wrap.querySelectorAll("tbody tr")[i].querySelectorAll("td");
  const small = rowOf(1)[2].querySelector(".sz-t--short");
  assert.equal(text(small), "SWT at SD", "at small each school's abbreviation");
  assert.equal(small.querySelectorAll(".team-link").length, 2, "still each team's link");
  assert.ok(text(rowOf(0)[2].querySelector(".sz-t--short")).startsWith("DINE at "), "a school the server could not name: its first letters");
  assert.deepEqual([text(rowOf(0)[5]), text(rowOf(1)[5])], ["From CFBD", "Saved at the final"]);
  heads[3].querySelector("button").click();
  assert.deepEqual(ids(), ["W 1-0", "L 10-24", "\u2013"], "the result sorts by its margin");
  wrap.querySelectorAll("tbody tr")[1].click();
  assert.equal(window.location.hash, "archive=6", "a row opens its game");
  list.unmount();
};

""" + RUNNER_JS
