// The two-team table (Phase 16, stream PROGRAM; audit P-01, P-02, P-06, P-09, DS-02, GX-05, GX-11; sizes 2026-10-10).
// One way to put us beside an opponent everywhere on the Game program, the Live sheet, the matchup sheet and the
// styleguide. Every data point has its own column: the national rank chip, the conference rank chip and the value
// each in a headed column, mirrored outward from the tug-of-war bar (our chips outside, our value against the bar,
// the opponent the other way round), a thin line between every column, the better value bold chalk and the other
// fog (ties stay neutral), and every chip with a list behind it a link to that list.
//
// The table draws at one of three sizes by its own box (ui/sizes.js; owner 2026-10-10, the matchup band locked):
//   large   both chips a side under "FBS rank" and "<conference> rank", the team's school and mascot over its three
//           columns with the rank heads under it, whole stat names on one line, the hints
//   medium  the national chip only under "FBS", the school (the abbreviation when the school will not fit on one
//           line), middle-length stat names, the hints
//   small   values and the bar only, the abbreviation, the shortest stat names, no hints
// Nothing wraps and nothing scrolls sideways; a table that cannot fit even at small shows at small anyway, the minimal
// table, never a note (owner 2026-10-10).
//
// Frozen API (the Live stream consumes these; do not change the signatures):
//   twoTeamTable({ rows, usAbbr, themAbbr, groups, better = true, usTeam, themTeam, usName, themName, usConf, themConf,
//                  year, ladder = false, underline = false, tug = false, labelHead = "Statistic", caption, extra,
//                  className, onSize })  -> .stat-table-wrap.tt-wrap[data-size]
//       row: { label, sub, format, higherIsBetter, leads, metric, metricYear, rowClass, key, scale, team, labelMid,
//              labelShort, us: { value, text, textShort, rank, of, tie, metric, href, conf }, them: { ...the same } }
//         conf      { rank, of, href, conference }: the conference rank chip, in its own column at large.
//         text      shown instead of fmtStat(value, format); value still decides who leads.
//         textShort a side's shorter words at small (wave 2: the leader lines' conference-game line, "940 yds" for
//                   "940 yds, 84/139, 7 TD, 2 int"), so a long line never holds a phone's table wider than its box.
//         leads     "us" | "them" | "even" overrides the comparison (edges, where the two values are different stats).
//         metric    the national list key (row-wide, or per side); usTeam/themTeam highlight the team, and
//                   metricYear (or year) opens that season's list. href on a side wins over metric.
//         key       the row's flash key (wave 2, 2026-10-10): each value cell carries data-k "<key>:us" / "<key>:them",
//                   so a page that redraws on every play (In Game, L-03) flashes only the numbers that changed.
//         scale     for a measure that runs either side of zero (PPA per play): the gap between the two values that
//                   leans the bar all the way. Two such values near zero have no meaningful share of their sum
//                   (+0.05 against -0.02 would lean all the way), so the bar leans by the gap over the scale instead.
//         team      the row is a team (Common opponents, wave 2): its label links to that team's page.
//         labelMid, labelShort  the row's own shorter words (a team's abbreviation at small) instead of the stat name's
//                   forms from ui/sizes.js; the long form is the label.
//       groups: [{ title, note, rows, us, them, missing }] draws group header rows inside the one table (rows is then
//                   ignored). us/them: a line under each team's own columns (its scheme); missing: { label, onClick }
//                   or { label, href } shown where a side has none, the way to go get it (never a blank).
//       usName/themName: the school and mascot for the large head; usTeam/themTeam the school; usAbbr/themAbbr short.
//       usHead/themHead: { long, mid, short } for a head that names a unit instead (the tape's "Swampwater Tech offense").
//       row.tag: a word under the row's bar (the tape's "by 39 ranks").
//       usConf/themConf: each side's conference short name for its rank head (ours from the identity by default).
//       better: a symmetric "Better" column (the leader's abbreviation in bold chalk, "Even" in fog).
//       ladder: a 0-100 national percentile track per row (GX-05): our dot and an opponent ring (large and medium).
//       underline: a 3px percentile underline inside each value cell (GX-11).
//       extra: [{ head, cell(row) -> node|text, className, size }] columns after the opponent's (the edges table);
//                   size "medium" or "large" names the smallest size that shows the column (default: every size).
//       tug (Phase 17 #14, owner pick 2026-10-07): a tug-of-war bar between the two teams instead of the Better
//                   column, leaning to the leader in that team's color, longer for a bigger gap in national rank;
//                   a row with no national ranks leans by its own two values (owner 2026-10-10, wave 2: how far ahead,
//                   never a fixed amount), so In Game's tables lean by the real margin.
//       centered (owner 2026-10-10, the leader lines): the stat name sits over its bar in the middle column and the two
//                   teams' columns mirror around it, so the edges and the center line run down the middle of the band.
//       onSize(size): called with "large", "medium", "small" or "none" whenever the table measures itself.
//       Players (tables wave 3, owner 2026-10-10: Leaders' "vs opponent" boards): a side's who, whoName and onWho put a
//                   player column on each team's side, outermost (our player outside our chips, theirs outside theirs), at
//                   every size. who is the name (text, drawn in its four forms by ui/dom.js personName) or a drawn node (a
//                   face and the name, its own personName inside) shown at large and medium; a node sits in one table only,
//                   so build fresh rows for each table. whoName is the player's name for a drawn who: at small the name
//                   alone, without the face (whoShort, plain words, is the older small form). onWho() makes it a button (the
//                   player card). Both sides get the column when any row names a player, so the table stays mirrored; a
//                   side with no player in that row shows a dash. whoHead (default "Player") heads the column. A table
//                   with no who is unchanged.
//                   Item 6 (owner 2026-10-11, "K. Crawford" when there is no room, one line only): a table with players steps
//                   down through the name steps as well (ui/sizes.js personSteps): large with full names, large with
//                   "K. Crawford", then each size with "K. Crawford", small with the surname, the reduced surname, and last the
//                   clip; names are settled within each side (a second letter for two who would read alike).
//                   whoSub: the player's second fact (his position), its own column beside the player at large and medium
//                   and gone at small (owner decision 1, 2026-10-10: a fact once drawn under a name gets its own column);
//                   whoSubHead (default "Pos") heads it. Both sides get it when any row has one.
//   applySize(wrap, size)         draw the wrap at one size (the tests, which have no layout engine, call this).
//   twoTeamLeader(row)            "us" | "them" | "even", or null when nothing can be compared.
//   percentile(rank, of)          0 (last) to 100 (first) from a national rank, or null. Ranks already run
//                                 best-first whichever way the stat runs, so a lower-is-better stat needs no flip.
//   listLink(href, label, { rank, of, name, className })  a text link to a list (the cover's and the card's
//                                 "SP+ #13"), offered to "kickoff:rank-link" first like a chip.
//   tugShare(row)                 how far the bar leans, 0.12 to 1: the gap in national rank over half the field, else
//                                 valueShare(row), else the least lean for a leader with nothing to measure.
//   valueShare(row)               how far ahead by the two values alone, 0 to 1: their gap over their sum (35 to 14 is
//                                 0.43, 14 to 0 all the way), or over row.scale when the row names one; null when a
//                                 value is missing or there is nothing to measure.
//   PPA_SCALE                     row.scale for a PPA row (0.5 per play leans all the way).

