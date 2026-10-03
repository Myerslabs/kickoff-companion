// The Live sheet (L1 to L7, L11, L12, L13, X7): the remote-control screen on the event stream.
// Pregame: the program's cover, notes, weather, and countdown. Live: strip, quarter line, team
// stats, win probability with the last play's success, leaders, and the remote bar opening
// everything else in a side sheet. Postgame: the final box, saved to the archive. The delay
// slider is saved on the device and every panel follows it through the stream.
//
// Saturday readiness (Phase 10a): the page is a fixed frame. The ticker, the delay slider, and the
// remote bar are built once per visit, so the crawl, a drag, and a bar scrolled sideways survive
// every play; the rest is redrawn per frame, and an open side sheet is redrawn in place with its
// scroll, filter, and sort. A frame that cannot be drawn leaves the last good screen up. The stream
// has a watchdog, and one function decides the status pill for the strip and the top bar from the
// stream, the display, and the feed health the server reports (the stream's hello and ping, and
// /api/live/status every minute).

import { screenLock } from "../awake.js";
import { isUs, usLabel, usName, usSchool } from "../identity.js";
import { cover } from "../ui/cover.js";
import { delaySlider } from "../ui/delay-slider.js";
import { DASH, el, fmtPct, fmtStat, fmtTime, isNum, recall, remember, replaceWith, text } from "../ui/dom.js";
import { driveList } from "../ui/drive-bar.js";
import { availabilityTable, editorial } from "../ui/editorial.js";
import { depthBlock, startersBlock } from "../ui/lineups.js";
import { leadersGrid } from "../ui/leaders.js";
import { weatherRow } from "../ui/matchup-card.js";
import { playLog } from "../ui/play-log.js";
import { openSheet, remoteBar } from "../ui/remote.js";
import { situationGrid } from "../ui/situation.js";
import { band, note } from "../ui/states.js";
import { statTable } from "../ui/stat-table.js";
import { strip } from "../ui/strip.js";
import { advancedBoxBlock } from "../ui/depth2.js";
import { scoresTable } from "../ui/scores.js";
import { shotChart } from "../ui/shot-chart.js";
import { ticker } from "../ui/ticker.js";
import { quarterLine, teamStatsTable } from "../ui/team-stats.js";
import { successRow, winProbabilityChart } from "../ui/wp-chart.js";
import { getPrefs, savePrefs } from "../prefs.js";
import { noteBuild } from "../build.js";
import { fetchJson } from "./common.js";
import { openPlayer } from "./player.js";

const DELAY_KEY = "live:delay";
const DEFAULT_DELAY = 30;
const STATUS_POLL_MS = 60 * 1000;
const FALLBACK_POLL_MS = 15 * 1000;
const TICKER_POLL_MS = 60 * 1000;
const ANALYTICS_RETRY_MS = 60 * 1000;
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

const BOX_COLUMNS = {
  passing: [{ key: "name", label: "Passing", kind: "text" }, { key: "C/ATT", label: "C/ATT", kind: "text", sortable: false }, { key: "YDS", label: "Yds" }, { key: "TD", label: "TD" }, { key: "INT", label: "Int" }, { key: "QBR", label: "QBR", format: "1f" }],
  rushing: [{ key: "name", label: "Rushing", kind: "text" }, { key: "CAR", label: "Car" }, { key: "YDS", label: "Yds" }, { key: "AVG", label: "Avg", format: "1f" }, { key: "TD", label: "TD" }],
  receiving: [{ key: "name", label: "Receiving", kind: "text" }, { key: "REC", label: "Rec" }, { key: "YDS", label: "Yds" }, { key: "AVG", label: "Avg", format: "1f" }, { key: "TD", label: "TD" }],
  defensive: [{ key: "name", label: "Defense", kind: "text" }, { key: "TOT", label: "Tkl" }, { key: "SACKS", label: "Sck", format: "1f" }, { key: "TFL", label: "TFL", format: "1f" }, { key: "PD", label: "PD" }],
  interceptions: [{ key: "name", label: "Interceptions", kind: "text" }, { key: "INT", label: "Int" }, { key: "YDS", label: "Yds" }, { key: "TD", label: "TD" }],
  kicking: [{ key: "name", label: "Kicking", kind: "text" }, { key: "FG", label: "FG", kind: "text", sortable: false }, { key: "XP", label: "XP", kind: "text", sortable: false }, { key: "PTS", label: "Pts" }],
  punting: [{ key: "name", label: "Punting", kind: "text" }, { key: "NO", label: "No" }, { key: "AVG", label: "Avg", format: "1f" }, { key: "LONG", label: "Long" }],
  puntReturns: [{ key: "name", label: "Punt returns", kind: "text" }, { key: "NO", label: "No" }, { key: "YDS", label: "Yds" }, { key: "TD", label: "TD" }],
  kickReturns: [{ key: "name", label: "Kick returns", kind: "text" }, { key: "NO", label: "No" }, { key: "YDS", label: "Yds" }, { key: "TD", label: "TD" }],
};
const LEADER_CATEGORIES = [["passing", "Passing", "YDS"], ["rushing", "Rushing", "YDS"], ["receiving", "Receiving", "YDS"], ["defensive", "Defense", "TOT"]];

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

/** "3 of 8" from {made, of}, or a dash. */
export function madeOf(value) {
  return value && isNum(value.made) && isNum(value.of) && value.of > 0 ? `${value.made} of ${value.of}` : DASH;
}

/** The value when it is a plain object, else an empty one: every frame is untrusted. */
function obj(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

/** The value when it is a list, with malformed records skipped; anything else is an empty list. */
function records(value) {
  return Array.isArray(value) ? value.filter((row) => row && typeof row === "object") : [];
}

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
  if (final) return { kind: "live", label: "Final" };
  if (feed?.state === "stale") return { kind: "stale", label: staleLabel(isNum(feed.staleSeconds) ? feed.staleSeconds + (isNum(feedAge) ? Math.max(0, feedAge) : 0) : null) };
  if (feed?.state === "no_live_key") return { kind: "offline", label: "No live feed on this key" };
  if (feed?.state === "waiting") return { kind: "quiet", label: "Waiting for CFBD" };
  return isNum(delay) && delay > 0 ? { kind: "delayed", label: `Delayed ${delay} s` } : { kind: "live", label: "Live" };
}

