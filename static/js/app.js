// Kickoff Companion: the app. The shell from the design system, a hash router for the views,
// and the views built so far: Season (Phase 3), Leaders, Roster, Recruiting (Phase 4),
// Newspaper, Game program, team pages (Phase 5), the Live sheet (Phase 7), and the radio (Phase 8),
// which lives in the shell so audio survives view changes. Views that arrive later say so.
// Opening rule (Phase 17 #32): the app always opens on the Game program, game day included; it never
// switches itself to the Live sheet. While our game is under way (the server's window.inProgress) the
// Live sheet's tab carries a LIVE marker (#25), checked once a minute.
//
// Phase 16 (stream F) router contract:
//   Routes are "#<id>=<arg>?<query>" (parseRoute in ui/national-link.js); the query is part of the route's
//   key, so the same page with another highlighted team redraws. Every factory is called as
//   factory(opts, arg, focus, params); season, leaders, ratings and recruiting receive { ...opts, arg, params }
//   (their streams decide what the arg means: "polls:AP", "<board>:<scope>", a sort key, a focus).
//   Before a new route mounts, document hears "kickoff:route" (detail: the route); open side sheets and the
//   player card close on it. Leaving a page keeps its scroll in history.state, and Back puts it back after
//   the view's first draw; history.state.depth counts the app's own entries (backRow uses it). A cold start at the
//   board (the kiosk, a bookmark, the home-screen icon) puts In Game under it first, so Back never leaves the app.
//   Item 6 (owner 2026-10-11): a side sheet, the player card and the menu each hold one history entry of the same page
//   (ui/layers.js), so Back closes the top layer and the page stays: such a pop keeps the route and its scroll. A tab or
//   menu item takes the layer's entry for the new page (goTo), so no dead entry is left behind.
//   The team route highlights no tab; the national list keeps the tab it was opened from.
//   Pull down at the top of a page, or 'r' on a keyboard, refreshes the current view.
//   Nothing opens by itself over the page (item 6, step C): "Not loaded yet" is a note on the Pre-Game Program and a dot
//   on the status pill (ui/readiness.js), a guest's welcome a note on the page it lands on (ui/guest.js).
//   The loading screen can always be left (item 6, step E): its bar has Reload from the first frame, index.html's watchdog
//   says "Could not load" and retries once when the app has not drawn its Menu in 10 s, the settings and the identity
//   each give up after 5 s, and a reload after a server restart waits until the server answers.

import { confLabel, loadIdentity, ours, usLabel, usSchool } from "./identity.js";
import { installClientLog } from "./client-log.js";
import { applyTextScale, applyTheme, getPrefs, loadPrefs } from "./prefs.js";
import { loadRadioSources, mountRadio } from "./radio.js";
import { el, isNum } from "./ui/dom.js";
import { keepScreenOn } from "./wake.js";
import { addAliases, enableHints } from "./ui/hints.js";
import { parseRoute, routeKey } from "./ui/national-link.js";
import { currentStop, loadStops, onStops, stopsNow, weekOf } from "./stops.js"; // the season as one line (owner 2026-10-30)
import { installNationalLinks } from "./ui/national-sheet.js";
import { installPullToRefresh } from "./ui/pull-refresh.js";
import { installToTop } from "./ui/to-top.js"; // the Top button (owner 2026-11-15)
import { MENU, shell } from "./ui/shell.js";
import { band } from "./ui/states.js";
import { fetchJson } from "./views/common.js";
import { createLeadersView } from "./views/leaders.js";
import { createLiveView } from "./views/live.js";
import { createNewspaperView } from "./views/newspaper.js";
import { createReaderView } from "./views/reader.js"; // FEAT-14: a copied story whole
import { createTop25View } from "./views/top25.js";
import { createImperialismView } from "./views/imperialism.js"; // FEAT-17: the Imperialism Map
import { createProgramView } from "./views/program.js";
import { createRatingsView } from "./views/ratings.js";
import { createConferenceView } from "./views/conference.js"; // the conference page (owner 2026-11-02): any conference, ours first
import { createRecruitingView } from "./views/recruiting.js";
import { createRosterView } from "./views/roster.js";
import { createSeasonView } from "./views/season.js";
import { createArchiveView } from "./views/archive.js";
import { createGlossaryView } from "./views/glossary.js";
import { createNationalView } from "./views/national.js";
import { createSettingsView } from "./views/settings.js";
import { createStatsView } from "./views/stats.js"; // ENH-10: the Stats menu's full lists
import { gameLine, loadProgram, openBand, openFromMenu } from "./views/panels.js"; // the menu's tables opened wide (the layout pass, 2026-10-22)
import { watchBands } from "./ui/band-open.js"; // ENH-46 (owner 2026-11-10): a band opens by itself from its own head, the menu lists pages
import { openTeam } from "./views/team.js"; // the team sheet; a team page is My Team's page of that team (wave 3, 2026-11-01)
import { createBoxView } from "./views/box.js";
import { bandTarget, createBandView, registerPages } from "./views/band.js"; // owner 2026-10-28: every band its own page
import { installCvd } from "./ui/cvd.js";
import { startGuestMode } from "./ui/guest.js";
import { installSpoiler } from "./ui/spoiler.js";
import { startReadiness } from "./ui/readiness.js";
import { startTrivia } from "./ui/trivia.js"; // the trivia (owner 2026-10-21): the join and the question popups
import { openTodo } from "./ui/todo.js"; // the To do flyout (the layout pass, 2026-10-22): the notes off the page
import { openFeedback } from "./ui/feedback.js"; // Send feedback with the logs (owner 2026-10-23)
import { openAsk } from "./ui/ask.js"; // FEAT-12: Ask about this page
import { refreshRow } from "./ui/claude-refresh.js"; // batch 4: Run with Claude at the top of the menu
import { startTrail } from "./ui/trail.js"; // what this tablet did lately, sent with a report
import { closeLayers, goTo, installLayerHistory, stepOverLeftovers, toTop } from "./ui/layers.js";
import { createBoardView, seedBoardHistory } from "./views/board.js";
import { createInviteView } from "./views/invite.js";
import { createPreseasonView } from "./views/preseason.js";
import { createInjuriesView } from "./views/injuries.js";
import { createSeasonsView } from "./views/seasons.js"; // rollover R2: the Seasons list
import { pastYear } from "./ui/past.js";
import { createPromptsView } from "./views/prompts.js";
import { createTriviaView } from "./views/trivia.js";
import { addNote, removeNote } from "./ui/page-notes.js";
import { claudeSignedOutSince, seasonSwitchNow, signedOutWords } from "./build.js";
import { installRunBar } from "./ui/run-bar.js";
import { reloadWhenServerAnswers, restartFlow, updateFlow } from "./ui/restart.js";
import { openSearch } from "./views/search.js";
import { clearViewing, onViewing, viewing, viewingInfo, viewRoute } from "./viewing.js"; // batch 3: switch teams on this device
import { openTeamSwitch } from "./ui/team-switch.js";
import { onDeviceGame } from "./watching.js"; // batch 3: another game on this device
import { createCompareView } from "./views/compare.js"; // batch 3: two players side by side

