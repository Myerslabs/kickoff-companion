// The Live sheet (L1 to L7, L11, L12, L13, X7): the remote-control screen on the event stream.
// Pregame (Phase 17 #25): the same sheet as during the game, every value a dash until plays arrive; it
// never switches the app to itself, and the program's cover and notes stay on the Game program. Live: strip, quarter line, team
// stats, win probability with the last play's success, leaders, and the remote bar opening
// everything else in a side sheet. Postgame: the final box, saved to the archive. The delay
// slider is saved on the device and every panel follows it through the stream.
//
// Saturday readiness (Phase 10a): the page is a fixed frame. The ticker, the delay slider, and the
// remote bar are built once per visit, so the crawl, a drag, and a bar scrolled sideways survive
// every play; the rest is redrawn per frame, and an open side sheet is redrawn in place with its
// scroll, filter, and sort. A frame that cannot be drawn leaves the last good screen up. The stream
// has a watchdog, and one function decides the status pill in the top bar from the stream, the display,
// and the feed health the server reports (the stream's hello and ping, and /api/live/status every minute).
// Phase 17 #29: the score strip no longer carries a second copy of the pill; both are pinned, so it showed twice.

import { boxTables } from "../ui/box-columns.js"; // final pass: one copy of the box-score columns; wave 2: one builder, sized
import { screenLock } from "../awake.js";
import { isUs, usLabel, usName, usSchool } from "../identity.js";
import { cover } from "../ui/cover.js";
import { delaySlider } from "../ui/delay-slider.js";
import { DASH, el, flashChanges, fmtDate, fmtDateTime, fmtPct, fmtStat, fmtTime, isNum, obj, records, reducedMotion, replaceWith, snapshotKeys, str, text } from "../ui/dom.js";
import { edgesTable } from "../ui/edges.js";
import { driveList } from "../ui/drive-bar.js";
import { availabilityTable, editorial } from "../ui/editorial.js";
import { lineupBlock } from "../ui/lineups_combined.js";
import { fullName, weatherRow } from "../ui/matchup-card.js";
import { crewText, staffParts } from "../ui/game-staff.js";
import { fillWiki, wikiLink } from "../ui/wiki-links.js";
import { playLog } from "../ui/play-log.js";
import { kickWind } from "../ui/wind.js";
import { openSheet, remoteBar } from "../ui/remote.js";
import { radioStations } from "../ui/radio-stations.js";
import { gameNotesPanel } from "../ui/game-notes.js";
import { inviteBody, loadInvite } from "./invite.js";
import { situationGrid } from "../ui/situation.js";
import { band, note, subhead } from "../ui/states.js";
import { statTableSkeleton } from "../ui/stat-table.js";
import { driveSummaryTable, fourthDownTable, madeOf, splitsTable, teamValueTable, tendencyTable, visitorsTable } from "../ui/in-game-tables.js";
import { playValueTable } from "../ui/play-value.js";
import { strip } from "../ui/strip.js";
import { boxHalves, lastPlayWords, lastPlaysList, scoreCell, stageTools, stripExtras, wpSummary } from "../ui/stage.js";
import { advancedBoxBlock } from "../ui/depth2.js";
import { scoresSummary, scoresTable } from "../ui/scores.js";
import { shotChart, shotCounts } from "../ui/shot-chart.js";
import { ticker } from "../ui/ticker.js";
import { feedEfficiencyTable, teamStatsTable } from "../ui/team-stats.js";
import { successRow, winProbabilityChart } from "../ui/wp-chart.js";
import { getPrefs, savePrefs } from "../prefs.js";
import { noteBuild } from "../build.js";
import { fetchJson } from "./common.js";
import { openPlayer } from "./player.js";

const DEFAULT_DELAY = 30;
const STATUS_POLL_MS = 60 * 1000;
const FALLBACK_POLL_MS = 15 * 1000;
const TICKER_POLL_MS = 60 * 1000;
const ANALYTICS_RETRY_MS = 60 * 1000;
const ANALYTICS_LATE_MS = 60 * 60 * 1000; // owner 2026-10-10: every minute for the first hour after the final, then hourly
const HELD_RETRY_MS = 5 * 1000; // a device still behind the held final asks again until its delay reaches it
const WATCHDOG_MS = 40 * 1000; // the server pings every 15 s when nothing else goes out
const WATCH_TICK_MS = 5 * 1000;
const RETRY_BASE_MS = 5 * 1000;
const RETRY_MAX_MS = 60 * 1000;
const VISITORS_TTL_MS = 10 * 60 * 1000;
const SOURCE_CLOSED = 2; // EventSource.CLOSED: the browser gave up and will not retry by itself
const STATE_ITEMS = new Set(["box", "drives", "plays", "situation", "value", "scores", "splits"]); // side sheets redrawn with every frame
const SYNC_POLL_MS = 4000;
const SYNC_GIVE_UP_MS = 120 * 1000;
const PLANS_URL = "https://collegefootballdata.com/api-tiers";
const FEED_STATES = new Set(["idle", "waiting", "ok", "stale", "no_live_key"]);


/** A player id CFBD sent: its box score and rosters use digit strings ("5132812"), some endpoints numbers. */
export function hasId(value) {
  return (typeof value === "string" && /^\d+$/.test(value.trim())) || (isNum(value) && value > 0);
}

/** "Q2 8:57" style period and clock for a play or a status, or a dash. */
export function periodClock(period, clock) {
  const p = isNum(period) ? (period <= 4 ? `Q${period}` : period === 5 ? "OT" : `${period - 4}OT`) : null;
  const c = clock && typeof clock === "object" && isNum(clock.minutes) && isNum(clock.seconds) ? `${clock.minutes}:${String(clock.seconds).padStart(2, "0")}` : null;
  return [p, c].filter(Boolean).join(" ") || DASH;
}

/** "3rd & 5" from a down and distance, or null. */
export function downText(down, distance) {
  if (!isNum(down) || !isNum(distance)) return null;
  const suffix = { 1: "st", 2: "nd", 3: "rd" }[down] || "th";
  return `${down}${suffix} & ${distance}`;
}

/** The Splits button's hint: the break the game is at, else the quarter. */
export function splitsHint(s) {
  const period = s?.period;
  const clock = s?.clock;
  const zero = clock && typeof clock === "object" && clock.minutes === 0 && clock.seconds === 0;
  if (s?.status === "final") return "final";
  if (zero && period === 2) return "Halftime";
  if (zero && period === 3) return "End Q3";
  return isNum(period) ? periodClock(period, null) : "by quarter";
}

/** The value when it is a plain object, else an empty one: every frame is untrusted. */
/** The value when it is a list, with malformed records skipped; anything else is an empty list. */
// --- pure rules, exported for the tests ----------------------------------------------------------

/** A delay in whole steps of 5 s from 0 to 120, or null when the value is not a number. */
export function clampDelay(value) {
  return isNum(value) ? Math.max(0, Math.min(120, Math.round(value / 5) * 5)) : null;
}

/**
 * The server's feed-health block (contract C1: /api/live/status, the stream's hello and ping),
 * cleaned up, or null when it is missing or malformed so the sheet behaves as it did before it.
 */
export function readFeed(raw) {
  if (!raw || typeof raw !== "object" || !FEED_STATES.has(raw.state)) return null;
  return {
    state: raw.state,
    staleSeconds: isNum(raw.staleSeconds) && raw.staleSeconds >= 0 ? raw.staleSeconds : null,
    consecutiveFailures: isNum(raw.consecutiveFailures) ? raw.consecutiveFailures : 0,
    lastError: typeof raw.lastError === "string" && raw.lastError.trim() ? raw.lastError.trim() : null,
    lastSuccessAt: typeof raw.lastSuccessAt === "string" ? raw.lastSuccessAt : null,
  };
}

/** "Stale 50 s, CFBD not answering" under two minutes, "Stale 3 min, CFBD not answering" after. */
export function staleLabel(seconds) {
  if (!isNum(seconds) || seconds < 0) return "Stale, CFBD not answering";
  const whole = Math.round(seconds);
  return whole < 120 ? `Stale ${whole} s, CFBD not answering` : `Stale ${Math.floor(whole / 60)} min, CFBD not answering`;
}

/** "Final · Sat Oct 10" for a held final (its kickoff's date), plain "Final" otherwise. Exported for the tests. */
export function finalLabel(s) {
  const when = Date.parse(s?.held?.kickoff ?? "");
  return isNum(when) ? `Final · ${fmtDate(s.held.kickoff, "short")}` : "Final";
}

/** Under the score after a final: when it was played, the whole game in the Archive, the next game's program. */
export function finalNote(s) {
  const id = s?.gameId;
  const when = Date.parse(s?.held?.kickoff ?? "");
  const until = Date.parse(s?.held?.until ?? "");
  return el(
    "p",
    { class: "note final-note" },
    `Final${isNum(when) ? `, ${fmtDate(s.held.kickoff)}` : ""}. `,
    isNum(id) || /^\d+$/.test(String(id ?? "")) ? el("a", { href: `#archive=${encodeURIComponent(String(id))}` }, "The whole game in the Archive") : "The game is saved to the Archive",
    ", ",
    el("a", { href: "#program" }, "the next game's program"),
    `.${isNum(until) ? ` In Game shows this final until ${fmtDateTime(s.held.until)}.` : ""}`,
  );
}

/**
 * The one status pill for the strip and the top bar, so the two always agree. In order: a frame
 * that could not be drawn, the stream (down: Offline, or Polling while the fallback poll works),
 * pregame, the final, then CFBD's health from the server's feed block, then the delay.
 * `feedAge` is how many seconds ago the feed block arrived, added to its staleSeconds.
 */
export function livePill({ displayError = false, streamDown = false, polled = false, pregame = false, statusDown = false, final = false, feed = null, feedAge = 0, delay = 0 } = {}) {
  if (displayError) return { kind: "stale", label: "Display error" };
  if (streamDown) return polled ? { kind: "stale", label: "Polling, stream down" } : { kind: "offline", label: "Offline" };
  if (pregame) return statusDown ? { kind: "offline", label: "Offline" } : { kind: "quiet", label: "Pregame" };
  if (final) return { kind: "live", label: typeof final === "string" && final.trim() ? final.trim() : "Final" }; // "Final · Sat Oct 10" while held
  if (feed?.state === "stale") return { kind: "stale", label: staleLabel(isNum(feed.staleSeconds) ? feed.staleSeconds + (isNum(feedAge) ? Math.max(0, feedAge) : 0) : null) };
  if (feed?.state === "no_live_key") return { kind: "offline", label: "No live feed on this key" };
  if (feed?.state === "waiting") return { kind: "quiet", label: "Waiting for CFBD" };
  return isNum(delay) && delay > 0 ? { kind: "delayed", label: `Delayed ${delay} s` } : { kind: "live", label: "Live" };
}

// --- helpers on a state frame --------------------------------------------------------------------

/** The band at the top of the viewport and where its top sits, so a rebuild can put it back there; null at the page's top
    or without a layout engine (the tests). */
