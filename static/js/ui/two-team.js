// The two-team table (Phase 16, stream PROGRAM; audit P-01, P-02, P-06, P-09, DS-02, GX-05, GX-11).
// One way to put us beside an opponent everywhere on the Game program, the Live sheet and the
// styleguide: each team's value and its national rank chip sit in ONE cell, a 2px divider stands
// before the opponent's cell, the better value is bold chalk and the other fog (ties stay neutral),
// and every chip with a list behind it is a link to that national list (the whole cell is the target).
//
// Frozen API (the Live stream consumes these; do not change the signatures):
//   twoTeamTable({ rows, usAbbr, themAbbr, groups, better = true, usTeam, themTeam, year, ladder = false,
//                  underline = false, labelHead = "Statistic", caption, extra, className })  -> .stat-table-wrap
//       row: { label, sub, format, higherIsBetter, leads, metric, metricYear, rowClass,
//              us: { value, text, rank, of, tie, metric, href, conf }, them: { ...the same } }
//         conf      (final pass, the leader lines) { rank, of, href, conference }: a second chip tagged "Conf" beside
//                   the national one, outside it with the tug bar; its own tap target.
//         text      shown instead of fmtStat(value, format); value still decides who leads.
//         leads     "us" | "them" | "even" overrides the comparison (edges, where the two values are different stats).
//         metric    the national list key (row-wide, or per side); usTeam/themTeam highlight the team, and
//                   metricYear (or year) opens that season's list. href on a side wins over metric.
//       groups: [{ title, note, rows }] draws group header rows inside the one table (rows is then ignored).
//       better: a symmetric "Better" column (the leader's abbreviation in bold chalk, "Even" in fog).
//       ladder: a 0-100 national percentile track per row (GX-05): our dot and an opponent ring.
//       underline: a 3px percentile underline inside each value cell (GX-11).
//       extra: [{ head, cell(row) -> node|text, className }] columns after the opponent's (the edges table).
//       tug (Phase 17 #14, owner pick 2026-10-07): a tug-of-war bar between the two teams instead of the Better
//                 column. The cells bracket it, mirrored: our chip and value pressed against its left end, the
//                 opponent's value and chip against its right; the bar leans to the leader in that team's color,
//                 longer for a bigger gap in national rank (row.edge when the row has one). No underline with it.
//   twoTeamLeader(row)            "us" | "them" | "even", or null when nothing can be compared.
//   percentile(rank, of)          0 (last) to 100 (first) from a national rank, or null. Ranks already run
//                                 best-first whichever way the stat runs, so a lower-is-better stat needs no flip.
//   listLink(href, label, { rank, of, name, className })  a text link to a list (the cover's and the card's
//                                 "SP+ #13"), offered to "kickoff:rank-link" first like a chip.

import { usLabel } from "../identity.js";
import { DASH, el, fmtStat, isNum, obj, records, text } from "./dom.js";
import { nationalHref } from "./national-link.js";
import { rankChip, rankChipPlaceholder } from "./stat-table.js";

const SIDES = ["us", "them"];

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
  const body = text(label);
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

function underlineBar(pct, side) {
  if (pct === null) return null;
  return el("span", { class: `tt__pct tt__pct--${side}`, "aria-hidden": "true" }, el("span", { class: "tt__pct-fill", style: { width: `${pct}%` } }));
}