import { confLabel, usLabel } from "../identity.js";
import { append, DASH, el, fmtStat, isNum, nameSteps, obj, personName, records, settleNames, teamLink, text } from "./dom.js";
import { nationalHref } from "./national-link.js";
import { applyNames, DROPPED, fitSize, labelForms, personSteps, sizeNote, splitStep, watchSize } from "./sizes.js";
import { rankChip } from "./stat-table.js";

const SIDES = ["us", "them"];
const RANK = { large: 0, medium: 1, small: 2 }; // a column with size S shows at every size at least as wide as S
const STEPS = ["large", "medium", "medium:abbr", "small"]; // medium twice: the school, then the abbreviation

function isHash(href) {
  return typeof href === "string" && href.startsWith("#") && href.length > 1;
}

/** 0 (the last team) to 100 (the first), rounded; null for a missing, impossible or one-team rank. */
export function percentile(rank, of) {
  if (!isNum(rank) || !isNum(of) || of <= 1 || rank < 1 || rank > of) return null;
  return Math.round((100 * (of - rank)) / (of - 1));
}

/** Who has the better number: the stat's direction when it is known, else the national ranks. */
export function twoTeamLeader(row) {
  const r = obj(row);
  if (r.leads === "us" || r.leads === "them" || r.leads === "even") return r.leads;
  const a = obj(r.us).value;
  const b = obj(r.them).value;
  if (typeof r.higherIsBetter === "boolean" && isNum(a) && isNum(b)) {
    if (a === b) return "even";
    return (r.higherIsBetter ? a > b : a < b) ? "us" : "them";
  }
  const ra = obj(r.us).rank;
  const rb = obj(r.them).rank;
  if (isNum(ra) && isNum(rb)) return ra === rb ? "even" : ra < rb ? "us" : "them";
  return null;
}

function valueText(row, side) {
  const s = obj(row[side]);
  if (typeof s.text === "string" && s.text.trim()) return text(s.text);
  const format = typeof s.format === "string" ? s.format : typeof row.format === "string" ? row.format : "0f";
  return s.value === null || s.value === undefined ? DASH : fmtStat(s.value, format);
}

function sideHref(row, side, opts) {
  const s = obj(row[side]);
  if (isHash(s.href)) return s.href;
  const metric = typeof s.metric === "string" ? s.metric : row.metric;
  const team = side === "us" ? opts.usTeam : opts.themTeam;
  const year = isNum(row.metricYear) || /^\d{4}$/.test(String(row.metricYear ?? "")) ? row.metricYear : opts.year;
  return nationalHref(metric, { team, year });
}

