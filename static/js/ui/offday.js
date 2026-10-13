// Context tables for the days between games (Phase 15): this season beside last, the road ahead,
// common opponents, and both teams' last season on the program. Tables only, every column guarded.

import { DASH, el, fmtDate, fmtStat, isNum, records, text } from "./dom.js";
import { nationalHref, pollHref } from "./national-link.js";
import { note } from "./states.js";
import { pollBadge, statTable } from "./stat-table.js";
import { weekCell } from "./weeks.js";
import { formSquares, logoLink, teamAbbrLink } from "./team-page.js";

const SIDE_TITLES = { offense: "Offense", defense: "Defense", both: "Overall" };
const h4 = (label) => el("h4", { class: "d2-head" }, label);

/**
 * This season and last, one table per side, each sized by its own box (tables wave 3, rule 3: every data point in its own
 * column): Statistic | this season | FBS rank | <conf> rank | last season | FBS rank | <conf> rank | Change. The FBS ranks
 * show from medium, the conference's at large (when the server sent them); each chip opens that season's list (last
 * season's carries ?year=). The defense's small head says "Def (allowed)" once for its rows (rule 5).
 * lastSeasonBlock(rows, year, thisYear, { team, conferenceLabel })
 */
export function lastSeasonBlock(rows, year, thisYear, { team, conferenceLabel } = {}) {
  const list = records(rows);
  if (!list.some((r) => isNum(r.last?.value))) return note(`${text(year)} numbers could not be loaded yet.`);
  const lastYear = (r) => (isNum(r.metricYear) ? r.metricYear : isNum(r.last?.year) ? r.last.year : isNum(year) ? year : null);
  const conf = typeof conferenceLabel === "string" && conferenceLabel.trim() ? conferenceLabel.trim() : "Conf";
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
    nowConf: r.now?.confRank,
    nowConfOf: r.now?.confOf,
    last: r.last?.value,
    lastRank: r.last?.rank,
    lastOf: r.last?.of,
    lastConf: r.last?.confRank,
    lastConfOf: r.last?.confOf,
    change: r.better === true ? "Better" : r.better === false ? "Worse" : DASH, // Phase 16 wave 3: words, no font arrows
  }));
  const confs = shaped.some((r) => isNum(r.nowConf) || isNum(r.lastConf));
  const season = (key, label, pick) => [
    { key, label, divider: true, render: (row) => el("span", { "data-k": `${key}:${text(row.key)}` }, fmtStat(row[key], row.format)) },
    { key: `${key}Rank`, label: "FBS rank", labelMid: "FBS", kind: "rank", of: `${key}Of`, size: "medium", link: (row) => nationalHref(row.metric, { team, year: pick(row) }) },
    confs ? { key: `${key}Conf`, label: `${conf} rank`, kind: "rank", of: `${key}ConfOf`, size: "large", link: (row) => nationalHref(row.metric, { team, year: pick(row), scope: "conference" }) } : null,
  ].filter(Boolean);
  const columns = (side) => [
    { key: "label", label: "Statistic", labelShort: side === "defense" ? "Def (allowed)" : "Stat", kind: "text" },
    ...season("now", String(thisYear ?? "This season"), () => null),
    ...season("last", String(year ?? "Last season"), (row) => row.metricYear),
    { key: "change", label: "Change", kind: "text", divider: true },
  ];
  const sides = [...new Set(shaped.map((r) => r.side))];
  return el(
    "div",
    { class: "d2 prof" },
    sides.map((side) => el("div", {}, h4(SIDE_TITLES[side] || text(side)), statTable({ compact: true, sizes: true, sortable: false, columns: columns(side), rows: shaped.filter((r) => r.side === side), caption: `${SIDE_TITLES[side] || side}: this season and last` }))),
    note(`Each season with its national rank among FBS teams${confs ? ` and its rank inside the ${conf}` : ""}. "Better" follows the stat's direction (fewer points allowed is better). ${text(year)} is the full season, bowls included.`),
  );
}

const SITE_SHORT = { Home: "H", Away: "A", Neutral: "N" };

/** A finished game of the opponent's, shaped for the standings' form squares (W or L, the score, where and whom). */
function formGame(g) {
  const res = typeof g.result === "string" && ["W", "L", "T"].includes(g.result) ? g.result : null;
  if (!res) return null;
  const score = typeof g.score === "string" ? /^(\d+)-(\d+)$/.exec(g.score.trim()) : null;
  return {
    result: res,
    points: isNum(g.points) ? g.points : score ? Number(score[1]) : null,
    opponentPoints: isNum(g.opponentPoints) ? g.opponentPoints : score ? Number(score[2]) : null,
    opponent: typeof g.opponent === "string" && g.opponent.trim() ? g.opponent.trim() : null,
    homeAway: g.homeAway === "away" || g.homeAway === "home" || g.homeAway === "neutral" ? g.homeAway : null,
  };
}

/** The moment an ISO date names, for sorting; null for anything else. */
function moment(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  const at = Date.parse(value);
  return Number.isFinite(at) ? at : null;
}

/**
 * Every remaining opponent, sized by its own box (tables wave 3): Wk | Date | Opponent | Site | Record | AP rank | SP+ |
 * FBS rank | Last three. At small: the week, the opponent's abbreviation (still its link), H, A or N, the record and SP+.
 * The last three read as the standings' W and L squares (each square's title the score and the opponent), so the Season
 * page reads results one way. Games sort; the schedule's order to start.
 * roadAheadBlock(rows, { logos: Map(school -> the schedule's opponent), sorts: a plain object the table keeps its order in })
 */
