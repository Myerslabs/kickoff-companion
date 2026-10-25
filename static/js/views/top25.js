// The Top 25 page (queue item 11, mock approved 2026-10-13): its own tab after Season ("Newspaper, Pre-Game Program,
// In Game, Season, Top 25"), and in the menu's Views like every page ("everything should always be accessible from the
// menu").
//
// Only the games of the week with an AP Top 25 team ("I only want the AP top 25 scores, no others"), "all games in a
// single pane of glass": a grid of cards (how many across: board 6 below); a last card alone in its row takes the whole
// row. Each card is a compact Pre-Game Program cover ("Same initial
// information for every game that the cover has in the pre-game program"): both teams with their logo, AP rank,
// records, last five and head coach; the countdown, or the live score with its quarter and clock, or the final; the line
// and the over/under; the date, time, stadium and TV; the pregame win probability; the weather. No headlines here (the
// newspaper has them). The order is the AP poll's (the layout pass, owner 2026-10-22: "always needs to show the games in
// order by the AP poll"; the server sorts). Ranked teams with no game are named in one line, "Off this week", no card for
// them.
//
// The layout pass, board 6 (https://claude.ai/artifact/JyA5ZPwaWeMxWhryx1aQsR, "just needs some better spacing"): the
// score alone in the middle, both sides' rows level, a long name on two lines (never the abbreviation the logo shows),
// "Head coach" over each coach, the when in two lines, the weather and the card's tools in its last row; two across on
// a tablet, three from 1700 px and four from 2500 (the design rule of 2026-10-21), one on a phone.
//
// Our game follows the spoiler delay, as on every page. The page refreshes every minute; the server's caches decide
// what that costs (nothing while no game is on).
//
// Post-freeze Wave 3 (owner 2026-10-25): an upset (an AP-ranked team beaten, or trailing live, by a lower-ranked or
// unranked team; the server's `upset`, from the scores the page shows) wears "Upset" or "Upset alert" in its kicker and
// a marked edge (ENH-5; this page only for now). The live, to come, final and upset counts are filters (ENH-6): a tap shows
// those games alone, a second tap or All shows every game again; the choice lasts while the page is open.
//
//   createTop25View({ onStatus })

import { usSchool } from "../identity.js";
import { cover } from "../ui/cover.js";
import { el, isNum, obj, records, teamLink, text } from "../ui/dom.js";
import { crewText } from "../ui/game-staff.js";
import { openMatchupSheet } from "../ui/matchup-sheet.js";
import { fitNames } from "../ui/paper-fit.js";
import { helpsChip } from "../ui/race.js";
import { band, note } from "../ui/states.js";
import { getPrefs } from "../prefs.js";
import { errorPanel, poller } from "./common.js";

const REFRESH_MS = 60 * 1000;

/** The quarter and the clock under a live score, short enough for the card's middle (board 6): "Q2 · 7:02", "OT", "2OT". */
export function clockText(g) {
  const period = isNum(g.period) && g.period >= 1 ? Math.floor(g.period) : null;
  const q = period ? (period <= 4 ? `Q${period}` : period === 5 ? "OT" : `${period - 4}OT`) : /half/i.test(text(g.detail)) ? "Halftime" : "Under way";
  return period && typeof g.clock === "string" && g.clock ? `${q} · ${g.clock}` : q;
}

/** A final's overtimes from its score by quarter: "OT", "2 OT", else null. */
export function overtimes(g) {
  const n = Math.max(Array.isArray(obj(g.home).lineScores) ? g.home.lineScores.length : 0, Array.isArray(obj(g.away).lineScores) ? g.away.lineScores.length : 0) - 4;
  return n > 0 ? (n === 1 ? "OT" : `${n} OT`) : null;
}

/** "Head coach" over the coach's name, on both sides of every card (board 6); a dash when the coach is unknown. */
function coachCell(team, side) {
  const name = typeof team.headCoach === "string" && team.headCoach.trim() ? team.headCoach.trim() : null;
  return el("div", { class: `game-staff cover__staff cover__staff--${side} top25-coach` }, el("span", { class: "top25-coach__label" }, "Head coach"), el("b", {}, text(name)));
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
  // the card's last row (board 6): What we need's chip (F8 feature 1: the game helps our path), then Matchup, which opens
  // the two teams side by side in a sheet (freeze wave F5, ui/matchup-sheet.js)
  const chip = g.helps && typeof g.helps === "object" ? helpsChip(g.helps) : null;
  const matchup = typeof away.school === "string" && away.school && typeof home.school === "string" && home.school
    ? el("button", { class: "btn top25-card__matchup", type: "button", "aria-haspopup": "dialog", onclick: () => openMatchupSheet({ away: away.school, home: home.school }) }, "Matchup")
    : null;
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
    staff: { us: coachCell(away, "us"), them: coachCell(home, "them") },
    conditions: weatherLine(g),
    extra: chip || matchup ? el("div", { class: "top25-card__tools" }, chip ? el("span", { class: "top25-card__helps" }, chip) : null, matchup) : null,
  });
  section.classList.add("top25-card", `top25-card--${status}`);
  if (g.isUs === true) section.classList.add("top25-card--us");
  if (upsetWord(g)) {
    // the badge leads the kicker; spoiler mode hides it with the scores (components.css), since it gives the result away
    section.classList.add("top25-card--upset", `top25-card--upset-${g.upset}`);
    const kicker = section.querySelector(".cover__kicker");
    const badge = el("span", { class: "top25-upset" }, upsetWord(g));
    if (kicker) kicker.prepend(badge, el("span", { class: "top25-upset__sep", "aria-hidden": "true" }, " · "));
    else section.prepend(el("p", { class: "cover__kicker" }, badge));
  }
  section.style.setProperty("--c-away", typeof away.color === "string" && away.color ? away.color : "var(--rule-strong)");
  section.style.setProperty("--c-home", typeof home.color === "string" && home.color ? home.color : "var(--rule-strong)");
  // a long name wraps to two balanced lines (board 6), so no name is fitted; the score still keeps to the middle column
  for (const num of section.querySelectorAll(".cover__center .num")) {
    num.dataset.oneline = "1"; // the score or the countdown keeps to the middle column: it shrinks, never runs under a name
    num.dataset.min = "20";
  }
  return section;
}