/** A list link that is not a chip: the page's side sheet may take the tap (same event as the chips). */
export function listLink(href, label, { rank, of, name, className } = {}) {
  const body = typeof Node !== "undefined" && label instanceof Node ? label : text(label); // a drawn value, or words
  if (!isHash(href)) return el("span", { class: className || null }, body);
  return el(
    "a",
    {
      class: `list-link${className ? ` ${className}` : ""}`,
      href,
      onclick: (event) => {
        event.stopPropagation();
        const offer = new CustomEvent("kickoff:rank-link", { detail: { href, rank: isNum(rank) ? rank : null, of: isNum(of) ? of : null, label: typeof name === "string" ? name : null }, cancelable: true });
        document.dispatchEvent(offer);
        if (offer.defaultPrevented) event.preventDefault();
      },
    },
    body,
  );
}

/** A label in its three forms, one shown per size; plain text when the forms are all the same word. */
function formsOf(label) {
  const f = labelForms(label);
  if (f.mid === f.long && f.short === f.long) return [text(f.long)];
  return [el("span", { class: "tt__t tt__t--long" }, f.long), el("span", { class: "tt__t tt__t--mid" }, f.mid), el("span", { class: "tt__t tt__t--short" }, f.short)];
}

/** A team's name in its three forms: school and mascot, the school, the abbreviation. */
function nameForms(long, mid, short) {
  const a = text(long || mid || short);
  const b = text(mid || short || long);
  const c = text(short || mid || long);
  if (a === b && b === c) return [a];
  return [el("span", { class: "tt__t tt__t--long" }, a), el("span", { class: "tt__t tt__t--mid" }, b), el("span", { class: "tt__t tt__t--short" }, c)];
}

function underlineBar(pct, side) {
  if (pct === null) return null;
  return el("span", { class: `tt__pct tt__pct--${side}`, "aria-hidden": "true" }, el("span", { class: "tt__pct-fill", style: { width: `${pct}%` } }));
}

function ladderCell(row, opts) {
  const us = percentile(obj(row.us).rank, obj(row.us).of);
  const them = percentile(obj(row.them).rank, obj(row.them).of);
  const td = el("td", { class: "tt__ladder tt__min-medium" });
  if (us === null && them === null) {
    td.append(el("span", { class: "tt__ladder-none" }, DASH));
    return td;
  }
  const says = [us !== null ? `${text(opts.usAbbr)} ${us}` : null, them !== null ? `${text(opts.themAbbr)} ${them}` : null].filter(Boolean).join(", ");
  td.append(
    el(
      "span",
      { class: "ladder", role: "img", "aria-label": `National percentile: ${says}`, title: `National percentile: ${says}` },
      el("span", { class: "ladder__track" }),
      el("span", { class: "ladder__mid" }),
      them !== null ? el("span", { class: "ladder__mark ladder__mark--them", style: { left: `${them}%` } }) : null,
      us !== null ? el("span", { class: "ladder__mark ladder__mark--us", style: { left: `${us}%` } }) : null,
    ),
  );
  return td;
}

/** No rank for this row (a rate, interceptions thrown, a damaged one): a dash in the chip's place, never a blank square. */
function noRank() {
  return el("span", { class: "tt__norank", title: "No rank for this stat" }, DASH);
}

/** The national rank chip in its own column, or a dash where the row has none. */
function natlCell(row, side, opts) {
  const s = obj(row[side]);
  const href = sideHref(row, side, opts);
  const chip = rankChip(s.rank, s.of, { href, label: text(row.label), tie: s.tie === true });
  return el("td", { class: `tt__rank tt__rank--natl tt__min-medium tt__${side}` }, chip || noRank());
}

/** The conference rank chip in its own column, or a dash where the side has none (or a damaged one). */
function confCell(row, side) {
  const c = obj(obj(row[side]).conf);
  const where = typeof c.conference === "string" && c.conference.trim() ? c.conference.trim() : "the conference";
  const chip = isNum(c.rank) ? rankChip(c.rank, c.of, { href: isHash(c.href) ? c.href : null, label: `${text(row.label)}, rank in ${where}` }) : null;
  return el("td", { class: `tt__rank tt__rank--conf tt__min-large tt__${side}` }, chip || noRank());
}

/** A string's trimmed words, or null for a blank or anything else. */
const words = (value) => (typeof value === "string" && value.trim() ? value.trim() : null);

/** A side's player as the table draws it at large and medium: the name, or the caller's drawn node; null when none. */
function whoOf(side) {
  const who = obj(side).who;
  if (typeof Node !== "undefined" && who instanceof Node) return who;
  return words(who);
}

/** One side's player (wave 3, the Leaders' "vs opponent" boards): the name in its four forms (item 6), or the caller's
 *  drawing at large and medium and the name alone at small; a button that opens the card when the side has onWho; a dash
 *  for a row with no player on that side. */