function scrollAnchor(frame) {
  if (typeof window === "undefined" || !isNum(window.scrollY) || window.scrollY <= 0 || !frame || typeof frame.querySelectorAll !== "function") return null;
  for (const el of frame.querySelectorAll("section.band[id], [id].band, .band[id]")) {
    if (typeof el.getBoundingClientRect !== "function") return null;
    const rect = el.getBoundingClientRect();
    if (rect.height > 0 && rect.bottom > 0) return { id: el.id, top: rect.top };
  }
  return null;
}

/** Scroll so the anchored band sits where it did before the rebuild (nothing when the band is gone or already there). */
function keepAnchor(anchor) {
  if (!anchor || typeof document === "undefined") return;
  const el = document.getElementById(anchor.id);
  if (!el || typeof el.getBoundingClientRect !== "function") return;
  const shift = el.getBoundingClientRect().top - anchor.top;
  if (Math.abs(shift) > 1 && typeof window.scrollBy === "function") window.scrollBy(0, shift);
}

function abbrOf(school, program) {
  if (!school) return DASH;
  if (isUs(school)) return usLabel();
  for (const side of [program?.us, program?.them]) if (side?.school === school && typeof side.abbreviation === "string" && side.abbreviation) return side.abbreviation;
  return String(school).slice(0, 3).toUpperCase();
}

/**
 * The team the sheet follows: the server's TEAM setting from the state frame, then the program's
 * own side, then the identity the shell loaded (a server from before Phase 11 sends neither).
 */
export function followedTeam(live, program) {
  const fromState = typeof live?.team === "string" && live.team.trim() ? live.team.trim() : null;
  const fromProgram = typeof program?.us?.school === "string" && program.us.school.trim() ? program.us.school.trim() : null;
  return fromState || fromProgram || usSchool();
}

/** Merge the derived box (from plays and the live feed) with the polled box score, which knows pass and rush yards. */
function mergedBox(state, team) {
  const derived = obj(obj(state.box)[team]);
  const polled = obj(obj(state.boxScore)[team]);
  return { ...derived, ...Object.fromEntries(Object.entries(polled).filter(([, v]) => v !== null && v !== undefined)), explosive: derived.explosive, successRate: derived.successRate, successCounts: derived.successCounts, plays: derived.plays || polled.plays, drives: derived.drives };
}


/** The box-score halves step through their rows on their own when longer than their column (freeze wave F5, owner
 *  2026-10-20; the 2026-10-11 board's panes stepped the same way), on the tablet and the board alike. */
const BOARD_STEP_MS = 2200; // one row every couple of seconds
const BOARD_REST_MS = 5000; // the pause at the end before the pane returns to the top

