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
SCENARIOS = ["pure", "components", "live", "ticker", "pregame", "oldserver", "silentstart", "archive", "gameinfo"]


@needs_node
def test_every_javascript_module_passes_node_check(tmp_path: Path):
    modules = sorted(STATIC_JS.rglob("*.js"))
    assert len(modules) >= 28
    for module in modules:
        # .mjs so Node reads it as the ES module the browser loads
        target = tmp_path / (module.relative_to(STATIC_JS).as_posix().replace("/", "__")[:-3] + ".mjs")
        target.write_text(module.read_text(encoding="utf-8"), encoding="utf-8")
        result = subprocess.run([NODE, "--check", str(target)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        assert result.returncode == 0, f"{module.relative_to(PROJECT_ROOT)}: {result.stderr[:400]}"


def test_stale_labels_are_gone():
    live = (STATIC_JS / "views" / "live.js").read_text(encoding="utf-8")
    for stale in ("Biscuit Belt and Top 25", "No Biscuit Belt or Top 25 games", "Biscuit Belt, Top 25", "opens by itself 30 minutes before kickoff"):
        assert stale not in live, stale
    for name in OWNED:
        source = (STATIC_JS / name).read_text(encoding="utf-8")
        assert "Biscuit Belt and Top 25" not in source and "Biscuit Belt, Top 25" not in source and "Biscuit Belt or Top 25" not in source, name
    # the ticker carries every FBS game; Phase 17 #25: the sheet no longer promises to open itself
    assert "FBS scores" in live and "every FBS game" in live and "No FBS games" in live
    assert "opens by itself" not in live and "1 hour before kickoff" not in live


def test_success_rate_row_is_not_repeated_in_the_feed_table():
    # final pass: the feed rows are one shared list (ui/team-stats.js FEED_ROWS) drawn by the Live sheet and the Archive
    live = (STATIC_JS / "views" / "live.js").read_text(encoding="utf-8")
    start = live.index("function feedStatsTable")
    body = live[start : live.index("function wpBlock")]
    assert "FEED_ROWS" in body and '"Success rate"' not in body
    rows = (STATIC_JS / "ui" / "team-stats.js").read_text(encoding="utf-8")
    rows = rows[rows.index("export const FEED_ROWS") : rows.index("];", rows.index("export const FEED_ROWS"))]
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
const layer = () => document.body.querySelector(".sheet-layer");
const sheetBody = () => document.body.querySelector(".sheet-layer .side-sheet__body");
const remoteButton = (container, id) => container.querySelector(`.remote__btn[data-id="${id}"]`);

// --- scenarios ------------------------------------------------------------------------------------

const scenarios = {};

// Public release Phase 7b: the TV crew and both staffs under the score, the shot chart, the hint when missing.
scenarios.gameinfo = async () => {
  const withCrew = clone(PROGRAM);
  withCrew.weather = { available: true, tempF: 71.6, windMph: 8, dome: false };
  withCrew.notes = {
    present: true, availability: [],
    broadcast: { network: "ABC", playByPlay: "Pat Caller", analyst: "Sam Color", sideline: ["Lee Field", null, 7], source: "network release" },
    coaches: { us: { headCoach: "Head Us", offensiveCoordinator: "Oc Us", defensiveCoordinator: null }, them: { headCoach: "Head Them" } },
  };
  const status = { mode: "live", window: WINDOW_OPEN, feed: feed("ok") };
  const { view, container } = await mountLive({ status, program: withCrew });
  latest().emit("hello", { delaySeconds: 30, mode: "live", gameId: 526000600, feed: feed("ok") });
  const frame = liveFrame();
  latest().emit("state", frame);
  await settle();
  const info = text(container.querySelector(".game-info"));
  assert.ok(info.includes("Vaught-Hemingway Stadium") && info.includes("72°F, wind 8 mph"), info);
  assert.ok(info.includes("ABC: Pat Caller, Sam Color, Lee Field (sideline)"), info);
  assert.ok(info.includes("SWT HC Head Us · OC Oc Us") && info.includes("HC Head Them") && !info.includes("DC"), info);
  assert.ok(!info.includes("Add "), "nothing missing, no hint");
  assert.equal(container.querySelector(".strip").parentNode, container.querySelector(".game-info").parentNode, "the strip and the line are siblings, so the strip stays sticky");
  const chart = container.querySelector("#live-chart");
  assert.ok(chart && text(chart.querySelector(".band__title")).includes("SWT offense"));
  assert.equal(chart.querySelectorAll(".shot-cell").length, 6, "six pass zones");
  assert.ok(!/\b(undefined|NaN|null)\b/.test(text(chart)), text(chart));
  chart.querySelectorAll(".shot-chart__seg button")[1].click();
  await settle();
  const runs = container.querySelector("#live-chart");
  assert.equal(runs.querySelectorAll(".shot-cell").length, 3, "three run lanes");
  assert.ok(text(runs.querySelector(".band__summary")).includes("runs by lane"));
  latest().emit("state", frame);
  assert.equal(container.querySelector("#live-chart").querySelectorAll(".shot-cell").length, 3, "the choice holds across frames");
  view.unmount();

  // no crew and no staffs in the notes: a quiet hint where to add them
  document.body.replaceChildren();
  const bare = await mountLive({ status, program: PROGRAM });
  latest().emit("hello", { delaySeconds: 30, mode: "live", gameId: 526000600, feed: feed("ok") });
  const empty = liveFrame();
  empty.shotChart = { "Swampwater Tech": { passes: { "deep-left": { attempts: "x" }, "short-left": null }, runs: "junk", unzoned: null, sacks: NaN } };
  latest().emit("state", empty);
  await settle();
  const hint = text(bare.container.querySelector(".game-info"));
  assert.ok(hint.includes("on ESPN") && hint.includes("Add the TV crew and the coaches with the notes prompt on the Game program."), hint);
  assert.ok(!/\b(undefined|NaN|null)\b/.test(text(bare.container.querySelector("#live-chart"))), "a damaged chart draws dashes");
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
  assert.equal(text(tickerNode.querySelector(".ticker__label")), "FBS scores");

  // F9: CFBD's rate, the source label, the summary only for a judged play, no Success rate row in the feed table.
  assert.equal(text(container.querySelector("#live-wp .band__summary")), "Last play: success");
  assert.equal(text(container.querySelector("#live-wp .success__source")), "Success rate, CFBD");
  assert.equal(text(container.querySelector("#live-wp .success__rate--us")), "SWT 38%");
  const statCells = container.querySelectorAll("#live-stats td.txt").map(text);
  assert.equal(statCells.filter((t) => t === "Success rate").length, 1, "one success-rate row: the team table's, not the feed table's");
  assert.ok(statCells.includes("Standard downs") && statCells.includes("Passing downs"));
  latest().emit("state", liveFrame({ lastPlay: { ...frame1.lastPlay, success: null } }));
  assert.equal(container.querySelector("#live-wp .band__summary"), null, "no verdict, no summary");
  assert.equal(container.querySelector(".live-ticker .ticker"), tickerNode, "the ticker survives a frame");
  assert.ok(!/\b(undefined|NaN|null)\b/.test(text(container)), "no raw value on the live sheet");

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
  rushing().querySelectorAll("th button").find((b) => text(b) === "Car").click();
  assert.equal(text(rushing().querySelector("th[aria-sort]")), "Car");
  latest().emit("state", withNewPlay(frame2, "Another play"));
  assert.equal(text(rushing().querySelector("th[aria-sort]")), "Car", "the sort survived a frame");

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
  // the slider lives in a side panel the Delay button opens, so it takes no room on the sheet.
  assert.equal(container.querySelector('input[type="range"]'), null, "no slider on the sheet itself");
  const delayButton = container.querySelector(".delay-button");
  assert.equal(text(delayButton), "Spoiler delay 30 s ›");
  delayButton.click();
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
  assert.equal(text(delayButton), "Spoiler delay 45 s ›", "the button says the delay");
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
  assert.equal(text(second.querySelector(".ticker__label")), "FBS scores, every 5 min");
  assert.ok(text(sheetBody()).includes("Swampwater Tech State"), "the open Scores sheet follows the ticker");
  assert.ok(!text(container).includes("Biscuit Belt") && !text(document.body).includes("Top 25"));
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
  // Phase 17 #25: before kickoff the sheet is the game sheet with dashes, never a promise to open itself
  assert.ok(!page.includes("opens by itself") && !page.includes("1 hour before"), page);
  assert.ok(page.includes("The sheet fills in as the game is played, 30 s behind the broadcast"), page);
  assert.ok(text(container.querySelector(".strip")).includes("Kickoff"), "the strip shows the kickoff");
  assert.ok(container.querySelector(".live-ticker .ticker"));
  assert.ok(container.querySelector(".remote"), "the remote bar is there before kickoff too");
  container.querySelector(".delay-button").click();  // public release Phase 7b: the slider opens in a side panel
  const slider = document.body.querySelector(".sheet-layer .delay");
  const range = slider.querySelector('input[type="range"]');
  range.value = "45";
  range.dispatchEvent(makeEvent("change"));
  assert.equal(sources.length, 0, "no stream before the window");
  assert.ok(text(container).includes("45 s behind the broadcast"));
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
  assert.ok(text(second.container).includes("The sheet fills in as the game is played"));
  second.view.unmount();
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
  assert.equal(text(container.querySelector("#live-wp .success__source")), "Success rate, play log");
  assert.equal(text(container.querySelector("#live-wp .success__rate--us small")), "29 of 75");
  assert.equal(text(container.querySelector("#live-wp .band__summary")), "Last play: failed");
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
      const cells = container.querySelectorAll("#archive-stats td.txt").map(text);
      assert.ok(cells.includes("PPA per play"), "the feed table is drawn"); // final pass: the Season tables' name
      assert.equal(cells.filter((t) => t === "Success rate").length, 1, "one success-rate row: the team table's, not the feed table's");
    }
    view.unmount();
  }
  route("/api/archive", () => envelope({ games: [null, "x", { gameId: 5, away: "Swampwater Tech", home: "Silver Dollar", usScore: 1, themScore: 0 }], skipped: 1 }));
  const list = createArchiveView({ onStatus: () => {} });
  const container = document.createElement("main");
  document.body.replaceChildren(container);
  list.mount(container);
  await settle();
  assert.ok(text(container).includes("1 game this app watched"));
  assert.ok(!/\b(undefined|NaN|null)\b/.test(text(container)));
  list.unmount();
};

""" + RUNNER_JS
