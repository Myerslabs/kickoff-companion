// The Tale of the tape (owner pick 2026-10-09; sizes 2026-10-10): both matchups of every stat, each on the shared two-team
// table (ui/two-team.js) with its own tug-of-war bar: our offense against their defense, then our defense against their
// offense, side by side on a wide band and stacked on a narrower one, each table sizing itself (large with the rank chips
// in their own headed columns, medium with the FBS chips, small with values and bars; nothing wraps, nothing scrolls).
// Rows come from the program's edges (app/services/profiles.py edges(): two rows per stat, one per side), through
// ui/edges.js edgeRows, so the Live sheet's Edges panel and this table never disagree. The three biggest edges on each
// side carry a "top 3" tag under their bar (spec P3).
//
//   tapeTable(edges, { usAbbr, themAbbr, usTeam, themTeam })  -> .tt-pair holding the two tables
//   tapePairs(edges, { usAbbr, themAbbr })                      the rows paired by stat (exported for the tests)

import { usLabel } from "../identity.js";
import { DASH, el, isNum, text } from "./dom.js";
import { edgeRows } from "./edges.js";
import { twoTeamTable } from "./two-team.js";

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

/** A unit's head in its three forms: "Swampwater Tech offense", "SWT offense", "SWT off". */
function unitHead(team, abbr, unit) {
  const school = typeof team === "string" && team.trim() ? team.trim() : text(abbr);
  return { long: `${school} ${unit}`, mid: `${text(abbr)} ${unit}`, short: `${text(abbr)} ${unit === "offense" ? "off" : "def"}` };
}

/** One matchup's table: our unit first, the three biggest edges tagged, the matchup words in the heads (not under each label). */
function sideTable(rows, side, opts) {
  const top = topThree(rows);
  const ours = side === "offense" ? "offense" : "defense";
  const theirs = side === "offense" ? "defense" : "offense";
  return twoTeamTable({
    rows: rows.map((r) => ({ ...r, sub: null, tag: top.has(r) ? "top 3" : null })),
    usAbbr: opts.usAbbr,
    themAbbr: opts.themAbbr,
    usTeam: opts.usTeam,
    themTeam: opts.themTeam,
    usHead: unitHead(opts.usTeam, opts.usAbbr, ours),
    themHead: unitHead(opts.themTeam, opts.themAbbr, theirs),
    tug: true,
    labelHead: "Statistic",
    className: "tt--edges tt--tape", // hints.js maps the edges' labels to the Edges entry
    caption: `Tale of the tape: ${opts.usAbbr} ${ours} against ${opts.themAbbr} ${theirs}, by national rank`,
  });
}

export function tapeTable(edges, { usAbbr = usLabel(), themAbbr = DASH, usTeam, themTeam } = {}) {
  const opts = { usAbbr: text(usAbbr), themAbbr: text(themAbbr), usTeam, themTeam };
  const rows = edgeRows(edges, { usAbbr: opts.usAbbr, themAbbr: opts.themAbbr });
  return el(
    "div",
    { class: "tt-pair tape-pair" },
    sideTable(rows.filter((r) => r.side === "offense"), "offense", opts),
    sideTable(rows.filter((r) => r.side !== "offense"), "defense", opts),
  );
}
