// The Tale of the tape (owner pick 2026-10-09): both matchups of a stat in ONE row, each with its own tug-of-war bar:
// our offense against their defense on the left, their offense against our defense on the right. The rank chips sit
// in their own headed columns, a space away from the values, so a row reads "rank, number, who leads, number, rank".
// Rows come from the program's edges (app/services/profiles.py edges(): two rows per stat, one per side), through
// ui/edges.js edgeRows, so the Live sheet's Edges panel and this table never disagree. The three biggest edges on
// each side carry a "top 3" tag under their bar (spec P3).
//
//   tapeTable(edges, { usAbbr, themAbbr, usTeam, themTeam })  -> .stat-table-wrap holding the table
//   tapePairs(edges, { usAbbr, themAbbr })                      the rows paired by stat (exported for the tests)

import { usLabel } from "../identity.js";
import { DASH, el, fmtStat, isNum, text } from "./dom.js";
import { nationalHref } from "./national-link.js";
import { rankChip, rankChipPlaceholder } from "./stat-table.js";
import { edgeRows } from "./edges.js";
import { tugShare } from "./two-team.js";

/** [{ label, offense: row | null, defense: row | null }] in the order the edges came (biggest gap first). */
export function tapePairs(edges, { usAbbr = usLabel(), themAbbr = DASH } = {}) {
  const pairs = new Map();
  for (const row of edgeRows(edges, { usAbbr, themAbbr })) {
    const key = text(row.label);
    if (!pairs.has(key)) pairs.set(key, { label: key, offense: null, defense: null });
    pairs.get(key)[row.side === "defense" ? "defense" : "offense"] = row;
  }
  return [...pairs.values()];
}

function topThree(rows) {
  return new Set(rows.filter((r) => r && isNum(r.edge)).sort((a, b) => Math.abs(b.edge) - Math.abs(a.edge)).slice(0, 3));
}

function chipCell(side, s, label, team) {
  let href = null;
  try {
    href = typeof s?.metric === "string" && s.metric ? nationalHref(s.metric, { team }) : null;
  } catch {
    href = null;
  }
  const chip = isNum(s?.rank) ? rankChip(s.rank, s.of, { href, label }) : rankChipPlaceholder();
  return el("td", { class: `num tape__rank tape__rank--${side}` }, chip);
}

function valueCell(side, s, lead) {
  const cls = ["num", "tape__val", `tape__val--${side}`];
  if (lead === side) cls.push("lead");
  else if (lead === "us" || lead === "them") cls.push("trail");
  return el("td", { class: cls.join(" ") }, isNum(s?.value) ? fmtStat(s.value, s?.format) : DASH);
}

function tugCell(row, { usAbbr, themAbbr }, top) {
  const td = el("td", { class: `tape__tug${top ? " tape__tug--top" : ""}` });
  const lead = row?.leads;
  const track = el("span", { class: "tug", role: "img" }, el("span", { class: "tug__mid" }));
  if (lead === "us" || lead === "them") {
    track.append(el("span", { class: `tug__bar tug__bar--${lead}`, style: { width: `${Math.round(tugShare(row) * 50)}%` } }));
    const gap = isNum(row.edge) ? Math.abs(row.edge) : null;
    const says = `${lead === "us" ? text(usAbbr) : text(themAbbr)} has the edge${gap !== null ? `, ${gap} national ranks apart` : ""}`;
    track.setAttribute("aria-label", says);
    track.setAttribute("title", says);
  } else {
    const says = lead === "even" ? "Even" : "No edge to show";
    track.setAttribute("aria-label", says);
    track.setAttribute("title", says);
  }
  td.append(track);
  if (top) td.append(el("span", { class: "tape__top" }, "top 3")); // never append(null): the DOM would print the word
  return td;
}

/** One side's five cells: chip, value, bar, value, chip (our unit first on the offense pair, theirs first on the other). */
function pairCells(row, first, opts, top) {
  if (!row) return [el("td", { class: "num tape__rank" }, DASH), el("td", { class: "num tape__val" }, DASH), el("td", { class: "tape__tug" }, ""), el("td", { class: "num tape__val" }, DASH), el("td", { class: "num tape__rank" }, DASH)];
  const second = first === "us" ? "them" : "us";
  const teamOf = (side) => (side === "us" ? opts.usTeam : opts.themTeam);
  return [
    chipCell(first, row[first], row.label, teamOf(first)),
    valueCell(first, row[first], row.leads),
    tugCell(row, opts, top),
    valueCell(second, row[second], row.leads),
    chipCell(second, row[second], row.label, teamOf(second)),
  ];
}

export function tapeTable(edges, { usAbbr = usLabel(), themAbbr = DASH, usTeam, themTeam } = {}) {
  const us = text(usAbbr);
  const them = text(themAbbr);
  const opts = { usAbbr: us, themAbbr: them, usTeam, themTeam };
  const pairs = tapePairs(edges, { usAbbr: us, themAbbr: them });
  const topOff = topThree(pairs.map((p) => p.offense));
  const topDef = topThree(pairs.map((p) => p.defense));
  const head = el(
    "thead",
    {},
    el(
      "tr",
      { class: "tape__pairs" },
      el("th", { scope: "col", rowspan: "2", class: "txt" }, "Statistic"),
      el("th", { scope: "colgroup", colspan: "5", class: "tape__pair tape__pair--off" }, `${us} offense against ${them} defense`),
      el("th", { scope: "colgroup", colspan: "5", class: "tape__pair tape__pair--def" }, `${them} offense against ${us} defense`),
    ),
    el(
      "tr",
      {},
      el("th", { scope: "col", class: "num" }, "FBS rank"),
      el("th", { scope: "col", class: "num tape__who" }, us),
      el("th", { scope: "col" }, "Edge"),
      el("th", { scope: "col", class: "num tape__who" }, them),
      el("th", { scope: "col", class: "num" }, "FBS rank"),
      el("th", { scope: "col", class: "num tape__first" }, "FBS rank"),
      el("th", { scope: "col", class: "num tape__who" }, them),
      el("th", { scope: "col" }, "Edge"),
      el("th", { scope: "col", class: "num tape__who" }, us),
      el("th", { scope: "col", class: "num" }, "FBS rank"),
    ),
  );
  const body = el(
    "tbody",
    {},
    ...pairs.map((p) =>
      el(
        "tr",
        {},
        el("td", { class: "txt tape__label" }, p.label),
        ...pairCells(p.offense, "us", opts, topOff.has(p.offense)),
        ...pairCells(p.defense, "them", opts, topDef.has(p.defense)),
      ),
    ),
  );
  const table = el("table", { class: "stat-table tape tt--edges" }, el("caption", { class: "sr-only" }, "Tale of the tape: each unit's national rank against the unit it faces, both matchups of every stat"), head, body);
  return el("div", { class: "stat-table-wrap stat-table-wrap--tape" }, table);
}