// --- helpers on a state frame --------------------------------------------------------------------

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

function leaderLine(category, row) {
  const s = obj(row.stats);
  const parts = {
    passing: [text(s["C/ATT"]), `${text(s.YDS)} yds`, isNum(s.TD) ? `${s.TD} TD` : null, isNum(s.INT) ? `${s.INT} int` : null],
    rushing: [`${text(s.CAR)} car`, `${text(s.YDS)} yds`, isNum(s.TD) ? `${s.TD} TD` : null],
    receiving: [`${text(s.REC)} rec`, `${text(s.YDS)} yds`, isNum(s.TD) ? `${s.TD} TD` : null],
    defensive: [`${text(s.TOT)} tkl`, isNum(s.SACKS) && s.SACKS > 0 ? `${s.SACKS} sck` : null, isNum(s.TFL) && s.TFL > 0 ? `${s.TFL} tfl` : null],
  }[category] || [text(s.YDS)];
  return parts.filter(Boolean).join(", ");
}

function leadersFromState(state, usName) {
  const teams = state.playerStats && typeof state.playerStats === "object" ? state.playerStats : null;
  if (!teams) return null;
  const us = state.home === usName ? state.home : state.away;
  const them = state.home === usName ? state.away : state.home;
  const top = (team, category, stat) => {
    const rows = records(obj(teams[team])[category]).filter((r) => isNum(r.stats?.[stat]));
    rows.sort((a, b) => b.stats[stat] - a.stats[stat]);
    const row = rows[0];
    // Play-by-play lines carry an id only when the roster matched the jersey and name: else no headshot, no card.
    return row ? { name: row.name, playerId: hasId(row.playerId) ? row.playerId : null, line: leaderLine(category, row), headshotUrl: hasId(row.playerId) ? `/media/headshot/${row.playerId}` : null } : null;
  };
  const categories = LEADER_CATEGORIES.map(([id, label, stat]) => ({ id, label, us: top(us, id, stat), them: top(them, id, stat) })).filter((c) => c.us || c.them);
  return categories.length ? categories : null; // the play-by-play has no tackles, so Defense waits for the box score
}

