// The Top 25 page (queue item 11, mock approved 2026-10-13): its own tab after Season ("Newspaper, Pre-Game Program,
// In Game, Season, Top 25"), and in the menu's Views like every page ("everything should always be accessible from the
// menu").
//
// Only the games of the week with an AP Top 25 team ("I only want the AP top 25 scores, no others"), "all games in a
// single pane of glass": a grid of cards, three across on a 1080p screen, two on the iPad held sideways, one on a
// phone; a last card alone in its row takes the whole row. Each card is a compact Pre-Game Program cover ("Same initial
// information for every game that the cover has in the pre-game program"): both teams with their logo, AP rank,
// records, last five and head coach; the countdown, or the live score with its quarter and clock, or the final; the line
// and the over/under; the date, time, stadium and TV; the pregame win probability; the weather. No headlines here (the
// newspaper has them). The order is the owner's: "The higher the ranked game, the higher the article". Ranked teams
// with no game are named in one line, "Off this week", no card for them.
//
// Our game follows the spoiler delay, as on every page. The page refreshes every minute; the server's caches decide
// what that costs (nothing while no game is on).
//
//   createTop25View({ onStatus })

import { usSchool } from "../identity.js";
import { cover } from "../ui/cover.js";
import { el, isNum, obj, records, teamLink, text } from "../ui/dom.js";
import { crewText, teamStaff } from "../ui/game-staff.js";
import { fitNames } from "../ui/paper-fit.js";
import { band, note } from "../ui/states.js";
import { getPrefs } from "../prefs.js";
import { errorPanel, poller } from "./common.js";

const REFRESH_MS = 60 * 1000;
const QUARTERS = ["1st quarter", "2nd quarter", "3rd quarter", "4th quarter"];

const abbr = (t) => text(t.abbreviation || (typeof t.school === "string" ? t.school.slice(0, 4).toUpperCase() : null));

function clockText(g) {
  const q = isNum(g.period) ? (g.period <= 4 ? QUARTERS[g.period - 1] : g.period === 5 ? "Overtime" : `${g.period - 4} overtimes`) : /half/i.test(text(g.detail)) ? "Halftime" : "Under way";
  return typeof g.clock === "string" && g.clock ? `${q}, ${g.clock}` : q;
}

function overtimes(g) {
  const n = Math.max(Array.isArray(obj(g.home).lineScores) ? g.home.lineScores.length : 0, Array.isArray(obj(g.away).lineScores) ? g.away.lineScores.length : 0) - 4;
  return n > 0 ? (n === 1 ? "overtime" : `${n} overtimes`) : null;
}

function weatherLine(g) {
  const w = obj(g.weather);
  const word = g.status === "final" ? "Kickoff" : g.status === "live" ? "At kickoff" : "Forecast";
  const bits = [
    w.indoors === true ? "indoors" : null,
    isNum(w.tempF) ? `${Math.round(w.tempF)}°F` : null,
    isNum(w.windMph) && w.indoors !== true ? `wind ${Math.round(w.windMph)} mph${typeof w.windDir === "string" && w.windDir ? ` ${w.windDir}` : ""}` : null,
    typeof w.sky === "string" && w.sky ? w.sky.toLowerCase() : null,
  ].filter(Boolean);
  if (!bits.length) return null;
  return el("div", { class: "top25-weather" }, el("span", { class: "top25-weather__label" }, word), ` ${bits.join(", ")}`);
}

function tagOf(g) {
  if (typeof g.bowl === "string" && g.bowl) return g.bowl;
  return g.conferenceGame === true ? text(g.conference || "Conference game") : "Non-conference";
}

function card(g) {
  const away = obj(g.away);
  const home = obj(g.home);
  const status = ["pre", "live", "final"].includes(g.status) ? g.status : "pre";
  const line = obj(g.line);
  const coaches = { coaches: { us: { headCoach: away.headCoach }, them: { headCoach: home.headCoach } } };
  const section = cover({
    compact: true,
    label: `${text(away.school)} ${g.neutralSite ? "versus" : "at"} ${text(home.school)}`,
    href: g.isUs === true ? "#live" : isNum(g.gameId) ? `#box=${g.gameId}` : null,
    us: away,
    them: home,
    homeIsUs: false,
    date: g.kickoff,
    startTimeTbd: g.startTimeTbd === true,
    venue: g.venue,
    neutralSite: g.neutralSite === true,
    tv: g.tv,
    crew: g.broadcast ? crewText({ broadcast: g.broadcast }, g) : null, // freeze wave F4: our game's announcers from the notes, as on the program's cover
    line: { formatted: typeof line.short === "string" && line.short ? line.short : line.formatted, overUnder: line.overUnder },
    pregame: { homeWinProbability: g.homeWinProbability },
    state: status === "pre" ? undefined : status,
    usPoints: away.points,
    themPoints: home.points,
    live: status === "live" ? { text: clockText(g) } : null,
    finalNote: status === "final" ? overtimes(g) : null,
    kicker: [g.isUs === true ? "Our game" : null, status === "live" ? "Live" : null, tagOf(g)].filter(Boolean).join(" · "),
    staff: { us: teamStaff(coaches, "us", { abbr: abbr(away), school: away.school }), them: teamStaff(coaches, "them", { abbr: abbr(home), school: home.school }) },
    conditions: weatherLine(g),
  });
  section.classList.add("top25-card", `top25-card--${status}`);
  if (g.isUs === true) section.classList.add("top25-card--us");
  section.style.setProperty("--c-away", typeof away.color === "string" && away.color ? away.color : "var(--rule-strong)");
  section.style.setProperty("--c-home", typeof home.color === "string" && home.color ? home.color : "var(--rule-strong)");
  for (const name of section.querySelectorAll(".cover__name")) {
    name.dataset.oneline = "1"; // a team's name on one line: it shrinks, then reads as its abbreviation
    name.dataset.min = "15";
  }
  for (const num of section.querySelectorAll(".cover__center .num")) {
    num.dataset.oneline = "1"; // the score or the countdown keeps to the middle column: it shrinks, never runs under a name
    num.dataset.min = "20";
  }
  return section;
}