const BUILT = {
  season: (opts, arg, focus, params) => createSeasonView({ ...opts, arg, params }),
  leaders: (opts, arg, focus, params) => createLeadersView({ ...opts, arg, params }),
  roster: (opts, arg, focus, params) => createRosterView({ ...opts, params }), // FEAT-5: ?team= any FBS team
  recruiting: (opts, arg, focus, params) => createRecruitingView({ ...opts, arg, params }),
  newspaper: (opts, arg, focus, params) => createNewspaperView({ ...opts, edition: arg, params }), // #newspaper=week-6 opens that week folded open (FEAT-14); ?poll=Coaches opens the polls on that poll (wave 3, 2026-11-01)
  story: (opts, arg, focus, params) => createReaderView({ ...opts, id: arg, season: params?.season }), // FEAT-14: the reader, #story=<id>; ?season=2026 a past season's (rollover R3)
  top25: (opts) => createTop25View(opts), // item 11: every game of the week with an AP Top 25 team
  picks: (opts) => createTop25View(opts), // FEAT-2's page folded into the Top 25 (wave 3, 2026-11-01): the old address lands there
  imperialism: (opts) => createImperialismView(opts), // FEAT-17: the Imperialism Map, in New until he places it
  blame: (opts) => createSeasonView({ ...opts, params: { band: "blame" } }), // FEAT-18's page dissolved into My Team (wave 3, 2026-11-01): the old address lands on the wheel
  program: (opts, arg, focus, params) => createProgramView({ ...opts, gameId: arg && /^\d+$/.test(arg) ? arg : null, focus, team: params?.team, tab: params?.tab, view: params?.view, season: params?.season }), // FEAT-5: any game, ?team= its side; ?tab=pre the Pre-Game as it stood, ?view= a box's switch (the line, 2026-10-30)
  postgame: (opts, arg, focus, params) => createProgramView({ ...opts, gameId: arg && /^\d+$/.test(arg) ? arg : null, focus, team: params?.team, tab: "post", season: params?.season }), // ?season=2026: rollover R2, that season's kept copy // the season as one line: a finished game's Post-Game stop
  team: (opts, arg, focus, params) => createSeasonView({ ...opts, params: { ...(params || {}), team: arg } }), // wave 3 (2026-11-01): a team's page is My Team's page of that team
  box: (opts, arg) => createBoxView({ ...opts, gameId: arg }),
  preseason: (opts) => createPreseasonView(opts), // Phase 17 Part 3a: the season loads and each primary team's preseason // Phase 17 #2: any game's box score, from a W or L square
  live: (opts) => createLiveView(opts),
  archive: (opts, arg) => createArchiveView({ ...opts, gameId: arg }),
  settings: (opts, arg) => createSettingsView({ ...opts, arg }), // #settings=radio opens that section (2026-10-16); the Profile page since 2026-10-22
  profile: (opts, arg) => createSettingsView({ ...opts, arg }), // the layout pass (owner 2026-10-22): "a Profile that shows your settings and setup information"
  ratings: (opts, arg, focus, params) => createRatingsView({ ...opts, arg, params }),
  conference: (opts, arg, focus, params) => createConferenceView({ ...opts, arg, params }), // the conference page (2026-11-02): #conference ours, #conference=<name> another
  stats: (opts, arg, focus, params) => createStatsView({ ...opts, arg, params }), // ENH-10: #stats=passing?view=teams, every team and every qualified player
  glossary: (opts, arg) => createGlossaryView({ ...opts, focusId: arg }),
  national: (opts, arg, focus, params) => createNationalView({ ...opts, arg, params }), // Phase 16 NV: a chip's list as a page
  myteams: (opts, arg, focus, params) => createSeasonView({ ...opts, params }), // board 9 (owner 2026-10-22): My Teams is the Season page's window now; the old address opens it
  invite: (opts) => createInviteView(opts), // Phase 18.6: the QR code for friends
  review: (opts, arg) => createSeasonView({ ...opts, review: true, past: pastYear(arg) }), // rollover R2: #review=2026 is that season's review as kept; Wave 7 (owner 2026-11-15): the season in review is My Team at the season's end (Phase 19's page told it from the schedule alone)
  board: (opts) => createBoardView(opts), // Phase 18.6: the Live sheet made for a wall
  seasons: (opts) => createSeasonsView(opts), // rollover R2 (owner 2026-11-15): this season and the ones before, as kept
  injuries: (opts) => createInjuriesView(opts), // owner 2026-10-10: our injuries through the season, from the game notes
  prompts: (opts) => createPromptsView(opts), // the Prompts phase (2026-10-13): every prompt, its Copy, Paste and Run, the one run, the schedule
  trivia: (opts) => createTriviaView(opts), // the trivia (2026-10-21): the room's board by team name, today's answers, the rules
  band: (opts, arg, focus, params) => createBandView({ ...opts, arg, params }), // owner 2026-10-28: #band=<page>:<band>, one band alone across the page
  compare: (opts, arg, focus, params) => createCompareView({ ...opts, arg, params }), // batch 3 (owner 2026-11-16): #compare=<id>,<id>, two players side by side
  setup: (opts) => createSettingsView(opts), // the Setup page joined the Profile (owner 2026-10-22): the old address lands on the Profile; the menu's Setup opens its flyout (#profile=setup)
};

