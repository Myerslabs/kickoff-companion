// Game leaders by category, ours left and the opponent right (screenshot brief, 2026-09-21).
// Each side is a tap target that opens the player card. A missing side says so, at the same height.
//
// Phase 16 (stream PROGRAM; audit LRP-12, P-07, L-06). Frozen API (the Live stream consumes it):
//   leadersGrid({ categories, usAbbr, themAbbr, onTap, head = true, className })
//       categories: [{ id, label, us: player, them: player }]
//       player: { name, playerId, number, position, headshotUrl, line }
//       line: a string ("12/20, 180 yds, 2 TD"), or { hero, rest }: hero is the category's key number
//       ("180 yds", bold chalk) and rest the others in fog ("12/20, 2 TD").
//       head: one "SWT | GBS" row over the columns; a 2px divider always stands between the two teams.
//   leaderLine(category, stats)   { hero, rest } for a box-score row (hero = the category's ORDER_KEY stat).
//   boxLeader(category, rows)     the top box-score row as { name, playerId, stats, line: { hero, rest }, lineText }.
//   statLine(value, format, stat) "4.5 sacks", "1,204 yds", "38 tkl": the value in its own format with a unit.
//   leadersSkeleton(categories)

import { usLabel } from "../identity.js";
import { DASH, el, fmtStat, isNum, playerFace, text } from "./dom.js";

const PARTS = {
  passing: (s) => ({ hero: `${text(s.YDS)} yds`, rest: [text(s["C/ATT"]), isNum(s.TD) ? `${s.TD} TD` : null, isNum(s.INT) ? `${s.INT} int` : null] }),
  rushing: (s) => ({ hero: `${text(s.YDS)} yds`, rest: [`${text(s.CAR)} car`, isNum(s.TD) ? `${s.TD} TD` : null] }),
  receiving: (s) => ({ hero: `${text(s.YDS)} yds`, rest: [`${text(s.REC)} rec`, isNum(s.TD) ? `${s.TD} TD` : null] }),
  defensive: (s) => ({ hero: `${text(s.TOT)} tkl`, rest: [isNum(s.TFL) && s.TFL > 0 ? `${s.TFL} tfl` : null, isNum(s.SACKS) && s.SACKS > 0 ? `${s.SACKS} sck` : null, isNum(s.PD) && s.PD > 0 ? `${s.PD} pd` : null] }),
  interceptions: (s) => ({ hero: `${text(s.INT)} int`, rest: [`${text(s.YDS)} yds`] }),
  kicking: (s) => ({ hero: `${text(s.PTS)} pts`, rest: [`FG ${text(s.FG)}`, `XP ${text(s.XP)}`] }),
  punting: (s) => ({ hero: `${text(s.AVG)} avg`, rest: [`${text(s.NO)} punts`, isNum(s.LONG) ? `long ${s.LONG}` : null] }),
  puntReturns: (s) => ({ hero: `${text(s.YDS)} yds`, rest: [`${text(s.NO)} ret`, isNum(s.TD) && s.TD > 0 ? `${s.TD} TD` : null] }),
  kickReturns: (s) => ({ hero: `${text(s.YDS)} yds`, rest: [`${text(s.NO)} ret`, isNum(s.TD) && s.TD > 0 ? `${s.TD} TD` : null] }),
};

const ORDER_KEY = { passing: "YDS", rushing: "YDS", receiving: "YDS", defensive: "TOT", interceptions: "INT", kicking: "PTS", punting: "AVG", puntReturns: "YDS", kickReturns: "YDS" };

// The unit after a season or game total: [one, many]. A stat not listed prints the bare number.
const UNITS = {
  YDS: ["yd", "yds"],
  TOT: ["tkl", "tkl"],
  SOLO: ["solo", "solo"],
  SACKS: ["sack", "sacks"],
  TFL: ["tfl", "tfl"],
  INT: ["int", "int"],
  PD: ["pd", "pd"],
  TD: ["TD", "TD"],
  REC: ["rec", "rec"],
  CAR: ["car", "car"],
  FGM: ["FG", "FG"],
  PTS: ["pt", "pts"],
  YPP: ["avg", "avg"],
  AVG: ["avg", "avg"],
};

