// Context tables for the days between games (Phase 15): this season beside last, the road ahead,
// common opponents, and both teams' last season on the program. Tables only, every column guarded.

import { DASH, el, fmtDate, fmtStat, isNum, records, teamLink, text } from "./dom.js";
import { nationalHref, pollHref } from "./national-link.js";
import { note } from "./states.js";
import { pollBadge, statTable } from "./stat-table.js";
import { weekCell } from "./weeks.js";
import { logoLink } from "./team-page.js";

const SIDE_TITLES = { offense: "Offense", defense: "Defense", both: "Overall" };
const h4 = (label) => el("h4", { class: "d2-head" }, label);

/** This season and last, one table per side: each value with its national chip in one cell (the chip opens that
 *  season's national list: last season's carries ?year=), and which is better. */
export function lastSeasonBlock(rows, year, thisYear, { team } = {}) {
  const list = records(rows);
  if (!list.some((r) => isNum(r.last?.value))) return note(`${text(year)} numbers could not be loaded yet.`);
  const lastYear = (r) => (isNum(r.metricYear) ? r.metricYear : isNum(r.last?.year) ? r.last.year : isNum(year) ? year : null);
  const valueCol = (key, label, rankKey, ofKey, pick) => ({
    key,
    label,
    divider: true,
    render: (row) => el("span", { "data-k": `${key}:${text(row.key)}` }, fmtStat(row[key], row.format)),
    rank: { key: rankKey, of: ofKey, link: (row) => nationalHref(row.metric, { team, year: pick(row) }), placeholder: true },
  });
  const columns = [
    { key: "label", label: "Statistic", kind: "text" },
    valueCol("now", String(thisYear ?? "This season"), "nowRank", "nowOf", () => null),
    valueCol("last", String(year ?? "Last season"), "lastRank", "lastOf", (row) => row.metricYear),
    { key: "change", label: "Change", kind: "text", divider: true },
  ];
  const shaped = list.map((r) => ({
    key: r.key,
    metric: r.metric,
    metricYear: lastYear(r),
    label: r.label,
    side: r.side,
    format: r.format,
    now: r.now?.value,
    nowRank: r.now?.rank,
    nowOf: r.now?.of,
    last: r.last?.value,
    lastRank: r.last?.rank,
    lastOf: r.last?.of,
    change: r.better === true ? "Better" : r.better === false ? "Worse" : DASH, // Phase 16 wave 3: words, no font arrows
  }));
  const sides = [...new Set(shaped.map((r) => r.side))];
  return el(
    "div",
    { class: "d2 prof" },
    sides.map((side) => el("div", {}, h4(SIDE_TITLES[side] || text(side)), statTable({ compact: true, sortable: false, columns, rows: shaped.filter((r) => r.side === side), caption: `${SIDE_TITLES[side] || side}: this season and last` }))),
    note(`Each season with its national rank among FBS teams. "Better" follows the stat's direction (fewer points allowed is better). ${text(year)} is the full season, bowls included.`),
  );
}

/** A finished game as 'W 31-24' in the result color and the opponent as a link (G3-07). */
function resultChunk(g) {
  const res = typeof g.result === "string" && ["W", "L", "T"].includes(g.result) ? g.result : null;
  const opponent = typeof g.opponent === "string" && g.opponent.trim() ? g.opponent.trim() : null;
  return el(
    "span",
    { class: "form-result" },
    el("b", { class: res === "W" ? "res--w" : res === "L" ? "res--l" : null }, `${res || DASH} ${text(g.score)}`),
    opponent ? [" ", teamLink(opponent, opponent)] : null,
  );
}

