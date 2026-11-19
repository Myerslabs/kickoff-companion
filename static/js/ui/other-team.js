// Another team's page (FEAT-5, owner 2026-10-25: "I want it to be for my team, but I also want to see every team the way I
// see my team"). Roster, Recruiting and the Pre-Game Program open for any FBS team with `?team=<school>`; this is the
// head that says whose page it is, with the way back to ours. Our own pages draw none.
//
//   otherTeam(params)                       the school asked for, or null for our own team (or none)
//   withTeam(url, team)                     "/api/roster" -> "/api/roster?team=Texas" (null team: the url as given)
//   otherTeamHead(info, what, ourHref)      the head: logo, "Texas roster", the conference, "Florida's roster"
//   teamLinks(school, schedule)             the team's own pages: Season, Roster, Recruiting, its next game's program

import { usSchool } from "../identity.js";
import { clearViewing, viewing } from "../viewing.js";
import { el, isNum, teamLogo, text } from "./dom.js";

export function otherTeam(params) {
  const raw = params && typeof params === "object" ? params.team : null;
  const name = typeof raw === "string" ? raw.trim() : "";
  return name && name !== usSchool() ? name : null;
}

export function withTeam(url, team) {
  if (!team) return url;
  return `${url}${url.includes("?") ? "&" : "?"}team=${encodeURIComponent(team)}`;
}

export function otherTeamHead(info, what, ourHref) {
  const block = info && typeof info === "object" ? info : {};
  const school = typeof block.school === "string" && block.school ? block.school : null;
  if (!school) return null;
  const ours = usSchool();
  return el(
    "header",
    { class: "team-head other-team flow-full", "aria-label": `${school} ${what}` },
    el(
      "div",
      { class: "team-head__top" },
      teamLogo(block, { size: 56, lazy: false, className: "team-head__logo" }),
      el("div", {}, el("div", { class: "team-head__name" }, `${school} ${what}`), block.conference ? el("div", { class: "team-head__conf" }, text(block.conference)) : null),
      backHome(school, ours, ourHref, what),
    ),
  );
}

/** The way back to ours: "Florida's roster"; on a device switched to this team (batch 3) "Back to Florida", which ends the
 *  switch; switched to another, our page by name (the bare address would follow the switch). */
function backHome(school, ours, ourHref, what) {
  if (!ours) return null;
  const shown = viewing();
  if (shown && shown === school) return el("button", { type: "button", class: "btn btn--quiet other-team__back", onclick: () => clearViewing() }, `Back to ${ours}`);
  if (!ourHref) return null;
  return el("a", { class: "btn btn--quiet other-team__back", href: shown ? withTeam(ourHref, ours) : ourHref }, `${ours}'s ${what}`);
}

export function teamLinks(school, schedule) {
  if (typeof school !== "string" || !school) return null;
  const q = school === usSchool() ? "" : `?team=${encodeURIComponent(school)}`;
  const games = Array.isArray(schedule) ? schedule.filter((g) => g && typeof g === "object") : [];
  const next = games.find((g) => g.completed !== true && (isNum(g.gameId) || /^\d{1,12}$/.test(String(g.gameId ?? ""))));
  const link = (href, words) => el("a", { class: "btn btn--quiet", href }, words);
  return el(
    "nav",
    { class: "other-team__links flow-full", "aria-label": `${school}'s pages` },
    link(`#season${q}`, "Season"),
    link(`#roster${q}`, "Roster"),
    link(`#recruiting${q}`, "Recruiting"),
    next ? link(`#program=${next.gameId}${q}`, "Next game's program") : null,
  );
}
