// The two-team stats table with sub-rows (L4 as revised 2026-09-21) and the quarter score line
// (L1). Parent rows are bold, sub-rows indent, and the side that leads a row is in chalk.
// Every value is guarded: a stat the box does not carry renders as a dash.
//
// Table sizes, wave 2 (owner 2026-10-10): every two-team table is the shared kit (ui/two-team.js, design rule 9) with the
// tug-of-war bar, sized by its own box: large has the stat's whole name and each team's school and mascot, medium the
// middle names and the school, small the shortest names and the abbreviation (ui/sizes.js FORMS). With no national
// ranks the bar leans by the two values themselves, how far one team is ahead.
//
//   teamStatRows(usBox, themBox)       the rows, in the screenshot brief's order: { label, kind, usValue, themValue,
//                                      higherIsBetter, us, them } (us/them the display strings)
//   teamStatsTable({ us, them, rows, labelHead = "Statistic", caption })
//       us/them: { abbr, box, school, name }: the abbreviation, the box, the school (medium's head) and the school and
//       mascot (large's head); rows default to teamStatRows(us.box, them.box), or pass a subset (the Situation panel,
//       the final box's rows CFBD has). Each value cell keeps its flash key "ts:<label>:us" / ":them" (L-03).
//   FEED_ROWS                          the live feed's efficiency measures: [label, feed key, format]
//   feedStatRows(usFeed, themFeed)     those rows for the kit, raw values so the leader shows (the PPA rows on PPA_SCALE);
//                                      rows neither side has go
//   feedEfficiencyTable({ feed, us, them, caption })   the feed rows on the kit (In Game and the Archive), or null when
//       the feed has none. us/them: { team, abbr, school, name }; team is the side's key in the feed (its school).
//   sideHeads(us, them)                { usAbbr, themAbbr, usTeam, themTeam, usName, themName } for twoTeamTable from each
//                                      side's { abbr, school, name } (a blank school or name is left out); In Game's other
//                                      two-team tables (ui/in-game-tables.js) take their heads the same way
//   quarterLine({ us, them })          the score by quarter (a scoreboard grid, not a table: large figures, the spoiler
//                                      blur and the flash keys); its columns narrow by its band's width, not the screen.

import { DASH, el, fmtNum, fmtPct, isNum, obj, records, text } from "./dom.js";
import { PPA_SCALE, twoTeamTable } from "./two-team.js";

function pair(a, b) {
  return isNum(a) && isNum(b) ? `${a}-${b}` : DASH;
}

/** "6-45" (count and yards) from the box score; the count alone before it posts (the play log knows no penalty yards). */
export function penaltyText(penalties) {
  const count = penalties?.count;
  const yards = penalties?.yards;
  if (isNum(count) && isNum(yards)) return `${count}-${yards}`;
  return isNum(count) ? String(count) : DASH;
}

function rate(made, of) {
  return isNum(made) && isNum(of) && of > 0 ? made / of : null;
}

function rawNum(box, key) {
  const value = box?.raw?.[key];
  if (isNum(value)) return value;
  const parsed = typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(parsed) ? parsed : null;
}

/** The per-team efficiency block CFBD's live feed carries (feedStats), as rows for In Game and the Archive:
 *  one list, named as the Season and program tables name the same measures (final pass: PPA, not EPA; scoring
 *  chances). The fourth item is the direction: every row is better higher except the start, which CFBD's feed gives as
 *  yards to the goal (the drives' mean startYardsToGoal), so fewer is better there, as on the season tables. */
export const FEED_ROWS = [
  ["Standard downs", "standardDownSuccessRate", "pct"],
  ["Passing downs", "passingDownSuccessRate", "pct"],
  ["PPA per play", "epaPerPlay", "+2f"],
  ["PPA per pass", "epaPerPass", "+2f"],
  ["PPA per rush", "epaPerRush", "+2f"],
  ["Explosiveness", "explosiveness", "2f"],
  ["Points per scoring chance", "pointsPerOpportunity", "2f"],
  ["Scoring chances", "scoringOpportunities", "0f"],
  ["Line yards per rush", "lineYardsPerRush", "1f"],
  ["Average start, yards to goal", "averageStartYardLine", "0f", false],
  ["Deserve to win", "deserveToWin", "pct"],
];

/**
 * The rows, in the order the screenshot brief lists them. `higherIsBetter` decides which side
 * is shown as leading; rows without it are neutral (time of possession, attempts).
 */