function whoCell(row, side) {
  const s = obj(row[side]);
  const long = whoOf(s);
  const td = el("td", { class: `txt tt__who tt__who--${side}` });
  if (long === null) {
    td.append(DASH);
    return td;
  }
  const drawn = typeof long !== "string";
  const named = drawn ? words(s.whoName) : long;
  const small = drawn ? (named ? personName(named) : words(s.whoShort)) : null; // a drawing's small form: the name, no face
  const big = drawn ? long : personName(long);
  const shown = small ? [el("span", { class: "tt__t tt__t--long tt__t--mid" }, big), el("span", { class: "tt__t tt__t--short" }, small)] : [big];
  if (typeof s.onWho !== "function") {
    append(td, shown);
    return td;
  }
  const inner = drawn && typeof long.querySelector === "function" ? long.querySelector(".pn") : null;
  const name = named || (inner && inner.__names ? inner.__names.full : null) || (drawn ? words(long.textContent) : null) || words(s.whoShort);
  td.append(
    el(
      "button",
      {
        class: "tt__who-btn",
        type: "button",
        title: name ? `Open ${name}'s card` : null,
        onclick: (event) => {
          event.stopPropagation();
          try {
            s.onWho();
          } catch (error) {
            console.error("twoTeamTable: a player's card could not open.", error);
          }
        },
      },
      shown,
    ),
  );
  return td;
}

/** A side's player fact (his position): its words, or null. */
function whoSubOf(side) {
  return words(obj(side).whoSub);
}

/** One side's player fact (his position) beside the player, at large and medium; a dash when the side has none. */
function whoSubCell(row, side) {
  return el("td", { class: `txt tt__pos tt__pos--${side} tt__min-medium` }, whoSubOf(row[side]) || DASH);
}

/** One team's value cell: bold chalk for the leader, fog for the other; the row's flash key when it has one. The number
 *  itself is a link to its national list where the row has one (Design rules, owner 2026-10-21: "Every stat number that
 *  has a national list or a chart behind it links to it"), the same offer the chip makes. */
function valueCell(row, side, lead, opts) {
  const s = obj(row[side]);
  const cls = ["num", "tt__cell", `tt__${side}`];
  if (lead === side) cls.push("lead");
  else if (lead === "us" || lead === "them") cls.push("trail");
  const key = typeof row.key === "string" && row.key.trim() ? `${row.key.trim()}:${side}` : null;
  const short = words(s.textShort);
  const shown = short ? [el("span", { class: "tt__t tt__t--long tt__t--mid" }, valueText(row, side)), el("span", { class: "tt__t tt__t--short" }, short)] : valueText(row, side);
  const href = valueText(row, side) === DASH ? null : sideHref(row, side, opts);
  const val = el("span", { class: "tt__val" }, shown);
  if (href) cls.push("tt__cell--link");
  return el("td", { class: cls.join(" "), dataset: key ? { k: key } : null }, href ? listLink(href, val, { rank: s.rank, of: s.of, name: text(row.label), className: "tt__val-link" }) : val, opts.underline && !opts.tug ? underlineBar(percentile(s.rank, s.of), side) : null);
}

const LEAST_LEAN = 0.12; // a leader always shows: the shortest bar that still reads as a lean
/** The scale for a PPA row (per play, pass or rush): half a point per play between two teams is as lopsided as a game
 *  or a season gets (a blowout runs about +0.45 against -0.15), so that gap leans all the way. */
export const PPA_SCALE = 0.5;

/** The national ranks between the two sides: the row's own edge, else the two ranks' gap; null without both. */
function rankGap(row) {
  const r = obj(row);
  if (isNum(r.edge)) return Math.abs(r.edge);
  const a = obj(r.us).rank;
  const b = obj(r.them).rank;
  return isNum(a) && isNum(b) ? Math.abs(a - b) : null;
}

/**
 * How far ahead by the two values alone (owner 2026-10-10, wave 2: a bar with no national ranks leans by the values'
 * own share): their gap over their sum, 0 to 1, so 35 to 14 leans 0.43 of the half, 450 yards to 300 leans 0.2 and 14
 * to 0 leans all the way. A measure that runs either side of zero (PPA) names its scale, the gap that leans all the way,
 * and leans by the gap over it. null when either value is missing or both are zero (nothing to measure).
 */
export function valueShare(row) {
  const r = obj(row);
  const a = obj(r.us).value;
  const b = obj(r.them).value;
  if (!isNum(a) || !isNum(b)) return null;
  if (isNum(r.scale) && r.scale > 0) return Math.min(1, Math.abs(a - b) / r.scale);
  const sum = Math.abs(a) + Math.abs(b);
  return sum > 0 ? Math.min(1, Math.abs(a - b) / sum) : null;
}

/** How far the bar leans, as a share of its half (0.12 to 1): the gap in national rank over half the field, else the
 *  values' own share; a leader with nothing to measure (a lead given by the caller, no numbers) leans the least. */
export function tugShare(row) {
  const r = obj(row);
  const of = isNum(obj(r.us).of) ? obj(r.us).of : obj(r.them).of;
  const gap = rankGap(r);
  const share = gap !== null && isNum(of) && of > 1 ? gap / (of / 2) : valueShare(r);
  return share === null ? LEAST_LEAN : Math.max(LEAST_LEAN, Math.min(1, share));
}

