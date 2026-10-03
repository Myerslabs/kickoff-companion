// The scores table (L10's list form): every FBS game with poll ranks, points, and the status line.
// Shared by the Live sheet's Scores panel and the Newspaper's Saturday Scores band (Phase 12).
// The rows come from /api/ticker, whose line for our game already follows the spoiler delay.

import { DASH, el, isNum, teamLink, text } from "./dom.js";

function side(team) {
  return el("td", { class: "txt" }, isNum(team?.rank) ? `#${team.rank} ` : "", teamLink(team?.school, text(team?.school)));
}

function points(team) {
  return el("td", { class: "num" }, isNum(team?.points) ? String(team.points) : DASH);
}

/** scoresTable({ games, emptyText }) — games are /api/ticker entries; malformed ones are skipped. */
export function scoresTable({ games = [], emptyText = "No FBS games on this week's slate." } = {}) {
  const rows = (Array.isArray(games) ? games : []).filter((g) => g && typeof g === "object");
  if (!rows.length) return el("p", { class: "note" }, emptyText);
  return el(
    "div",
    { class: "stat-table-wrap" },
    el(
      "table",
      { class: "stat-table stat-table--compact" },
      el("thead", {}, el("tr", {}, el("th", { class: "txt", scope: "col" }, "Away"), el("th", { scope: "col" }, ""), el("th", { class: "txt", scope: "col" }, "Home"), el("th", { scope: "col" }, ""), el("th", { class: "txt", scope: "col" }, "Status"))),
      el("tbody", {}, rows.map((g) => el("tr", { class: g.isUs ? "is-us" : null }, side(g.away), points(g.away), side(g.home), points(g.home), el("td", { class: "txt" }, text(g.detail))))),
    ),
  );
}