export function teamStatRows(u = {}, t = {}) {
  const row = (label, kind, usValue, themValue, { format = "0f", higherIsBetter, usText, themText } = {}) => ({
    label,
    kind,
    usValue,
    themValue,
    higherIsBetter,
    us: usText ?? formatValue(usValue, format),
    them: themText ?? formatValue(themValue, format),
  });
  return [
    row("Points", "parent", u.points, t.points, { higherIsBetter: true }),
    row("Yards", "parent", u.totalYards, t.totalYards, { higherIsBetter: true }),
    row("Yards per play", "sub", u.yardsPerPlay, t.yardsPerPlay, { format: "1f", higherIsBetter: true }),
    row("Plays", "sub", u.plays, t.plays, {}),
    row("Drives", "sub", u.drives, t.drives, {}),
    row("20+ yard plays", "sub", u.explosive?.twenty, t.explosive?.twenty, { higherIsBetter: true }),
    row("40+ yard plays", "sub", u.explosive?.forty, t.explosive?.forty, { higherIsBetter: true }),
    row("Success rate", "sub", u.successRate, t.successRate, { format: "pct", higherIsBetter: true }),
    row("Pass yards", "parent", u.netPassingYards, t.netPassingYards, { higherIsBetter: true }),
    row("Comp-Att", "sub", null, null, { usText: text(u.raw?.completionAttempts), themText: text(t.raw?.completionAttempts) }),
    row("Yards per attempt", "sub", rawNum(u, "yardsPerPass"), rawNum(t, "yardsPerPass"), { format: "1f", higherIsBetter: true }),
    row("Passing TDs", "sub", rawNum(u, "passingTDs"), rawNum(t, "passingTDs"), { higherIsBetter: true }),
    row("Rush yards", "parent", u.rushingYards, t.rushingYards, { higherIsBetter: true }),
    row("Carries", "sub", rawNum(u, "rushingAttempts"), rawNum(t, "rushingAttempts"), {}), // final pass: carries everywhere, never attempts
    row("Yards per carry", "sub", rawNum(u, "yardsPerRushAttempt"), rawNum(t, "yardsPerRushAttempt"), { format: "1f", higherIsBetter: true }),
    row("Rushing TDs", "sub", rawNum(u, "rushingTDs"), rawNum(t, "rushingTDs"), { higherIsBetter: true }),
    row("First downs", "parent", u.firstDowns, t.firstDowns, { higherIsBetter: true }),
    row("Third down", "sub", rate(u.thirdDown?.made, u.thirdDown?.of), rate(t.thirdDown?.made, t.thirdDown?.of), { higherIsBetter: true, usText: pair(u.thirdDown?.made, u.thirdDown?.of), themText: pair(t.thirdDown?.made, t.thirdDown?.of) }),
    row("Fourth down", "sub", rate(u.fourthDown?.made, u.fourthDown?.of), rate(t.fourthDown?.made, t.fourthDown?.of), { higherIsBetter: true, usText: pair(u.fourthDown?.made, u.fourthDown?.of), themText: pair(t.fourthDown?.made, t.fourthDown?.of) }),
    row("Red zone", "sub", rate(u.redZone?.scores, u.redZone?.trips), rate(t.redZone?.scores, t.redZone?.trips), { higherIsBetter: true, usText: pair(u.redZone?.scores, u.redZone?.trips), themText: pair(t.redZone?.scores, t.redZone?.trips) }),
    row("Turnovers", "parent", u.turnovers, t.turnovers, { higherIsBetter: false }),
    row("Fumbles lost", "sub", rawNum(u, "fumblesLost"), rawNum(t, "fumblesLost"), { higherIsBetter: false }),
    row("Interceptions thrown", "sub", rawNum(u, "passesIntercepted"), rawNum(t, "passesIntercepted"), { higherIsBetter: false }),
    row("Penalties", "parent", u.penalties?.yards, t.penalties?.yards, { higherIsBetter: false, usText: penaltyText(u.penalties), themText: penaltyText(t.penalties) }),
    row("Sacks", "parent", rawNum(u, "sacks"), rawNum(t, "sacks"), { higherIsBetter: true }),
    row("Tackles for loss", "sub", rawNum(u, "tacklesForLoss"), rawNum(t, "tacklesForLoss"), { higherIsBetter: true }),
    row("Time of possession", "parent", null, null, { usText: text(u.possessionTime), themText: text(t.possessionTime) }),
  ];
}

function formatValue(value, format) {
  if (format === "pct") return fmtPct(value, 1); // final pass: one decimal in tables
  if (format === "1f") return fmtNum(value, 1);
  return fmtNum(value, 0);
}

function numOrNull(value) {
  return isNum(value) ? value : null;
}

function wordsOf(value) {
  return typeof value === "string" && value.trim() && value.trim() !== DASH ? value.trim() : undefined; // a dash is no name
}