function tugCell(row, lead, opts) {
  const td = el("td", { class: "tt__tug" });
  const track = el("span", { class: "tug", role: "img" }, el("span", { class: "tug__mid" }));
  if (lead === "us" || lead === "them") {
    const share = tugShare(row);
    track.append(el("span", { class: `tug__bar tug__bar--${lead}`, style: { width: `${Math.round(share * 50)}%` } }));
    const gap = rankGap(row);
    const who = lead === "us" ? text(opts.usAbbr) : text(opts.themAbbr);
    const other = lead === "us" ? "them" : "us";
    const margin = gap !== null ? `, ${gap} national ranks apart` : valueShare(row) !== null ? `, ${valueText(row, lead)} to ${valueText(row, other)}` : "";
    const says = `${who} has the edge${margin}`;
    track.setAttribute("aria-label", says);
    track.setAttribute("title", says);
  } else {
    const says = lead === "even" ? "Even" : "No edge to show";
    track.setAttribute("aria-label", says);
    track.setAttribute("title", says);
  }
  td.append(track);
  if (typeof row.tag === "string" && row.tag.trim()) td.append(el("small", { class: "tt__tag" }, row.tag.trim())); // the tape's "by 39 ranks"
  return td;
}

function betterCell(lead, opts) {
  const who = lead === "us" ? text(opts.usAbbr) : lead === "them" ? text(opts.themAbbr) : lead === "even" ? "Even" : DASH;
  return el("td", { class: `txt tt__better${lead === "us" || lead === "them" ? " lead" : ""}` }, who);
}

function minClass(size) {
  return size === "large" || size === "medium" ? ` tt__min-${size}` : "";
}

function extraCell(column, row) {
  let content = DASH;
  try {
    const out = column.cell(row);
    content = out === null || out === undefined || out === false || (typeof out === "number" && !isNum(out)) ? DASH : typeof out === "object" ? out : text(out);
  } catch (error) {
    console.error(`twoTeamTable: the ${text(column.head)} column could not draw a cell.`, error);
  }
  return el("td", { class: `${column.className || "num"}${minClass(column.size)}` }, content);
}

/** A row's label: its own shorter words when it names them (a team's abbreviation), else the stat name's forms; a link to
 *  the team's page when the row is a team (Common opponents). */
function rowLabel(row, label) {
  const mid = words(row.labelMid);
  const short = words(row.labelShort);
  const forms = mid || short ? nameForms(label, mid || label, short || mid || label) : formsOf(label);
  const team = words(row.team);
  return team ? teamLink(team, forms) : forms;
}

function bodyRow(row, opts) {
  const lead = twoTeamLeader(row);
  const label = text(row.label);
  const sub = typeof row.sub === "string" && row.sub.trim() ? el("small", {}, row.sub.trim()) : null;
  if (opts.centered) {
    // the label over its bar in the middle column, a team's columns mirrored on each side (the leader lines)
    const mid = tugCell(row, lead, opts);
    mid.className = "tt__tug tt__mid";
    mid.dataset.term = label;
    mid.prepend(el("span", { class: "tt__mid-words" }, formsOf(label), sub));
    return el(
      "tr",
      { class: typeof row.rowClass === "string" && row.rowClass ? row.rowClass : null },
      opts.cols.us.who ? whoCell(row, "us") : null,
      opts.cols.us.pos ? whoSubCell(row, "us") : null,
      opts.cols.us.natl ? natlCell(row, "us", opts) : null,
      opts.cols.us.conf ? confCell(row, "us") : null,
      valueCell(row, "us", lead, opts),
      mid,
      valueCell(row, "them", lead, opts),
      opts.cols.them.conf ? confCell(row, "them") : null,
      opts.cols.them.natl ? natlCell(row, "them", opts) : null,
      opts.cols.them.pos ? whoSubCell(row, "them") : null,
      opts.cols.them.who ? whoCell(row, "them") : null,
      opts.ladder ? ladderCell(row, opts) : null,
      opts.extra.map((column) => extraCell(column, row)),
      opts.better ? betterCell(lead, opts) : null,
    );
  }
  return el(
    "tr",
    { class: typeof row.rowClass === "string" && row.rowClass ? row.rowClass : null },
    el("td", { class: "txt tt__label", dataset: { term: label } }, rowLabel(row, label), sub),
    opts.cols.us.who ? whoCell(row, "us") : null,
    opts.cols.us.pos ? whoSubCell(row, "us") : null,
    opts.cols.us.natl ? natlCell(row, "us", opts) : null,
    opts.cols.us.conf ? confCell(row, "us") : null,
    valueCell(row, "us", lead, opts),
    opts.tug ? tugCell(row, lead, opts) : null,
    valueCell(row, "them", lead, opts),
    opts.cols.them.conf ? confCell(row, "them") : null,
    opts.cols.them.natl ? natlCell(row, "them", opts) : null,
    opts.cols.them.pos ? whoSubCell(row, "them") : null,
    opts.cols.them.who ? whoCell(row, "them") : null,
    opts.ladder ? ladderCell(row, opts) : null,
    opts.extra.map((column) => extraCell(column, row)),
    opts.better ? betterCell(lead, opts) : null,
  );
}

/** The way to go get a missing line (a scheme the notes do not have yet): a button or a link, never a blank. */
function getLink(missing) {
  const m = obj(missing);
  const label = typeof m.label === "string" && m.label.trim() ? m.label.trim() : "Not in the notes yet";
  if (typeof m.onClick === "function") return el("button", { class: "tt__get", type: "button", onclick: m.onClick }, label);
  if (isHash(m.href) || (typeof m.href === "string" && /^https?:/.test(m.href))) return el("a", { class: "tt__get", href: m.href }, label);
  return el("span", { class: "tt__get tt__get--plain" }, label);
}