/** Every remaining opponent: when, where, record, AP (a poll badge), SP+ with its chip, and the last three results. */
export function roadAheadBlock(rows, { logos } = {}) {
  const list = records(rows);
  if (!list.length) return note("No games left on the schedule.");
  const shaped = list.map((r) => ({
    week: weekCell(r),
    date: fmtDate(r.date, "short"),
    opponent: r.opponent,
    site: r.site,
    record: r.record || DASH,
    apRank: r.apRank,
    sp: r.sp,
    spRank: r.spRank,
    spOf: r.spOf,
    spMetric: r.spMetric,
    lastThree: records(r.lastThree),
  }));
  const opponentOf = (row) => (typeof row.opponent === "string" ? row.opponent : null);
  return el(
    "div",
    { class: "d2" },
    statTable({
      compact: true,
      columns: [
        { key: "week", label: "Wk", dim: true },
        { key: "date", label: "Date", kind: "text" },
        { key: "opponent", label: "Opponent", kind: "text", render: (row) => logoLink(row.opponent, logos instanceof Map ? logos.get(row.opponent) : null) },
        { key: "site", label: "Site", kind: "text" },
        { key: "record", label: "Record" },
        { key: "apRank", label: "AP", render: (row) => (isNum(row.apRank) ? pollBadge(row.apRank, "AP", { href: pollHref("AP", { team: opponentOf(row) }), label: opponentOf(row), showPoll: false }) : el("span", { class: "nr" }, "NR")) },
        { key: "sp", label: "SP+", format: "1f", divider: true, rank: { key: "spRank", of: "spOf", link: (row) => nationalHref(row.spMetric, { team: opponentOf(row) }), placeholder: true } },
        { key: "form", label: "Last three", kind: "text", divider: true, render: (row) => (row.lastThree.length ? el("span", { class: "form-results" }, row.lastThree.map(resultChunk)) : DASH) },
      ],
      rows: shaped,
      sortable: false,
      caption: "The road ahead",
    }),
    note("Record and form count this season's finished games; SP+ is this week's rating."),
  );
}

function results(list) {
  return records(list).map((g) => `${text(g.result)} ${text(g.score)}`).join(", ") || DASH;
}

/** Teams both sides have played, with each result and the margin. */
export function commonOpponentsBlock(rows, usName, themName) {
  const list = records(rows);
  if (!list.length) return note(`${text(usName)} and ${text(themName)} have no opponent in common yet this season.`);
  const shaped = list.map((r) => ({ opponent: r.opponent, us: results(r.us), usMargin: r.usMargin, them: results(r.them), themMargin: r.themMargin }));
  return el(
    "div",
    { class: "d2" },
    statTable({
      compact: true,
      columns: [
        { key: "opponent", label: "Opponent", kind: "text", team: true },
        { key: "us", label: text(usName), kind: "text", divider: true },
        { key: "usMargin", label: "Margin", format: "+0f" },
        { key: "them", label: text(themName), kind: "text", divider: true },
        { key: "themMargin", label: "Margin", format: "+0f" },
      ],
      rows: shaped,
      sortable: true,
      caption: "Common opponents",
    }),
    note("Scores read from each team's side. Margins add up every meeting."),
  );
}

/** Both teams' last season, one row per stat, each value with its national rank. */
// Phase 16 (stream PROGRAM, audit P-01/P-02): the shared two-team table, sides as group rows, chips that
// open last season's national list. (Imported here, not at the top, so the Season stream's edits to the
// import block never meet this.)
import { twoTeamTable as programTwoTeam } from "./two-team.js";

export function lastSeasonTwoTeam(data, usAbbr, themAbbr, { usTeam, themTeam, ladder = false, tug = false } = {}) {
  const d = data && typeof data === "object" ? data : {};
  const list = records(d.rows);
  if (!list.some((r) => isNum(r.us?.value) || isNum(r.them?.value))) return note(`${text(d.year)} numbers could not be loaded yet.`);
  const sides = [...new Set(list.map((r) => r.side))];
  const groups = sides.map((side) => ({
    title: SIDE_TITLES[side] || text(side),
    rows: list.filter((r) => r.side === side).map((r) => ({ label: r.label, format: r.format, higherIsBetter: r.higherIsBetter, metric: r.metric, metricYear: r.metricYear ?? d.year, us: { value: r.us?.value, rank: r.us?.rank, of: r.us?.of }, them: { value: r.them?.value, rank: r.them?.rank, of: r.them?.of } })),
  }));
  return el("div", { class: "d2" }, programTwoTeam({ groups, usAbbr: text(usAbbr), themAbbr: text(themAbbr), usTeam, themTeam, ladder, tug, tug, caption: `${text(d.year)} season, both teams` }));
}
