// The scores table (L10's list form): every FBS game with poll ranks, points, and the status line.
// Shared by In Game's Scores panel and the Newspaper's Saturday Scores band (Phase 12).
// The rows come from /api/ticker, whose line for our game already follows the spoiler delay.
//
// Phase 16 wave 3 (audit G3-14, L-15): rows grouped Live, Upcoming, Final in the server's order, each group headed
// with its count; a final's winner in bold and its loser in fog; a live status in the "good" color and a kickoff
// time in fog, each in a small boxed tag; poll ranks as linked poll badges. The table is built once and update(games)
// patches it in place, flashing only the points that changed.
//
// Table sizes, wave 2 (owner 2026-10-10; docs/03-DESIGN.md, Table sizes): the table sizes itself by its own box like a
// stat table (applyStatSize, fitSize), in place, since the kit has no group rows or update(). Every data point has its own
// column (rule 3): the AP rank leaves the name cell for a column before each team ("AP rank" at large, "AP" at medium, a
// dash for an unranked team), gone at small; the school at large and medium, its abbreviation at small; the points under
// "Pts". The group rows span the columns each size shows, and each update measures again.
//
//   scoresTable({ games, emptyText })  -> <div class="stat-table-wrap"> with update(games) and applySize(size) (draw at
//                                      one size by hand, for the tests)
//   scoresSummary(games)               "6 live · 21 final · 33 to come", or "" for none

import { DASH, el, flashChanges, isNum, obj, snapshotKeys, str, teamLink, text } from "./dom.js";
import { pollHref } from "./national-link.js";
import { DROPPED, fitSize, watchSize } from "./sizes.js";
import { applyStatSize, pollBadge, sizedText } from "./stat-table.js";

const GROUPS = [["live", "Live"], ["pre", "Upcoming"], ["final", "Final"]];
const WIDTH = { large: 7, medium: 7, small: 5 }; // the columns each size shows (the two AP rank columns go at small)

function games(list) {
  return (Array.isArray(list) ? list : []).filter((g) => g && typeof g === "object" && !Array.isArray(g));
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
  const mine = obj(game[side]).points;
  const theirs = obj(game[side === "home" ? "away" : "home"]).points;
  if (!isNum(mine) || !isNum(theirs) || mine === theirs) return null;
  return mine > theirs ? "win" : "lose";
}

/** A team's AP rank in its own column (medium and large): the poll badge, or a dash when it is unranked. */
function rankCell(game, side) {
  const t = obj(game[side]);
  const school = str(t.school);
  const badge = isNum(t.rank) ? pollBadge(t.rank, "AP", { href: pollHref("AP", { team: school }), label: school, showPoll: false }) : null;
  return el("td", { class: "num scores__rank st__min-medium" }, badge || DASH);
}

/** A team's name: the school at large and medium, its abbreviation at small, a link to its page. */
function team(game, side) {
  const t = obj(game[side]);
  const school = str(t.school);
  const result = outcome(game, side);
  return el("td", { class: `txt scores__team${result ? ` scores__team--${result}` : ""}` }, school ? teamLink(school, sizedText(school, school, str(t.abbr) || school)) : DASH);
}

function points(game, side) {
  const t = obj(game[side]);
  const result = outcome(game, side);
  return el("td", { class: `num scores__pts${result ? ` scores__pts--${result}` : ""}`, dataset: { k: `pts:${text(game.gameId)}:${side}` } }, isNum(t.points) ? String(t.points) : DASH);
}

function statusCell(game) {
  return el("td", { class: "txt" }, el("span", { class: `scores__st scores__st--${groupOf(game)}`, dataset: { k: `st:${text(game.gameId)}` } }, text(game.detail)));
}

function rows(list, width) {
  const all = games(list);
  const out = [];
  for (const [status, label] of GROUPS) {
    const these = all.filter((g) => groupOf(g) === status);
    if (!these.length) continue;
    out.push(el("tr", { class: "scores__group" }, el("th", { scope: "rowgroup", colspan: String(width) }, `${label} (${these.length})`)));
    for (const g of these) out.push(el("tr", { class: g.isUs ? "is-us" : null }, rankCell(g, "away"), team(g, "away"), points(g, "away"), rankCell(g, "home"), team(g, "home"), points(g, "home"), statusCell(g)));
  }
  return out;
}

/** A column head in its three forms; the long one is the term the stat hints look up. */
function head(label, mid, short, className) {
  return el("th", { class: className, scope: "col", dataset: { term: label } }, sizedText(label, mid, short));
}

/** scoresTable({ games, emptyText }) — games are /api/ticker entries; malformed ones are skipped. */
export function scoresTable({ games: list = [], emptyText = "No FBS games on this week's slate." } = {}) {
  const tbody = el("tbody", {});
  const table = el(
    "table",
    { class: "stat-table stat-table--compact scores" },
    el("caption", { class: "sr-only" }, "Scores"),
    el(
      "thead",
      {},
      el(
        "tr",
        {},
        head("AP rank", "AP", "AP", "num st__min-medium"),
        head("Away", null, null, "txt"),
        head("Pts", null, null, "num"),
        head("AP rank", "AP", "AP", "num st__min-medium"),
        head("Home", null, null, "txt"),
        head("Pts", null, null, "num"),
        head("Status", null, null, "txt"),
      ),
    ),
    tbody,
  );
  const empty = el("p", { class: "note" }, typeof emptyText === "string" && emptyText ? emptyText : "No FBS games on this week's slate.");
  const wrap = el("div", { class: "stat-table-wrap scores-wrap" });
  const width = () => WIDTH[wrap.dataset.size] || WIDTH.large;
  /** Draw at one size: the attribute the stylesheet keys on, and the group rows spanning the columns it shows. */
  const apply = (size) => {
    applyStatSize(wrap, size);
    for (const th of tbody.querySelectorAll("tr.scores__group th")) th.setAttribute("colspan", String(width()));
  };
  apply("large");
  watchSize(wrap, () => {
    const size = fitSize(wrap, table, apply);
    if (size === null) return;
    if (size === DROPPED) wrap.classList.remove("stat-table-wrap--fits");
    else wrap.classList.add("stat-table-wrap--fits"); // never a scroll box
  });
  let shown = false;
  const draw = (next) => {
    const list2 = games(next);
    if (!list2.length) {
      wrap.replaceChildren(empty);
      shown = false;
      return;
    }
    const before = snapshotKeys(tbody);
    tbody.replaceChildren(...rows(list2, width()));
    if (!shown) {
      wrap.replaceChildren(table);
      shown = true;
    }
    flashChanges(before, tbody); // only the points and statuses that changed since the last draw
    if (typeof wrap.measure === "function") wrap.measure(); // a longer name may need a smaller size
  };
  draw(list);
  wrap.update = draw;
  wrap.applySize = apply; // draw at one size by hand (the tests, which have no layout engine to measure with)
  return wrap;
}