/** A group's header row: the title alone, or the title with each team's line under its own columns. */
function groupRow(set, opts) {
  const title = text(set.title);
  // the note sits in a box that takes the row's width instead of setting it (contain: inline-size), so a long note never
  // widens a table that is only as wide as its numbers
  const titleNode = [formsOf(title), typeof set.note === "string" && set.note.trim() ? el("div", { class: "tt__note" }, el("small", {}, set.note.trim())) : null];
  const sided = typeof set.us === "string" || typeof set.them === "string" || set.missing;
  if (!sided) return el("tr", { class: "tt__group" }, el("th", { scope: "rowgroup", colspan: String(opts.width.large), dataset: { term: title } }, titleNode));
  const line = (side) => (typeof set[side] === "string" && set[side].trim() ? text(set[side].trim()) : set.missing ? getLink(set.missing) : DASH);
  if (opts.centered) {
    return el(
      "tr",
      { class: "tt__group tt__group--sided" },
      el("td", { class: "tt__scheme tt__us", colspan: String(opts.span.large.us) }, line("us")),
      el("th", { scope: "rowgroup", class: "tt__group-title tt__mid", dataset: { term: title } }, titleNode),
      el("td", { class: "tt__scheme tt__them", colspan: String(opts.span.large.them) }, line("them")),
      opts.span.large.tail ? el("td", { class: "tt__scheme-tail", colspan: String(opts.span.large.tail) }) : null,
    );
  }
  return el(
    "tr",
    { class: "tt__group tt__group--sided" },
    el("th", { scope: "rowgroup", class: "tt__group-title", dataset: { term: title } }, titleNode),
    el("td", { class: "tt__scheme tt__us", colspan: String(opts.span.large.us) }, line("us")),
    opts.tug ? el("td", { class: "tt__tug tt__scheme-gap" }) : null,
    el("td", { class: "tt__scheme tt__them", colspan: String(opts.span.large.them) }, line("them")),
    opts.span.large.tail ? el("td", { class: "tt__scheme-tail", colspan: String(opts.span.large.tail) }) : null,
  );
}

/** The column counts at each size: the whole width, each team's own columns, the columns after the opponent's. */
function layout(opts) {
  const at = (size) => {
    const shows = (min) => RANK[size] <= RANK[min || "small"];
    const side = (s) => 1 + (opts.cols[s].who ? 1 : 0) + (opts.cols[s].pos && shows("medium") ? 1 : 0) + (opts.cols[s].natl && shows("medium") ? 1 : 0) + (opts.cols[s].conf && shows("large") ? 1 : 0); // the player at every size, his position from medium
    const tail = (opts.ladder && shows("medium") ? 1 : 0) + opts.extra.filter((c) => shows(c.size)).length + (opts.better ? 1 : 0);
    const middle = opts.centered ? 1 : 1 + (opts.tug ? 1 : 0); // centered: the label and the bar share the middle column
    return { us: side("us"), them: side("them"), tail, width: middle + side("us") + side("them") + tail };
  };
  return { large: at("large"), medium: at("medium"), small: at("small") };
}

/**
 * Draw a wrap at one size: the size attribute the stylesheet keys on, the group rows' spans, the dropped
 * table's note. "medium:abbr" is medium with the abbreviations for the team heads.
 */
export function applySize(wrap, size) {
  const parts = size === DROPPED ? { size: DROPPED, form: null } : splitStep(size);
  const step = parts.size;
  const base = step === DROPPED ? DROPPED : step.split(":")[0];
  const plan = wrap.__tt;
  wrap.dataset.size = base;
  if (step === "medium:abbr") wrap.dataset.names = "short";
  else delete wrap.dataset.names;
  // the players' names (item 6): the step's form, else full names at large and "K. Crawford" below it
  if (plan && plan.people) applyNames(wrap, parts.form || (base === "large" ? "full" : "initial"));
  if (!plan) return;
  const spans = plan.span[base === DROPPED ? "small" : base] || plan.span.small;
  for (const tr of wrap.querySelectorAll("tr.tt__group")) {
    if (!tr.classList.contains("tt__group--sided")) {
      tr.querySelector("th")?.setAttribute("colspan", String(spans.width));
      continue;
    }
    const title = tr.querySelector("th");
    const us = tr.querySelector("td.tt__scheme.tt__us");
    const them = tr.querySelector("td.tt__scheme.tt__them");
    const gap = tr.querySelector("td.tt__scheme-gap");
    const tail = tr.querySelector("td.tt__scheme-tail");
    const small = base === "small" || base === DROPPED;
    title?.setAttribute("colspan", String(small ? spans.width : 1));
    for (const cell of [us, them, gap, tail]) if (cell) cell.hidden = small;
    us?.setAttribute("colspan", String(spans.us));
    them?.setAttribute("colspan", String(spans.them));
    if (tail) {
      tail.setAttribute("colspan", String(Math.max(1, spans.tail)));
      if (!spans.tail) tail.hidden = true;
    }
  }
  for (const td of wrap.querySelectorAll("td.tt__none")) td.setAttribute("colspan", String(spans.width));
  const table = wrap.querySelector("table");
  let note = wrap.querySelector(".size-note");
  if (base === DROPPED) {
    if (table) table.hidden = true;
    if (!note) wrap.append(sizeNote());
    wrap.classList.add("stat-table-wrap--dropped");
  } else {
    if (table) table.hidden = false;
    if (note) note.remove();
    wrap.classList.remove("stat-table-wrap--dropped");
  }
}

