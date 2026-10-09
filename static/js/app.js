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
//   the view's first draw; history.state.depth counts the app's own entries (backRow uses it).
//   The team route highlights no tab; the national list keeps the tab it was opened from.
//   Pull down at the top of a page, or 'r' on a keyboard, refreshes the current view.

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
import { menuWith, shell } from "./ui/shell.js";
import { band } from "./ui/states.js";
import { fetchJson } from "./views/common.js";
import { createLeadersView } from "./views/leaders.js";
import { createLiveView } from "./views/live.js";
import { createNewspaperView } from "./views/newspaper.js";
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
import { maybeShowReadiness } from "./ui/readiness.js";
import { createBoardView } from "./views/board.js";
import { createInviteView } from "./views/invite.js";
import { createPreseasonView } from "./views/preseason.js";
import { createReviewView } from "./views/review.js";
import { restartFlow } from "./ui/restart.js";
import { openSearch } from "./views/search.js";

const BUILT = {
  season: (opts, arg, focus, params) => createSeasonView({ ...opts, arg, params }),
  leaders: (opts, arg, focus, params) => createLeadersView({ ...opts, arg, params }),
  roster: (opts) => createRosterView(opts),
  recruiting: (opts, arg, focus, params) => createRecruitingView({ ...opts, arg, params }),
  newspaper: (opts) => createNewspaperView(opts),
  program: (opts, arg, focus) => createProgramView({ ...opts, gameId: arg && /^\d+$/.test(arg) ? arg : null, focus }),
  team: (opts, arg, focus, params) => createTeamView({ ...opts, school: arg, params }),
  box: (opts, arg) => createBoxView({ ...opts, gameId: arg }),
  preseason: (opts) => createPreseasonView(opts), // Phase 17 Part 3a: the season loads and each primary team's preseason // Phase 17 #2: any game's box score, from a W or L square
  live: (opts) => createLiveView(opts),
  archive: (opts, arg) => createArchiveView({ ...opts, gameId: arg }),
  settings: (opts) => createSettingsView(opts),
  ratings: (opts, arg, focus, params) => createRatingsView({ ...opts, arg, params }),
  glossary: (opts, arg) => createGlossaryView({ ...opts, focusId: arg }),
  national: (opts, arg, focus, params) => createNationalView({ ...opts, arg, params }), // Phase 16 NV: a chip's list as a page
  myteams: (opts) => createMyTeamsView(opts), // public release Phase 5b
  invite: (opts) => createInviteView(opts), // Phase 18.6: the QR code for friends
  review: (opts) => createReviewView(opts), // Phase 19: the season told from the schedule
  board: (opts) => createBoardView(opts), // Phase 18.6: the Live sheet made for a wall
};

const LATER = {
  radio: ["Radio", "The team's radio plays from the bar at the bottom of every page; pick the station in Settings."],
  injuries: ["Injury report", "The availability report lives on the Game program."],
};

const VALID = new Set([...Object.keys(BUILT), ...Object.keys(LATER), "radio", "injuries"]);
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

/** Keep the LIVE marker current: once now, then every minute and whenever the page comes back into view. */
function watchLiveGame(page) {
  let busy = false;
  const check = async () => {
    if (busy) return;
    busy = true;
    try {
      const delay = Number(getPrefs()?.delaySeconds); // the marker goes by what a sheet this far behind has seen
      const envelope = await fetchJson(`/api/live/status?delay=${Number.isFinite(delay) && delay >= 0 ? Math.round(delay) : 0}`);
      page.setLive(gameIsLive(envelope?.data));
    } catch (error) {
      console.warn("Could not check for a live game; the LIVE marker keeps its last state.", error?.message || error);
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

/**
 * Phase 12: when the server has a newer build than this page (a restart, or a file changed under
 * static/), a banner offers the reload. Away from the Live sheet the page also reloads by itself the
 * next time it comes back into view, so a tablet left on the Season page is never stuck on old code;
 * during a game only the banner shows, so nothing reloads under the viewer.
 */
function watchForUpdates(page) {
  let pending = false;
  document.addEventListener("kickoff:update", () => {
    if (pending) return;
    pending = true;
    const banner = el(
      "div",
      { class: "update-banner", role: "status" },
      el("span", {}, "A new version of the app is on the server."),
      el("button", { class: "btn", type: "button", onclick: () => window.location.reload() }, "Reload"),
    );
    page.root.insertBefore(banner, page.main);
  });
  // Phase 16 wave 3: the server's own code changed on disk (an update was pulled): only a restart brings it in
  let restartOffered = false;
  document.addEventListener("kickoff:restart-needed", () => {
    if (restartOffered) return;
    restartOffered = true;
    const said = el("span", { class: "note", role: "status" }, "");
    const button = el("button", { class: "btn", type: "button", onclick: async () => {
      button.disabled = true;
      await restartFlow({ say: (words) => { said.textContent = ` ${words}`; }, confirmDuringGame: async () => window.confirm("Our game is under way: the Live sheet drops for about 15 seconds while the server restarts. Restart anyway?") });
      button.disabled = false;
    } }, "Restart the server");
    const banner = el("div", { class: "update-banner", role: "status" }, el("span", {}, "The server's code was updated. Restart it to use the new version."), button, said);
    page.root.insertBefore(banner, page.main);
  });
  document.addEventListener("visibilitychange", () => {
    if (pending && document.visibilityState === "visible" && !["#live", "#board"].includes(window.location.hash)) window.location.reload(); // the board is the live view on a wall: the banner only
  });
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
    onNavigate: (id) => {
      if (window.location.hash !== `#${id}`) window.location.hash = id;
      else show({ id, arg: null });
    },
    onSearch: () => openSearch(),
    menu: menuWith(prefsMeta()?.teamSet?.extraPrimaries), // public release Phase 5b: primary teams one tap away
  });
  root.replaceChildren(page.root);
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
    if (route.id === "injuries") route = { id: "program", arg: null, focus: "program-availability" }; // so does the availability report
    const key = routeKey(route);
    if (currentKey === key) {
      if (restore?.pending) restore = null;
      if (route.focus) focusBand(route.focus);
      return;
    }
    const entry = markEntry();
    const backTo = isNum(entry.scrollY) && restore?.pending ? entry.scrollY : null;
    restore = backTo !== null ? { y: backTo, until: Date.now() + 5000 } : null;
    try {
      document.dispatchEvent(new CustomEvent("kickoff:route", { detail: route })); // sheets and the player card close
    } catch (error) {
      console.error("A layer did not close on the route change.", error);
    }
    if (view) {
      view.unmount();
      view = null;
    }
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
    if (event.key === "/" && !document.querySelector(".sheet-layer .search")) {
      event.preventDefault();
      openSearch();
    } else if ((event.key === "r" || event.key === "R") && !event.shiftKey && !document.querySelector("[data-modal]")) {
      event.preventDefault();
      pull.trigger();
    }
  });
  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-team]:not(.team-link)");
    if (link && link.dataset.team) {
      event.preventDefault();
      openTeam(link.dataset.team);
    }
  });
  installCvd(); // Phase 19: this device's color-blind friendly colors
  installSpoiler(); // Phase 19: this device's spoiler switch
  startGuestMode(); // Phase 18.6: a guest's page says it is view-only
  setTimeout(() => maybeShowReadiness(), 4000); // Phase 18.3: once per server start per device, only when something is not loaded
  if (initial) show(initial);
  else {
    window.location.hash = "program"; // Phase 17 #32: the Game program is home
    show({ id: "program", arg: null });
  }
}

// The guard lets the test suite import the opening rule under Node, where there is no page.
if (typeof document !== "undefined") start();