registerPages(BUILT); // the menu's flyouts and the band's own page mount the router's own views

const LATER = {
  radio: ["Radio", "The team's radio plays from the bar at the bottom of every page; pick the station in Settings."],
};

const VALID = new Set([...Object.keys(BUILT), ...Object.keys(LATER), "radio"]);
const NO_TAB = new Set(["team", "box", "invite", "board", "compare"]); // a team page and a box score belong to no tab (DS-03)
const KEEP_TAB = new Set(["national"]); // a list keeps the tab it was opened from

/** "#program=401856699" -> { id: "program", arg: "401856699" }; "#team=Kansas%20State" -> { id: "team", arg: "Kansas State" } */
function parseHash() {
  return parseRoute(window.location.hash || "", VALID);
}

/** The page a band's own page is drawn from (#band=season:season-polls -> the Season route), else the band route itself. */
function bandPage(route) {
  const target = bandTarget(route.arg, route.params);
  const page = target ? parseRoute(`#${target.address}`, VALID) : null;
  return page && page.id !== "band" ? page : route;
}

function readState() {
  try {
    const state = window.history?.state;
    return state && typeof state === "object" ? state : {};
  } catch {
    return {};
  }
}

function writeState(patch) {
  try {
    window.history.replaceState({ ...readState(), ...patch }, "");
  } catch {
    // replaceState can be refused (rate limits, sandboxing): only the scroll memory is lost
  }
}

function laterView(id) {
  const [title, message] = LATER[id] || ["Not here yet", "This view is not built yet."];
  return el("div", { class: "page" }, band({ id: `later-${id}`, title, collapsible: false, state: { status: "empty", message } }));
}

/** Whether the /api/live/status data says our game is under way: the LIVE marker on the Live sheet's tab. */
export function gameIsLive(statusData) {
  const data = statusData && typeof statusData === "object" ? statusData : null;
  const gameWindow = data && data.window && typeof data.window === "object" ? data.window : null;
  return Boolean(gameWindow) && gameWindow.inProgress === true && data.mode !== "replay";
}

const LIVE_CHECK_MS = 60000;
const DOWN_RETRY_MS = Object.freeze([2000, 4000, 8000]); // a server that does not answer is asked again sooner: it is restarting

/**
 * Keep the LIVE marker current: once now, then every minute and whenever the page comes back into view. A check the
 * server does not answer (it is restarting, owner bug 2026-10-13) is asked again after 2, 4 and 8 s, so the new build's
 * envelope arrives, and the To do's new-version note shows, seconds after the server is back.
 */
function watchLiveGame(page) {
  let busy = false;
  let misses = 0;
  let retry = null;
  const check = async () => {
    if (busy) return;
    busy = true;
    try {
      const delay = Number(getPrefs()?.delaySeconds); // the marker goes by what a sheet this far behind has seen
      const envelope = await fetchJson(`/api/live/status?delay=${Number.isFinite(delay) && delay >= 0 ? Math.round(delay) : 0}`);
      page.setLive(gameIsLive(envelope?.data));
      misses = 0;
    } catch (error) {
      console.warn("Could not check for a live game; the LIVE marker keeps its last state.", error?.message || error);
      const wait = DOWN_RETRY_MS[Math.min(misses, DOWN_RETRY_MS.length - 1)];
      misses += 1;
      clearTimeout(retry);
      retry = setTimeout(check, wait);
    } finally {
      busy = false;
    }
  };
  check();
  setInterval(check, LIVE_CHECK_MS);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") check();
  });
}

const UPDATE_SEEN_KEY = "kickoff.update.seen"; // FEAT-13: the newest commit whose note was closed
const TODAY_SEEN_KEY = "kickoff.today.seen";