/** "4.5 sacks", "1,204 yds", "1 sack": the value in the board's own format (never forced to 0f) with its unit. */
export function statLine(value, format, stat) {
  if (!isNum(value)) return DASH;
  const shown = fmtStat(value, typeof format === "string" && format ? format : Number.isInteger(value) ? "0f" : "1f");
  const unit = UNITS[typeof stat === "string" ? stat.toUpperCase() : ""];
  if (!unit) return shown;
  return `${shown} ${value === 1 ? unit[0] : unit[1]}`;
}

/** { hero, rest } for one box-score row: the category's key number first, the others after it. */
export function leaderLine(category, stats) {
  const s = stats && typeof stats === "object" ? stats : {};
  const make = PARTS[category];
  if (!make) return { hero: text(s[ORDER_KEY[category] || "YDS"]), rest: "" };
  const { hero, rest } = make(s);
  return { hero, rest: rest.filter(Boolean).join(", ") };
}

/** The top box-score row for a category, as {name, playerId, line: {hero, rest}, lineText, stats}. Null when nothing is judged. */
export function boxLeader(category, rows) {
  const key = ORDER_KEY[category] || "YDS";
  const list = (Array.isArray(rows) ? rows : []).filter((row) => row && isNum(row.stats?.[key]));
  if (!list.length) return null;
  list.sort((a, b) => b.stats[key] - a.stats[key]);
  const top = list[0];
  const line = leaderLine(category, top.stats);
  return { name: top.name, playerId: top.playerId, line, lineText: [line.hero, line.rest].filter(Boolean).join(", "), stats: top.stats };
}

function lineNode(line) {
  if (line && typeof line === "object" && !Array.isArray(line)) {
    const hero = typeof line.hero === "string" || isNum(line.hero) ? text(line.hero) : DASH;
    const rest = typeof line.rest === "string" && line.rest.trim() ? line.rest.trim() : null;
    return el("div", { class: "leader__line" }, el("b", { class: "leader__hero" }, hero), rest ? el("span", { class: "leader__rest" }, `, ${rest}`) : null);
  }
  return el("div", { class: "leader__line" }, text(line));
}

function side({ player, abbr, them, onTap }) {
  const cls = them ? "leader--them" : "leader--us";
  if (!player || typeof player !== "object") return el("div", { class: `leader leader--empty ${cls}` }, `No ${abbr} line yet`);
  const meta = [abbr, player.position].filter((v) => typeof v === "string" && v.trim() && v !== DASH).map((v) => v.trim()).join(" ");
  return el(
    "button",
    { class: `leader ${cls}`, type: "button", onclick: () => onTap && onTap(player) },
    playerFace(player, { them, abbr, size: 44 }),
    el("div", { class: "leader__text" }, el("div", { class: "leader__name" }, text(player.name)), lineNode(player.line), el("div", { class: "leader__meta" }, meta || DASH)),
  );
}

/**
 * leadersGrid({ categories: [{ id, label, us: player, them: player }], usAbbr, themAbbr, onTap, head, className })
 */
export function leadersGrid({ categories = [], usAbbr = usLabel(), themAbbr = DASH, onTap, head = true, className } = {}) {
  const us = text(usAbbr);
  const them = text(themAbbr);
  const list = (Array.isArray(categories) ? categories : []).filter((cat) => cat && typeof cat === "object");
  return el(
    "div",
    { class: `leaders${className ? ` ${className}` : ""}` },
    head && list.length ? el("div", { class: "leaders__head" }, el("span", { class: "leaders__abbr leaders__abbr--us" }, us), el("span", { class: "leaders__abbr leaders__abbr--them" }, them)) : null,
    list.map((cat) =>
      el(
        "div",
        { class: "leader-cat" },
        el("div", { class: "leader-cat__title" }, text(cat.label)),
        side({ player: cat.us, abbr: us, them: false, onTap: (p) => onTap && onTap(p, "us") }),
        side({ player: cat.them, abbr: them, them: true, onTap: (p) => onTap && onTap(p, "them") }),
      ),
    ),
  );
}

export function leadersSkeleton(categories = 4) {
  return el(
    "div",
    { class: "leaders" },
    Array.from({ length: categories }, () => el("div", { class: "leader-cat" }, el("div", { class: "skel", style: { gridColumn: "1 / -1", height: "12px", width: "80px", margin: "0 auto" } }), el("div", { class: "skel", style: { height: "44px" } }), el("div", { class: "skel", style: { height: "44px" } }))),
  );
}