export function createLiveView({ onStatus } = {}) {
  const savedDelay = Number(getPrefs().delaySeconds ?? recall(DELAY_KEY, DEFAULT_DELAY));
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

  // --- the status pill ---------------------------------------------------------------------------

  function pillNow() {
    return livePill({
      displayError: state.displayError || state.sheetError,
      streamDown: state.mode !== "pregame" && state.errors > 0,
      polled: state.polled,
      pregame: state.mode === "pregame",
      statusDown: Boolean(state.statusError),
      final: state.live?.status === "final",
      feed: state.feed,
      feedAge: state.feedAt ? (Date.now() - state.feedAt) / 1000 : 0,
      delay: state.delay,
    });
  }

  /** Push the current pill to the strip (in place) and to the top bar. */
  function refreshPill() {
    if (!container) return;
    const next = pillNow();
    if (state.strip && typeof state.strip.setPill === "function") state.strip.setPill(next);
    const key = `${next.kind}|${next.label}`;
    if (key !== state.pillKey) {
      state.pillKey = key;
      setStatus(next);
    }
  }

  function takeFeed(raw) {
    const feed = readFeed(raw);
    if (raw !== null && raw !== undefined && !feed) warnOnce("feed-shape", "Live sheet: the server's feed block was not readable; the pill ignores it.", raw);
    state.feed = feed;
    state.feedAt = Date.now();
  }

  // --- pregame -----------------------------------------------------------------------------------

  async function loadProgram() {
    try {
      const envelope = await fetchJson("/api/program/next");
      state.program = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
      state.programError = null;
    } catch (error) {
      state.programError = error?.message || "Could not load the program";
      console.warn(`Live sheet: the program did not load: ${state.programError}`);
    }
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
      if (message !== state.tickerError) console.warn(`Live sheet: the ticker did not load: ${message}`);
      state.tickerError = message;
    }
    if (!container) return;
    updateTicker();
    if (state.sheet?.id === "scores") refreshOpenSheet();
  }

  function tickerGames(includeUs = false) {
    return records(state.ticker?.games)
      .filter((g) => includeUs || !g.isUs)
      .map((g) => ({ ...g, detail: g.status === "pre" ? (g.startTimeTbd ? "TBD" : fmtTime(g.kickoff)) : g.detail }));
  }

  function tickerLabel() {
    // Public release Phase 5b: the My teams ticker names itself; the schedule's cadence comes from the server (5 or 20 min).
    const base = state.ticker?.mode === "mine" ? "My teams" : "FBS scores";
    const minutes = isNum(state.ticker?.refreshMinutes) ? state.ticker.refreshMinutes : 5;
    return state.ticker?.source === "games" ? `${base}, every ${minutes} min` : base;
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
      state.tickerNode.setGames(games, label);
      state.tickerSig = signature;
      return;
    }
    const next = ticker({ games, id: "live", label });
    const old = state.tickerNode;
    tickerHost.replaceChildren(next);
    if (old && typeof old.destroy === "function") old.destroy();
    state.tickerNode = next;
    state.tickerSig = signature;
  }

  function scoresBand() {
    const games = tickerGames(true);
    const table = scoresTable({ games, emptyText: state.tickerError ? `${state.tickerError}.` : "No FBS games on this week's slate." });
    return band({ title: "Around the country", collapsible: false, summary: state.ticker?.source === "games" ? "scores from the schedule; live scores show with a Tier 1 or bigger key" : "", body: () => el("div", {}, table, typeof state.ticker?.modeNote === "string" && state.ticker.modeNote ? el("p", { class: "note" }, state.ticker.modeNote) : null, el("p", { class: "note" }, state.ticker?.mode === "mine" ? "Your primary and secondary teams' games. Our line follows your spoiler delay. Switch to every game in Settings." : "Scores only. Our line follows your spoiler delay.")) });
  }

  // --- post-game analytics (L8, L9) --------------------------------------------------------------------

  const analyticsComplete = () => Boolean(state.analytics?.winProbability?.available && state.analytics?.ppa?.available);

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
      console.warn(`Live sheet: the post-game analytics did not load: ${state.analyticsError}`);
    }
    state.analyticsBusy = false;
    if (!container) return;
    clearTimeout(state.analyticsTimer);
    state.analyticsTimer = analyticsComplete()
      ? null
      : setTimeout(() => {
          state.analyticsTimer = null;
          maybeLoadAnalytics();
        }, ANALYTICS_RETRY_MS);
    render();
  }

  /**
   * The live feed's own efficiency numbers per team (EPA, explosiveness, the down splits), when the
   * document carries them. The overall success rate is not repeated here: the success row shows it.
   */
  function feedStatsTable(s) {
    const feed = s.feedStats;
    if (!feed || typeof feed !== "object") return null;
    const us = obj(feed[usTeam()]);
    const them = obj(feed[themSide().name]);
    const spec = [["Standard downs", "standardDownSuccessRate", "pct"], ["Passing downs", "passingDownSuccessRate", "pct"], ["EPA per play", "epaPerPlay", "+2f"], ["EPA per pass", "epaPerPass", "+2f"], ["EPA per rush", "epaPerRush", "+2f"], ["Explosiveness", "explosiveness", "2f"], ["Points per opportunity", "pointsPerOpportunity", "1f"], ["Scoring opportunities", "scoringOpportunities", "0f"], ["Line yards per rush", "lineYardsPerRush", "1f"], ["Average start", "averageStartYardLine", "0f"], ["Deserve to win", "deserveToWin", "pct"]];
    const rows = spec.map(([label, key, format]) => ({ label, usText: isNum(us[key]) ? fmtStat(us[key], format) : DASH, themText: isNum(them[key]) ? fmtStat(them[key], format) : DASH, has: isNum(us[key]) || isNum(them[key]) })).filter((r) => r.has);
    if (!rows.length) return null;
    return el(
      "div",
      {},
      el("h3", { style: { padding: "12px 12px 4px", color: "var(--fog)" } }, "Efficiency, from the live feed"),
      statTable({ compact: true, columns: [{ key: "label", label: "Per play", kind: "text", sortable: false }, { key: "usText", label: usAbbr(), kind: "text", sortable: false }, { key: "themText", label: themSide().abbr, kind: "text", sortable: false }], rows }),
    );
  }

  function wpBlock(s, usHome, pregame) {
    const wp = state.analytics?.winProbability;
    const postGame = wp?.available && Array.isArray(wp.series) ? wp.series : [];
    // In the game: CFBD's scoreboard readings, released on the same delay as the plays (Phase 11).
    const live = s.liveWinProbability && Array.isArray(s.liveWinProbability.series) ? s.liveWinProbability.series : [];
    const series = postGame.length ? postGame : live;
    const chart = winProbabilityChart({ series, homeIsUs: usHome, usAbbr: usAbbr(), pregame, final: s.status === "final" });
    let why;
    if (postGame.length) why = `${postGame.length} plays from CFBD's post-game model.`;
    else if (live.length && s.status !== "final") why = `${live.length} ${live.length === 1 ? "reading" : "readings"} from CFBD's scoreboard, about one a minute while this sheet is open, ${state.delay} s behind like every panel. The play-by-play chart posts after the final.`;
    else if (live.length) why = `${live.length} in-game readings from CFBD's scoreboard; the play-by-play chart replaces them once CFBD posts it.`;
    else if (s.status === "final") why = state.analytics ? wp?.note || "CFBD has not posted the win probability yet; the sheet checks again every minute." : state.analyticsError ? `${state.analyticsError}. Retrying every minute.` : "Loading the post-game win probability.";
    else why = isNum(pregame) ? "No in-game reading yet; this is the pregame number. Readings from CFBD's scoreboard start once the game is under way." : "No win probability for this game yet.";
    return el("div", {}, chart, el("p", { class: "note" }, why));
  }

  function teamValueTable(teams) {
    const rows = [["Offense", "offense"], ["Defense", "defense"]].flatMap(([label, side]) => ["overall", "passing", "rushing"].map((key) => ({ label: `${label}, ${key}`, us: teams?.us?.[side]?.[key], them: teams?.them?.[side]?.[key] })));
    if (!rows.some((r) => isNum(r.us) || isNum(r.them))) return note("No team values for this game yet.");
    return statTable({ compact: true, columns: [{ key: "label", label: "PPA per play", kind: "text", sortable: false }, { key: "us", label: usAbbr(), format: "+2f", sortable: false }, { key: "them", label: themSide().abbr, format: "+2f", sortable: false }], rows });
  }

  function ppaBand(s) {
    const a = state.analytics;
    const p = a?.ppa;
    const columns = [{ key: "name", label: "Player", kind: "text", sub: "position", sortable: false }, { key: "all", label: "PPA/play", format: "+2f", sortable: false }, { key: "pass", label: "Pass", format: "+2f", sortable: false }, { key: "rush", label: "Rush", format: "+2f", sortable: false }];
    const side = (title, rows, them) => el("div", {}, el("h3", { style: { padding: "12px 12px 4px", color: "var(--fog)" } }, title), rows.length ? statTable({ compact: true, columns, rows, onRowTap: (row) => openPlayer(row.playerId, { ...row, isUs: !them }) }) : note("No player values yet."));
    let body;
    if (s.status !== "final") body = note("Per-play PPA shows in the play log when the feed carries it. Player values post after the final.");
    else if (!a) body = note(state.analyticsError ? `${state.analyticsError}. Retrying every minute.` : "Loading play value.");
    else if (!p?.available) body = note(p?.note || "CFBD has not posted play value for this game yet; the sheet checks again every minute.");
    else body = el("div", {}, teamValueTable(p.teams), el("div", { class: "twocol" }, side(usWords(), records(p.players?.us), false), side(themSide().name, records(p.players?.them), true)));
    const value = band({ title: "Play value", collapsible: false, summary: "PPA per play", body: () => body });
    if (s.status !== "final" || !a?.advancedBox) return value;
    // Phase 13: after the final, CFBD's advanced box score under the play value
    return [value, band({ title: "Advanced box score", collapsible: false, summary: "by quarter, players' value", body: () => advancedBoxBlock(a.advancedBox, { us: usTeam(), them: themSide().name, usAbbr: usAbbr(), themAbbr: themSide().abbr }) })];
  }

  function pregameParts() {
    const p = state.program;
    if (!p) {
      const failed = Boolean(state.programError);
      const message = failed ? `${text(state.programError)}. The sheet tries again every minute.` : "No game of ours is on the schedule ahead. The sheet checks again every minute.";
      return { top: band({ title: "Live sheet", collapsible: false, state: { status: failed ? "error" : "empty", message }, errorLead: "Could not load the next game." }) };
    }
    const g = obj(p.game);
    const n = obj(p.notes);
    const w = obj(p.weather);
    const availability = records(n.availability);
    const kickoffText = g.startTimeTbd ? "Time TBD" : fmtTime(g.kickoff);
    return {
      top: el("div", {}, cover({ kicker: "Pregame", date: g.kickoff, startTimeTbd: g.startTimeTbd, venue: g.venue, neutralSite: g.neutralSite, tv: g.tv, homeIsUs: g.homeIsUs, us: obj(p.us), them: obj(p.them), line: obj(p.line), pregame: { homeWinProbability: p.pregame?.homeWinProbability }, reveal: false }), gameInfo(p)),
      middle: el("p", { class: "note" }, `The live sheet opens by itself 1 hour before kickoff, and plays start flowing 30 minutes before. It follows the game ${state.delay} s behind the broadcast; the Delay button changes it and syncs it to your TV.`),
      bottom: [
        el("div", { class: "spread spread--2" }, band({ title: "Program notes", collapsible: false, state: { status: "ready" }, body: () => (n.present ? editorial({ byline: { author: n.author, writtenAt: n.writtenAt }, sources: Array.isArray(n.sources) ? n.sources : [], sections: Array.isArray(n.sections) ? n.sections : [] }) : note(n.error ? `${n.error}.` : "No notes for this game yet.")) }), band({ title: "Weather at kickoff", collapsible: false, state: { status: "ready" }, body: () => el("div", { style: { padding: "12px" } }, w.available ? weatherRow({ kickoffText, tempF: w.tempF, windMph: w.windMph, windDir: typeof w.windDir === "string" ? w.windDir : null, sky: w.sky, precipChance: w.precipChance, indoors: Boolean(w.dome), source: w.source }) : weatherRow({ kickoffText, note: w.error || "No forecast yet." })) })),
        band({ title: "Availability report", collapsible: false, state: { status: "ready" }, body: () => (availability.length ? availabilityTable({ rows: availability, source: n.availabilitySource, updatedAt: n.availabilityUpdatedAt }) : note("No availability report for this game yet.")) }),
        band({ title: "Starting lineups", collapsible: false, state: { status: "ready" }, body: () => startersBlock({ lineups: n.lineups, us: obj(p.us), them: obj(p.them), availability, onPlayer: (row) => openPlayer(row.playerId, { ...row.player, name: row.name, position: row.slot, isUs: row.isUs !== false }) }) }),
      ],
    };
  }

  function delayLabel() {
    return `Spoiler delay ${state.delay} s ›`;
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
    remember(DELAY_KEY, next);
    if (state.delayButton) state.delayButton.textContent = delayLabel();
    savePrefs({ delaySeconds: next }).catch((error) => console.warn(`Live sheet: the delay is kept on this device only; the server did not save it: ${error?.message || error}`));
    if (!container) return; // a nudge that settled after the sheet closed is saved, nothing more
    if (state.mode !== "pregame") connect();
    else render(); // the pregame note repeats the delay
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
    const b = obj(n.broadcast);
    const name = (value) => (typeof value === "string" && value.trim() ? value.trim() : null);
    const venue = name(g.venue);
    const weather = w.available && isNum(w.tempF) ? `${Math.round(w.tempF)}°F${isNum(w.windMph) ? `, wind ${Math.round(w.windMph)} mph` : ""}${w.dome ? ", indoors" : ""}` : null;
    const sideline = (Array.isArray(b.sideline) ? b.sideline : []).map(name).filter(Boolean);
    const voices = [name(b.playByPlay), name(b.analyst), ...sideline.map((s) => `${s} (sideline)`)].filter(Boolean);
    const network = name(b.network) || name(g.tv);
    const crew = voices.length ? `${network ? `${network}: ` : ""}${voices.join(", ")}` : null;
    const staff = (side, label) => {
      const s = obj(obj(n.coaches)[side]);
      const parts = [["HC", s.headCoach], ["OC", s.offensiveCoordinator], ["DC", s.defensiveCoordinator]].filter(([, v]) => name(v)).map(([k, v]) => `${k} ${name(v)}`);
      return parts.length ? el("span", { class: "game-info__staff" }, el("b", {}, label), ` ${parts.join(" · ")}`) : null;
    };
    const usStaff = staff("us", usAbbr());
    const themStaff = staff("them", themSide().abbr);
    const missing = [crew ? null : "the TV crew", usStaff || themStaff ? null : "the coaches"].filter(Boolean);
    return el(
      "div",
      { class: "game-info", "aria-label": "Game details" },
      el("div", { class: "game-info__line" }, [venue, weather, crew ? el("span", {}, el("b", {}, "TV "), crew) : network ? `on ${network}` : null].filter(Boolean).flatMap((part, i) => (i ? [el("span", { class: "game-info__dot", "aria-hidden": "true" }, " · "), part] : [part]))),
      usStaff || themStaff ? el("div", { class: "game-info__line" }, usStaff, usStaff && themStaff ? el("span", { class: "game-info__dot", "aria-hidden": "true" }, "  |  ") : null, themStaff) : null,
      missing.length ? el("p", { class: "game-info__hint" }, `Add ${missing.join(" and ")} with the notes prompt on the `, el("a", { href: "#program" }, "Game program"), ".") : null,
    );
  }

  // --- live and postgame ---------------------------------------------------------------------------

  function stripFor(s) {
    const usHome = s.home === usTeam();
    const usPts = usHome ? s.homeScore : s.awayScore;
    const themPts = usHome ? s.awayScore : s.homeScore;
    const possession = s.possession === usTeam() ? "us" : s.possession ? "them" : null;
    return strip({ us: { abbr: usAbbr(), points: usPts, timeouts: null }, them: { abbr: themSide().abbr, points: themPts, timeouts: null }, status: s.status === "final" ? "final" : s.status === "pre" ? "pre" : "live", period: s.period, clock: s.clock, possession, down: s.down, distance: s.distance, yardsToGoal: s.yardsToGoal, pill: pillNow(), sticky: true });
  }

  // --- Phase 12: splits, tendencies, drive summary, fourth down, sync ---------------------------------

  const SPLIT_ROWS = [
    ["Plays", "plays", "0f"],
    ["Yards", "yards", "0f"],
    ["Yards per play", "yardsPerPlay", "1f"],
    ["Success", "success", "madeOf"],
    ["EPA per play (no TD plays)", "epaPerPlay", "+2f"],
    ["20+ yard plays", "explosive", "0f"],
    ["Turnovers", "turnovers", "0f"],
    ["3rd downs", "thirdDown", "madeOf"],
  ];

  function splitsTable(splits, team) {
    const periods = Array.isArray(splits?.periods) ? splits.periods.filter((p) => typeof p === "string") : [];
    const byPeriod = obj(obj(splits?.teams)[team]);
    const keys = [...periods, "Game"];
    const rows = SPLIT_ROWS.map(([label, key, format]) => {
      const row = { label };
      for (const period of keys) {
        const cell = obj(byPeriod[period])[key];
        row[period] = format === "madeOf" ? madeOf(cell) : isNum(cell) ? fmtStat(cell, format) : DASH;
      }
      return row;
    });
    return statTable({ compact: true, columns: [{ key: "label", label: "Per quarter", kind: "text", sortable: false }, ...keys.map((k) => ({ key: k, label: k, kind: "text", sortable: false }))], rows });
  }

  function tendencyTable(tendencies, team) {
    const rows = records(obj(tendencies)[team]).map((r) => ({
      label: text(r.label),
      plays: isNum(r.plays) ? r.plays : 0,
      passRate: isNum(r.passRate) ? fmtPct(r.passRate) : DASH,
      run: madeOf(r.runSuccess),
      pass: madeOf(r.passSuccess),
    }));
    if (!rows.some((r) => r.plays > 0)) return note("No snaps yet.");
    return statTable({ compact: true, columns: [{ key: "label", label: "Situation", kind: "text", sortable: false }, { key: "plays", label: "Plays", sortable: false }, { key: "passRate", label: "Pass %", kind: "text", sortable: false }, { key: "run", label: "Run success", kind: "text", sortable: false }, { key: "pass", label: "Pass success", kind: "text", sortable: false }], rows });
  }

  function splitsBand(s) {
    const splits = obj(s.splits);
    const notes = Array.isArray(splits.notes) ? splits.notes.filter((n) => typeof n === "string" && n) : [];
    const has = Array.isArray(splits.periods) && splits.periods.length > 0;
    const us = usTeam();
    const them = themSide().name;
    if (!has) return band({ title: "Splits", collapsible: false, state: { status: "empty", message: "Splits appear after the first snap." } });
    return [
      band({ title: "Quarter by quarter", collapsible: false, summary: "from the play log", body: () => el("div", {}, notes.length ? el("ul", { class: "note-list" }, notes.map((n) => el("li", {}, n))) : note("Nothing stands out between the quarters yet."), el("h3", { style: { padding: "12px 12px 4px", color: "var(--fog)" } }, usWords()), splitsTable(splits, us), el("h3", { style: { padding: "12px 12px 4px", color: "var(--fog)" } }, text(them)), splitsTable(splits, them)) }),
      band({ title: "Tendencies by situation", collapsible: false, summary: "run or pass, and success", body: () => el("div", {}, el("h3", { style: { padding: "12px 12px 4px", color: "var(--fog)" } }, usWords()), tendencyTable(s.tendencies, us), el("h3", { style: { padding: "12px 12px 4px", color: "var(--fog)" } }, text(them)), tendencyTable(s.tendencies, them), note("Passing downs: 2nd and 8 or more, 3rd or 4th and 5 or more (CFBD's tags when the feed sends them). Success is CFBD's.")) }),
    ];
  }

  function driveSummaryTable(s) {
    const summary = obj(s.driveSummary);
    const us = obj(summary[usTeam()]);
    const them = obj(summary[themSide().name]);
    if (!isNum(us.drives) && !isNum(them.drives)) return null;
    const spec = [["Finished drives", "drives", "0f"], ["Points on drives", "points", "0f"], ["Points per drive", "pointsPerDrive", "2f"], ["Three-and-outs", "threeAndOuts", "0f"], ["Turnovers", "turnovers", "0f"], ["Scoring chances (1st down at the 40 or closer)", "opportunities", "0f"], ["Points per chance", "pointsPerOpportunity", "2f"]];
    const rows = spec.map(([label, key, format]) => ({ label, us: isNum(us[key]) ? fmtStat(us[key], format) : DASH, them: isNum(them[key]) ? fmtStat(them[key], format) : DASH }));
    return statTable({ compact: true, columns: [{ key: "label", label: "Drives", kind: "text", sortable: false }, { key: "us", label: usAbbr(), kind: "text", sortable: false }, { key: "them", label: themSide().abbr, kind: "text", sortable: false }], rows });
  }

  function fourthDownBlock(s) {
    const f = s.fourthDown;
    if (!f || typeof f !== "object" || !isNum(f.breakEven)) return null;
    const offense = s.possession === usTeam() ? usAbbr() : s.possession ? themSide().abbr : DASH;
    const ep = (v) => (isNum(v) ? `${v >= 0 ? "+" : ""}${v.toFixed(1)}` : DASH);
    const rows = [{ option: "Go for it", ep: `${ep(f.go?.success)} if it converts, ${ep(f.go?.fail)} if not`, note: `Breaks even at ${fmtPct(f.breakEven)} to convert` }];
    if (f.fieldGoal && typeof f.fieldGoal === "object") rows.push({ option: `Field goal, ${text(f.fieldGoal.distance)} yd`, ep: ep(f.fieldGoal.ep), note: isNum(f.fieldGoal.makeChance) ? `${fmtPct(f.fieldGoal.makeChance)} to make` : DASH });
    if (f.punt && typeof f.punt === "object") rows.push({ option: "Punt (40 net)", ep: ep(f.punt.ep), note: DASH });
    return el(
      "div",
      { class: "fourth-down" },
      el("h3", { style: { padding: "12px 12px 4px", color: "var(--fog)" } }, `${offense} ${downText(f.down, f.distance) || "4th down"}, ${text(f.yardsToGoal)} to goal: go or kick?`),
      statTable({ compact: true, columns: [{ key: "option", label: "Choice", kind: "text", sortable: false }, { key: "ep", label: "Expected points", kind: "text", sortable: false }, { key: "note", label: "", kind: "text", sortable: false }], rows }),
      note(`Going for it beats the ${f.best === "fieldGoal" ? "field goal" : "punt"} when the chance to convert is above ${fmtPct(f.breakEven)}. From CFBD's expected points; a conversion counts as gaining exactly the line to gain.`),
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
  function leadersNote(s) {
    const sources = Object.values(obj(s.playerStatsSource));
    if (!sources.includes("plays")) return "From CFBD's box score.";
    return sources.includes("box") ? "From the box score where CFBD has posted it, else from the play-by-play." : "From the play-by-play until CFBD posts the box score; no tackles yet.";
  }

  function sheetFor(s) {
    const usHome = s.home === usTeam();
    const usBox = mergedBox(s, usTeam());
    const themBox = mergedBox(s, themSide().name);
    const pregame = state.program?.pregame?.usWinProbability;
    const leaders = leadersFromState(s, usTeam());
    const lastPlay = s.lastPlay && typeof s.lastPlay === "object" ? s.lastPlay : null;
    const judged = typeof lastPlay?.success === "boolean";
    // CFBD's own team rate carries no counts; a server from before Phase 10a counted the play log itself.
    const rateSource = isNum(usBox.successCounts?.judged) || isNum(themBox.successCounts?.judged) ? "play log" : "CFBD";
    const statsNote = s.boxScore ? "Yards, downs, and turnovers from the box score; plays from the play log; success rate from CFBD." : "From the play log until CFBD posts the box score; success rate from CFBD.";
    const sheet = el("div", { class: "sheet sheet--live sheet--remote" });
    sheet.append(
      band({ id: "live-score", title: "Score by quarter", kind: "neutral", area: "score", collapsible: false, summary: s.status === "final" ? "Final" : "", body: () => quarterLine({ us: { abbr: usAbbr(), scores: usHome ? s.homeLineScores : s.awayLineScores, total: usHome ? s.homeScore : s.awayScore }, them: { abbr: themSide().abbr, scores: usHome ? s.awayLineScores : s.homeLineScores, total: usHome ? s.awayScore : s.homeScore } }) }),
      band({ id: "live-stats", title: "Team stats", kind: "neutral", area: "stats", summary: `${text(usBox.totalYards)} to ${text(themBox.totalYards)} yds`, state: s.counts?.plays ? { status: "ready", updatedText: statsNote } : { status: "empty", message: "Team stats appear after the first play." }, body: () => el("div", {}, teamStatsTable({ us: { abbr: usAbbr(), box: usBox }, them: { abbr: themSide().abbr, box: themBox } }), feedStatsTable(s)) }),
      band({
        id: "live-wp",
        title: "Win probability",
        kind: "neutral",
        area: "wp",
        summary: judged ? `Last play: ${lastPlay.success ? "success" : "failed"}` : "",
        body: () => el("div", {}, wpBlock(s, usHome, pregame), fourthDownBlock(s), successRow({ play: lastPlay, offenseAbbr: lastPlay?.offense === usTeam() ? usAbbr() : themSide().abbr, us: { abbr: usAbbr(), rate: usBox.successRate, counts: usBox.successCounts }, them: { abbr: themSide().abbr, rate: themBox.successRate, counts: themBox.successCounts }, source: rateSource })),
      }),
      band({
        id: "live-chart",
        title: `Shot chart: ${usAbbr()} offense`,
        kind: "neutral",
        area: "chart",
        summary: state.chartView === "runs" ? "runs by lane" : "passes by zone",
        state: obj(obj(s.shotChart)[usTeam()]).passes ? { status: "ready" } : { status: "empty", message: "The chart fills in with the first pass or run." },
        body: () => shotChart({ chart: obj(s.shotChart)[usTeam()], view: state.chartView, team: usWords(), onView: (view) => { state.chartView = view; render(); } }),
      }),
      band({ id: "live-leaders", title: "Leaders", kind: "neutral", area: "leaders", summary: leaders && Object.values(obj(s.playerStatsSource)).includes("box") ? "tap a player for the card" : "", state: leaders ? { status: "ready", updatedText: leadersNote(s) } : { status: "empty", message: "Player lines appear after the first pass or run." }, body: () => leadersGrid({ categories: leaders || [], usAbbr: usAbbr(), themAbbr: themSide().abbr, onTap: (player, side) => (hasId(player?.playerId) ? openPlayer(player.playerId, { ...player, isUs: side === "us" }) : null) }) }),
    );
    return sheet;
  }

  // --- the side sheets ---------------------------------------------------------------------------

  /** The sort the reader picked for one table in the open sheet, else the table's default. */
  const sheetSort = (key, fallback) => state.sheet?.sorts[key] || fallback;
  const keepSort = (key) => (sort) => {
    if (state.sheet) state.sheet.sorts[key] = sort;
  };

  function boxTables(s, team, them) {
    const cats = obj(obj(s.playerStats)[team]);
    const names = Object.keys(BOX_COLUMNS).filter((name) => records(cats[name]).length);
    if (!names.length) return note("Player lines appear after the first pass or run.");
    const fromPlays = obj(s.playerStatsSource)[team] === "plays";
    return el(
      "div",
      {},
      fromPlays ? note("Passing, rushing, and receiving from the play-by-play until CFBD posts the box score.") : null,
      names.map((name) => {
        const columns = BOX_COLUMNS[name];
        const key = `${them ? "them" : "us"}:${name}`;
        const rows = records(cats[name]).map((r) => ({ name: r.name, playerId: r.playerId, ...obj(r.stats) }));
        return statTable({ columns, rows, compact: true, sort: sheetSort(key, { key: columns[2]?.key || columns[1].key, dir: "descending" }), onSort: keepSort(key), onRowTap: (row) => (hasId(row.playerId) ? openPlayer(row.playerId, { ...row, isUs: !them }) : null) });
      }),
    );
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
      { id: "box", label: "Box score", hint: "both teams", body: () => [band({ title: usWords(), kind: "us", collapsible: false, body: () => boxTables(s, usTeam(), false) }), band({ title: themSide().name, kind: "them", collapsible: false, body: () => boxTables(s, themSide().name, true) })] },
      { id: "drives", label: "Drives", hint: `${isNum(s.counts?.drives) ? s.counts.drives : 0} drives`, body: () => band({ title: "Drives", collapsible: false, body: () => (drives.length ? el("div", {}, driveSummaryTable(s), driveList({ drives, us: usSide(), them: themSide(), currentId: s.currentDriveId ?? null })) : note("Drives appear after kickoff.")) }) },
      { id: "splits", label: "Splits", hint: splitsHint(s), body: () => splitsBand(s) },
      { id: "plays", label: "Plays", hint: `${isNum(s.counts?.plays) ? s.counts.plays : 0} plays`, body: () => band({ title: "Play by play", collapsible: false, body: () => (plays.length ? playLog({ plays, us: usSide(), them: themSide(), maxHeight: 9999, filter: state.sheet?.filter || "all", onFilter: (id) => { if (state.sheet) state.sheet.filter = id; } }) : note("Plays appear after kickoff.")) }) },
      { id: "situation", label: "Situation", hint: `3rd ${text(usBox.thirdDown?.made)}-${text(usBox.thirdDown?.of)}`, body: () => band({ title: "Situation", collapsible: false, body: () => situationGrid({ us: { abbr: usAbbr(), box: usBox }, them: { abbr: themSide().abbr, box: themBox } }) }) },
      { id: "edges", label: "Edges", hint: "season ranks", body: () => band({ title: "Matchup edges", collapsible: false, body: () => (edges.length ? statTable({ compact: true, sortable: true, columns: [{ key: "label", label: "Matchup", kind: "text", sortable: false }, { key: "usRank", label: `${usSide().abbr} rank`, sortable: false }, { key: "themRank", label: `${themSide().abbr} rank`, sortable: false }, { key: "edge", label: "Edge", format: "+0f", sortable: false }], rows: edges }) : note("Edges appear once both teams have played.")) }) },
      { id: "weather", label: "Weather", hint: "game site", body: () => band({ title: "Weather", collapsible: false, body: () => el("div", { style: { padding: "12px" } }, weather.available ? weatherRow({ kickoffText: fmtTime(p.game?.kickoff), tempF: weather.tempF, windMph: weather.windMph, windDir: typeof weather.windDir === "string" ? weather.windDir : null, sky: weather.sky, precipChance: weather.precipChance, indoors: Boolean(weather.dome), source: weather.source }) : weatherRow({ kickoffText: fmtTime(p.game?.kickoff), note: weather.error || "No forecast." })) }) },
      { id: "visitors", label: "Visitors", hint: "recruits", body: () => visitorsBand() },
      { id: "injuries", label: "Injuries", hint: "availability", body: () => band({ title: "Availability report", collapsible: false, body: () => (availability.length ? availabilityTable({ rows: availability, source: p.notes?.availabilitySource, updatedAt: p.notes?.availabilityUpdatedAt }) : note("No availability report for this game yet.")) }) },
      // 2026-10-02: who starts and who is behind them, from the notes file's published charts (ui/lineups.js)
      { id: "lineups", label: "Lineups", hint: "starters, depth", body: () => [band({ title: "Starting lineups", collapsible: false, body: () => startersBlock({ lineups: p.notes?.lineups, us: p.us, them: p.them, availability, onPlayer: (row) => openPlayer(row.playerId, { ...row.player, name: row.name, position: row.slot, isUs: row.isUs !== false }) }) }), band({ title: "Depth charts", collapsible: false, body: () => depthBlock({ lineups: p.notes?.lineups, us: p.us, them: p.them, availability }) })] },
      { id: "scores", label: "Scores", hint: "every FBS game", body: () => scoresBand() },
      { id: "value", label: "Play value", hint: "PPA", body: () => ppaBand(s) },
    ];
  }

  function visitorsContent(v) {
    const columns = [{ key: "name", label: "Recruit", kind: "text", sub: "position", sortable: false }, { key: "stars", label: "Stars", sortable: false }, { key: "highSchool", label: "High school", kind: "text", sortable: false }, { key: "status", label: "Status", kind: "text", sortable: false }];
    const side = (title, rows) => el("div", {}, el("h3", { style: { padding: "12px 12px 4px", color: "var(--fog)" } }, title), rows.length ? statTable({ compact: true, columns, rows }) : note("No visitors listed."));
    return band({ title: "Recruits on hand", collapsible: false, body: () => el("div", {}, v.note ? note(text(v.note)) : null, el("div", { class: "twocol" }, side(`Visiting ${usTeam()}`, records(v.home)), side(`Visiting ${text(v.opponent)}`, records(v.away)))) });
  }

  /** Recruits on hand: fetched when the sheet opens, kept ten minutes, never refetched per play. */
  function visitorsBand() {
    const cached = state.visitors;
    if (cached && Date.now() - cached.at < VISITORS_TTL_MS) return visitorsContent(cached.data);
    const host = band({ title: "Recruits on hand", collapsible: false, state: { status: "loading" } });
    fetchJson("/api/recruiting")
      .then((envelope) => {
        const v = obj(envelope?.data?.visitors);
        state.visitors = { data: v, at: Date.now() };
        host.replaceWith(visitorsContent(v));
      })
      .catch((error) => {
        console.warn(`Live sheet: the visitors did not load: ${error?.message || error}`);
        host.replaceWith(band({ title: "Recruits on hand", collapsible: false, state: { status: "error", message: `${error?.message || "The request failed"}. Close the panel and open it again to retry.` } }));
      });
    return host;
  }

  /** A panel that fails to draw shows an error inside the sheet instead of breaking the button. */
  function safeBody(item) {
    try {
      return item.body();
    } catch (error) {
      console.error(`Live sheet: the ${item.label} panel could not be drawn.`, error);
      return band({ title: text(item.label), collapsible: false, state: { status: "error", message: "This panel could not be drawn. Close it and open it again." }, errorLead: "Display error." });
    }
  }

  function openItem(id) {
    const item = state.items.find((i) => i.id === id);
    if (!item || !container) return;
    closeSheet();
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
      console.error(`Live sheet: the ${item.label} panel could not be redrawn; the last good one stays.`, error);
      state.sheetError = true;
    }
    if (state.sheetError !== hadError) refreshPill();
  }

  function liveParts(s) {
    const stripEl = stripFor(s);
    return {
      top: [stripEl, gameInfo(state.program)], // siblings: the strip stays sticky against the page, not a wrapper
      strip: stripEl,
      middle: [sheetFor(s), s.status === "final" ? el("p", { class: "note" }, "Final. This game is saved to the archive.") : null],
      bottom: null,
      items: remoteItems(s),
    };
  }

  // --- the frame and the render ----------------------------------------------------------------------

  function buildFrame() {
    const slot = () => el("div", { style: { display: "contents" } });
    slots = { top: slot(), middle: slot(), bottom: slot() };
    tickerHost = el("div", { class: "live-ticker" });
    state.delayButton = el("button", { class: "btn btn--quiet delay-button", type: "button", "aria-haspopup": "dialog", onclick: () => openDelaySheet() }, delayLabel());
    frame = el("div", {}, slots.top, el("div", { class: "live-tools" }, state.delayButton), tickerHost, slots.middle, slots.bottom);
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
      console.error("Live sheet: this update could not be drawn; the last good screen stays up.", error);
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
    frame.className = pregame ? "season" : "";
    frame.style.gridTemplateColumns = pregame ? "minmax(0, 1fr)" : "";
    replaceWith(slots.top, view.top);
    replaceWith(slots.middle, view.middle);
    replaceWith(slots.bottom, view.bottom);
    state.strip = view.strip || null;
    if (pregame) {
      closeSheet();
      if (state.bar) state.bar.style.display = "none";
    } else {
      state.items = view.items;
      if (!state.bar) {
        state.bar = remoteBar({ items: view.items, onOpen: openItem });
        frame.append(state.bar);
      }
      state.bar.style.display = "";
      for (const item of view.items) state.bar.setHint(item.id, item.hint);
      if (state.sheet) state.bar.setActive(state.sheet.id);
      refreshOpenSheet();
    }
    refreshPill();
    if (!pregame && state.live.status === "final") maybeLoadAnalytics();
  }

  // --- the stream --------------------------------------------------------------------------------------

  function parseFrame(event, name) {
    try {
      return JSON.parse(event.data);
    } catch (error) {
      console.warn(`Live sheet: dropped a ${name} frame that was not JSON.`, error);
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
      console.error("Live sheet: the event stream could not be opened.", error);
      state.errors += 1;
      startFallback();
      scheduleRetry();
      refreshPill();
      return;
    }
    state.source = source;
    state.helloSeen = false;
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
        if (next !== null) console.warn("Live sheet: dropped a state frame that was not an object.");
        refreshPill();
        return;
      }
      if (Object.prototype.hasOwnProperty.call(next, "feed")) {
        state.pingCapable = true;
        takeFeed(next.feed); // during play the stream is never quiet enough for a ping, so each frame carries the feed health
      }
      state.live = next;
      state.mode = next.status === "final" ? "postgame" : "live";
      render();
      holdAwake(next.status !== "final");
    });
    source.onerror = () => {
      if (state.source !== source) return;
      state.errors += 1;
      if (state.errors === 1) console.warn("Live sheet: the event stream dropped; polling the state every 15 s until it is back.");
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
      const data = envelope?.data;
      state.polled = true;
      if (data && typeof data === "object" && !Array.isArray(data) && data.gameId) {
        if (data.engine && typeof data.engine === "object" && Object.prototype.hasOwnProperty.call(data.engine, "feed")) takeFeed(data.engine.feed);
        state.live = data;
        state.mode = data.status === "final" ? "postgame" : "live";
        render();
        holdAwake(data.status !== "final");
      } else refreshPill();
    } catch (error) {
      if (!container) return;
      if (state.polled || !warned.has("poll")) console.warn(`Live sheet: the fallback poll failed: ${error?.message || error}`);
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
      console.warn(`Live sheet: nothing from the stream for ${Math.round(silent / 1000)} s; reconnecting.`);
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
      if (open && state.mode === "pregame") {
        state.mode = "live";
        connect();
      }
    } catch (error) {
      if (!container) return;
      const message = error?.message || "Could not reach the server";
      if (message !== state.statusError) console.warn(`Live sheet: the status check failed: ${message}`);
      state.statusError = message;
    }
    if (retryProgram && !state.program && container) {
      await loadProgram();
      if (container && state.program && (state.mode === "pregame" || !state.live)) render();
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
      warnOnce("wake-lock", "Live sheet: the screen may sleep; the wake lock was refused.", error?.message || error);
    } finally {
      state.wakeLockPending = false;
    }
  }

  function releaseWakeLock() {
    const sentinel = state.wakeLock;
    state.wakeLock = null;
    if (sentinel && !sentinel.released) sentinel.release().catch((error) => console.warn(`Live sheet: the wake lock did not release: ${error?.message || error}`));
  }

  function onVisible() {
    if (!container || document.visibilityState !== "visible") return;
    if (state.mode !== "pregame" && (!state.source || state.source.readyState === SOURCE_CLOSED)) connect();
    if (wantAwake()) holdAwake(true);
    checkWindow();
  }

  return {
    async mount(target) {
      container = target;
      container.replaceChildren(el("div", { class: "season", style: { gridTemplateColumns: "minmax(0, 1fr)" } }, band({ title: "Live sheet", collapsible: false, state: { status: "loading" } })));
      state.pillKey = "quiet|Loading";
      setStatus({ kind: "quiet", label: "Loading" });
      buildFrame();
      document.addEventListener("visibilitychange", onVisible);
      state.watchTimer = setInterval(watch, WATCH_TICK_MS);
      await loadProgram();
      if (!container) return; // left before the program arrived
      render();
      await checkWindow({ retryProgram: false });
      if (!container) return;
      state.statusTimer = setInterval(checkWindow, STATUS_POLL_MS);
      loadTicker();
      state.tickerTimer = setInterval(loadTicker, TICKER_POLL_MS);
    },
    refresh() {
      return checkWindow();
    },
    unmount() {
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
      releaseWakeLock();
      if (state.tickerNode && typeof state.tickerNode.destroy === "function") state.tickerNode.destroy();
      state.tickerNode = null;
      document.removeEventListener("visibilitychange", onVisible);
      container = null;
      if (slider && typeof slider.flush === "function") slider.flush(); // a nudge still settling is saved
    },
  };
}

export { fmtPct };
