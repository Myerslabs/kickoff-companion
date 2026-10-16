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
import { applyTextScale, applyTheme, getPrefs, loadPrefs, prefsMeta } from "./prefs.js";
import { loadRadioSources, mountRadio } from "./radio.js";
import { el, isNum } from "./ui/dom.js";
import { keepScreenOn } from "./wake.js";
import { addAliases, enableHints } from "./ui/hints.js";
import { parseRoute, routeKey } from "./ui/national-link.js";
import { installNationalLinks } from "./ui/national-sheet.js";
import { installPullToRefresh } from "./ui/pull-refresh.js";
import { MENU, shell } from "./ui/shell.js";
import { band } from "./ui/states.js";
import { fetchJson } from "./views/common.js";
import { createLeadersView } from "./views/leaders.js";
import { createLiveView } from "./views/live.js";
import { createNewspaperView } from "./views/newspaper.js";
import { createTop25View } from "./views/top25.js";
import { createProgramView } from "./views/program.js";
import { createRatingsView } from "./views/ratings.js";
import { createRecruitingView } from "./views/recruiting.js";
import { createRosterView } from "./views/roster.js";
import { createSeasonView } from "./views/season.js";
import { createArchiveView } from "./views/archive.js";
import { createGlossaryView } from "./views/glossary.js";
import { createNationalView } from "./views/national.js";
import { createMyTeamsView } from "./views/myteams.js";
import { createSettingsView } from "./views/settings.js";
import { createTeamView, openTeam } from "./views/team.js";
import { createBoxView } from "./views/box.js";
import { installCvd } from "./ui/cvd.js";
import { startGuestMode } from "./ui/guest.js";
import { installSpoiler } from "./ui/spoiler.js";
import { startReadiness } from "./ui/readiness.js";
import { closeLayers, goTo, installLayerHistory, stepOverLeftovers } from "./ui/layers.js";
import { createBoardView, seedBoardHistory } from "./views/board.js";
import { createInviteView } from "./views/invite.js";
import { createPreseasonView } from "./views/preseason.js";
import { createReviewView } from "./views/review.js";
import { createInjuriesView } from "./views/injuries.js";
import { createPromptsView } from "./views/prompts.js";
import { addNote } from "./ui/page-notes.js";
import { installRunBar } from "./ui/run-bar.js";
import { createSetupPageView } from "./views/setup-page.js";
import { reloadWhenServerAnswers, restartFlow } from "./ui/restart.js";
import { openSearch } from "./views/search.js";

const BUILT = {
  season: (opts, arg, focus, params) => createSeasonView({ ...opts, arg, params }),
  leaders: (opts, arg, focus, params) => createLeadersView({ ...opts, arg, params }),
  roster: (opts) => createRosterView(opts),
  recruiting: (opts, arg, focus, params) => createRecruitingView({ ...opts, arg, params }),
  newspaper: (opts, arg) => createNewspaperView({ ...opts, edition: arg }), // items 10-12: #newspaper=week-6 opens an earlier edition
  top25: (opts) => createTop25View(opts), // item 11: every game of the week with an AP Top 25 team
  program: (opts, arg, focus) => createProgramView({ ...opts, gameId: arg && /^\d+$/.test(arg) ? arg : null, focus }),
  team: (opts, arg, focus, params) => createTeamView({ ...opts, school: arg, params }),
  box: (opts, arg) => createBoxView({ ...opts, gameId: arg }),
  preseason: (opts) => createPreseasonView(opts), // Phase 17 Part 3a: the season loads and each primary team's preseason // Phase 17 #2: any game's box score, from a W or L square
  live: (opts) => createLiveView(opts),
  archive: (opts, arg) => createArchiveView({ ...opts, gameId: arg }),
  settings: (opts, arg) => createSettingsView({ ...opts, arg }), // #settings=radio opens that section (2026-10-16)
  ratings: (opts, arg, focus, params) => createRatingsView({ ...opts, arg, params }),
  glossary: (opts, arg) => createGlossaryView({ ...opts, focusId: arg }),
  national: (opts, arg, focus, params) => createNationalView({ ...opts, arg, params }), // Phase 16 NV: a chip's list as a page
  myteams: (opts) => createMyTeamsView(opts), // public release Phase 5b
  invite: (opts) => createInviteView(opts), // Phase 18.6: the QR code for friends
  review: (opts) => createReviewView(opts), // Phase 19: the season told from the schedule
  board: (opts) => createBoardView(opts), // Phase 18.6: the Live sheet made for a wall
  injuries: (opts) => createInjuriesView(opts), // owner 2026-10-10: our injuries through the season, from the game notes
  prompts: (opts) => createPromptsView(opts), // the Prompts phase (2026-10-13): every prompt, its Copy, Paste and Run, the one run, the schedule
  setup: (opts) => createSetupPageView(opts), // owner 2026-10-10: the demo, the archive, the season in review and the radio
};

