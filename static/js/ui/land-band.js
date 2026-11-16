// Our land (the Season stop, the season as one line Wave 4; the owner's board of 2026-10-30): one team's standing on the
// Imperialism Map (FEAT-17) as a band of the Season page, from /api/imperialism/<season>/team/<team>: its cells and share
// of the map, its rank among the schools holding land, the last few pieces taken and lost, and the way to the whole map.
// No map yet (a 503 with the words why) or a team with no land (404) reads as an empty state, never an error page.
//
//   landBand(team, { season, id })

import { eventLine } from "../views/imperialism.js";
import { fetchJson } from "../views/common.js";
import { el, fmtNum, isNum, ordinal, text } from "./dom.js";
import { band, note } from "./states.js";

const TITLE = "Our land";
const LINES = 6;

function shell(id, title, state, extra = {}) {
  return band({ id, title, collapsible: true, foldable: true, state, ...extra });
}

/** The band's body from the team's answer: the head line, the last pieces taken and lost, the link. */
export function landBody(d, team) {
  const now = d.now && typeof d.now === "object" ? d.now : {};
  const weeks = Array.isArray(d.weeks) ? d.weeks.filter((w) => w && typeof w === "object") : [];
  const last = weeks.length ? weeks[weeks.length - 1] : null;
  const labelOf = new Map(weeks.map((w) => [`${w.phase}:${w.week}`, w.label]));
  const events = (Array.isArray(d.events) ? d.events : []).filter((e) => e && typeof e === "object" && isNum(e.cellsMoved) && e.cellsMoved > 0);
  const lines = events.map((e) => eventLine(e, team, labelOf.get(`${e.phase}:${e.week}`) || text(e.label) || "")).reverse().slice(0, LINES);
  const start = weeks.length && isNum(weeks[0].cells) ? weeks[0].cells : null;
  const facts = [
    isNum(now.rank) && isNum(now.of) ? `${ordinal(now.rank)} of the ${now.of} schools holding land` : "no land right now",
    start !== null ? `started with ${fmtNum(start)}` : null,
    last && typeof last.record === "string" && last.record ? `${last.record} ${text(last.label) ? `after ${last.label}` : ""}`.trim() : null,
  ].filter(Boolean);
  return el(
    "div",
    { class: "land" },
    el("div", { class: "land__head" }, el("p", { class: "land__cells" }, el("b", {}, fmtNum(isNum(now.cells) ? now.cells : 0)), el("span", {}, `${now.cells === 1 ? "cell" : "cells"} · ${isNum(now.pct) ? now.pct.toFixed(1) : "0.0"}% of the map`)), el("p", { class: "land__facts" }, facts.join(" · "))),
    el("h4", { class: "d2-head" }, "Taken and lost, latest first"),
    lines.length
      ? el("ul", { class: "land__list" }, ...lines.map((l) => el("li", { class: "land__line" }, el("span", { class: "land__week" }, l.week), el("span", { class: "land__words" }, l.words), el("b", { class: `land__moved${l.cells > 0 ? " is-up" : l.cells < 0 ? " is-down" : ""}` }, `${l.cells > 0 ? "+" : ""}${fmtNum(l.cells)}`))))
      : note(`No land has changed hands for ${team} yet.`),
    el("p", { class: "land__more" }, el("a", { class: "btn btn--quiet", href: "#imperialism" }, "Open the Imperialism Map")),
  );
}

export function landBand(team, { season = null, id = "season-land" } = {}) {
  if (typeof team !== "string" || !team || !isNum(season)) return null;
  const host = el("div", { class: "land-host" }, shell(id, TITLE, { status: "loading" }, { skeleton: () => el("div", { class: "skel skel--block" }) }));
  fetchJson(`/api/imperialism/${encodeURIComponent(String(season))}/team/${encodeURIComponent(team)}`)
    .then((envelope) => {
      const d = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
      const now = d.now && typeof d.now === "object" ? d.now : {};
      host.replaceChildren(shell(id, TITLE, { status: "ready" }, { summary: `${fmtNum(isNum(now.cells) ? now.cells : 0)} cells${isNum(now.rank) ? ` · ${ordinal(now.rank)} by land` : ""}`, body: () => landBody(d, team) }));
    })
    .catch((error) => {
      const status = isNum(error?.status) ? error.status : null;
      if (status === 404) {
        host.replaceChildren(shell(id, TITLE, { status: "empty", message: `${team} holds no land on this season's map.` }));
        return;
      }
      if (status === 503) {
        host.replaceChildren(shell(id, TITLE, { status: "empty", message: text(error?.message) || "The map has not been worked out yet. The weekly run draws it Sundays." }));
        return;
      }
      host.replaceChildren(shell(id, TITLE, { status: "error", message: `${text(error?.message || "no answer")}.` }));
    });
  return host;
}