/** Each side's heads for the kit: the abbreviation (small), the school (medium), the school and mascot (large). */
export function sideHeads(us, them) {
  const u = obj(us);
  const t = obj(them);
  return { usAbbr: text(u.abbr), themAbbr: text(t.abbr), usTeam: wordsOf(u.school), themTeam: wordsOf(t.school), usName: wordsOf(u.name), themName: wordsOf(t.name) };
}

/**
 * teamStatsTable({ us: {abbr, box, school, name}, them: {...}, rows, labelHead, caption })
 * `rows` defaults to teamStatRows(us.box, them.box); pass a subset for a summary.
 */
export function teamStatsTable(options) {
  const { us, them, rows, labelHead = "Statistic", caption = "Team stats" } = obj(options);
  const list = Array.isArray(rows) ? records(rows) : teamStatRows(obj(obj(us).box), obj(obj(them).box));
  return twoTeamTable({
    rows: list.map((r) => {
      const label = text(r.label);
      return {
        label,
        key: `ts:${label}`, // L-03: the per-play flash, the same keys as before the kit
        rowClass: r.kind === "sub" ? "is-sub" : "is-parent",
        higherIsBetter: typeof r.higherIsBetter === "boolean" ? r.higherIsBetter : undefined,
        us: { value: numOrNull(r.usValue), text: typeof r.us === "string" ? r.us : DASH },
        them: { value: numOrNull(r.themValue), text: typeof r.them === "string" ? r.them : DASH },
      };
    }),
    ...sideHeads(us, them),
    labelHead,
    tug: true, // rule 9: the shared kit with the bar; no ranks here, so it leans by the values
    caption,
  });
}

/** The feed's rows for the kit: raw values so the leader shows, rows that neither side has dropped. The signed rows
 *  (PPA, either side of zero) lean by their gap on PPA_SCALE, the rest by the two values' share. */
export function feedStatRows(usFeed, themFeed) {
  const u = obj(usFeed);
  const t = obj(themFeed);
  return FEED_ROWS.map(([label, key, format, higherIsBetter = true]) => ({ label, format, higherIsBetter, scale: format === "+2f" ? PPA_SCALE : undefined, us: { value: numOrNull(u[key]) }, them: { value: numOrNull(t[key]) } })).filter((r) => r.us.value !== null || r.them.value !== null);
}

/**
 * feedEfficiencyTable({ feed, us: {team, abbr, school, name}, them: {...}, caption })
 * The live feed's efficiency numbers for both teams on the kit, or null when the feed carries none of them.
 */
export function feedEfficiencyTable(options) {
  const { feed, us, them, caption = "Efficiency, from the live feed" } = obj(options);
  const f = obj(feed);
  const team = (side) => (typeof obj(side).team === "string" ? obj(side).team : "");
  const rows = feedStatRows(team(us) ? f[team(us)] : null, team(them) ? f[team(them)] : null);
  if (!rows.length) return null;
  return twoTeamTable({ rows, ...sideHeads(us, them), labelHead: "Statistic", tug: true, caption });
}

export function teamStatsSkeleton(rows = 8) {
  return el("div", {}, Array.from({ length: rows }, () => el("div", { class: "skel skel--row" })));
}

/**
 * quarterLine({ us: {abbr, scores: [..], total}, them: {abbr, scores, total} })
 * Quarter columns follow the longer score list, so overtime adds a column instead of breaking.
 */
export function quarterLine({ us = {}, them = {} }) {
  const usScores = Array.isArray(us.scores) ? us.scores : [];
  const themScores = Array.isArray(them.scores) ? them.scores : [];
  const periods = Math.max(4, usScores.length, themScores.length);
  const heads = Array.from({ length: periods }, (_, i) => (i < 4 ? `Q${i + 1}` : periods === 5 ? "OT" : `${i - 3}OT`));
  const total = (scores, given) => (isNum(given) ? given : scores.every(isNum) && scores.length ? scores.reduce((a, b) => a + b, 0) : null);
  const row = (side, kind) =>
    el(
      "div",
      { class: `qline__row qline__row--${kind}`, style: { display: "contents" } },
      el("div", { class: `qline__team qline__team--${kind}` }, text(side.abbr)),
      Array.from({ length: periods }, (_, i) => el("div", { class: "qline__val", dataset: { k: `q:${kind}:${i}` } }, isNum(side.scores?.[i]) ? side.scores[i] : DASH)),
      el("div", { class: "qline__val qline__val--tot", dataset: { k: `q:${kind}:t` } }, text(total(side.scores || [], side.total))),
    );
  return el(
    "div",
    { class: "qline", role: "table", "aria-label": "Score by quarter", style: { "--q": String(periods) } },
    el("div", { class: "qline__head qline__head--label" }, ""),
    heads.map((h) => el("div", { class: "qline__head" }, h)),
    el("div", { class: "qline__head" }, "T"),
    row(us, "us"),
    row(them, "them"),
  );
}
