// The scores table (L10's list form): every FBS game with poll ranks, points, and the status line.
// Shared by the Live sheet's Scores panel and the Newspaper's Saturday Scores band (Phase 12).
// The rows come from /api/ticker, whose line for our game already follows the spoiler delay.
//
// Phase 16 wave 3 (audit G3-14, L-15): rows grouped Live, Upcoming, Final in the server's order, each group headed
// with its count; a final's winner in bold and its loser in fog; a live status in the "good" color and a kickoff
// time in fog, each in a small boxed tag; poll ranks as linked poll badges. The table is built once and update(games)
// patches it in place, flashing only the points that changed.
//
//   scoresTable({ games, emptyText })  -> <div class="stat-table-wrap"> with update(games)
//   scoresSummary(games)               "6 live · 21 final · 33 to come", or "" for none

import { DASH, el, flashChanges, isNum, snapshotKeys, teamLink, text } from "./dom.js";
import { pollHref } from "./national-link.js";
import { pollBadge } from "./stat-table.js";

const GROUPS = [["live", "Live"], ["pre", "Upcoming"], ["final", "Final"]];

function games(list) {
  return (Array.isArray(list) ? list : []).filter((g) => g && typeof g === "object");
}

function groupOf(game) {
  return game.status === "live" || game.status === "final" ? game.status : "pre";
}

export function scoresSummary(list) {
  const rows = games(list);
  const count = (status) => rows.filter((g) => groupOf(g) === status).length;
  return [[count("live"), "live"], [count("final"), "final"], [count("pre"), "to come"]].filter(([n]) => n > 0).map(([n, w]) => `${n} ${w}`).join(" · ");
}

function outcome(game, side) {
  if (game.status !== "final") return null;
  const mine = game[side]?.points;
  const theirs = game[side === "home" ? "away" : "home"]?.points;
  if (!isNum(mine) || !isNum(theirs) || mine === theirs) return null;
  return mine > theirs ? "win" : "lose";
}

function team(game, side) {
  const t = game[side] && typeof game[side] === "object" ? game[side] : {};
  const school = typeof t.school === "string" && t.school ? t.school : null;
  const rank = isNum(t.rank) ? pollBadge(t.rank, "AP", { href: pollHref("AP", { team: school }), label: school, showPoll: false }) : null;
  const result = outcome(game, side);
  return el("td", { class: `txt scores__team${result ? ` scores__team--${result}` : ""}` }, rank, rank ? " " : null, teamLink(school, text(school)));
}

function points(game, side) {
  const t = game[side] && typeof game[side] === "object" ? game[side] : {};
  const result = outcome(game, side);
  return el("td", { class: `num scores__pts${result ? ` scores__pts--${result}` : ""}`, dataset: { k: `pts:${text(game.gameId)}:${side}` } }, isNum(t.points) ? String(t.points) : DASH);
}

function statusCell(game) {
  return el("td", { class: "txt" }, el("span", { class: `scores__st scores__st--${groupOf(game)}`, dataset: { k: `st:${text(game.gameId)}` } }, text(game.detail)));
}

function rows(list) {
  const all = games(list);
  const out = [];
  for (const [status, label] of GROUPS) {
    const these = all.filter((g) => groupOf(g) === status);
    if (!these.length) continue;
    out.push(el("tr", { class: "scores__group" }, el("th", { scope: "rowgroup", colspan: "5" }, `${label} (${these.length})`)));
    for (const g of these) out.push(el("tr", { class: g.isUs ? "is-us" : null }, team(g, "away"), points(g, "away"), team(g, "home"), points(g, "home"), statusCell(g)));
  }
  return out;
}

/** scoresTable({ games, emptyText }) — games are /api/ticker entries; malformed ones are skipped. */
export function scoresTable({ games: list = [], emptyText = "No FBS games on this week's slate." } = {}) {
  const tbody = el("tbody", {});
  const table = el(
    "table",
    { class: "stat-table stat-table--compact scores" },
    el("caption", { class: "sr-only" }, "Scores"),
    el("thead", {}, el("tr", {}, el("th", { class: "txt", scope: "col" }, "Away"), el("th", { scope: "col" }, ""), el("th", { class: "txt", scope: "col" }, "Home"), el("th", { scope: "col" }, ""), el("th", { class: "txt", scope: "col" }, "Status"))),
    tbody,
  );
  const empty = el("p", { class: "note" }, emptyText);
  const wrap = el("div", { class: "stat-table-wrap" });
  let shown = false;
  const draw = (next) => {
    const list2 = games(next);
    if (!list2.length) {
      wrap.replaceChildren(empty);
      shown = false;
      return;
    }
    const before = snapshotKeys(tbody);
    tbody.replaceChildren(...rows(list2));
    if (!shown) {
      wrap.replaceChildren(table);
      shown = true;
    }
    flashChanges(before, tbody); // only the points and statuses that changed since the last draw
  };
  draw(list);
  wrap.update = draw;
  return wrap;
}