/** Today on this device, YYYY-MM-DD. */
function todayKey(now = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/**
 * On this day (wave B, owner 2026-10-13: "the stadium was built 84 years ago today"): the dated events the
 * facts prompt collected, for the teams the app follows and this week's opponent, as the one reminder note, once a day
 * on each device, with its close button. Never a popup.
 */
const CHECK_SEEN_KEY = "kickoff.datacheck.seen"; // ENH-29: the data check whose note was closed

/**
 * ENH-29: the weekly data check found facts the web says are out of date: a To do note for the host, once per check, with
 * the first few and the way to the whole list (Settings, Claude, What Claude learned).
 */
async function startDataCheckNote() {
  if (document.body?.dataset?.role === "guest") return null;
  const envelope = await fetchJson("/api/writing/datacheck/latest");
  const written = envelope?.data?.written && typeof envelope.data.written === "object" ? envelope.data.written : null;
  const findings = (Array.isArray(written?.findings) ? written.findings : []).filter((f) => f && typeof f === "object" && typeof f.subject === "string");
  if (!findings.length || typeof written.writtenAt !== "string") return null;
  let seen = null;
  try {
    seen = window.localStorage.getItem(CHECK_SEEN_KEY);
  } catch {
    seen = null;
  }
  if (seen === written.writtenAt) return null;
  const count = findings.length === 1 ? "1 fact" : `${findings.length} facts`;
  return addNote({
    id: "datacheck",
    title: `The data check found ${count} out of date`,
    body: () => el("div", {}, el("ul", { class: "writing__list" }, findings.slice(0, 3).map((f) => el("li", {}, el("b", {}, `${f.subject}: `), typeof f.webSays === "string" ? f.webSays : "see the check"))), el("p", {}, el("a", { class: "btn btn--quiet", href: "#profile=claude" }, "See the whole check"))),
    onDismiss: () => {
      try {
        window.localStorage.setItem(CHECK_SEEN_KEY, written.writtenAt);
      } catch {
        // no storage: the note comes back next load, the safe direction
      }
    },
  });
}

async function startTodayNote() {
  let seen = null;
  try {
    seen = window.localStorage.getItem(TODAY_SEEN_KEY);
  } catch {
    seen = null;
  }
  if (seen === todayKey()) return null;
  const envelope = await fetchJson("/api/today");
  const events = Array.isArray(envelope?.data?.events) ? envelope.data.events.filter((e) => e && typeof e === "object" && typeof e.event === "string" && isNum(e.years)) : [];
  if (!events.length) return null;
  const line = (e) => `${e.event.trim()}, ${e.years} ${e.years === 1 ? "year" : "years"} ago today${typeof e.school === "string" && e.school ? ` (${e.school})` : ""}.`;
  return addNote({
    id: "today",
    title: "On this day",
    body: () => (events.length === 1 ? el("p", {}, line(events[0])) : el("ul", { class: "plain-list" }, events.slice(0, 6).map((e) => el("li", {}, line(e))))),
    onDismiss: () => {
      try {
        window.localStorage.setItem(TODAY_SEEN_KEY, todayKey());
      } catch {
        // no storage: the note comes back next load
      }
    },
    onShow: () => {
      try {
        window.localStorage.setItem(TODAY_SEEN_KEY, todayKey());
      } catch {
        // as above
      }
    },
  });
}

/**
 * FEAT-13: new commits on GitHub's main (the update check, asked of GitHub at most once an hour): the same note as every
 * other reminder (owner 2026-10-13), once per update on each device; its close button remembers the newest commit. One
 * tap brings the update in and restarts the server with it; the app never updates by itself (owner 2026-10-26). A guest
 * gets no note: only the host updates.
 */
async function startUpdateNote() {
  if (document.body?.dataset?.role === "guest") return null;
  const envelope = await fetchJson("/api/updates");
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
  if (!data || data.canUpdate !== true || !isNum(data.behind) || data.behind < 1) return null;
  const changes = (Array.isArray(data.changes) ? data.changes : []).filter((c) => c && typeof c === "object" && typeof c.subject === "string" && c.subject);
  const newest = typeof changes[0]?.short === "string" ? changes[0].short : `behind-${data.behind}`;
  let seen = null;
  try {
    seen = window.localStorage.getItem(UPDATE_SEEN_KEY);
  } catch {
    seen = null;
  }
  if (seen === newest) return null;
  const said = el("p", { class: "note", role: "status" }, "");
  const go = el("button", { class: "btn btn--primary", type: "button", onclick: async (event) => {
    event.currentTarget.disabled = true;
    await updateFlow({ say: (words) => { said.textContent = words; }, confirmDuringGame: async (message) => window.confirm(`${message} Update anyway?`) });
  } }, "Update now");
  const count = data.behind === 1 ? "1 change" : `${data.behind} changes`;
  return addNote({
    id: "github-update",
    title: `Update ready: ${count}`,
    body: () => el("div", { class: "update-note" },
      changes.length ? el("ul", { class: "update-list" }, ...changes.slice(0, 5).map((c) => el("li", {}, c.subject))) : null,
      changes.length > 5 ? el("p", { class: "note" }, `and ${changes.length - 5} more (Settings, About, lists them all).`) : null,
      data.packagesChange ? el("p", { class: "note" }, "It brings new packages too: the restart takes a few minutes.") : null,
      el("p", {}, go),
      said),
    onDismiss: () => {
      try {
        window.localStorage.setItem(UPDATE_SEEN_KEY, newest);
      } catch {
        // no storage: the note comes back next load, the safe direction
      }
    },
  });
}

/**
 * Phase 12: when the server has a newer build than this page (a restart, or a file changed under static/), the page needs
 * the new code. Since 2026-11-14 (owner: "make sure the page doesnt refresh when browsing", then "Say so, never reload")
 * it never reloads under the reader: the To do says a new version is on the server, Reload brings it in now, and opening
 * another page brings it in then, the reload landing on the page opened. The device that tapped Update or Restart reloads
 * by itself (ui/restart.js). Item 6, step E: the page reloads only once the server answers (ui/restart.js
 * reloadWhenServerAnswers), never into a server that is still restarting or a Wi-Fi still reconnecting after the iPad wakes.
 */
const RELOADED_AT_KEY = "kickoff.update.reloadedAt";
const RELOAD_LOOP_MS = 60000;

/**
 * A reload for a new build is remembered for a minute (owner bug 2026-10-13: "the page refreshes every 5 seconds"): when
 * the server keeps answering with a different build, as two servers on one address do, the page reloads once and then
 * keeps still with the note, instead of looping.
 */
function reloadedJustNow() {
  try {
    const at = Number(window.sessionStorage.getItem(RELOADED_AT_KEY));
    return Number.isFinite(at) && at > 0 && Date.now() - at < RELOAD_LOOP_MS;
  } catch {
    return false;
  }
}

function rememberReload() {
  try {
    window.sessionStorage.setItem(RELOADED_AT_KEY, String(Date.now()));
  } catch {
    // no storage: the loop guard cannot remember; the note still shows
  }
}

function watchForUpdates() {
  let pending = false;
  document.addEventListener("kickoff:update", (event) => {
    if (pending) return;
    pending = true;
    const looping = reloadedJustNow();
    if (looping) console.warn("The server answered with another build within a minute of a reload; the page keeps still.", event?.detail);
    const said = el("span", { class: "note", role: "status" }, "");
    const reloadButton = el("button", { class: "btn", type: "button", onclick: async () => {
      reloadButton.disabled = true;
      const reloaded = await reloadWhenServerAnswers({ onWait: () => { said.textContent = " Waiting for the server…"; } });
      if (!reloaded) {
        reloadButton.disabled = false;
        said.textContent = " The server is not answering yet. Try again in a moment.";
      }
    } }, "Reload");
    // one format for every reminder (owner 2026-10-13): a note at the top of the page with its close button (ui/page-notes.js)
    addNote({ id: "update", title: "A new version of the app is on the server", body: () => el("div", { class: "page-note__row" }, el("span", {}, looping ? "The server answered with two different builds within a minute, so the page keeps still. If two servers are running on this address, stop one, then Reload." : "It loads when you open another page; Reload brings it in now."), reloadButton, said) });
  });
  // opening another page brings the new version in, the reload landing on the page opened (never under the reader)
  window.addEventListener("hashchange", () => {
    if (!pending || reloadedJustNow()) return;
    rememberReload();
    reloadWhenServerAnswers();
  });
  // Phase 16 wave 3: the server's own code changed on disk (an update was pulled): only a restart brings it in
  let restartOffered = false;
  document.addEventListener("kickoff:restart-needed", () => {
    if (restartOffered) return;
    restartOffered = true;
    const said = el("span", { class: "note", role: "status" }, "");
    const button = el("button", { class: "btn", type: "button", onclick: async () => {
      button.disabled = true;
      await restartFlow({ say: (words) => { said.textContent = ` ${words}`; }, confirmDuringGame: async () => window.confirm("Our game is under way: the In Game sheet drops for about 15 seconds while the server restarts. Restart anyway?") });
      button.disabled = false;
    } }, "Restart the server");
    addNote({ id: "restart-needed", title: "The server's code was updated", body: () => el("div", { class: "page-note__row" }, el("span", {}, "Restart the server to use the new version."), button, said) });
  });
  // a Claude run ended (ui/run-bar.js): the page keeps what it shows and the To do says the new data is in (owner
  // 2026-11-14: "Say so, never reload"); the next page opened has it anyway, so the note leaves with this page
  document.addEventListener("kickoff:data-loaded", () => {
    const refresh = el("button", { class: "btn", type: "button", onclick: () => {
      removeNote("data-loaded");
      document.dispatchEvent(new CustomEvent("kickoff:refresh"));
    } }, "Refresh");
    addNote({ id: "data-loaded", title: "New data is in", leaveWithPage: true, body: () => el("div", { class: "page-note__row" }, el("span", {}, "Claude Code finished loading. Refresh shows it on this page; any page you open has it."), refresh) });
  });
  document.addEventListener("kickoff:claude-signin", (event) => showClaudeSignin(event?.detail?.since));
  document.addEventListener("kickoff:season-switch", (event) => showSeasonSwitch(event?.detail));
}

// The season's switch (rollover R2, owner 2026-11-15): for two weeks after the app moved to the next season by itself, the To
// do says so on every device until it is cleared there (remembered per device and season); while a due switch fails, the
// host's devices say why (a guest has nothing to do about it).
const SEASON_NOTE_KEY = "kickoff.seasonNote";

function seasonNoteCleared(to) {
  try {
    return window.localStorage?.getItem(SEASON_NOTE_KEY) === String(to);
  } catch {
    return false; // storage refused: the note shows until cleared on this visit
  }
}

function showSeasonSwitch(value) {
  const failed = value && typeof value.failed === "object" && value.failed ? value.failed : null;
  const switched = value && typeof value.switched === "object" && value.switched ? value.switched : null;
  if (failed) {
    if (!claudeRoleKnown || document.body?.dataset?.role === "guest") return;
    addNote({ id: "season-switch", title: `The move to ${String(failed.to ?? "the next season")} is waiting`, body: () => el("div", { class: "page-note__row" }, el("span", {}, String(failed.error || "The switch could not be made; the app tries again within the hour.")), el("a", { class: "btn btn--quiet", href: "#seasons" }, "Seasons")) });
    return;
  }
  if (!switched || seasonNoteCleared(switched.to)) {
    removeNote("season-switch");
    return;
  }
  const from = String(switched.from ?? "Last season");
  addNote({
    id: "season-switch",
    title: `The app is on ${String(switched.to ?? "the new season")} now`,
    body: () => el("div", { class: "page-note__row" }, el("span", {}, `${from} is kept under Menu, My Teams, Seasons: its season in review and every game.`), el("a", { class: "btn btn--quiet", href: "#seasons" }, "Seasons")),
    onDismiss: () => {
      try {
        window.localStorage?.setItem(SEASON_NOTE_KEY, String(switched.to));
      } catch {
        // storage refused: it shows again on the next visit
      }
    },
  });
}

// Claude Code signed out on the server computer (owner 2026-11-15, "Yes, fix it first"): the To do says so on the host's
// devices, with what to do, until a run gets through (build.js noteClaude); a guest has nothing to do about it. The first
// answers come before the listener and before the device knows whether it is a guest's, so the boot shows what the server
// already said once guest mode has answered (claudeRoleKnown); after that, each change is heard as it comes.
let claudeRoleKnown = false;

function showClaudeSignin(since) {
  if (!since) {
    removeNote("claude-signin");
    return;
  }
  if (!claudeRoleKnown || document.body?.dataset?.role === "guest") return;
  addNote({ id: "claude-signin", title: "Claude Code is signed out", body: () => el("div", { class: "page-note__row" }, el("span", {}, signedOutWords(since))) });
}

// index.html's watchdog (item 6, step E) retries a failed start once per tab and remembers it here; once the app has drawn
// its top bar the memory goes, so a later failed start gets its own retry. Storage refused: the watchdog never retries by
// itself (it cannot remember that it did), and its Reload still works.
const BOOT_RETRY_KEY = "kickoff.bootRetry";

function forgetBootRetry() {
  try {
    window.sessionStorage?.removeItem(BOOT_RETRY_KEY);
  } catch {
    // storage refused: nothing was remembered
  }
}

/** The page's scroll goes into the current history entry as the reader scrolls (at most every 300 ms), and
 *  once more on every tap, before a link can move the app to another entry. */
function rememberScroll() {
  let timer = null;
  const save = () => writeState({ scrollY: Math.round(window.scrollY) });
  window.addEventListener(
    "scroll",
    () => {
      if (timer) return;
      timer = setTimeout(() => {
        timer = null;
        save();
      }, 300);
    },
    { passive: true },
  );
  document.addEventListener("click", save, { capture: true });
}

/** Public release Phase 9b: in the demo, a banner across the top says so and leads to the demo page (what a key
 *  does, your own team). A server from before 9b has no /api/demo; then nothing shows. */
function showDemoBanner(page) {
  fetchJson("/api/demo")
    .then((envelope) => {
      const data = envelope?.data;
      if (!data || data.demo !== true) return;
      const banner = el("div", { class: "demo-banner", role: "note" }, el("span", {}, "Demo: a sample season with invented games and one under way."), el("a", { href: "/demo" }, data.configured === true ? "Back to my team ›" : "Use my own team ›"));
      page.root.insertBefore(banner, page.root.firstChild);
    })
    .catch((error) => console.warn("Could not tell whether this is the demo.", error?.message || error));
}

/** The page Ask about this page names (FEAT-12): the address on screen, with the team on a device switched to another one
 *  (batch 3, review 2026-11-19), so Claude reads the page as the one shown and not as ours. */
function askRoute() {
  const hash = window.location.hash || "#program";
  const route = parseRoute(hash, VALID);
  const team = route ? viewRoute(route)?.params?.team : null;
  if (!team || route.params?.team) return hash;
  return `${hash}${hash.includes("?") ? "&" : "?"}team=${encodeURIComponent(team)}`;
}

function isTyping(target) {
  return Boolean(target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable));
}