const realGame = (g) => g.home && typeof g.home === "object" && g.away && typeof g.away === "object";

/** "Upset" for a final, "Upset alert" while the ranked team trails live; null otherwise (ENH-5). */
export function upsetWord(g) {
  return g?.upset === "final" ? "Upset" : g?.upset === "live" ? "Upset alert" : null;
}

/** The games a filter keeps (ENH-6): all, or those live, to come, final, or upsets. */
export function filtered(games, filter) {
  if (filter === "upset") return games.filter((g) => upsetWord(g));
  if (["live", "pre", "final"].includes(filter)) return games.filter((g) => (["pre", "live", "final"].includes(g.status) ? g.status : "pre") === filter);
  return games;
}

const FILTER_WORDS = { live: "live", pre: "to come", final: "final", upset: "upsets" };

function header(data, state = { filter: null }, onFilter = () => {}) {
  const counts = obj(data.counts);
  const games = records(data.games).filter(realGame);
  const delay = Number(data.delaySeconds);
  const poll = obj(data.poll);
  const label = text(data.label || "This week");
  const title = label === "Bowl season" ? "AP Top 25, bowl season" : `AP Top 25, ${label}`;
  const sub = [isNum(poll.week) ? `AP poll, week ${poll.week}` : null, `${games.length} ${games.length === 1 ? "game" : "games"} with a ranked team`].filter(Boolean).join(" · ");
  const order = games.length > 1 ? el("b", { class: "top25-head__order" }, "In poll order") : null; // board 6: says how the cards run
  // the counts are filters (ENH-6): a pressed count shows its games alone; a count of none cannot be pressed
  const pill = (id, n, live = false) => {
    const count = isNum(n) ? n : 0;
    const on = state.filter === id;
    return el("button", { class: `top25-count${live ? " top25-count--live" : ""}${id === "upset" ? " top25-count--upset" : ""}${on ? " is-on" : ""}`, type: "button", "aria-pressed": on ? "true" : "false", disabled: count === 0 && !on ? true : null, onclick: () => onFilter(on ? null : id) }, live ? el("i", { class: "top25-live-dot", "aria-hidden": "true" }) : null, `${count} ${FILTER_WORDS[id]}`);
  };
  const all = el("button", { class: `top25-count${state.filter ? "" : " is-on"}`, type: "button", "aria-pressed": state.filter ? "false" : "true", onclick: () => onFilter(null) }, "All");
  return el(
    "header",
    { class: "top25-head" },
    el("div", { class: "top25-head__words" }, el("h1", { class: "top25-head__title" }, title), el("p", { class: "top25-head__line" }, order, order ? " · " : null, sub)),
    el("div", { class: "top25-head__counts", role: "group", "aria-label": "Show games" }, all, pill("live", counts.live, true), pill("pre", counts.pre), pill("final", counts.final), pill("upset", counts.upset)),
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

function render(envelope, container, state = { filter: null }, onFilter = () => {}) {
  const data = obj(envelope?.data);
  const games = records(data.games).filter(realGame);
  const shown = filtered(games, state.filter);
  const empty = typeof data.note === "string" && data.note ? data.note : "No game this week has an AP Top 25 team.";
  const none = state.filter ? `No ${FILTER_WORDS[state.filter] === "to come" ? "games to come" : `${FILTER_WORDS[state.filter]}${state.filter === "upset" ? "" : " games"}`} right now. All shows every game.` : empty;
  const page = el(
    "div",
    { class: "page page--wide top25" },
    header(data, state, onFilter),
    shown.length ? el("div", { class: "top25-grid" }, shown.map(card)) : band({ id: "top25-empty", title: "This week's games", collapsible: false, state: { status: "ready" }, body: () => note(none, { kind: "empty" }) }),
    offLine(data.offThisWeek),
  );
  container.replaceChildren(page);
  return page;
}

export function createTop25View({ onStatus } = {}) {
  const delay = Number(getPrefs().delaySeconds);
  const state = { filter: null }; // the count pressed (ENH-6), kept across the minute's refreshes while the page is open
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
      const draw = () => {
        page = render(envelope, container, state, (next) => {
          state.filter = next;
          draw();
          schedule();
        });
      };
      draw();
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