export function twoTeamTable({ rows, usAbbr = usLabel(), themAbbr = DASH, groups, better = true, usTeam, themTeam, usName, themName, usHead, themHead, usConf, themConf, year, ladder = false, underline = false, tug = false, centered = false, labelHead = "Statistic", whoHead = "Player", whoSubHead = "Pos", caption, extra, className, onSize } = {}) {
  const sets = Array.isArray(groups)
    ? records(groups).map((g) => ({ title: g.title, note: g.note, rows: records(g.rows), us: g.us, them: g.them, missing: g.missing }))
    : [{ title: null, note: null, rows: records(rows) }];
  const all = sets.flatMap((s) => s.rows);
  const withWho = all.some((r) => SIDES.some((side) => whoOf(r[side]) !== null)); // a player on either side: both sides get the column, mirrored
  const withSub = withWho && all.some((r) => SIDES.some((side) => whoSubOf(r[side]) !== null)); // the player's position, mirrored too
  const cols = Object.fromEntries(SIDES.map((side) => [side, { natl: all.some((r) => isNum(obj(r[side]).rank)), conf: all.some((r) => isNum(obj(obj(r[side]).conf).rank)), who: withWho, pos: withSub }]));
  const extras = (Array.isArray(extra) ? extra : []).filter((c) => c && typeof c.cell === "function");
  const withTug = tug === true || centered === true; // centered (owner 2026-10-10, the leader lines: "the edges sucked to the middle"): the label over its bar in the middle, both teams mirrored around it
  const opts = { usAbbr: text(usAbbr), themAbbr: text(themAbbr), usTeam, themTeam, year, better: better !== false && !withTug, ladder: Boolean(ladder), underline: Boolean(underline), tug: withTug, centered: centered === true, extra: extras, cols };
  opts.span = layout(opts);
  opts.width = { large: opts.span.large.width };
  // each side's conference for its rank head: the option, else the name the rows carry, else ours from the identity
  const rowConf = (side) => {
    const found = all.map((r) => obj(obj(r[side]).conf).conference).find((c) => typeof c === "string" && c.trim());
    return found ? found.trim() : null;
  };
  const conf = { us: text(usConf || rowConf("us") || confLabel()), them: text(themConf || rowConf("them") || usConf || confLabel()) };
  const head = text(labelHead);
  // each team's head in its three forms: usHead/themHead { long, mid, short } when a caller names units (the tape's
  // "Swampwater Tech offense"), else the school and mascot, the school, the abbreviation
  const words = (side) => {
    const given = side === "us" ? usHead : themHead;
    if (given && typeof given === "object") return nameForms(given.long, given.mid, given.short);
    return side === "us" ? nameForms(usName, usTeam, opts.usAbbr) : nameForms(themName, themTeam, opts.themAbbr);
  };

  // the rank heads: "FBS rank" and "<conference> rank" in the large head's second row, "FBS" alone in the one-row head
  const rankHead = (side, kind, { oneRow = false } = {}) => {
    const long = kind === "natl" ? "FBS rank" : `${conf[side]} rank`;
    return el("th", { class: `tt__rank tt__rank--${kind} tt__${side} tt__min-${kind === "natl" ? "medium" : "large"}`, scope: "col", dataset: { term: long } }, oneRow && kind === "natl" ? "FBS" : long);
  };
  const tailHeads = (rowspan) => [
    opts.ladder ? el("th", { class: "tt__ladder tt__min-medium", scope: "col", rowspan, title: "National percentile, 0 to 100: the dot is " + opts.usAbbr + ", the ring " + opts.themAbbr }, el("span", { class: "ladder-head" }, el("span", {}, "0"), el("span", {}, "Percentile"), el("span", {}, "100"))) : null,
    extras.map((column) => el("th", { class: `${column.headClass || ""}${minClass(column.size)}`.trim() || null, scope: "col", rowspan }, text(column.head))),
    opts.better ? el("th", { class: "tt__better", scope: "col", rowspan }, "Better") : null,
  ];
  // the player column's head, outermost on each side (wave 3)
  const whoWords = text(whoHead);
  const whoHeadCell = (side) => el("th", { class: `txt tt__who tt__who--${side}`, scope: "col", dataset: { term: whoWords } }, formsOf(whoWords));
  const subWords = text(whoSubHead);
  const subHeadCell = (side) => el("th", { class: `txt tt__pos tt__pos--${side} tt__min-medium`, scope: "col", dataset: { term: subWords } }, formsOf(subWords));
  // large: the team over its own columns, the rank heads under it (centered: the label head in the middle, over the bars)
  const midHead = (rowspan) => el("th", { class: "tt__tug tt__mid", scope: "col", rowspan, dataset: { term: head } }, formsOf(head));
  const headA = opts.centered
    ? el(
        "tr",
        { class: "tt__head tt__head--a" },
        el("th", { class: "tt__team us tt__us", scope: "colgroup", colspan: String(opts.span.large.us) }, words("us")),
        midHead("2"),
        el("th", { class: "tt__team them tt__them", scope: "colgroup", colspan: String(opts.span.large.them) }, words("them")),
        tailHeads("2"),
      )
    : el(
        "tr",
        { class: "tt__head tt__head--a" },
        el("th", { class: "txt tt__label", scope: "col", rowspan: "2", dataset: { term: head } }, formsOf(head)),
        el("th", { class: "tt__team us tt__us", scope: "colgroup", colspan: String(opts.span.large.us) }, words("us")),
        opts.tug ? el("th", { class: "tt__tug", scope: "col", rowspan: "2" }, "Edge") : null,
        el("th", { class: "tt__team them tt__them", scope: "colgroup", colspan: String(opts.span.large.them) }, words("them")),
        tailHeads("2"),
      );
  const headB = el(
    "tr",
    { class: "tt__head tt__head--b" },
    cols.us.who ? whoHeadCell("us") : null,
    cols.us.pos ? subHeadCell("us") : null,
    cols.us.natl ? rankHead("us", "natl") : null,
    cols.us.conf ? rankHead("us", "conf") : null,
    el("th", { class: "us tt__us tt__blank", scope: "col" }),
    el("th", { class: "them tt__them tt__blank", scope: "col" }),
    cols.them.conf ? rankHead("them", "conf") : null,
    cols.them.natl ? rankHead("them", "natl") : null,
    cols.them.pos ? subHeadCell("them") : null,
    cols.them.who ? whoHeadCell("them") : null,
  );
  // medium and small: one row
  const headOne = opts.centered
    ? el(
        "tr",
        { class: "tt__head tt__head--one" },
        cols.us.who ? whoHeadCell("us") : null,
        cols.us.pos ? subHeadCell("us") : null,
        cols.us.natl ? rankHead("us", "natl", { oneRow: true }) : null,
        el("th", { class: "us tt__us", scope: "col" }, words("us")),
        midHead(null),
        el("th", { class: "them tt__them", scope: "col" }, words("them")),
        cols.them.natl ? rankHead("them", "natl", { oneRow: true }) : null,
        cols.them.pos ? subHeadCell("them") : null,
        cols.them.who ? whoHeadCell("them") : null,
        tailHeads(null),
      )
    : el(
        "tr",
        { class: "tt__head tt__head--one" },
        el("th", { class: "txt tt__label", scope: "col", dataset: { term: head } }, formsOf(head)),
        cols.us.who ? whoHeadCell("us") : null,
        cols.us.pos ? subHeadCell("us") : null,
        cols.us.natl ? rankHead("us", "natl", { oneRow: true }) : null,
        el("th", { class: "us tt__us", scope: "col" }, words("us")),
        opts.tug ? el("th", { class: "tt__tug", scope: "col" }, "Edge") : null,
        el("th", { class: "them tt__them", scope: "col" }, words("them")),
        cols.them.natl ? rankHead("them", "natl", { oneRow: true }) : null,
        cols.them.pos ? subHeadCell("them") : null,
        cols.them.who ? whoHeadCell("them") : null,
        tailHeads(null),
      );
  const bodies = sets.map((set) =>
    el(
      "tbody",
      {},
      set.title ? groupRow(set, opts) : null,
      set.rows.map((row) => bodyRow(row, opts)),
      set.rows.length === 0 ? el("tr", {}, el("td", { class: "txt tt__none", colspan: String(opts.span.large.width) }, "No rows.")) : null,
    ),
  );
  const table = el("table", { class: `stat-table stat-table--compact tt${opts.ladder ? " tt--ladder" : ""}${opts.underline && !opts.tug ? " tt--underline" : ""}${opts.tug ? " tt--tug" : ""}${opts.centered ? " tt--centered" : ""}` }, caption ? el("caption", { class: "sr-only" }, text(caption)) : null, el("thead", {}, headA, headB, headOne), bodies);
  const wrap = el("div", { class: `stat-table-wrap tt-wrap${className ? ` ${className}` : ""}` }, table);
  // each side's names settled on their own (item 6, owner answer 7: compared within each side)
  if (withWho) for (const side of SIDES) settleNames(table.querySelectorAll(`td.tt__who--${side}`));
  wrap.__tt = { span: opts.span, people: withWho };
  applySize(wrap, withWho ? "large/full" : "large");
  let last = null;
  watchSize(wrap, () => {
    const size = fitSize(wrap, table, (step) => applySize(wrap, step), withWho ? personSteps(STEPS, nameSteps(table)) : STEPS);
    if (size === null) return;
    if (size === DROPPED) wrap.classList.remove("stat-table-wrap--fits");
    else wrap.classList.add("stat-table-wrap--fits"); // never a scroll box: the header sticks
    const base = size === DROPPED ? DROPPED : splitStep(size).size.split(":")[0];
    if (base !== last && typeof onSize === "function") onSize(base);
    last = base;
  });
  return wrap;
}