async function start() {
  installClientLog(); // tablet errors reach logs/app.log (kickoff.client) from here on
  startTrail(); // the pages, taps, sheets and errors of the last 15 minutes, for Send feedback (owner 2026-10-23)
  applyTextScale(); // this device's text size, before anything is drawn (UX-09)
  applyTheme(); // ENH-35: this device's theme too, so a light device never flashes the dark one first
  const root = document.getElementById("app");
  await Promise.all([loadPrefs(), loadIdentity()]); // the delay and who "we" are come from the server before anything renders
  document.title = ours().title;
  applyTheme(); // again, now that the team's colors are known
  addAliases("national-conference-rank", [confLabel(), `${confLabel()} rank`]); // labels that name the team or its conference
  addAliases("edges", [`${usLabel()} rank`]);
  addAliases("pregame-win-probability", [`${usSchool()} win probability`]);
  document.querySelector('meta[name="apple-mobile-web-app-title"]')?.setAttribute("content", ours().name || "Kickoff"); // the home-screen label on iOS
  const initial = parseHash();
  const page = shell({
    current: initial ? initial.id : "program",
    status: { kind: "quiet", label: "Loading" },
    // a tab, the wordmark or a menu item; with a sheet or the card open (the top bar stays above them from 700 px up)
    // the new page takes the layer's own history entry, and the page already showing just closes them
    onNavigate: (id) => {
      if (window.location.hash !== `#${id}`) goTo(id);
      else {
        closeLayers();
        toTop(); // ENH-33: a tab for the page already showing goes back to its top
        show({ id, arg: null });
      }
    },
    // item 6 review: the top bar stays above sheets now, so a second tap on Search reuses the open one (as "/" does)
    onSearch: () => {
      const input = document.querySelector(".sheet-layer[data-modal] .search__input");
      if (input) {
        input.focus();
        input.select();
        return;
      }
      openSearch();
    },
    menu: MENU, // the layout pass (owner 2026-10-22): one level at a time, ui/menu-tree.js
    onOpen: (entry, ctx) => openFromMenu(entry, ctx), // a table in the menu opens wide by itself (views/panels.js)
    onTodo: () => openTodo(), // the To do row at the top of the menu (owner 2026-10-22: "its own flyout")
    onFeedback: () => openFeedback(), // Send feedback at the foot of the menu (owner 2026-10-23)
    onAsk: () => openAsk({ route: askRoute() }), // FEAT-12: Ask about this page (batch 3: with the team switched to)
    claudeRow: ({ close }) => (viewing() ? null : refreshRow({ route: window.location.hash || "#program", onStart: (result) => { if (result.ok) close(); } })), // batch 4; batch 3: a device switched to another team shows their pages, so Claude's refresh of ours stays out of its menu
    subOf: (key) => (key === "game" ? loadProgram().then(() => gameLine()).catch(() => "") : ""), // the game the matchup's tables are about
    onSwitchTeam: () => openTeamSwitch(), // batch 3 (owner 2026-11-16): see the app as another team on this device
    onBackHome: () => clearViewing(),
  });
  page.setViewing(viewingInfo());
  root.replaceChildren(page.root); // the loading bar (and its Reload, item 6) gives way to the real one with its Menu
  forgetBootRetry();
  try {
    enableHints(document.body); // stat names explain themselves when tapped (owner request 2026-09-26)
  } catch (error) {
    console.error("Stat hints could not start; the app works without them.", error);
  }
  showDemoBanner(page);
  mountRadio(page.root.querySelector(".shell__radio"));
  loadRadioSources();
  watchForUpdates();
  watchLiveGame(page);
  installRunBar(page.notes); // owner 2026-10-16: Claude Code loads in the background, one bar above the page, one refresh at the end
  keepScreenOn();
  rememberScroll();

  let view = null;
  let currentKey = null;
  let depth = 0;
  let shown = false;
  let restore = null; // { y, until } after a Back: the scroll to put back once the view has drawn

  function focusBand(id) {
    const target = document.getElementById(id);
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function markEntry() {
    const state = readState();
    if (isNum(state.depth)) depth = state.depth; // an entry seen before (Back or Forward)
    else {
      depth = shown ? depth + 1 : 0;
      writeState({ depth });
    }
    shown = true;
    return state;
  }

  function putBack() {
    if (!restore || restore.pending || Date.now() > restore.until) {
      if (restore && !restore.pending) restore = null;
      return;
    }
    window.scrollTo(0, restore.y);
    if (Math.abs(window.scrollY - restore.y) < 2) restore = null; // done; a page still too short tries again on its next draw
  }

  // A view that draws without "kickoff:rendered" (its own poller) still gets its scroll back: a few quiet
  // retries while it loads. Any touch, wheel or key from the reader ends the restore at once.
  function keepPuttingBack() {
    if (!restore || restore.pending) return;
    putBack();
    if (restore) setTimeout(keepPuttingBack, 200);
  }
  for (const type of ["wheel", "touchstart", "keydown", "pointerdown"]) {
    window.addEventListener(type, () => {
      if (restore && !restore.pending) restore = null;
    }, { passive: true, capture: true });
  }

  // The season as one line (owner 2026-10-30): the middle tab reads the stop that leads now, and the Newspaper tab follows
  // the week on screen (a Pre-Game or Post-Game stop of another week opens that week's paper). One week position for the app.
  let landHome = false; // rollover R3: true from a start with no page asked until the line first answers
  const STOP_TAB = new Set(["program", "postgame", "season", "myteams", "preseason", "review"]); // rollover R3: the season in review leads once the season is over
  function applyStops(line) {
    const current = line && line.current ? line.current : currentStop();
    if (viewing()) {
      // batch 3: a switched device's middle tab is that team's own next program (viewing.js adds its ?team=); our line stays ours
      page.setStop({ label: "Pre-Game Program", detail: viewing(), href: "#program" });
      followWeek(lastRoute);
      return;
    }
    page.setStop(current);
    // rollover R3 (owner 2026-11-15): opened with no page asked, the app lands on the season in review once the season is over
    // and on the Preseason Magazine before it starts; any other time, and once the reader has moved, home stays the program
    if (landHome && line) {
      landHome = false;
      const kind = current && typeof current.kind === "string" ? current.kind : "";
      if ((kind === "book" || kind === "preseason") && window.location.hash === "#program" && typeof current.href === "string" && current.href.startsWith("#")) window.location.replace(current.href);
    }
    followWeek(lastRoute);
  }
  let lastRoute = null;
  function followWeek(route) {
    lastRoute = route;
    let key = null;
    if (route && !viewing() && (route.id === "program" || route.id === "postgame") && route.arg) {
      const item = weekOf(route.arg);
      const current = currentStop();
      if (item && Number.isFinite(item.week) && !(current && current.week === item.week)) {
        const week = item.seasonType && item.seasonType !== "regular" ? "postseason" : `week-${item.week}`;
        key = route.id === "postgame" ? `${week}-sunday` : week; // Wave 6 (2026-11-15): a Post-Game stop opens its game's Sunday paper
      }
    }
    page.setNewspaperWeek(key);
  }
  // ENH-46: every band the page on screen draws gets the button that opens it wide by itself (the band of this page: another
  // team's page opens that team's band); the pages redraw as their answers arrive, so the holder is watched
  watchBands(page.main, { route: () => window.location.hash, onOpen: (entry, ctx) => openBand(entry, ctx) });
  onStops(applyStops);
  loadStops().then(applyStops).catch(() => {});
  if (stopsNow()) applyStops(stopsNow());

  function show(route) {
    if (route.id === "radio") route = { id: "program", arg: null, focus: "program-radio" }; // the radio control lives on the Game program
    route = viewRoute(route); // batch 3: a page that follows the switch opens on the team this device is switched to
    const key = routeKey(route);
    if (currentKey === key) {
      if (restore?.pending) restore = null;
      if (route.focus) focusBand(route.focus);
      return;
    }
    const entry = markEntry();
    if (route.id === "board" && depth === 0 && seedBoardHistory()) depth = 1; // item 6, step A: Back from a cold board lands on In Game
    const backTo = isNum(entry.scrollY) && restore?.pending ? entry.scrollY : null;
    restore = backTo !== null ? { y: backTo, until: Date.now() + 5000 } : null;
    try {
      document.dispatchEvent(new CustomEvent("kickoff:route", { detail: route })); // sheets and the player card close
    } catch (error) {
      console.error("A layer did not close on the route change.", error);
    }
    if (view) {
      try {
        view.unmount();
      } catch (error) {
        console.error("The last view did not unmount cleanly.", error);
      }
      view = null;
    }
    // the board hides the top bar and the tabs for the whole body: never let that outlive the board (a page with no
    // menu needs the browser's back button; owner bug 2026-10-10)
    if (route.id !== "board") document.body.classList.remove("board-mode", "board-awake");
    currentKey = key;
    const shown = route.id === "band" ? bandPage(route) : route; // a band's own page belongs to its page's tab and status
    if (!KEEP_TAB.has(shown.id)) page.setCurrent(NO_TAB.has(shown.id) ? null : shown.id === "story" ? "newspaper" : STOP_TAB.has(shown.id) ? "program" : shown.id); // the reader is the Newspaper's; the stops share the middle tab
    followWeek(route);
    page.setPage(shown); // ENH-4: the Data status card describes this page
    if (route.id === "archive" && route.arg) window.scrollTo(0, 0);
    page.main.replaceChildren();
    const factory = BUILT[route.id];
    if (factory) {
      view = factory({ onStatus: (status) => page.setStatus(status) }, route.arg, route.focus, route.params || {});
      view.mount(page.main);
    } else {
      page.setStatus({ kind: "quiet", label: "Not built yet" });
      page.main.append(laterView(route.id));
    }
    window.scrollTo(0, 0);
    if (restore) setTimeout(keepPuttingBack, 0); // an instant-back page is already drawn
  }

  function refreshCurrent() {
    try {
      return typeof view?.refresh === "function" ? view.refresh() : null;
    } catch (error) {
      console.error("The refresh failed.", error);
      return null;
    }
  }

  window.addEventListener("popstate", () => {
    // a layer's own entry (a sheet, the card, the menu: ui/layers.js) is the same page: no hashchange follows, and the
    // page keeps its place
    const route = parseHash();
    if (route && currentKey !== null && routeKey(route.id === "radio" ? { id: "program", arg: null } : route) === currentKey) return;
    restore = { pending: true }; // the hashchange that follows is a Back or Forward: put its scroll back
  });
  window.addEventListener("hashchange", () => {
    const route = parseHash();
    if (route) show(route);
    else if (restore?.pending) restore = null;
  });
  // batch 3: a game watched on this device alone (or back to the room's): In Game on screen redraws for it
  onDeviceGame(() => {
    const route = parseHash();
    if (route && route.id === "live") {
      currentKey = null;
      show(route);
    }
  });
  // batch 3: switching (or Back to ours) redraws the page on screen for the team now shown, and the middle tab follows
  onViewing((info) => {
    page.setViewing(info);
    applyStops(stopsNow());
    closeLayers();
    currentKey = null;
    show(parseHash() || { id: "program", arg: null });
    window.scrollTo(0, 0);
  });
  document.addEventListener("kickoff:rendered", putBack);
  document.addEventListener("kickoff:retry", () => refreshCurrent()); // Phase 16 wave 3 (DS-12): the status card's Retry now
  // Phase 16 NV: a linked rank chip or poll badge opens its list in a side sheet over this page (never a route
  // change, so the Live sheet stays mounted); the sheet's 'Full page' link is the #national route.
  installNationalLinks(document);
  // Every team name on any page is a link: ours to the full team page, others to a flyout.
  document.addEventListener("kickoff:team", (event) => {
    // Design rules (owner 2026-10-21): "Every team name links out: ours to the Season page, others to a flyout"
    if (typeof event.detail === "string" && event.detail === usSchool() && viewing()) window.location.hash = `team=${encodeURIComponent(usSchool())}`; // batch 3, switched: our page by name (#season follows the switch)
    else if (typeof event.detail === "string" && event.detail === usSchool()) window.location.hash = "season";
    else openTeam(event.detail);
  });
  const pull = installPullToRefresh({ root: page.main, host: page.root, onRefresh: refreshCurrent });
  document.addEventListener("kickoff:refresh", () => pull.trigger()); // the Refresh beside the status pill and the To do's (owner 2026-11-14)
  // Phase 15: "/" opens search; Phase 16: "r" refreshes the page (the pull-down of a keyboard). Not while typing.
  document.addEventListener("keydown", (event) => {
    const target = event.target;
    if (isTyping(target) || event.ctrlKey || event.metaKey || event.altKey) return;
    // not while the menu is open (item 6): Search would open behind it and an Escape would close both
    if (event.key === "/" && !document.querySelector(".sheet-layer .search") && !document.querySelector(".drawer[open]")) {
      event.preventDefault();
      openSearch();
    } else if ((event.key === "r" || event.key === "R") && !event.shiftKey && !document.querySelector("[data-modal]")) {
      event.preventDefault();
      pull.trigger();
    }
  });
  document.addEventListener("click", (event) => {
    // a Wikipedia link carries data-team for its lookup (ui/wiki-links.js) and is not a team tap: a coach's name opens
    // the coach's page, not the team flyout (owner bug 2026-10-10)
    const link = event.target.closest("[data-team]:not(.team-link):not(.wiki-link)");
    if (link && link.dataset.team) {
      event.preventDefault();
      openTeam(link.dataset.team);
    }
  });
  installCvd(); // Phase 19: this device's color-blind friendly colors
  installSpoiler(); // Phase 19: this device's spoiler switch
  installLayerHistory(); // item 6: Back closes the top sheet, the card or the menu, and the page stays
  installToTop(); // owner 2026-11-15: "an action to throw you back to the top of the page", bottom right from a screen down
  // Phase 18.3 and item 6, step C: once per server start per device, only when something is not loaded, a note on the
  // Pre-Game Program and a dot on the status pill; checked once the first page has drawn (its fetches go first) and the
  // device knows whether it is a guest (a guest gets the welcome note instead, ui/guest.js)
  let readinessAsked = false;
  const askReadiness = () => {
    if (readinessAsked) return;
    readinessAsked = true;
    startReadiness(page).catch((error) => console.warn("The Not loaded yet check did not finish.", error?.message || error));
    startUpdateNote().catch((error) => console.warn("The update check did not finish.", error?.message || error));
    startTodayNote().catch((error) => console.warn("The on-this-day check did not finish.", error?.message || error));
    startDataCheckNote().catch((error) => console.warn("The data check note did not finish.", error?.message || error));
  };
  const guestKnown = startGuestMode().catch(() => null); // Phase 18.6: a guest's page says it is view-only
  guestKnown.then(() => startTrivia()).catch((error) => console.error("The trivia could not start.", error)); // the trivia (2026-10-21): the join note once a day, then the popups while this tablet plays
  guestKnown.then(() => {
    claudeRoleKnown = true; // 2026-11-15: a host's device now says what the server already said about Claude Code's sign-in
    showClaudeSignin(claudeSignedOutSince());
    showSeasonSwitch(seasonSwitchNow()); // rollover R2: a failing switch is the host's to see
  });
  const drawn = new Promise((resolve) => {
    document.addEventListener("kickoff:rendered", resolve, { once: true });
    setTimeout(resolve, 4000); // a page that draws without the event (its own stream) still gets the check
  });
  Promise.all([guestKnown, drawn]).then(askReadiness);
  if (initial) show(initial);
  else {
    landHome = true; // rollover R3: the line, once it answers, may lead elsewhere (the season in review, the Magazine)
    window.location.hash = "program"; // Phase 17 #32: the Game program is home
    show({ id: "program", arg: null });
  }
  stepOverLeftovers(); // a reload while a sheet was open: its entry, its sheet gone, is stepped back over
}

// The guard lets the test suite import the opening rule under Node, where there is no page.
if (typeof document !== "undefined") start();
