// The team switch (batch 3, owner 2026-11-16: the top bar and every team's name). A side sheet: Back to our team while
// switched, this week's opponent first, the teams this device switched to lately, then a search of every FBS team. A pick
// switches this device for this visit (viewing.js); nothing is kept on the server.
//
//   openTeamSwitch()             the sheet
//   nextOpponent(line)           this week's opponent from the season's line (stops.js), or null
//   switchButton(school, info)   "Change to <school>" for a team's sheet; null for ours or the team already switched to

import { usSchool } from "../identity.js";
import { stopsNow } from "../stops.js";
import { clearViewing, setViewing, viewing, viewingInfo } from "../viewing.js";
import { fetchJson } from "../views/common.js";
import { el, teamLogo, text } from "./dom.js";
import { openSheet } from "./remote.js";

const RECENT_KEY = "kickoff:viewing-recent";
const RECENT_MAX = 5;
const SEARCH_WAIT_MS = 180;

const str = (value) => (typeof value === "string" ? value.trim() : "");

export function nextOpponent(line = stopsNow()) {
  const items = Array.isArray(line?.items) ? line.items.filter((item) => item && typeof item === "object" && item.kind === "week") : [];
  const current = line && typeof line.current === "object" ? line.current : null;
  const atStop = current && current.gameId !== null && current.gameId !== undefined ? items.find((item) => String(item.gameId) === String(current.gameId)) : null;
  const item = atStop || items.find((week) => !week.result) || null;
  return item ? str(item.opponent) || null : null;
}

function recent() {
  try {
    const list = JSON.parse(globalThis.sessionStorage?.getItem(RECENT_KEY) || "[]");
    return Array.isArray(list) ? list.filter((team) => team && typeof team === "object" && str(team.school)).slice(0, RECENT_MAX) : [];
  } catch {
    return [];
  }
}

function remember(team) {
  try {
    const list = [team, ...recent().filter((t) => t.school !== team.school)].slice(0, RECENT_MAX);
    globalThis.sessionStorage?.setItem(RECENT_KEY, JSON.stringify(list));
  } catch {
    // no storage: the sheet just lists no recent teams
  }
}

/** The teams /api/search finds for `q` (never players), each { school, abbreviation, conference, mascot, logo, logoDark }. */
async function findTeams(q) {
  const envelope = await fetchJson(`/api/search?q=${encodeURIComponent(q)}`);
  const teams = envelope?.data && Array.isArray(envelope.data.teams) ? envelope.data.teams : [];
  return teams.filter((team) => team && typeof team === "object" && str(team.school));
}

/** A school's own row from the search (its logo and conference), or the name alone when the search has nothing. */
async function teamInfo(school) {
  try {
    const teams = await findTeams(school);
    return teams.find((team) => team.school === school) || { school };
  } catch {
    return { school };
  }
}

function choose(team, close) {
  if (typeof close === "function") close();
  if (!team || team.school === usSchool()) {
    clearViewing();
    return;
  }
  remember(team);
  setViewing(team);
}

/** "Change to Kentucky" for a team's own sheet (views/team.js): ours and the team already switched to get none. */
export function switchButton(school, info = null, { onDone } = {}) {
  const name = str(school);
  if (!name || name === usSchool() || name === viewing()) return null;
  return el(
    "button",
    {
      type: "button",
      class: "btn btn--quiet team-switch__to",
      title: `See the app as ${name} on this device`,
      onclick: async () => {
        const team = info && typeof info === "object" && str(info.school) === name ? info : await teamInfo(name);
        choose(team, onDone);
      },
    },
    `Change to ${name}`,
  );
}

export function openTeamSwitch() {
  const now = viewingInfo();
  const ours = usSchool();
  let handle = null;
  const close = () => handle?.close();

  function row(team, note) {
    const current = now ? now.school === team.school : team.school === ours;
    return el(
      "button",
      { type: "button", class: `team-switch__row${current ? " is-current" : ""}`, "aria-current": current ? "true" : null, onclick: () => choose(team, close) },
      teamLogo(team, { size: 32 }),
      el("span", { class: "team-switch__words" }, el("b", {}, text(team.school)), note || team.conference ? el("small", {}, text(note || team.conference)) : null),
      current ? el("span", { class: "team-switch__mark" }, "On screen") : null,
    );
  }

  const opponentSlot = el("div", { class: "team-switch__group" });
  const results = el("div", { class: "team-switch__results", "aria-live": "polite" });
  const input = el("input", { type: "search", class: "team-switch__input", placeholder: "Search any FBS team", "aria-label": "Search any FBS team", autocomplete: "off", enterkeyhint: "search" });

  const back = now
    ? el(
        "button",
        { type: "button", class: "btn btn--primary team-switch__back", onclick: () => choose({ school: ours }, close) },
        `Back to ${ours}`,
      )
    : null;

  const opponent = nextOpponent();
  if (opponent && opponent !== ours) {
    opponentSlot.append(el("h3", { class: "team-switch__head" }, "This week"), row({ school: opponent }, "Our opponent"));
    teamInfo(opponent).then((team) => {
      opponentSlot.replaceChildren(el("h3", { class: "team-switch__head" }, "This week"), row(team, "Our opponent"));
    });
  }
  const lately = recent().filter((team) => team.school !== opponent && team.school !== ours);
  const recentGroup = lately.length ? el("div", { class: "team-switch__group" }, el("h3", { class: "team-switch__head" }, "Lately"), ...lately.map((team) => row(team))) : null;

  let timer = null;
  let asked = 0;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) {
      results.replaceChildren();
      return;
    }
    timer = setTimeout(async () => {
      const mine = ++asked;
      results.replaceChildren(el("p", { class: "team-switch__note" }, "Searching…"));
      try {
        const teams = await findTeams(q);
        if (mine !== asked) return;
        results.replaceChildren(...(teams.length ? teams.slice(0, 12).map((team) => row(team, team.school === ours ? "Our team" : null)) : [el("p", { class: "team-switch__note" }, `No FBS team matches "${q}".`)]));
      } catch (error) {
        if (mine !== asked) return;
        results.replaceChildren(el("p", { class: "team-switch__note team-switch__note--error" }, `The search did not answer (${text(error?.message) || "error"}).`));
      }
    }, SEARCH_WAIT_MS);
  });

  const body = el(
    "div",
    { class: "team-switch" },
    el("p", { class: "team-switch__lede" }, now ? `This device is showing ${now.school}. My Team, the Pre-Game Program, the paper, the roster and recruiting follow the switch; nothing is saved.` : "See the app as another team on this device only, until you switch back. Nothing is saved."),
    back,
    opponentSlot,
    recentGroup,
    el("div", { class: "team-switch__group" }, el("h3", { class: "team-switch__head" }, "Any team"), input, results),
  );
  handle = openSheet({ title: "Change team", body, className: "team-switch-sheet" }); // batch 3 review: "a change team for the switch"
  setTimeout(() => {
    try {
      if (!(globalThis.matchMedia && globalThis.matchMedia("(pointer: coarse)").matches)) input.focus(); // a tablet's keyboard waits for a tap
    } catch {
      // no matchMedia: leave the focus
    }
  }, 50);
  return handle;
}
