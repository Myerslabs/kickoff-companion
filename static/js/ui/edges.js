// Biggest edges (Phase 16, stream PROGRAM; audit P-11 items 3-4, L-02): unit against unit, drawn as a
// two-team table so the Game program and the Live sheet's Edges panel read the same way. Each side's
// cell is its value with a rank chip linking to that stat's national list: on an offense row our
// chip is its offense stat and the opponent's its defense stat, on a defense row the other way round.
// The edge is signed (positive favors our unit); the table draws it as a tug-of-war bar that leans to the side it favours (Phase 17).
//
// Frozen API (the Live stream consumes these; do not change the signatures):
//   edgesTable(edges, { usAbbr, themAbbr, usTeam, themTeam, limit })  -> .stat-table-wrap (a two-team table)
//       edges: the /api/program `edges` rows { label, side, usRank, themRank, of, themOf, edge, usValue, themValue,
//       format, usFormat, themFormat, usKey, themKey, usMetric, themMetric }. A bad row is skipped.
//   edgeRows(edges, { usAbbr, themAbbr })   the same rows shaped for twoTeamTable (exported for the tests).
//   edgesSummary(edges, { usAbbr, themAbbr })  "SWT better in 14 of 24 · Biggest: Passing, SWT O vs GBS D, +95", or "".

import { usLabel } from "../identity.js";
import { DASH, el, fmtSigned, isNum, records, text } from "./dom.js";
import { twoTeamTable } from "./two-team.js";

/** "Passing: Swampwater Tech offense vs Gravy Boat State defense" -> "Passing". */
function unitName(label) {
  const s = typeof label === "string" ? label.trim() : "";
  if (!s) return DASH;
  const cut = s.indexOf(":");
  return cut > 0 ? s.slice(0, cut).trim() : s;
}

function metricOf(metric, key) {
  if (typeof metric === "string" && metric) return metric;
  return typeof key === "string" && key ? `profile:${key}` : null;
}

function isOffense(row) {
  return row.side !== "defense"; // the payload says "offense" or "defense"; anything else reads as our offense
}

export function edgeRows(edges, { usAbbr = usLabel(), themAbbr = DASH } = {}) {
  const us = text(usAbbr);
  const them = text(themAbbr);
  return records(edges)
    .filter((e) => isNum(e.usRank) || isNum(e.themRank) || isNum(e.edge))
    .map((e) => {
      const offense = isOffense(e);
      const edge = isNum(e.edge) ? e.edge : isNum(e.usRank) && isNum(e.themRank) ? e.themRank - e.usRank : null;
      return {
        label: unitName(e.label),
        sub: offense ? `${us} offense vs ${them} defense` : `${them} offense vs ${us} defense`,
        side: offense ? "offense" : "defense",
        edge,
        leads: isNum(edge) ? (edge > 0 ? "us" : edge < 0 ? "them" : "even") : null,
        rowClass: null, // Phase 17 #16: no tinted rows; the tug bar says whose edge it is
        us: { value: e.usValue, format: e.usFormat || e.format, rank: e.usRank, of: e.of, metric: metricOf(e.usMetric, e.usKey) },
        them: { value: e.themValue, format: e.themFormat || e.format, rank: e.themRank, of: isNum(e.themOf) ? e.themOf : e.of, metric: metricOf(e.themMetric, e.themKey) },
      };
    });
}

export function edgesTable(edges, { usAbbr = usLabel(), themAbbr = DASH, usTeam, themTeam, limit } = {}) {
  let rows = edgeRows(edges, { usAbbr, themAbbr });
  if (isNum(limit) && limit > 0) rows = rows.slice(0, limit);
  const us = text(usAbbr);
  const them = text(themAbbr);
  return twoTeamTable({
    rows,
    usAbbr: us,
    themAbbr: them,
    usTeam,
    themTeam,
    tug: true, // Phase 17 #14, #16: the bar leans to the unit with the edge, in its team's color
    className: "tt--edges", // hints.js maps these composed labels ("Passing: SWT offense vs ...") to the Edges entry
    labelHead: "Matchup",
    caption: "Biggest edges, unit against unit by national rank",
  });
}

export function edgesSummary(edges, { usAbbr = usLabel(), themAbbr = DASH } = {}) {
  const rows = edgeRows(edges, { usAbbr, themAbbr }).filter((r) => isNum(r.edge));
  if (!rows.length) return "";
  const us = text(usAbbr);
  const them = text(themAbbr);
  const ahead = rows.filter((r) => r.edge > 0).length;
  const top = rows.reduce((best, r) => (Math.abs(r.edge) > Math.abs(best.edge) ? r : best), rows[0]);
  // Phase 17 (#15): plain words, not "SWT O vs GRID D, +95"
  const units = top.side === "offense" ? `${us} offense vs ${them} defense` : `${them} offense vs ${us} defense`;
  const who = top.edge > 0 ? us : top.edge < 0 ? them : null;
  return `${us} better in ${ahead} of ${rows.length} · Biggest: ${top.label}, ${units}, ${who ? `${who} by ${Math.abs(top.edge)} ranks` : "even"}`;
}