export function createLiveView({ onStatus, board = false } = {}) {
  const savedDelay = Number(getPrefs().delaySeconds ?? DEFAULT_DELAY); // the server's prefs always carry a delay; the device memory that was read here was never reached (freeze wave F1, F15)
  const state = {
    delay: isNum(savedDelay) && savedDelay >= 0 && savedDelay <= 120 ? clampDelay(savedDelay) : DEFAULT_DELAY,
    mode: "pregame", // pregame, live, postgame
    program: null,
    programError: null,
    live: null,
    // the stream and its fallbacks
    source: null,
    fallback: null,
    retryTimer: null,
    retries: 0,
    errors: 0,
    polled: false,
    lastFrameAt: 0,
    pingCapable: false, // the server sends pings (contract C2), so a silent stream is a stuck one
    helloSeen: false, // the current stream said hello, so its hello (not /api/live/status) decides pingCapable
    // the server's game window and its view of CFBD (contract C1)
    window: null,
    feed: null,
    feedAt: 0,
    statusError: null,
    statusTimer: null,
    watchTimer: null,
    displayError: false,
    sheetError: false, // the open side sheet could not be redrawn and shows its last good body
    pillKey: "",
    wakeLock: null,
    wakeLockPending: false,
    ticker: null,
    tickerError: null,
    tickerTimer: null,
    tickerSeq: 0,
    tickerNode: null,
    tickerSig: null,
    analytics: null,
    analyticsError: null,
    analyticsFor: null,
    analyticsBusy: false,
    analyticsTimer: null,
    // the parts built once per visit, and the open side sheet: { id, handle, sorts, filter }
    items: [],
    bar: null,
    strip: null,
    sheet: null,
    slider: null,
    visitors: null,
  };
  let container = null;
  let frame = null;
  let slots = null;
  let tickerHost = null;
  const warned = new Set();
  const warnOnce = (key, message, detail) => {
    if (warned.has(key)) return;
    warned.add(key);
    if (detail === undefined) console.warn(message);
    else console.warn(message, detail);
  };
  const setStatus = (next) => {
    if (typeof onStatus === "function") onStatus(next);
  };
  // The followed team comes from the server (TEAM in .env); read fresh on every use, since the
  // state frame and the program arrive after the sheet is built.
  const usTeam = () => followedTeam(state.live, state.program);
  const usAbbr = () => abbrOf(usTeam(), state.program);
  const usWords = () => (isUs(usTeam()) ? usName() : usTeam());
  const usSide = () => ({ name: usTeam(), abbr: usAbbr() });
  const themSide = () => {
    const s = state.live;
    const school = s ? (s.home === usTeam() ? s.away : s.home) : state.program?.them?.school;
    return { name: school || DASH, abbr: abbrOf(school, state.program) };
  };
  /** A side's heads for the two-team tables (tables wave 2): its key in the state's blocks (the school), the abbreviation
   *  at small, the school at medium, the school and mascot at large (the program's team block knows the mascot). */
  const headsFor = (school, abbr) => {
    const known = typeof school === "string" && school.trim() && school !== DASH ? school.trim() : null;
    const block = [state.program?.us, state.program?.them].find((t) => t && typeof t === "object" && t.school === known);
    return { team: known, abbr, school: known, name: (block && fullName(block)) || known };
  };
  const usHeads = () => headsFor(usTeam(), usAbbr());
  const themHeads = () => headsFor(themSide().name, themSide().abbr);
  const bothHeads = () => ({ us: usHeads(), them: themHeads() });

  // --- the status pill ---------------------------------------------------------------------------

  function pillNow() {
    return livePill({
      displayError: state.displayError || state.sheetError,
      streamDown: state.mode !== "pregame" && state.errors > 0,
      polled: state.polled,
      pregame: state.mode === "pregame",
      statusDown: Boolean(state.statusError),
      final: state.live?.status === "final" ? finalLabel(state.live) : false,
      feed: state.feed,
      feedAge: state.feedAt ? (Date.now() - state.feedAt) / 1000 : 0,
      delay: state.delay,
    });
  }

  /** Push the current pill to the top bar. */
  function refreshPill() {
    if (!container) return;
    const next = pillNow();
    const key = `${next.kind}|${next.label}`;
    if (key !== state.pillKey) {
      state.pillKey = key;
      setStatus(next);
    }
  }

  function takeFeed(raw) {
    const feed = readFeed(raw);
    if (raw !== null && raw !== undefined && !feed) warnOnce("feed-shape", "In Game: the server's feed block was not readable; the pill ignores it.", raw);
    state.feed = feed;
    state.feedAt = Date.now();
  }

  // --- pregame -----------------------------------------------------------------------------------

  /** The next game's program, or a given game's (a held final draws with its own game line, never next week's). Only the
      newest request lands, so a slow answer for another game never overwrites the one the sheet is showing. */
  async function loadProgram(gameId = null) {
    const ticket = (state.programTicket = (state.programTicket || 0) + 1);
    const id = gameId !== null && gameId !== undefined && /^\d+$/.test(String(gameId)) ? String(gameId) : null;
    try {
      const envelope = await fetchJson(id ? `/api/program/${encodeURIComponent(id)}` : "/api/program/next");
      if (ticket !== state.programTicket) return;
      state.program = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
      state.programError = null;
    } catch (error) {
      if (ticket !== state.programTicket) return;
      if (id && String(state.program?.game?.gameId ?? "") !== id) state.program = null; // never another game's line under this one
      state.programError = error?.message || "Could not load the program";
      console.warn(`In Game: the program did not load: ${state.programError}`);
    }
  }

  // --- the held final (owner 2026-10-10: In Game keeps our last final until noon the day after the game) ---------------

  /** Whatever belonged to the game the sheet showed (its post-game numbers, the plays already seen) goes when another game
      takes the sheet over. */
  function resetGame() {
    clearTimeout(state.analyticsTimer);
    clearTimeout(state.heldTimer);
    Object.assign(state, { analytics: null, analyticsFor: null, analyticsError: null, analyticsTimer: null, heldTimer: null, heldFor: null, finalSeenAt: null, seenPlays: null });
  }

  /** The held final at this device's delay (/api/live/final): built from the server's log, so the spoiler rule holds. A
      device still behind the final asks again every few seconds; a final changes nothing, so no stream is opened. */
  async function loadHeld() {
    if (!container || state.heldBusy) return;
    state.heldBusy = true;
    try {
      const envelope = await fetchJson(`/api/live/final?delay=${Math.round(state.delay)}`);
      if (!container) return;
      const data = obj(envelope?.data);
      const gameId = data.gameId;
      if (typeof data.status === "string" && (isNum(gameId) || /^\d+$/.test(String(gameId ?? "")))) {
        if (state.live && String(state.live.gameId) !== String(gameId)) resetGame();
        state.live = data;
        state.heldFor = gameId;
        state.mode = "postgame";
        if (String(state.program?.game?.gameId ?? "") !== String(gameId)) await loadProgram(gameId);
        if (!container) return;
        clearTimeout(state.heldTimer);
        state.heldTimer = data.status === "final" ? null : setTimeout(() => { state.heldTimer = null; loadHeld(); }, HELD_RETRY_MS);
        render();
      } else if (data.waiting === true) {
        clearTimeout(state.heldTimer);
        state.heldTimer = setTimeout(() => { state.heldTimer = null; loadHeld(); }, HELD_RETRY_MS);
      }
    } catch (error) {
      if (container) console.warn(`In Game: the held final did not load: ${error?.message || error}`);
    } finally {
      state.heldBusy = false;
    }
  }

  /** A replay that finished on this sheet's game: its final stays up (nothing is held for a replay). */
  function replayed(data) {
    const r = data?.replay && typeof data.replay === "object" ? data.replay : null;
    return Boolean(r && r.finished === true && state.live && String(r.gameId ?? "") === String(state.live.gameId ?? "") && (state.heldFor === null || state.heldFor === undefined));
  }

  /** The sheet shows a game whose time has passed: the server's next window is another game's. */
  function sheetGameOver() {
    return Boolean(state.live && state.window && String(state.window.gameId ?? "") !== String(state.live.gameId ?? ""));
  }

  /** The hold is over (noon the day after the game) or the final belongs to no one now: the next game's pregame sheet; the
      final lives on in the Archive. */
  async function letGo() {
    disconnect();
    resetGame();
    state.live = null;
    state.mode = "pregame";
    state.errors = 0;
    await loadProgram();
    if (container) render();
  }

  // --- the ticker (L10), one node per visit --------------------------------------------------------

  async function loadTicker() {
    const seq = ++state.tickerSeq; // a slow answer for an older delay must not win over a newer one
    try {
      const envelope = await fetchJson(`/api/ticker?delay=${state.delay}`);
      if (seq !== state.tickerSeq) return;
      state.ticker = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
      state.tickerError = null;
    } catch (error) {
      if (seq !== state.tickerSeq) return;
      const message = error?.message || "Could not load the ticker";
      if (message !== state.tickerError) console.warn(`In Game: the ticker did not load: ${message}`);
      state.tickerError = message;
    }
    if (!container) return;
    updateTicker();
    if (state.sheet?.id === "scores") refreshOpenSheet();
  }

  function tickerGames(includeUs = false) {
    const national = state.ticker?.mode !== "mine"; // Phase 16 wave 3 (6A): stars only when the line shows every game
    return records(state.ticker?.games)
      .filter((g) => includeUs || !g.isUs)
      .map((g) => ({ ...g, star: national && g.isMine === true && !g.isUs, detail: g.status === "pre" ? (g.startTimeTbd ? "TBD" : fmtTime(g.kickoff)) : g.detail }));
  }

  /** "6 live" when games are under way, else what the list holds (L-14). */
  function scoresHint() {
    const games = records(state.ticker?.games);
    const live = games.filter((g) => g.status === "live").length;
    if (live) return `${live} live`;
    return state.ticker?.mode === "mine" ? "your teams" : "every FBS game";
  }

  function tickerEmpty() {
    return state.ticker?.mode === "mine" ? "None of your other teams play right now." : "No other games right now.";
  }

  function tickerLabel() {
    // Public release Phase 5b: the My teams ticker names itself; the schedule's cadence comes from the server (5 or 20 min).
    // freeze wave F5 (owner 2026-10-20): no "FBS scores" label, everyone knows a ticker; the My teams one still names itself
    const base = state.ticker?.mode === "mine" ? "My teams" : "";
    const minutes = isNum(state.ticker?.refreshMinutes) ? state.ticker.refreshMinutes : 5;
    return base && state.ticker?.source === "games" ? `${base}, every ${minutes} min` : base;
  }

  /**
   * One ticker node per visit. New games are swapped into the running line only when the games or
   * the label changed, so the crawl never restarts; a ticker without setGames is replaced whole.
   */
  function updateTicker() {
    if (!tickerHost) return;
    const games = tickerGames();
    const label = tickerLabel();
    const signature = JSON.stringify([label, games]);
    if (state.tickerNode && signature === state.tickerSig) return;
    if (state.tickerNode && typeof state.tickerNode.setGames === "function") {
      state.tickerNode.setGames(games, label, tickerEmpty());
      state.tickerSig = signature;
      return;
    }
    const next = ticker({ games, id: "live", label, emptyText: tickerEmpty() });
    const old = state.tickerNode;
    tickerHost.replaceChildren(next);
    if (old && typeof old.destroy === "function") old.destroy();
    state.tickerNode = next;
    state.tickerSig = signature;
  }

  function scoresBand() {
    const games = tickerGames(true);
    // Phase 16 wave 3: one table for the sheet's life, patched each minute so only the changed scores flash
    if (state.scoresTable) state.scoresTable.update(games);
    else state.scoresTable = scoresTable({ games, emptyText: state.tickerError ? `${state.tickerError}.` : "No FBS games on this week's slate." });
    const table = state.scoresTable;
    return band({ title: "Around the country", collapsible: false, summary: state.ticker?.source === "games" ? "scores from the schedule; live scores show with a Tier 1 or bigger key" : scoresSummary(games), body: () => el("div", {}, table, typeof state.ticker?.modeNote === "string" && state.ticker.modeNote ? el("p", { class: "note" }, state.ticker.modeNote) : null, el("p", { class: "note" }, state.ticker?.mode === "mine" ? "Your primary and secondary teams' games. Our line follows your spoiler delay. Switch to every game in Settings." : "Scores only. Our line follows your spoiler delay.")) });
  }

  // --- post-game analytics (L8, L9) --------------------------------------------------------------------

  const analyticsComplete = () => Boolean(state.analytics?.winProbability?.available && state.analytics?.ppa?.available);
  /** The post-game numbers of the game on the sheet, never another game's (a sheet that outlived its game). */
  const gameAnalytics = (s) => (state.analytics && String(state.analyticsFor ?? "") === String(s?.gameId ?? "") ? state.analytics : null);

  /** Every minute for the first hour after the final, then hourly (owner 2026-10-10). The held final's time stamp, else
      the moment this sheet first showed the final. */
  function analyticsWait(s) {
    const at = Date.parse(s?.held?.finalAt ?? "");
    if (!isNum(state.finalSeenAt)) state.finalSeenAt = Date.now();
    const since = Date.now() - (isNum(at) ? at : state.finalSeenAt);
    return since < ANALYTICS_LATE_MS ? ANALYTICS_RETRY_MS : ANALYTICS_LATE_MS;
  }
  const retryWords = (s) => (analyticsWait(s) >= ANALYTICS_LATE_MS ? "every hour" : "every minute");

  /**
   * After the final, fetch CFBD's post-game win probability and play value, then once a minute
   * until both are posted. Every render calls this; a scheduled retry means "not yet", so a
   * render never starts a second fetch of its own.
   */
  async function maybeLoadAnalytics() {
    const s = state.live;
    if (!container || !s?.gameId || s.status !== "final" || state.analyticsBusy) return;
    if (state.analyticsFor === s.gameId && (analyticsComplete() || state.analyticsTimer)) return;
    state.analyticsBusy = true;
    state.analyticsFor = s.gameId;
    try {
      const envelope = await fetchJson(`/api/games/${encodeURIComponent(s.gameId)}/analytics`);
      state.analytics = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
      state.analyticsError = null;
    } catch (error) {
      state.analyticsError = error?.message || "Could not load the analytics";
      console.warn(`In Game: the post-game analytics did not load: ${state.analyticsError}`);
    }
    state.analyticsBusy = false;
    if (!container) return;
    clearTimeout(state.analyticsTimer);
    state.analyticsTimer = analyticsComplete()
      ? null
      : setTimeout(() => {
          state.analyticsTimer = null;
          maybeLoadAnalytics();
        }, analyticsWait(s));
    render();
  }

  /**
   * The live feed's own efficiency numbers per team (PPA, explosiveness, the down splits), when the document carries them:
   * FEED_ROWS on the two-team kit with the bar (ui/team-stats.js feedEfficiencyTable, one builder with the Archive). The
   * overall success rate is not repeated here: the success row shows it.
   */
  function feedStatsTable(s) {
    const table = feedEfficiencyTable({ feed: s.feedStats, ...bothHeads() });
    return table ? el("div", {}, subhead("Efficiency, from the live feed"), table) : null;
  }

  function wpBlock(s, usHome, pregame) {
    const wp = gameAnalytics(s)?.winProbability;
    const postGame = wp?.available && Array.isArray(wp.series) ? wp.series : [];
    // In the game: CFBD's scoreboard readings, released on the same delay as the plays (Phase 11).
    const live = s.liveWinProbability && Array.isArray(s.liveWinProbability.series) ? s.liveWinProbability.series : [];
    const series = postGame.length ? postGame : live;
    const chart = winProbabilityChart({ series, homeIsUs: usHome, usAbbr: usAbbr(), pregame, final: s.status === "final", plays: records(s.plays) });
    let why;
    if (postGame.length) why = `${postGame.length} plays from CFBD's post-game model.`;
    else if (live.length && s.status !== "final") why = `${live.length} ${live.length === 1 ? "reading" : "readings"} from CFBD's scoreboard, about one a minute while this sheet is open, ${state.delay} s behind like every panel. The play-by-play chart posts after the final.`;
    else if (live.length) why = `${live.length} in-game readings from CFBD's scoreboard; the play-by-play chart replaces them once CFBD posts it.`;
    else if (s.status === "final") why = gameAnalytics(s) ? wp?.note || `CFBD has not posted the win probability yet; the sheet checks again ${retryWords(s)}.` : state.analyticsError ? `${state.analyticsError}. Retrying ${retryWords(s)}.` : "Loading the post-game win probability.";
    else why = isNum(pregame) ? "No in-game reading yet; this is the pregame number. Readings from CFBD's scoreboard start once the game is under way." : "No win probability for this game yet.";
    return el("div", {}, chart, el("p", { class: "note" }, why));
  }

  function ppaBand(s) {
    const a = gameAnalytics(s);
    const p = a?.ppa;
    // wave 2: the players' tables are the shared play value kit (ui/play-value.js), sized like the Pre-Game Program's
    const side = (title, rows, them) => el("div", {}, subhead(title, { team: them ? themSide().name : usTeam(), side: them ? "them" : "us" }), rows.length ? playValueTable(rows, { onTap: (row) => openPlayer(row.playerId, { ...row, isUs: !them }), caption: `${title}, PPA per play` }) : note("No player values yet."));
    let body;
    if (s.status !== "final") body = note("Per-play PPA shows in the play log when the feed carries it. Player values post after the final.");
    else if (!a) body = note(state.analyticsError ? `${state.analyticsError}. Retrying ${retryWords(s)}.` : "Loading play value.");
    else if (!p?.available) body = note(p?.note || `CFBD has not posted play value for this game yet; the sheet checks again ${retryWords(s)}.`);
    else body = el("div", {}, teamValueTable(p.teams, bothHeads()), el("div", { class: "twocol" }, side(usWords(), records(p.players?.us), false), side(themSide().name, records(p.players?.them), true)));
    const value = band({ title: "Play value", collapsible: false, summary: "PPA per play", body: () => body });
    if (s.status !== "final" || !a?.advancedBox) return value;
    // Phase 13: after the final, CFBD's advanced box score under the play value; wave 2: the schools and mascots head its
    // two teams' table at large, and a player's row opens his card (as on the Pre-Game Program)
    const us = usHeads();
    const them = themHeads();
    const box = () => advancedBoxBlock(a.advancedBox, { us: usTeam(), them: themSide().name, usAbbr: usAbbr(), themAbbr: themSide().abbr, usName: us.name || undefined, themName: them.name || undefined, onPlayer: (row) => (hasId(row.playerId) ? openPlayer(row.playerId, { ...row, boardLabel: "PPA per play", value: fmtStat(row.ppa, "+2f") }) : null) });
    return [value, band({ id: "live-advanced-box", title: "Advanced box score", collapsible: false, foldable: true, summary: "by quarter, players' value", body: box })];
  }

  /**
   * The live state before the first play (Phase 17 #25): the shape the server's state has at kickoff, with
   * every value empty, so the pregame sheet is the game sheet showing dashes rather than a second program.
   */
  function emptyLive(p) {
    const g = obj(p.game);
    const ours = followedTeam(null, p);
    const theirs = text(obj(p.them).school);
    const home = g.homeIsUs === false ? theirs : ours;
    const away = g.homeIsUs === false ? ours : theirs;
    return {
      gameId: g.gameId ?? null, mode: "live", status: "pre", home, away,
      homeScore: null, awayScore: null, period: null, clock: null, possession: null, down: null, distance: null, yardsToGoal: null,
      homeLineScores: null, awayLineScores: null, boxScore: null, feedStats: null, playerStats: null, playerStatsSource: {}, liveWinProbability: null,
      plays: [], drives: [], splits: { periods: [], teams: {}, notes: [] }, tendencies: {}, shotChart: {},
    };
  }

  function kickoffLabel(g) {
    if (!g.kickoff) return "Kickoff TBD";
    return g.startTimeTbd ? `Kickoff ${fmtDate(g.kickoff, "short")}, time TBD` : `Kickoff ${fmtDate(g.kickoff, "short")} ${fmtTime(g.kickoff)}`;
  }

  function pregameParts() {
    const p = state.program;
    if (!p || !p.game || typeof p.game !== "object") { // final pass: an answer with no game (the season is over) is the same as none
      const failed = Boolean(state.programError);
      const message = failed ? `${text(state.programError)}. The sheet tries again every minute.` : "No game of ours is on the schedule ahead. The sheet checks again every minute.";
      return { top: band({ title: "In Game", collapsible: false, state: { status: failed ? "error" : "empty", message }, errorLead: "Could not load the next game." }) };
    }
    const g = obj(p.game);
    const s = emptyLive(p);
    const stripEl = stripFor(s, kickoffLabel(g));
    const line = `${kickoffLabel(g)}. The sheet fills in as the game is played, ${state.delay} s behind the broadcast; the Spoiler delay button changes that.`;
    return {
      top: [stripEl, essentials(s)],
      strip: stripEl,
      middle: [stageFor(s)],
      bottom: null,
      items: remoteItems(s),
      state: s,
      boardNote: line, // the board's spoiler-delay bar before kickoff
    };
  }

  function delayLabel() {
    return `Spoiler delay ${state.delay} s ›`;
  }

  /** The button in the panel row (wave F5): short, the sheet says the rest. */
  function shortDelayLabel() {
    return `Delay ${state.delay} s`;
  }

  /** The delay slider and Sync to my TV in a side panel, opened from the Delay button (public release Phase 7b). */
  function openDelaySheet() {
    if (state.delaySheet) return;
    const handle = openSheet({
      title: "Spoiler delay",
      body: () => delayBlock(),
      onClose: () => {
        if (state.slider && typeof state.slider.flush === "function") state.slider.flush(); // a nudge still settling is saved
        if (state.delaySheet === handle) state.delaySheet = null;
      },
    });
    state.delaySheet = handle;
  }

  function delayBlock() {
    state.slider = delaySlider({ value: state.delay, onChange: (value) => setDelay(value) });
    return el("div", {}, state.slider, el("p", { class: "note" }, "Saved for every device. Audio from the radio cannot be delayed; the delay applies to every panel here and to our line in the ticker."), syncBlock());
  }

  function setDelay(value) {
    const next = clampDelay(value);
    if (next === null || next === state.delay) return; // nothing changed: no reconnect
    state.delay = next;
    if (state.tools) state.tools.setDelayLabel(shortDelayLabel());
    savePrefs({ delaySeconds: next }).catch((error) => console.warn(`In Game: the delay is kept on this device only; the server did not save it: ${error?.message || error}`));
    if (!container) return; // a nudge that settled after the sheet closed is saved, nothing more
    if (state.heldFor !== null && state.heldFor !== undefined) loadHeld(); // the held final at the new delay (the spoiler rule), no stream
    else if (state.mode !== "pregame") connect();
    else render(); // the pregame line repeats the delay
    loadTicker();
    refreshPill();
  }

  // --- the game line (public release Phase 7b) ---------------------------------------------------------

  /** Venue, weather and the TV crew on one line, then each team's head coach and coordinators: at a glance
   *  under the score. The crew and the staffs come from the notes (the Game program's prompt); a missing one
   *  says where to add it. */
  function gameInfo(p) {
    if (!p || typeof p !== "object") return null;
    const g = obj(p.game);
    const n = obj(p.notes);
    const w = obj(p.weather);
    const name = (value) => (typeof value === "string" && value.trim() ? value.trim() : null);
    const venueName = name(g.venue);
    const venue = venueName ? wikiLink("stadium", { venue: venueName }, venueName) : null; // Phase 19: the stadium's own page
    const weatherText = w.available && isNum(w.tempF) ? `${Math.round(w.tempF)}°F${isNum(w.windMph) ? `, wind ${Math.round(w.windMph)} mph` : ""}${w.dome ? ", indoors" : ""}` : null;
    const weather = weatherText ? el("span", {}, weatherText, " ", kickWind({ windMph: w.available ? w.windMph : null, indoors: w.dome === true })) : null; // Phase 17 #6
    const network = name(obj(n.broadcast).network) || name(g.tv);
    const crew = crewText(n, g);
    const staff = (side, label, school) => {
      const words = staffParts(n, side, school);
      return words.length ? el("span", { class: "game-info__staff" }, el("b", {}, label), " ", ...words) : null;
    };
    const usStaff = staff("us", usAbbr(), usTeam());
    const themStaff = staff("them", themSide().abbr, themSide().name);
    const missing = [crew ? null : "the TV crew", usStaff || themStaff ? null : "the coaches"].filter(Boolean);
    return el(
      "div",
      { class: "game-info", "aria-label": "Game details" },
      el("div", { class: "game-info__line" }, [venue, weather, crew ? el("span", {}, el("b", {}, "TV "), crew) : network ? `on ${network}` : null].filter(Boolean).flatMap((part, i) => (i ? [el("span", { class: "game-info__dot", "aria-hidden": "true" }, " · "), part] : [part]))),
      usStaff || themStaff ? el("div", { class: "game-info__line" }, usStaff, usStaff && themStaff ? el("span", { class: "game-info__dot", "aria-hidden": "true" }, "  |  ") : null, themStaff) : null,
      missing.length ? el("p", { class: "game-info__hint" }, `Add ${missing.join(" and ")} with the notes prompt on the `, el("a", { href: "#program" }, "Pre-Game Program"), ".") : null,
    );
  }

  // --- live and postgame ---------------------------------------------------------------------------

  function stripFor(s, kickoffText = null) {
    const usHome = s.home === usTeam();
    const usPts = usHome ? s.homeScore : s.awayScore;
    const themPts = usHome ? s.awayScore : s.homeScore;
    const possession = s.possession === usTeam() ? "us" : s.possession ? "them" : null;
    // freeze wave F5: the win probability as a percentage and the last play ride on the strip (owner 2026-10-20)
    const extras = stripExtras({ wp: wpSummary(s, { usHome, pregame: state.program?.pregame?.usWinProbability }), lastPlay: s.status === "pre" ? null : lastPlayWords(s.lastPlay, { abbr: (school) => abbrOf(school, state.program) }), usAbbr: usAbbr() });
    return strip({ extras, us: { abbr: usAbbr(), points: usPts, timeouts: null }, them: { abbr: themSide().abbr, points: themPts, timeouts: null }, status: s.status === "final" ? "final" : s.status === "pre" ? "pre" : "live", period: s.period, clock: s.clock, possession, down: s.down, distance: s.distance, yardsToGoal: s.yardsToGoal, kickoffText, pill: null, sticky: true });
  }

  // --- Phase 12: splits, tendencies, drive summary, fourth down, sync ---------------------------------

  // Wave 2 (owner 2026-10-10): the tables are ui/in-game-tables.js, each sized by its own box (the side sheet, a phone,
  // a board pane alike); the two-team ones are the shared kit with the tug bar (rule 9)
  function splitsBand(s) {
    const splits = obj(s.splits);
    const notes = Array.isArray(splits.notes) ? splits.notes.filter((n) => typeof n === "string" && n) : [];
    const has = Array.isArray(splits.periods) && splits.periods.length > 0;
    const us = usTeam();
    const them = themSide().name;
    if (!has) return band({ title: "Splits", collapsible: false, state: { status: "empty", message: "Splits appear after the first snap." } });
    return [
      band({ title: "Quarter by quarter", collapsible: false, summary: "from the play log", body: () => el("div", {}, notes.length ? el("ul", { class: "note-list" }, notes.map((n) => el("li", {}, n))) : note("Nothing stands out between the quarters yet."), subhead(usWords(), { team: usTeam(), side: "us" }), splitsTable(splits, us, { caption: `${usWords()} by quarter` }), subhead(text(them), { team: them, side: "them" }), splitsTable(splits, them, { caption: `${text(them)} by quarter` })) }),
      band({ title: "Tendencies by situation", collapsible: false, summary: "run or pass, and success", body: () => el("div", {}, subhead(usWords(), { team: usTeam(), side: "us" }), tendencyTable(s.tendencies, us, { caption: `${usWords()} by situation` }), subhead(text(them), { team: them, side: "them" }), tendencyTable(s.tendencies, them, { caption: `${text(them)} by situation` }), note("Passing downs: 2nd and 8 or more, 3rd or 4th and 5 or more (CFBD's tags when the feed sends them). Success is CFBD's.")) }),
    ];
  }

  function fourthDownBlock(s) {
    const f = s.fourthDown;
    const table = fourthDownTable(f);
    if (!table) return null;
    const offense = s.possession === usTeam() ? usAbbr() : s.possession ? themSide().abbr : DASH;
    return el(
      "div",
      { class: "fourth-down" },
      subhead(`${offense} ${downText(f.down, f.distance) || "4th down"}, ${text(f.yardsToGoal)} to goal: go or kick?`),
      table,
      note(`Going for it beats the ${f.best === "fieldGoal" ? "field goal" : "punt"} when the chance to convert is above ${fmtPct(f.breakEven, 1)}. Going for it: expected points if it converts and if it fails. From CFBD's expected points; a conversion counts as gaining exactly the line to gain.`),
    );
  }

  // Sync to my TV: tap on a snap, pick which snap it was, the delay is set from the measurement.
  function syncBlock() {
    const host = el("div", { class: "sync" });
    const draw = () => {
      const sy = state.sync || { phase: "idle" };
      const intro = el("p", { class: "note" }, "Tap the button at the moment you see a snap on TV. The app measures how far your TV runs behind and sets the delay so plays show up after the TV shows them.");
      const button = el("button", { class: "btn", type: "button", disabled: sy.phase === "waiting" ? true : null, onclick: () => startSync() }, sy.phase === "waiting" ? "Listening for that snap…" : "Sync to my TV");
      const parts = [intro, button];
      if (sy.phase === "waiting" || sy.phase === "choose") {
        const candidates = records(sy.candidates);
        if (candidates.length) {
          parts.push(el("p", { class: "note" }, "Which snap did you see? Only the down and the spot are shown, never the result."));
          parts.push(
            el(
              "div",
              { class: "sync__choices" },
              candidates.map((c) =>
                el(
                  "button",
                  { class: "btn btn--quiet", type: "button", onclick: () => applySync(c, sy.feed) },
                  `${periodClock(c.period, c.clock)} · ${c.offense === usTeam() ? usAbbr() : themSide().abbr} ${downText(c.down, c.distance) || ""}${isNum(c.yardsToGoal) ? `, ${c.yardsToGoal} to goal` : ""} → ${isNum(c.suggestedDelay) ? `${c.suggestedDelay} s` : DASH}`,
                ),
              ),
            ),
          );
        }
        if (sy.note) parts.push(note(text(sy.note)));
      }
      if (sy.phase === "done" || sy.phase === "error") parts.push(note(text(sy.message)));
      host.replaceChildren(...parts);
    };
    state.syncDraw = draw;
    draw();
    return host;
  }

  function stopSync() {
    if (state.syncTimer) clearTimeout(state.syncTimer);
    state.syncTimer = null;
  }

  async function startSync() {
    stopSync();
    state.sync = { phase: "waiting", candidates: [], note: "Waiting for that snap to reach the feed (usually under a minute).", startedAt: Date.now() };
    state.syncDraw?.();
    try {
      const first = await fetchJson("/api/live/sync");
      const data = obj(first?.data);
      if (typeof data.tapAt !== "string") throw new Error(text(data.note) || "The server did not stamp the tap");
      state.sync.tapAt = data.tapAt;
      pollSync();
    } catch (error) {
      state.sync = { phase: "error", message: `Sync failed: ${error?.message || error}. Try again on the next snap.` };
      state.syncDraw?.();
    }
  }

  async function pollSync() {
    const sy = state.sync;
    if (!sy || !sy.tapAt || !container) return;
    try {
      const envelope = await fetchJson(`/api/live/sync?tapAt=${encodeURIComponent(sy.tapAt)}`);
      if (state.sync !== sy) return; // a newer tap replaced this one
      const data = obj(envelope?.data);
      sy.candidates = records(data.candidates);
      sy.feed = obj(data.feedLatency);
      sy.note = data.note || null;
      if (sy.candidates.length) sy.phase = "choose";
    } catch (error) {
      sy.note = `Could not ask the server: ${error?.message || error}. Still trying.`;
    }
    state.syncDraw?.();
    if (state.sync !== sy || sy.phase === "done") return;
    if (Date.now() - sy.startedAt > SYNC_GIVE_UP_MS) {
      if (!sy.candidates.length) {
        state.sync = { phase: "error", message: "That snap never reached the feed. Try again on another snap." };
        state.syncDraw?.();
      }
      return;
    }
    if (sy.candidates.length < 3) state.syncTimer = setTimeout(pollSync, SYNC_POLL_MS);
  }

  function applySync(candidate, feed) {
    stopSync();
    const value = clampDelay(candidate?.suggestedDelay);
    if (value === null) return;
    if (state.slider && typeof state.slider.setDelay === "function") state.slider.setDelay(value); // the slider shows the new value
    setDelay(value);
    const lag = isNum(candidate.tvLagSeconds) ? `your TV shows a snap about ${Math.round(candidate.tvLagSeconds)} s after it happens` : "your TV lag was measured";
    const fast = isNum(feed?.fastSeconds) ? `; the feed brings plays ${Math.round(feed.fastSeconds)} s after the snap at its fastest (median ${Math.round(feed.medianSeconds)} s)` : "";
    state.sync = { phase: "done", message: `Delay set to ${value} s: ${lag}${fast}. Sync again whenever the TV stream changes.` };
    state.syncDraw?.();
  }

  /** Where the leaders come from: the box score, or the play-by-play until CFBD posts it (Phase 11). */

  /**
   * The shot chart band. On the sheet it switches between passes and runs (the switch redraws the chart alone, in place:
   * a whole-sheet render replaced every band under the reader and threw the page back to the top, owner bug 2026-10-10).
   * fixed: one view and no switch, for the board, which shows the pass chart and the run chart side by side (owner mock
   * 2026-10-11).
   */
  function chartBand(s, { view = null, fixed = false, id = "live-chart" } = {}) {
    const shown = () => (fixed ? view : state.chartView);
    return band({
      id,
      title: `Shot chart: ${usAbbr()} offense`,
      kind: "neutral",
      area: "chart",
      summary: view === "both" ? shotCounts(obj(s.shotChart)[usTeam()]) : shown() === "runs" ? "runs by lane" : "passes by zone",
      state: obj(obj(s.shotChart)[usTeam()]).passes ? { status: "ready" } : { status: "empty", message: "The chart fills in with the first pass or run." },
      body: () => {
        const host = el("div", { class: "shot-chart-host" });
        const draw = () => {
          host.replaceChildren(
            shotChart({
              chart: obj(s.shotChart)[usTeam()],
              view: shown(),
              team: usWords(),
              fixed,
              onView: fixed
                ? undefined
                : (next) => {
                    state.chartView = next;
                    draw();
                    const summary = host.closest(".band")?.querySelector(".band__summary");
                    if (summary) summary.textContent = next === "runs" ? "runs by lane" : "passes by zone";
                  },
            }),
          );
        };
        draw();
        return host;
      },
    });
  }

  /** Team stats, with the live feed's efficiency lines under it (the Box score panel carries it since wave F5). */
  function teamStatsBand(s) {
    const usBox = mergedBox(s, usTeam());
    const themBox = mergedBox(s, themSide().name);
    const statsNote = s.boxScore ? "Yards, downs, and turnovers from the box score; plays from the play log; success rate from CFBD." : "From the play log until CFBD posts the box score; success rate from CFBD.";
    return band({ id: "live-stats", title: "Team stats", kind: "neutral", collapsible: false, summary: `${text(usBox.totalYards)} to ${text(themBox.totalYards)} yds`, state: s.counts?.plays ? { status: "ready", updatedText: statsNote } : { status: "empty", message: "Team stats appear after the first play." }, body: () => el("div", {}, teamStatsTable({ us: { ...usHeads(), box: usBox }, them: { ...themHeads(), box: themBox } }), feedStatsTable(s)) }); // wave 2: the schools and mascots head it at large
  }

  /** The win probability chart with the last play's success and the fourth-down call (the Situation panel since wave F5). */
  function winProbabilityBand(s) {
    const usHome = s.home === usTeam();
    const usBox = mergedBox(s, usTeam());
    const themBox = mergedBox(s, themSide().name);
    const pregame = state.program?.pregame?.usWinProbability;
    const lastPlay = s.lastPlay && typeof s.lastPlay === "object" ? s.lastPlay : null;
    const judged = typeof lastPlay?.success === "boolean";
    // CFBD's own team rate carries no counts; a server from before Phase 10a counted the play log itself.
    const rateSource = isNum(usBox.successCounts?.judged) || isNum(themBox.successCounts?.judged) ? "play log" : "CFBD";
    return band({
      id: "live-wp",
      title: "Win probability",
      kind: "neutral",
      collapsible: false,
      summary: judged ? `Last play: ${lastPlay.success ? "success" : "failed"}` : "",
      body: () => el("div", {}, wpBlock(s, usHome, pregame), fourthDownBlock(s), successRow({ play: lastPlay, offenseAbbr: lastPlay?.offense === usTeam() ? usAbbr() : themSide().abbr, us: { abbr: usAbbr(), rate: usBox.successRate, counts: usBox.successCounts }, them: { abbr: themSide().abbr, rate: themBox.successRate, counts: themBox.successCounts }, source: rateSource })),
    });
  }

  /**
   * In Game on one screen (freeze wave F5, the owner's mock of 2026-10-20): the box score with both teams side by side,
   * then the last five plays, Score by quarter with the drive lines, and the shot chart with the passes over the line of
   * scrimmage and the runs under it. The strip above it carries the percentage and the last play; the panels hold the rest.
   */
  function stageFor(s) {
    const usHome = s.home === usTeam();
    const us = usSide();
    const them = themSide();
    const lines = obj(s.playerStats);
    const haveLines = Object.values(lines).some((cats) => Object.values(obj(cats)).some((rows) => records(rows).length));
    const fromPlays = Object.values(obj(s.playerStatsSource)).includes("plays");
    return el(
      "div",
      { class: "stage" },
      band({ id: "live-box", title: "Box score", kind: "neutral", collapsible: false, summary: haveLines ? (fromPlays ? "from the play-by-play until CFBD posts the box score" : "both teams") : "", state: haveLines ? { status: "ready" } : { status: "empty", message: "Player lines appear after the first pass or run." }, body: () => boxHalves({ us, them, usTables: boxPanel(s, usTeam(), false), themTables: boxPanel(s, themSide().name, true) }) }),
      el(
        "div",
        { class: "stage__row" },
        band({ id: "live-plays", title: "Last 5 plays", kind: "neutral", collapsible: false, summary: records(s.plays).length ? "newest first" : "", body: () => lastPlaysList({ plays: records(s.plays), us, them, limit: 5 }) }),
        band({ id: "live-score", title: "Score by quarter", kind: "neutral", collapsible: false, summary: s.status === "final" ? "Final" : "", body: () => scoreCell({ s, us, them, usHome }) }),
        chartBand(s, { view: "both", fixed: true }),
      ),
    );
  }

  /** The essentials under the strip on a phone or an iPad held upright (the stage hides them): the last play and the percentage, large. */
  function essentials(s) {
    const usHome = s.home === usTeam();
    const wp = wpSummary(s, { usHome, pregame: state.program?.pregame?.usWinProbability });
    const words = s.status === "pre" ? null : lastPlayWords(s.lastPlay, { abbr: (school) => abbrOf(school, state.program) });
    const pct = isNum(wp.pct) ? wp.pct : wp.kickoff;
    if (!words && !isNum(pct)) return null;
    const kick = isNum(wp.pct) && isNum(wp.kickoff) ? `, ${fmtPct(wp.kickoff)} at kickoff` : isNum(wp.pct) ? "" : " at kickoff";
    return el(
      "div",
      { class: "stage-essentials" },
      words ? [el("span", { class: "stage-essentials__label" }, "Last play"), el("span", { class: "stage-essentials__words", dataset: { k: "ess:last" } }, words)] : null,
      isNum(pct) ? el("span", { class: "stage-essentials__wp" }, el("b", { dataset: { k: "ess:wp" } }, fmtPct(pct)), `${usAbbr()} to win${kick}`) : null,
    );
  }

  // --- the side sheets ---------------------------------------------------------------------------

  /** One team's box score (wave 2: the shared sized builder, ui/box-columns.js), each category keeping the order the
   *  reader picked while the sheet is open. */
  function boxPanel(s, team, them) {
    const side = them ? "them" : "us";
    return boxTables({
      categories: obj(obj(s.playerStats)[team]),
      emptyText: "Player lines appear after the first pass or run.",
      fromPlays: obj(s.playerStatsSource)[team] === "plays",
      sort: (name) => state.sheet?.sorts[`${side}:${name}`] || null,
      onSort: (name, order) => {
        if (state.sheet) state.sheet.sorts[`${side}:${name}`] = order;
      },
      onTap: (row) => (hasId(row.playerId) ? openPlayer(row.playerId, { ...row, isUs: !them }) : null),
    });
  }

  function remoteItems(s) {
    const p = state.program || {};
    const usBox = mergedBox(s, usTeam());
    const themBox = mergedBox(s, themSide().name);
    const plays = records(s.plays);
    const drives = records(s.drives);
    const edges = records(p.edges);
    const weather = obj(p.weather);
    const availability = records(p.notes?.availability);
    return [
      { id: "box", label: "Box score", hint: "both teams", body: () => [teamStatsBand(s), band({ title: usWords(), kind: "us", collapsible: false, body: () => boxPanel(s, usTeam(), false) }), band({ title: themSide().name, kind: "them", collapsible: false, body: () => boxPanel(s, themSide().name, true) })] }, // wave F5: Team stats left the page for this panel
      { id: "drives", label: "Drives", hint: `${isNum(s.counts?.drives) ? s.counts.drives : 0} drives`, body: () => band({ title: "Drives", collapsible: false, body: () => (drives.length ? el("div", {}, driveSummaryTable(s.driveSummary, bothHeads()), driveList({ drives, us: usSide(), them: themSide(), currentId: s.currentDriveId ?? null })) : note("Drives appear after kickoff.")) }) },
      { id: "splits", label: "Splits", hint: splitsHint(s), body: () => splitsBand(s) },
      { id: "plays", label: "Plays", hint: `${isNum(s.counts?.plays) ? s.counts.plays : 0} plays`, body: () => band({ title: "Play by play", collapsible: false, body: () => (plays.length ? playLog({ plays, us: usSide(), them: themSide(), freshIds: freshPlays(plays), filter: state.sheet?.filter || "all", onFilter: (id) => { if (state.sheet) state.sheet.filter = id; } }) : note("Plays appear after kickoff.")) }) },
      { id: "situation", label: "Situation", hint: `3rd ${text(usBox.thirdDown?.made)}-${text(usBox.thirdDown?.of)}`, body: () => [band({ title: "Situation", collapsible: false, body: () => situationGrid({ us: { ...usHeads(), box: usBox }, them: { ...themHeads(), box: themBox } }) }), winProbabilityBand(s)] }, // wave F5: the win probability chart left the page for this panel
      { id: "edges", label: "Edges", hint: "season ranks", body: () => band({ title: "Matchup edges", collapsible: false, body: () => (edges.length ? edgesTable(edges, { usAbbr: usSide().abbr, themAbbr: themSide().abbr, usTeam: usTeam(), themTeam: themSide().name }) : note("Edges appear once both teams have played.")) }) }, // Phase 16 wave 3 (L-02)
      { id: "weather", label: "Weather", hint: "game site", body: () => band({ title: "Weather", collapsible: false, body: () => el("div", { style: { padding: "12px" } }, weather.available ? weatherRow({ kickoffText: fmtTime(p.game?.kickoff), tempF: weather.tempF, windMph: weather.windMph, windDir: typeof weather.windDir === "string" ? weather.windDir : null, sky: weather.sky, precipChance: weather.precipChance, indoors: Boolean(weather.dome), source: weather.source }) : weatherRow({ kickoffText: fmtTime(p.game?.kickoff), note: weather.error || "No forecast." })) }) },
      { id: "visitors", label: "Visitors", hint: "recruits", body: () => visitorsBand() },
      { id: "injuries", label: "Injuries", hint: "availability", body: () => band({ title: "Availability report", collapsible: false, body: () => (availability.length ? availabilityTable({ rows: availability, source: p.notes?.availabilitySource, updatedAt: p.notes?.availabilityUpdatedAt, teams: [{ school: usTeam(), abbreviation: usSide().abbr }, { school: themSide().name, abbreviation: themSide().abbr }] }) : note("No availability report for this game yet.")) }) },
      // 2026-10-02: who starts and who is behind them, from the notes file's published charts (ui/lineups.js)
      { id: "lineups", label: "Lineups", hint: "starters, depth", body: () => [band({ title: "Lineups and depth", collapsible: false, body: () => lineupBlock({ lineups: p.notes?.lineups, us: p.us, them: p.them, availability, coaches: p.notes?.coaches, schemes: p.notes?.schemes, onPlayer: (row) => openPlayer(row.playerId, { ...row.player, name: row.name, position: row.slot, isUs: row.isUs !== false }) }) })] }, // freeze wave F4: the coordinators and schemes head each matchup
      { id: "scores", label: "Scores", hint: scoresHint(), body: () => scoresBand() },
      { id: "value", label: "Play value", hint: gameAnalytics(s)?.ppa?.available ? "PPA" : "after the final", body: () => ppaBand(s) },
    ];
  }

  /** The plays not seen in the last draw (none on the first draw of a game, so the list doesn't all slide in). */
  function freshPlays(plays) {
    const ids = plays.map((p) => p.id).filter((id) => id !== null && id !== undefined);
    const seen = state.seenPlays;
    state.seenPlays = new Set(ids);
    return seen instanceof Set && seen.size ? new Set(ids.filter((id) => !seen.has(id))) : new Set();
  }

  function visitorsContent(v) {
    // wave 2: each side's recruits a sized table (ui/in-game-tables.js): the high school, hometown and class at large
    const side = (title, team, which, rows) => el("div", {}, subhead(title, { team, side: which }), visitorsTable(rows, { caption: title }));
    return band({ title: "Recruits on hand", collapsible: false, body: () => el("div", {}, v.note ? note(text(v.note)) : null, el("div", { class: "twocol" }, side(`Visiting ${usTeam()}`, usTeam(), "us", records(v.home)), side(`Visiting ${text(v.opponent)}`, typeof v.opponent === "string" ? v.opponent : null, "them", records(v.away)))) });
  }

  /** Recruits on hand: fetched when the sheet opens, kept ten minutes, never refetched per play. */
  function visitorsBand() {
    const cached = state.visitors;
    if (cached && Date.now() - cached.at < VISITORS_TTL_MS) return visitorsContent(cached.data);
    const host = band({ title: "Recruits on hand", collapsible: false, state: { status: "loading" }, skeleton: () => el("div", { class: "twocol" }, statTableSkeleton(4), statTableSkeleton(4)) });
    fetchJson("/api/recruiting")
      .then((envelope) => {
        const v = obj(envelope?.data?.visitors);
        state.visitors = { data: v, at: Date.now() };
        host.replaceWith(visitorsContent(v));
      })
      .catch((error) => {
        console.warn(`In Game: the visitors did not load: ${error?.message || error}`);
        host.replaceWith(band({ title: "Recruits on hand", collapsible: false, state: { status: "error", message: `${error?.message || "The request failed"}. Close the panel and open it again to retry.` } }));
      });
    return host;
  }

  /** A panel that fails to draw shows an error inside the sheet instead of breaking the button. */
  function safeBody(item) {
    try {
      return item.body();
    } catch (error) {
      console.error(`In Game: the ${item.label} panel could not be drawn.`, error);
      return band({ title: text(item.label), collapsible: false, state: { status: "error", message: "This panel could not be drawn. Close it and open it again." }, errorLead: "Display error." });
    }
  }

  function openItem(id) {
    const item = state.items.find((i) => i.id === id);
    if (!item || !container) return;
    const open = state.sheet;
    if (open?.handle && typeof open.handle.setBody === "function" && open.id !== id) {
      open.id = id; // Phase 16 wave 3 (L-10): the same sheet, its title and body swapped
      open.sorts = {};
      open.filter = "all";
      state.sheetError = false;
      state.seenPlays = null; // a play list just opened draws without sliding
      open.handle.setTitle(item.label);
      open.handle.setBody(() => safeBody(item));
      if (state.bar) state.bar.setActive(id);
      refreshPill();
      return;
    }
    closeSheet();
    state.seenPlays = null;
    const sheet = { id, handle: null, sorts: {}, filter: "all" };
    state.sheet = sheet;
    if (state.bar) state.bar.setActive(id);
    sheet.handle = openSheet({
      title: item.label,
      body: () => safeBody(item),
      onClose: () => {
        if (state.sheet !== sheet) return;
        state.sheet = null;
        state.sheetError = false; // the panel that could not be redrawn is gone
        if (state.bar) state.bar.setActive(null);
        refreshPill();
      },
    });
    refreshPill(); // a Display error from the sheet just closed no longer applies
  }

  // --- the board (owner mock 2026-10-11, queue item 7): one 1080p screen, nothing to scroll ---------------------------
  // Win probability and Leaders across the top left, the pass chart and the run chart under them with the QR between them
  // and the right half, Team stats and one In Game panel as two full-height columns (the Box score until a menu button
  // picks another). Along the bottom, edge to edge: the score strip with the radio at its left, the ticker, the
  // spoiler-delay line and the twelve menu buttons. Score by quarter and the game line are not on the board. Below the
  // TV size (components.css) the same cells stack and the page scrolls. The long columns step through their rows on
  // their own, as the old board's panes did.

  /** The board's skeleton, built once: the cells keep their place (and their scroll) while every frame redraws them. */
  function buildTv() {
    // the board (freeze wave F5, owner 2026-10-20: "the big screen should mirror the tablet's exactly"): In Game's own
    // frame, with a foot in place of the buttons: the radio, the delay line (or the final's), the QR (views/board.js)
    const tv = { radio: el("div", { class: "tv__radio" }), note: el("div", { class: "tv__note" }), qr: el("div", { class: "tv__qr" }) };
    state.tv = tv;
    return el("div", { class: "tv live-frame" }, slots.top, slots.middle, tickerHost, slots.bottom, el("div", { class: "tv__foot" }, tv.radio, tv.note, tv.qr));
  }

  /** The delay line for a game under way (In Game says it only before kickoff). */
  function tvDelayLine() {
    return el("p", {}, "Every panel runs ", el("b", { class: "tv__delay" }, `${state.delay} s`), " behind the broadcast, so the board never gets ahead of the TV; the Spoiler delay button on In Game changes that.");
  }

  /** The board's foot: the final's line, else the delay line. The rest of the board is In Game's own frame. */
  function drawTv(view) {
    const tv = state.tv;
    if (!tv) return;
    const note = view.boardNote;
    replaceWith(tv.note, typeof note === "string" ? el("p", {}, note) : note || tvDelayLine());
  }

  /** The columns that step through their rows: each box-score half (owner 2026-10-20: longer than its column, it steps). */
  function stepScrollers() {
    return frame && typeof frame.querySelectorAll === "function" ? [...frame.querySelectorAll(".stage-step")] : [];
  }

  function startStepping() {
    if (state.stepTimer || typeof setInterval !== "function" || reducedMotion()) return;
    state.stepRest = new WeakMap();
    state.stepTimer = setInterval(stepTv, BOARD_STEP_MS);
  }

  /** Each long column moves one row; at its end it rests, then returns to the top (a column that fits never moves). */
  function stepTv() {
    const rest = state.stepRest || (state.stepRest = new WeakMap());
    for (const node of stepScrollers()) {
      const room = node.scrollHeight - node.clientHeight;
      if (!(room > 0)) continue;
      if (node.scrollTop >= room - 1) {
        const waited = (rest.get(node) || 0) + BOARD_STEP_MS;
        if (waited >= BOARD_REST_MS) {
          rest.set(node, 0);
          node.scrollTo({ top: 0, behavior: "auto" });
        } else rest.set(node, waited);
        continue;
      }
      const row = node.querySelector("tbody tr, li, .play");
      const step = row && row.getBoundingClientRect().height > 0 ? row.getBoundingClientRect().height : 28;
      node.scrollTo({ top: Math.min(room, node.scrollTop + step), behavior: "smooth" });
    }
  }

  function stopTv() {
    if (state.stepTimer) clearInterval(state.stepTimer);
    state.stepTimer = null;
  }

  /** Close the open sheet, if any; the caller refreshes the pill. */
  function closeSheet() {
    const open = state.sheet;
    state.sheet = null;
    state.sheetError = false;
    if (open?.handle) open.handle.close();
    if (state.bar) state.bar.setActive(null);
  }

  /**
   * Redraw the open state-driven sheet from the newest items, where the reader is. It runs after
   * the main screen is swapped, so a panel that cannot be drawn never holds back the strip or the
   * score: that panel keeps its last good body and the pill says Display error until it draws again.
   */
  function refreshOpenSheet() {
    const open = state.sheet;
    if (!open?.handle || !STATE_ITEMS.has(open.id)) return;
    const item = state.items.find((i) => i.id === open.id);
    if (!item) return;
    const hadError = state.sheetError;
    try {
      open.handle.update(item.body);
      state.sheetError = false;
    } catch (error) {
      console.error(`In Game: the ${item.label} panel could not be redrawn; the last good one stays.`, error);
      state.sheetError = true;
    }
    if (state.sheetError !== hadError) refreshPill();
  }

  function liveParts(s) {
    const stripEl = stripFor(s);
    return {
      // siblings: the strip stays sticky against the page, not a wrapper; after a final the owner's held-final line (2026-10-10:
      // the Archive, the next game's program, how long this final stays up) sits under the strip, one line, the stage below it
      top: [stripEl, essentials(s), s.status === "final" ? finalNote(s) : null],
      strip: stripEl,
      middle: [stageFor(s)],
      bottom: null,
      items: remoteItems(s),
      state: s,
      boardNote: s.status === "final" ? finalNote(s) : null, // the board's bar: the final's line, else the delay line
    };
  }

  // --- the frame and the render ----------------------------------------------------------------------

  function openNotesSheet() {
    const gameId = state.live?.gameId ?? state.program?.game?.gameId;
    const context = () => {
      const s = state.live;
      if (!s || typeof s !== "object") return null;
      const usHome = s.home === usTeam();
      const us = usHome ? s.homeScore : s.awayScore;
      const them = usHome ? s.awayScore : s.homeScore;
      return { period: isNum(s.period) ? s.period : null, clock: typeof s.clock === "string" ? s.clock : s.clock && typeof s.clock === "object" && isNum(s.clock.minutes) ? `${s.clock.minutes}:${String(isNum(s.clock.seconds) ? s.clock.seconds : 0).padStart(2, "0")}` : null, score: isNum(us) && isNum(them) ? `${usAbbr()} ${us}, ${themSide().abbr} ${them}` : null };
    };
    // freeze wave F5 (owner 2026-10-20): one Notes sheet: your own lines first (they are part of the program notes now), the
    // program notes themselves, the schemes, then the game line with the crew and the coaches
    const p = state.program;
    const n = obj(p?.notes);
    const schemes = obj(n.schemes);
    const schemeLine = (label, o) => {
      const bits = [str(o.offense) ? `${o.offense.trim()} offense` : null, str(o.defense) ? `${o.defense.trim()} defense` : null].filter(Boolean);
      return bits.length ? el("p", { class: "note notes-sheet__scheme" }, el("b", {}, text(label)), " ", bits.join(", ")) : null;
    };
    const body = () =>
      el(
        "div",
        { class: "notes-sheet" },
        gameId ? gameNotesPanel({ gameId, getContext: context }) : el("p", { class: "note" }, "There is no game to write about yet."),
        n.present ? editorial({ byline: { author: n.author, writtenAt: n.writtenAt }, sources: records(n.sources), sections: records(n.sections) }) : el("p", { class: "note" }, "No program notes for this game yet. ", el("a", { href: "#program" }, "Add them on the Pre-Game Program"), "."),
        schemeLine(usAbbr(), schemes),
        schemeLine(themSide().abbr, obj(schemes.opponent)),
        gameInfo(p),
      );
    openSheet({ title: "Notes", body });
  }

  async function openInviteSheet() {
    const handle = openSheet({ title: "Invite friends", body: () => el("p", { class: "note" }, "Getting the address…") });
    try {
      handle.setBody(inviteBody(await loadInvite()));
    } catch (error) {
      handle.setBody(el("p", { class: "note" }, `The address did not load: ${error?.message || "no answer"}.`));
    }
  }

  function buildFrame() {
    const slot = () => el("div", { style: { display: "contents" } });
    slots = { top: slot(), middle: slot(), bottom: slot() };
    tickerHost = el("div", { class: "live-ticker" });
    // freeze wave F5 (owner 2026-10-20: "where the touch is"): the five tools sit in the panel row at the bottom, buttons of
    // the same kind: the delay (Phase 7b), the radio (owner 2026-10-11: within reach at every moment), the Notes (Phase 19: your
    // own lines, part of the program notes now), Invite (Phase 18.6) and the Big screen (owner 2026-10-10: reached from here only)
    state.tools = stageTools({ delayLabel: shortDelayLabel(), onDelay: () => openDelaySheet(), onRadio: () => openSheet({ title: "Radio", body: () => radioStations() }), onNotes: openNotesSheet, onInvite: openInviteSheet });
    frame = board ? buildTv() : el("div", { class: "live-frame" }, slots.top, slots.middle, tickerHost, slots.bottom);
    updateTicker();
  }

  /**
   * Draw the current state. Everything is built first; only a complete build replaces what is on
   * screen, so a frame that cannot be drawn leaves the last good one up with a Display error pill.
   * The open side sheet is redrawn after the swap, on its own, so it cannot hold the screen back.
   */
  function render() {
    if (!container) return;
    const pregame = state.mode === "pregame" || !state.live || typeof state.live !== "object";
    let view;
    try {
      view = pregame ? pregameParts() : liveParts(state.live);
    } catch (error) {
      console.error("In Game: this update could not be drawn; the last good screen stays up.", error);
      state.displayError = true;
      refreshPill();
      return;
    }
    state.displayError = false;
    if (state.feed?.state === "no_live_key" && view.top) {
      // Public release Phase 5a: say what a bigger plan adds, instead of only a red pill.
      view.top = el("div", {}, el("p", { class: "note plan-note" }, "Play-by-play during the game shows with a Tier 2 CFBD key. The score, the box score after the final and the rest of the app work on your plan. ", el("a", { href: PLANS_URL, target: "_blank", rel: "noopener" }, "See CFBD's plans")), view.top);
    }
    if (frame.parentNode !== container) container.replaceChildren(frame);
    const sheet = Array.isArray(view.items); // the game sheet, live or still empty before kickoff
    if (board) frame.className = sheet ? "tv live-frame" : "tv live-frame tv--empty"; // no game yet: the sheet's own message, nothing else
    else {
      frame.className = sheet ? "live-frame" : "season";
      frame.style.gridTemplateColumns = sheet ? "" : "minmax(0, 1fr)";
    }
    const gameKey = state.live && typeof state.live === "object" ? state.live.gameId ?? null : null;
    const before = state.flashReady && state.flashGame === gameKey ? snapshotKeys(frame) : null;
    // owner bug 2026-10-10 (a phone): every update rebuilt the panels and the page snapped to the top, so nothing below the
    // score could be read during the game. The band under the reader's eye stays where it is across the rebuild; the board
    // (big screen mode) keeps its top, which is what it is for.
    const anchor = document.body.classList.contains("board-mode") ? null : scrollAnchor(frame);
    replaceWith(slots.top, view.top);
    replaceWith(slots.middle, view.middle);
    replaceWith(slots.bottom, view.bottom);
    if (board && sheet) drawTv(view); // the board's foot: the final's line, else the delay line
    keepAnchor(anchor);
    fillWiki(frame); // Phase 19: the stadium and the coaches become their Wikipedia pages
    if (before) flashChanges(before, frame); // Phase 16 wave 3 (L-03): only what changed since the last frame
    state.flashReady = !pregame;
    state.flashGame = gameKey;
    state.strip = view.strip || null;
    if (!sheet) {
      closeSheet();
      if (state.bar) state.bar.style.display = "none";
      stopTv();
    } else {
      state.items = view.items;
      if (!board) {
        if (!state.bar) {
          state.bar = remoteBar({ items: view.items, onOpen: openItem });
          state.bar.classList.add("remote--stage"); // wave F5: one row, labels only, the tools at its end
          state.bar.append(...state.tools);
          frame.append(state.bar);
        }
        state.bar.style.display = "";
        for (const item of view.items) state.bar.setHint(item.id, item.hint);
        if (state.sheet) state.bar.setActive(state.sheet.id);
        refreshOpenSheet();
      }
      startStepping(); // the box-score halves step through their rows when longer than their column (wave F5)
    }
    refreshPill();
    if (!pregame && state.live.status === "final") maybeLoadAnalytics();
  }

  // --- the stream --------------------------------------------------------------------------------------

  function parseFrame(event, name) {
    try {
      return JSON.parse(event.data);
    } catch (error) {
      console.warn(`In Game: dropped a ${name} frame that was not JSON.`, error);
      return null;
    }
  }

  /** A hello or a state frame: the stream works, so the fallback poll and the error count go. */
  function streamAlive() {
    state.lastFrameAt = Date.now();
    state.errors = 0;
    state.polled = false;
    state.retries = 0;
    stopFallback();
  }

  function connect() {
    closeSource();
    if (!container) return;
    let source;
    try {
      source = new EventSource(`/api/live/stream?delay=${state.delay}`);
    } catch (error) {
      console.error("In Game: the event stream could not be opened.", error);
      state.errors += 1;
      startFallback();
      scheduleRetry();
      refreshPill();
      return;
    }
    state.source = source;
    state.helloSeen = false;
    state.flashReady = false; // a reconnect (a new delay) redraws everything: nothing flashes on its first frame
    state.lastFrameAt = Date.now();
    source.addEventListener("hello", (event) => {
      if (state.source !== source) return;
      streamAlive();
      const data = parseFrame(event, "hello");
      if (data && typeof data === "object") {
        state.helloSeen = true;
        state.pingCapable = Object.prototype.hasOwnProperty.call(data, "feed"); // a server from before Phase 10a sends no feed and no pings
        if (state.pingCapable) takeFeed(data.feed);
        noteBuild(data.build); // a restarted server says hello with its new build
      }
      refreshPill();
    });
    source.addEventListener("ping", (event) => {
      if (state.source !== source) return;
      state.lastFrameAt = Date.now();
      state.pingCapable = true;
      const data = parseFrame(event, "ping");
      if (data && typeof data === "object" && Object.prototype.hasOwnProperty.call(data, "feed")) takeFeed(data.feed);
      refreshPill();
    });
    source.addEventListener("state", (event) => {
      if (state.source !== source) return;
      streamAlive();
      const next = parseFrame(event, "state");
      if (!next || typeof next !== "object" || Array.isArray(next)) {
        if (next !== null) console.warn("In Game: dropped a state frame that was not an object.");
        refreshPill();
        return;
      }
      if (Object.prototype.hasOwnProperty.call(next, "feed")) {
        state.pingCapable = true;
        takeFeed(next.feed); // during play the stream is never quiet enough for a ping, so each frame carries the feed health
      }
      if (state.live && String(state.live.gameId ?? "") !== String(next.gameId ?? "")) resetGame(); // another game: nothing of the last one carries over
      state.live = next;
      state.mode = next.status === "final" ? "postgame" : "live";
      render();
      holdAwake(next.status !== "final");
    });
    source.onerror = () => {
      if (state.source !== source) return;
      state.errors += 1;
      if (state.errors === 1) console.warn("In Game: the event stream dropped; polling the state every 15 s until it is back.");
      startFallback();
      if (source.readyState === SOURCE_CLOSED) scheduleRetry();
      refreshPill();
    };
  }

  function closeSource() {
    if (state.source) state.source.close();
    state.source = null;
    clearTimeout(state.retryTimer);
    state.retryTimer = null;
  }

  function startFallback() {
    if (!state.fallback) state.fallback = setInterval(pollState, FALLBACK_POLL_MS);
  }

  function stopFallback() {
    if (state.fallback) clearInterval(state.fallback);
    state.fallback = null;
  }

  /** The browser closed the stream for good: open a new one after 5, 10, 20, 40, then every 60 s. */
  function scheduleRetry() {
    if (state.retryTimer || !container) return;
    const wait = Math.min(RETRY_MAX_MS, RETRY_BASE_MS * 2 ** Math.min(state.retries, 4));
    state.retries += 1;
    state.retryTimer = setTimeout(() => {
      state.retryTimer = null;
      if (container && state.mode !== "pregame") connect();
    }, wait);
  }

  function disconnect() {
    closeSource();
    stopFallback();
  }

  async function pollState() {
    if (!container) return;
    try {
      const envelope = await fetchJson(`/api/live/state?delay=${state.delay}`);
      if (!container || !state.errors) return; // the stream came back while this was in flight
      if (state.heldFor !== null && state.heldFor !== undefined) return; // the held final is the sheet now; the engine's state is not (freeze wave F1, F6)
      const data = envelope?.data;
      state.polled = true;
      if (data && typeof data === "object" && !Array.isArray(data) && data.gameId) {
        if (data.engine && typeof data.engine === "object" && Object.prototype.hasOwnProperty.call(data.engine, "feed")) takeFeed(data.engine.feed);
        if (state.live && String(state.live.gameId ?? "") !== String(data.gameId ?? "")) resetGame();
        state.live = data;
        state.mode = data.status === "final" ? "postgame" : "live";
        render();
        holdAwake(data.status !== "final");
      } else refreshPill();
    } catch (error) {
      if (!container) return;
      if (state.polled || !warned.has("poll")) console.warn(`In Game: the fallback poll failed: ${error?.message || error}`);
      warned.add("poll");
      state.polled = false;
      refreshPill();
    }
  }

  /** Every 5 s: a stream that has said nothing for 40 s is reopened; a stale age keeps counting. */
  function watch() {
    if (!container) return;
    const silent = Date.now() - state.lastFrameAt;
    if (state.mode !== "pregame" && state.source && state.pingCapable && silent > WATCHDOG_MS) {
      console.warn(`In Game: nothing from the stream for ${Math.round(silent / 1000)} s; reconnecting.`);
      connect();
      return;
    }
    if (state.feed?.state === "stale") refreshPill();
  }

  async function checkWindow({ retryProgram = true } = {}) {
    if (!container) return;
    try {
      const envelope = await fetchJson("/api/live/status");
      if (!container) return;
      const data = obj(envelope?.data);
      state.statusError = null;
      state.window = data.window && typeof data.window === "object" ? data.window : null;
      if (Object.prototype.hasOwnProperty.call(data, "feed")) {
        takeFeed(data.feed);
        // A server with the feed block pings its streams (C1 with C2), so a stream that opens and
        // never says hello is reopened by the watchdog too; once a hello arrives, it decides.
        if (!state.helloSeen) state.pingCapable = true;
      }
      const open = state.window?.open === true || data.mode === "replay";
      const held = data.held && typeof data.held === "object" && data.held.gameId !== undefined && data.held.gameId !== null ? data.held : null;
      // a game under way takes the sheet over from a pregame sheet, a held final, or a final of another game
      const another = state.live && state.window && String(state.window.gameId ?? "") !== String(state.live.gameId ?? "") && state.live.status === "final";
      if (open && (state.mode === "pregame" || state.heldFor !== null && state.heldFor !== undefined || another)) {
        if (state.mode !== "pregame") {
          disconnect();
          resetGame();
          state.live = null;
          state.program = null;
          loadProgram();
        }
        state.mode = "live";
        connect();
      } else if (!open && held && (state.mode === "pregame" || String(state.heldFor ?? "") === String(held.gameId) || String(state.live?.gameId ?? "") === String(held.gameId)) && state.live?.status !== "final") {
        disconnect(); // a stream that was down stays down, and its fallback poll stops, so nothing overwrites the held final (freeze wave F1, F6)
        state.errors = 0;
        await loadHeld(); // a fresh sheet, or one still mid-game on the held game (a restart cut its stream): the final at its delay
      } else if (!open && !held && !replayed(data) && (state.heldFor !== null && state.heldFor !== undefined || state.live?.status === "final" || sheetGameOver())) {
        await letGo();
      }
    } catch (error) {
      if (!container) return;
      const message = error?.message || "Could not reach the server";
      if (message !== state.statusError) console.warn(`In Game: the status check failed: ${message}`);
      state.statusError = message;
    }
    const want = state.heldFor !== null && state.heldFor !== undefined ? String(state.heldFor) : null; // a held final wants its own game's program
    const wrong = want !== null && String(state.program?.game?.gameId ?? "") !== want;
    if (retryProgram && container && (!state.program || wrong)) {
      await loadProgram(want);
      if (container && state.program && (state.mode === "pregame" || !state.live || (want !== null && String(state.program?.game?.gameId ?? "") === want))) render();
    }
    refreshPill();
  }

  // --- keeping the screen on --------------------------------------------------------------------------

  const wantAwake = () => Boolean(container) && state.mode === "live" && state.live?.status !== "final";

  async function holdAwake(on) {
    if (!on) {
      releaseWakeLock();
      return;
    }
    if (!wantAwake() || state.wakeLockPending || (state.wakeLock && !state.wakeLock.released)) return;
    const api = screenLock(); // the browser's wake lock, or the video fallback over plain HTTP (Phase 4b)
    if (!api || document.visibilityState !== "visible") return;
    state.wakeLockPending = true;
    try {
      const sentinel = await api.request("screen");
      if (!wantAwake()) {
        await sentinel.release(); // the game ended or the sheet closed while the request was out
        return;
      }
      sentinel.addEventListener("release", () => {
        if (state.wakeLock === sentinel) state.wakeLock = null; // the system let go (tab hidden, battery saver); the next frame asks again
      });
      state.wakeLock = sentinel;
    } catch (error) {
      state.wakeLock = null;
      warnOnce("wake-lock", "In Game: the screen may sleep; the wake lock was refused.", error?.message || error);
    } finally {
      state.wakeLockPending = false;
    }
  }

  function releaseWakeLock() {
    const sentinel = state.wakeLock;
    state.wakeLock = null;
    if (sentinel && !sentinel.released) sentinel.release().catch((error) => console.warn(`In Game: the wake lock did not release: ${error?.message || error}`));
  }

  function onVisible() {
    if (!container || document.visibilityState !== "visible") return;
    if (state.heldFor !== null && state.heldFor !== undefined) loadHeld(); // a held final wakes to itself, never a stream
    else if (state.mode !== "pregame" && (!state.source || state.source.readyState === SOURCE_CLOSED)) connect();
    if (wantAwake()) holdAwake(true);
    checkWindow();
  }

  return {
    async mount(target) {
      container = target;
      container.replaceChildren(el("div", { class: "season", style: { gridTemplateColumns: "minmax(0, 1fr)" } }, band({ title: "In Game", collapsible: false, state: { status: "loading" } })));
      state.pillKey = "quiet|Loading";
      setStatus({ kind: "quiet", label: "Loading" });
      buildFrame();
      document.addEventListener("visibilitychange", onVisible);
      state.watchTimer = setInterval(watch, WATCH_TICK_MS);
      const next = loadProgram(); // the next game's, unless a held final asks for its own (the newer request wins)
      await checkWindow({ retryProgram: false });
      await next;
      if (!container) return; // left before the program arrived
      render();
      state.statusTimer = setInterval(checkWindow, STATUS_POLL_MS);
      loadTicker();
      state.tickerTimer = setInterval(loadTicker, TICKER_POLL_MS);
    },
    refresh() {
      return checkWindow();
    },
    unmount() {
      stopTv();
      const slider = state.slider;
      stopSync();
      closeSheet();
      if (state.delaySheet) state.delaySheet.close();
      state.delaySheet = null;
      disconnect();
      if (state.statusTimer) clearInterval(state.statusTimer);
      if (state.tickerTimer) clearInterval(state.tickerTimer);
      if (state.watchTimer) clearInterval(state.watchTimer);
      state.statusTimer = state.tickerTimer = state.watchTimer = null;
      clearTimeout(state.analyticsTimer);
      state.analyticsTimer = null;
      clearTimeout(state.heldTimer); // freeze wave F1, F9
      state.heldTimer = null;
      releaseWakeLock();
      if (state.tickerNode && typeof state.tickerNode.destroy === "function") state.tickerNode.destroy();
      state.tickerNode = null;
      document.removeEventListener("visibilitychange", onVisible);
      container = null;
      if (slider && typeof slider.flush === "function") slider.flush(); // a nudge still settling is saved
    },
  };
}

export { fmtPct, madeOf }; // madeOf lives with In Game's tables (ui/in-game-tables.js) since wave 2