function ladderCell(row, opts) {
  const us = percentile(obj(row.us).rank, obj(row.us).of);
  const them = percentile(obj(row.them).rank, obj(row.them).of);
  const td = el("td", { class: "tt__ladder" });
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

/** One team's cell: value, then its chip (or an invisible one so values line up), the whole cell a link. */
function sideCell(row, side, lead, opts) {
  const s = obj(row[side]);
  const href = sideHref(row, side, opts);
  const chip = rankChip(s.rank, s.of, { href, label: text(row.label), tie: s.tie === true });
  const cls = ["num", "tt__cell", side === "them" ? "tt__them" : "tt__us"];
  if (lead === side) cls.push("lead");
  else if (lead === "us" || lead === "them") cls.push("trail");
  if (chip && href) cls.push("tt__cell--link");
  const value = el("span", { class: "tt__val" }, valueText(row, side));
  const mark = chip || (opts.placeholders[side] ? rankChipPlaceholder() : null);
  const conf = confMark(row, side);
  // with the tug bar the cells bracket it: our chips outside, our value against the bar; the opponent mirrored
  const inside = opts.tug && side === "us" ? [conf, mark, value] : [value, mark, conf];
  return el(
    "td",
    { class: cls.join(" ") },
    ...inside,
    opts.underline && !opts.tug ? underlineBar(percentile(s.rank, s.of), side) : null,
  );
}

/** The conference rank chip with its "Conf" tag, or null when the side has none (or a damaged one). */
function confMark(row, side) {
  const c = obj(obj(row[side]).conf);
  if (!isNum(c.rank)) return null;
  const where = typeof c.conference === "string" && c.conference.trim() ? c.conference.trim() : "the conference";
  const chip = rankChip(c.rank, c.of, { href: isHash(c.href) ? c.href : null, label: `${text(row.label)}, rank in ${where}` });
  return chip ? el("span", { class: "tt__conf", title: `Rank in ${where}` }, chip, el("small", {}, "Conf")) : null;
}

/** How far the bar leans, as a share of its half (0.12 to 1): the gap in national rank over the field size. */
export function tugShare(row) {
  const r = obj(row);
  const of = isNum(obj(r.us).of) ? obj(r.us).of : obj(r.them).of;
  const gap = isNum(r.edge) ? Math.abs(r.edge) : isNum(obj(r.us).rank) && isNum(obj(r.them).rank) ? Math.abs(obj(r.us).rank - obj(r.them).rank) : null;
  if (gap === null || !isNum(of) || of <= 1) return 0.35; // a leader with no ranks to measure: a middling lean
  return Math.max(0.12, Math.min(1, gap / (of / 2)));
}

function tugCell(row, lead, opts) {
  const td = el("td", { class: "tt__tug" });
  const track = el("span", { class: "tug", role: "img" }, el("span", { class: "tug__mid" }));
  if (lead === "us" || lead === "them") {
    const share = tugShare(row);
    track.append(el("span", { class: `tug__bar tug__bar--${lead}`, style: { width: `${Math.round(share * 50)}%` } }));
    const gap = isNum(row.edge) ? Math.abs(row.edge) : isNum(obj(row.us).rank) && isNum(obj(row.them).rank) ? Math.abs(obj(row.us).rank - obj(row.them).rank) : null;
    const who = lead === "us" ? text(opts.usAbbr) : text(opts.themAbbr);
    const says = `${who} has the edge${gap !== null ? `, ${gap} national ranks apart` : ""}`;
    track.setAttribute("aria-label", says);
    track.setAttribute("title", says);
  } else {
    const says = lead === "even" ? "Even" : "No edge to show";
    track.setAttribute("aria-label", says);
    track.setAttribute("title", says);
  }
  td.append(track);
  return td;
}

function betterCell(lead, opts) {
  const who = lead === "us" ? text(opts.usAbbr) : lead === "them" ? text(opts.themAbbr) : lead === "even" ? "Even" : DASH;
  return el("td", { class: `txt tt__better${lead === "us" || lead === "them" ? " lead" : ""}` }, who);
}

function extraCell(column, row) {
  let content = DASH;
  try {
    const out = column.cell(row);
    content = out === null || out === undefined || out === false || (typeof out === "number" && !isNum(out)) ? DASH : typeof out === "object" ? out : text(out);
  } catch (error) {
    console.error(`twoTeamTable: the ${text(column.head)} column could not draw a cell.`, error);
  }
  return el("td", { class: column.className || "num" }, content);
}

function bodyRow(row, opts) {
  const lead = twoTeamLeader(row);
  return el(
    "tr",
    { class: typeof row.rowClass === "string" && row.rowClass ? row.rowClass : null },
    el("td", { class: "txt tt__label" }, text(row.label), typeof row.sub === "string" && row.sub.trim() ? el("small", {}, row.sub.trim()) : null),
    sideCell(row, "us", lead, opts),
    opts.tug ? tugCell(row, lead, opts) : null,
    sideCell(row, "them", lead, opts),
    opts.ladder ? ladderCell(row, opts) : null,
    opts.extra.map((column) => extraCell(column, row)),
    opts.better ? betterCell(lead, opts) : null,
  );
}

/** Measure like the stat table does: a table that fits lets go of its scroll box so its header sticks. */
function watchFit(wrap, table) {
  const measure = () => {
    try {
      const wide = table.scrollWidth;
      const room = wrap.clientWidth;
      if (!isNum(wide) || !isNum(room) || room <= 0) return;
      if (wide <= room + 1) wrap.classList.add("stat-table-wrap--fits");
      else wrap.classList.remove("stat-table-wrap--fits");
    } catch (error) {
      console.error("twoTeamTable: could not measure a table.", error);
    }
  };
  wrap.measure = measure; // the stat table's one shared resize listener calls this too
  if (!isNum(wrap.clientWidth) || typeof requestAnimationFrame !== "function") return; // no layout engine (tests)
  let tries = 0;
  const first = () => {
    if (wrap.isConnected && wrap.clientWidth > 0) measure();
    else if (tries++ < 10) requestAnimationFrame(first);
  };
  requestAnimationFrame(first);
}

export function twoTeamTable({ rows, usAbbr = usLabel(), themAbbr = DASH, groups, better = true, usTeam, themTeam, year, ladder = false, underline = false, tug = false, labelHead = "Statistic", caption, extra, className } = {}) {
  const sets = Array.isArray(groups)
    ? records(groups).map((g) => ({ title: g.title, note: g.note, rows: records(g.rows) }))
    : [{ title: null, note: null, rows: records(rows) }];
  const all = sets.flatMap((s) => s.rows);
  const placeholders = Object.fromEntries(SIDES.map((side) => [side, all.some((r) => isNum(obj(r[side]).rank))]));
  const extras = (Array.isArray(extra) ? extra : []).filter((c) => c && typeof c.cell === "function");
  const withTug = tug === true;
  const opts = { usAbbr: text(usAbbr), themAbbr: text(themAbbr), usTeam, themTeam, year, better: better !== false && !withTug, ladder: Boolean(ladder), underline: Boolean(underline), tug: withTug, extra: extras, placeholders };
  const width = 3 + (opts.tug ? 1 : 0) + (opts.ladder ? 1 : 0) + extras.length + (opts.better ? 1 : 0);

  const head = el(
    "thead",
    {},
    el(
      "tr",
      {},
      el("th", { class: "txt", scope: "col" }, text(labelHead)),
      el("th", { class: "us", scope: "col" }, opts.usAbbr),
      opts.tug ? el("th", { class: "tt__tug", scope: "col" }, "Edge") : null,
      el("th", { class: "them tt__them", scope: "col" }, opts.themAbbr),
      opts.ladder ? el("th", { class: "tt__ladder", scope: "col", title: "National percentile, 0 to 100: the dot is " + opts.usAbbr + ", the ring " + opts.themAbbr }, el("span", { class: "ladder-head" }, el("span", {}, "0"), el("span", {}, "Percentile"), el("span", {}, "100"))) : null,
      extras.map((column) => el("th", { class: column.headClass || null, scope: "col" }, text(column.head))),
      opts.better ? el("th", { class: "tt__better", scope: "col" }, "Better") : null,
    ),
  );
  const bodies = sets.map((set) =>
    el(
      "tbody",
      {},
      set.title ? el("tr", { class: "tt__group" }, el("th", { scope: "rowgroup", colspan: String(width) }, text(set.title), typeof set.note === "string" && set.note.trim() ? el("small", {}, ` · ${set.note.trim()}`) : null)) : null,
      set.rows.map((row) => bodyRow(row, opts)),
      set.rows.length === 0 ? el("tr", {}, el("td", { class: "txt", colspan: String(width) }, "No rows.")) : null,
    ),
  );
  const table = el("table", { class: `stat-table stat-table--compact tt${opts.ladder ? " tt--ladder" : ""}${opts.underline && !opts.tug ? " tt--underline" : ""}${opts.tug ? " tt--tug" : ""}` }, caption ? el("caption", { class: "sr-only" }, text(caption)) : null, head, bodies);
  const wrap = el("div", { class: `stat-table-wrap tt-wrap${className ? ` ${className}` : ""}` }, table);
  watchFit(wrap, table);
  return wrap;
}