export function roadAheadBlock(rows, { logos, sorts } = {}) {
  const list = records(rows);
  if (!list.length) return note("No games left on the schedule.");
  const teams = logos instanceof Map ? logos : new Map();
  const shaped = list.map((r, order) => {
    const opponent = typeof r.opponent === "string" && r.opponent.trim() ? r.opponent.trim() : null;
    const found = opponent ? teams.get(opponent) : null;
    const meta = found && typeof found === "object" ? found : null;
    const form = records(r.lastThree).map(formGame).filter(Boolean);
    return {
      order,
      week: weekCell(r),
      when: moment(r.date),
      date: fmtDate(r.date, "short"),
      opponent,
      meta,
      abbr: typeof meta?.abbreviation === "string" && meta.abbreviation.trim() ? meta.abbreviation.trim() : null,
      site: typeof r.site === "string" && r.site.trim() ? r.site.trim() : DASH,
      siteShort: SITE_SHORT[r.site] || null,
      record: typeof r.record === "string" && r.record.trim() ? r.record.trim() : DASH,
      apRank: r.apRank,
      sp: r.sp,
      spRank: r.spRank,
      spOf: r.spOf,
      spMetric: r.spMetric,
      form,
      formWins: form.filter((g) => g.result === "W").length,
    };
  });
  const state = sorts && typeof sorts === "object" ? sorts : {};
  return el(
    "div",
    { class: "d2 road-ahead" },
    statTable({
      compact: true,
      sizes: true,
      columns: [
        { key: "week", label: "Wk", dim: true, sortKey: "order" }, // the schedule's order, so a bowl follows the weeks
        { key: "date", label: "Date", kind: "text", size: "medium", sortKey: "when" },
        { key: "opponent", label: "Opponent", kind: "text", render: (row) => logoLink(row.opponent, row.meta), renderShort: (row) => teamAbbrLink(row.opponent, row.abbr) },
        { key: "site", label: "Site", kind: "text", shortKey: "siteShort" },
        { key: "record", label: "Record" },
        { key: "apRank", label: "AP rank", labelMid: "AP", size: "medium", render: (row) => (isNum(row.apRank) ? pollBadge(row.apRank, "AP", { href: pollHref("AP", { team: row.opponent }), label: row.opponent, showPoll: false }) : el("span", { class: "nr" }, "NR")) },
        { key: "sp", label: "SP+", format: "1f", divider: true },
        { key: "spRank", label: "FBS rank", labelMid: "FBS", kind: "rank", of: "spOf", size: "medium", link: (row) => nationalHref(row.spMetric, { team: row.opponent }) },
        { key: "form", label: "Last three", size: "medium", divider: true, sortKey: "formWins", render: (row) => formSquares(row.form, { limit: 3 }) || DASH },
      ].map((column) => ({ ...column, tieKey: "order" })), // a tie keeps the schedule's order
      rows: shaped,
      sort: state.road && typeof state.road.key === "string" ? state.road : { key: "week", dir: "ascending" },
      onSort: (sort) => {
        state.road = sort; // the reader's order survives a refresh
      },
      caption: "The road ahead",
    }),
    note("Record and the last three count this season's finished games, the newest on the right; SP+ is this week's rating."),
  );
}

function results(list) {
  return records(list).map((g) => `${text(g.result)} ${text(g.score)}`).join(", ") || DASH;
}

/** The margins' scale for the bar (wave 2): four touchdowns between the two teams' results against the same opponent leans
 *  all the way. Margins run either side of zero (a win and a loss), so they lean by their gap over this, never their share. */
export const MARGIN_SCALE = 28;

/** Common opponents as two-team rows: the opponent (its team page, its abbreviation at small), each side's results, and
 *  the margins (every meeting added up) deciding who did better against it. Exported for the tests. */
export function commonOpponentRows(rows) {
  return records(rows)
    .filter((r) => typeof r.opponent === "string" && r.opponent.trim())
    .map((r) => {
      const opponent = r.opponent.trim();
      const abbr = typeof r.opponentAbbr === "string" && r.opponentAbbr.trim() ? r.opponentAbbr.trim() : null;
      return {
        label: opponent,
        team: opponent,
        labelShort: abbr || undefined,
        higherIsBetter: true,
        scale: MARGIN_SCALE,
        us: { value: isNum(r.usMargin) ? r.usMargin : null, text: results(r.us) },
        them: { value: isNum(r.themMargin) ? r.themMargin : null, text: results(r.them) },
      };
    });
}

/**
 * Teams both sides have played, on the two-team kit (rule 9; owner 2026-10-10, wave 2): each side's results against the
 * opponent under its own head, the bar leaning to the side that did better against it by the margins. We sit first.
 * commonOpponentsBlock(rows, { usAbbr, themAbbr, usTeam, themTeam, usName, themName })
 */
export function commonOpponentsBlock(rows, { usAbbr, themAbbr, usTeam, themTeam, usName, themName } = {}) {
  const shaped = commonOpponentRows(rows);
  if (!shaped.length) return note(`${text(usTeam || usAbbr)} and ${text(themTeam || themAbbr)} have no opponent in common yet this season.`);
  return el(
    "div",
    { class: "d2" },
    programTwoTeam({ rows: shaped, usAbbr: text(usAbbr), themAbbr: text(themAbbr), usTeam, themTeam, usName, themName, tug: true, labelHead: "Opponent", caption: "Common opponents" }),
    note("Scores read from each team's side. The bar leans to the team that did better against that opponent, by the margins (every meeting added up)."),
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