const realGame = (g) => g.home && typeof g.home === "object" && g.away && typeof g.away === "object";

function header(data) {
  const counts = obj(data.counts);
  const games = records(data.games).filter(realGame);
  const delay = Number(data.delaySeconds);
  const poll = obj(data.poll);
  const label = text(data.label || "This week");
  const title = label === "Bowl season" ? "AP Top 25, bowl season" : `AP Top 25, ${label}`;
  const sub = [isNum(poll.week) ? `AP poll, week ${poll.week}` : null, `${games.length} ${games.length === 1 ? "game" : "games"} with a ranked team`].filter(Boolean).join(" · ");
  const pill = (n, words, live = false) => el("span", { class: `top25-count${live ? " top25-count--live" : ""}` }, live ? el("i", { class: "top25-live-dot", "aria-hidden": "true" }) : null, `${isNum(n) ? n : 0} ${words}`);
  return el(
    "header",
    { class: "top25-head" },
    el("div", { class: "top25-head__words" }, el("h1", { class: "top25-head__title" }, title), el("p", { class: "top25-head__line" }, sub)),
    el("div", { class: "top25-head__counts" }, pill(counts.live, "live", true), pill(counts.pre, "to come"), pill(counts.final, "final")),
    el(
      "p",
      { class: "top25-head__delay" },
      Number.isFinite(delay) && delay > 0
        ? `Our game follows your spoiler delay: its score runs ${Math.round(delay)} s behind the broadcast, so this page never gets ahead of the TV. The Spoiler delay button on In Game changes it.`
        : "Our game shows the feed as it comes, with no spoiler delay. The Spoiler delay button on In Game sets one.",
      data.weather === "none" ? " Weather for every game shows with a Tier 1 key." : null,
    ),
  );
}

function offLine(teams) {
  const off = records(teams);
  if (!off.length) return null;
  const us = usSchool();
  return el(
    "p",
    { class: "top25-off" },
    el("b", {}, "Off this week: "),
    off.flatMap((t, i) => [i ? ", " : null, el("span", { class: `top25-off__team${t.school === us ? " is-us" : ""}` }, isNum(t.rank) ? `No. ${t.rank} ` : null, t.school ? teamLink(t.school, text(t.school)) : text(null))]).filter(Boolean),
  );
}

function render(envelope, container) {
  const data = obj(envelope?.data);
  const games = records(data.games).filter(realGame);
  const empty = typeof data.note === "string" && data.note ? data.note : "No game this week has an AP Top 25 team.";
  const page = el(
    "div",
    { class: "page page--wide top25" },
    header(data),
    games.length ? el("div", { class: "top25-grid" }, games.map(card)) : band({ id: "top25-empty", title: "This week's games", collapsible: false, state: { status: "ready" }, body: () => note(empty, { kind: "empty" }) }),
    offLine(data.offThisWeek),
  );
  container.replaceChildren(page);
  return page;
}

export function createTop25View({ onStatus } = {}) {
  const delay = Number(getPrefs().delaySeconds);
  let page = null;
  let frame = null;
  let timer = null;
  const fit = () => {
    frame = null;
    try {
      if (page && page.isConnected && page.clientWidth > 0) fitNames(page);
    } catch (error) {
      console.error("The Top 25 names could not be fitted; they keep their plain sizes.", error);
    }
  };
  const schedule = () => {
    if (frame === null && typeof requestAnimationFrame === "function") frame = requestAnimationFrame(fit);
  };
  const onResize = () => {
    clearTimeout(timer);
    timer = setTimeout(schedule, 150);
  };
  const inner = poller({
    url: `/api/top25?delay=${Number.isFinite(delay) ? delay : 30}`,
    refreshMs: REFRESH_MS,
    holdDuringRuns: false, // live scores: never held for a data load (2026-10-16)
    onStatus,
    render: (envelope, container) => {
      page = render(envelope, container);
      schedule();
      if (typeof document !== "undefined" && document.fonts?.ready) document.fonts.ready.then(schedule).catch(() => {});
    },
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Top 25", message, retry)),
    loadingDetail: "This week's ranked games",
    renderLoading: () =>
      el(
        "div",
        { class: "page page--wide top25" },
        el("header", { class: "top25-head" }, el("div", { class: "skel", style: { width: "min(360px, 60%)", height: "32px" } })),
        el("div", { class: "top25-grid" }, [1, 2, 3, 4, 5, 6].map(() => el("div", { class: "top25-card top25-card--skel" }, el("div", { class: "skel" })))),
      ),
  });
  const win = typeof window !== "undefined" && typeof window.addEventListener === "function" ? window : null;
  return {
    mount(target) {
      inner.mount(target);
      win?.addEventListener("resize", onResize);
    },
    refresh: () => inner.refresh(),
    unmount() {
      win?.removeEventListener("resize", onResize);
      clearTimeout(timer);
      if (frame !== null && typeof cancelAnimationFrame === "function") cancelAnimationFrame(frame);
      frame = null;
      page = null;
      inner.unmount();
    },
    get last() {
      return inner.last;
    },
  };
}