const LATER = {
  radio: ["Radio", "The team's radio plays from the bar at the bottom of every page; pick the station in Settings."],
};

const VALID = new Set([...Object.keys(BUILT), ...Object.keys(LATER), "radio"]);
const NO_TAB = new Set(["team", "box", "invite", "board"]); // a team page and a box score belong to no tab (DS-03)
const KEEP_TAB = new Set(["national"]); // a list keeps the tab it was opened from

/** "#program=401856699" -> { id: "program", arg: "401856699" }; "#team=Kansas%20State" -> { id: "team", arg: "Kansas State" } */
function parseHash() {
  return parseRoute(window.location.hash || "", VALID);
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

let gameUnderWay = false; // what the last live check said; the restart reload keeps its hands off In Game and the board then

/**
 * Keep the LIVE marker current: once now, then every minute and whenever the page comes back into view. A check the
 * server does not answer (it is restarting, owner bug 2026-10-13) is asked again after 2, 4 and 8 s, so the new build's
 * envelope arrives, and the page reloads, seconds after the server is back instead of up to a minute later.
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
      gameUnderWay = gameIsLive(envelope?.data);
      page.setLive(gameUnderWay);
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

const RELEASE_SEEN_KEY = "kickoff.release.seen";
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
 * A newer release is out (the update check, Phase 16 wave 3, asked of GitHub once a day): the same note as every other
 * reminder (owner 2026-10-13), once per release on each device; its close button remembers the version. The app never
 * downloads or installs anything by itself.
 */
async function startReleaseNote() {
  const envelope = await fetchJson("/api/updates");
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
  if (!data || data.newer !== true || typeof data.latest !== "string" || !data.latest) return null;
  let seen = null;
  try {
    seen = window.localStorage.getItem(RELEASE_SEEN_KEY);
  } catch {
    seen = null;
  }
  if (seen === data.latest) return null;
  const link = typeof data.url === "string" && /^https:\/\//.test(data.url) ? el("a", { href: data.url, target: "_blank", rel: "noopener" }, "See what changed") : null;
  return addNote({
    id: "release",
    title: `Version ${data.latest} is out`,
    body: () => el("p", {}, `You run ${typeof data.current === "string" ? data.current : "an older version"}. `, link, link ? ". " : "", "Settings, About, says how to update."),
    onDismiss: () => {
      try {
        window.localStorage.setItem(RELEASE_SEEN_KEY, data.latest);
      } catch {
        // no storage: the note comes back next load, the safe direction
      }
    },
  });
}

/** The view the address names: "live" for "#live" and "#live=...", "" for none. */
function viewInAddress() {
  return String(window.location.hash || "").replace(/^#/, "").split(/[=?]/)[0];
}

/**
 * Whether a reload now would pull the page out from under a viewer: In Game or the board while our game is under way
 * (the banner shows there instead, and the reload waits for the next view). Anywhere else, any time, the page reloads.
 */
function holdsAViewer() {
  return gameUnderWay && ["live", "board"].includes(viewInAddress());
}

/**
 * Phase 12: when the server has a newer build than this page (a restart, or a file changed under
 * static/), the page reloads by itself as soon as the server answers (owner bug 2026-10-13: "when I restart the
 * server, the page does not refresh"; until then it waited to come back into view), so no device is ever left on
 * old code. The one hold: In Game and the board while our game is under way show the banner and reload the next
 * time they come into view, so nothing reloads under the viewer.
 * Item 6, step E: either way the page reloads only once the server answers (ui/restart.js reloadWhenServerAnswers),
 * never into a server that is still restarting or a Wi-Fi still reconnecting after the iPad wakes.
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

function watchForUpdates(page) {
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
    addNote({ id: "update", title: "A new version of the app is on the server", body: () => el("div", { class: "page-note__row" }, el("span", {}, looping ? "The server answered with two different builds within a minute, so the page keeps still. If two servers are running on this address, stop one, then Reload." : "The page reloads by itself once the server answers; Reload does it now."), reloadButton, said) });
    if (!looping && document.visibilityState === "visible" && !holdsAViewer()) {
      rememberReload();
      reloadWhenServerAnswers({ onWait: () => { said.textContent = " Waiting for the server…"; } });
    }
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
  document.addEventListener("visibilitychange", () => {
    // a server that never answers leaves the page and its banner
    if (pending && document.visibilityState === "visible" && !holdsAViewer() && !reloadedJustNow()) {
      rememberReload();
      reloadWhenServerAnswers();
    }
  });
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
      const banner = el("div", { class: "demo-banner", role: "note" }, el("span", {}, "Demo: a made-up league with a game under way."), el("a", { href: "/demo" }, data.configured === true ? "Back to my team ›" : "Use my own team ›"));
      page.root.insertBefore(banner, page.root.firstChild);
    })
    .catch((error) => console.warn("Could not tell whether this is the demo.", error?.message || error));
}

/** Public release Phase 5b: ask the server to load the primary teams' pages now, so they open at once.
 *  The server decides (a Tier 2 key, at most every ten minutes); a failure only means they load on demand. */
function warmPrimaries() {
  if ((prefsMeta()?.teamSet?.extraPrimaries || []).length === 0) return;
  fetch("/api/myteams/warm", { method: "POST" }).catch((error) => console.warn("The primary teams' pages were not warmed; they load when opened.", error?.message || error));
}

function isTyping(target) {
  return Boolean(target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable));
}

async function start() {
  installClientLog(); // tablet errors reach logs/app.log (kickoff.client) from here on
  applyTextScale(); // this device's text size, before anything is drawn (UX-09)
  const root = document.getElementById("app");
  await Promise.all([loadPrefs(), loadIdentity()]); // the theme, the delay and who "we" are come from the server before anything renders
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
    menu: MENU, // owner 2026-10-10: the other primary teams are reached from the My Teams page, not the menu
  });
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
  warmPrimaries();
  watchForUpdates(page);
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

  function show(route) {
    if (route.id === "radio") route = { id: "program", arg: null, focus: "program-radio" }; // the radio control lives on the Game program
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
    if (!KEEP_TAB.has(route.id)) page.setCurrent(NO_TAB.has(route.id) ? null : route.id);
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
  document.addEventListener("kickoff:rendered", putBack);
  document.addEventListener("kickoff:retry", () => refreshCurrent()); // Phase 16 wave 3 (DS-12): the status card's Retry now
  // Phase 16 NV: a linked rank chip or poll badge opens its list in a side sheet over this page (never a route
  // change, so the Live sheet stays mounted); the sheet's 'Full page' link is the #national route.
  installNationalLinks(document);
  // Every team name on any page is a link: ours to the full team page, others to a flyout.
  document.addEventListener("kickoff:team", (event) => openTeam(event.detail));
  const pull = installPullToRefresh({ root: page.main, host: page.root, onRefresh: refreshCurrent });
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
  // Phase 18.3 and item 6, step C: once per server start per device, only when something is not loaded, a note on the
  // Pre-Game Program and a dot on the status pill; checked once the first page has drawn (its fetches go first) and the
  // device knows whether it is a guest (a guest gets the welcome note instead, ui/guest.js)
  let readinessAsked = false;
  const askReadiness = () => {
    if (readinessAsked) return;
    readinessAsked = true;
    startReadiness(page).catch((error) => console.warn("The Not loaded yet check did not finish.", error?.message || error));
    startReleaseNote().catch((error) => console.warn("The update check did not finish.", error?.message || error));
    startTodayNote().catch((error) => console.warn("The on-this-day check did not finish.", error?.message || error));
  };
  const guestKnown = startGuestMode().catch(() => null); // Phase 18.6: a guest's page says it is view-only
  const drawn = new Promise((resolve) => {
    document.addEventListener("kickoff:rendered", resolve, { once: true });
    setTimeout(resolve, 4000); // a page that draws without the event (its own stream) still gets the check
  });
  Promise.all([guestKnown, drawn]).then(askReadiness);
  if (initial) show(initial);
  else {
    window.location.hash = "program"; // Phase 17 #32: the Game program is home
    show({ id: "program", arg: null });
  }
  stepOverLeftovers(); // a reload while a sheet was open: its entry, its sheet gone, is stepped back over
}

// The guard lets the test suite import the opening rule under Node, where there is no page.
if (typeof document !== "undefined") start();
