// In Game's own tables (L4, Phase 12, X7): the quarter splits, the tendencies by situation, the drive summary, the
// fourth-down choice, each team's play value and the recruits on hand. In Game's side panels draw them, and the game-day
// board draws the same panels inline in four narrow panes.
//
// Table sizes, wave 2 (owner 2026-10-10; docs/03-DESIGN.md, Table sizes): each table sizes itself by its own box, so the
// 780 px side sheet, a phone and a board pane follow the same steps. Large has whole heads and stat names, medium the
// middle names, small the shortest names, the made-of counts as "3-8" and the surname. Every two-team table is the shared
// kit with the tug-of-war bar (rule 9), leaning by the real margin (no national ranks here). A table of stat names keeps
// its written order; the recruits sort (a table of players, owner 2026-09-26).
//
//   madeOf(value), madeShort(value)    "3 of 8" and "3-8" from { made, of }, or a dash
//   SPLIT_ROWS                         the quarter splits' rows: [label, key, format]
//   splitRows(splits, team)            one team's rows, a field per period plus "Game" (and "<period>Short" for a count)
//   splitsTable(splits, team, { caption })   every period and the game at every size (rule 2: only the names shorten)
//   tendencyRows(list)                 the live tendencies as rows: the run rate a number (one decimal in the table)
//   tendencyTable(tendencies, team, { caption })   the plays from medium; the note "No snaps yet." before the first one
//   DRIVE_ROWS                         the drive summary's rows: [label, key, format, higherIsBetter]
//   driveSummaryTable(summary, sides)  the kit with the bar, or null before the first finished drive
//   fourthDownRows(f), fourthDownTable(f, { caption })   one data point per column (rule 3); null when there is no choice
//   TEAM_VALUE_ROWS                    each unit's PPA per play: [label, unit, key, higherIsBetter]; the defense's rows say
//                                      allowed (CFBD's game defense PPA is what the defense allowed: lower is better)
//   teamValueTable(teams, sides)       the kit with the bar, or the note when CFBD sent no team values
//   visitorRows(list), visitorsTable(list, { caption })   the high school, hometown and class at large only
//
//   sides: { us: { team, abbr, school, name }, them: { ... } }: team is the side's key in the server's blocks (its school),
//          abbr, school and name the two-team heads at small, medium and large (ui/team-stats.js sideHeads).

import { DASH, fmtPct, fmtStat, isNum, obj, records, str, text } from "./dom.js";
import { note } from "./states.js";
import { statTable } from "./stat-table.js";
import { sideHeads } from "./team-stats.js";
import { PPA_SCALE, twoTeamTable } from "./two-team.js";

const num = (value) => (isNum(value) ? value : null);

/** "3 of 8" from {made, of}, or a dash. */
export function madeOf(value) {
  return value && isNum(value.made) && isNum(value.of) && value.of > 0 ? `${value.made} of ${value.of}` : DASH;
}

/** "3-8" from {made, of} for a small table, or a dash. */
export function madeShort(value) {
  return value && isNum(value.made) && isNum(value.of) && value.of > 0 ? `${value.made}-${value.of}` : DASH;
}

/** One side's block from a server map keyed by school ({ "Swampwater Tech": {...} }), or {}. */
function blockFor(map, side) {
  const team = obj(side).team;
  return typeof team === "string" && team ? obj(obj(map)[team]) : {};
}

// --- quarter by quarter ----------------------------------------------------------------------------------------------

// One name per stat (design rule 6): PPA, not EPA; "Third down" as Team stats and the Season tables say it
export const SPLIT_ROWS = [
  ["Plays", "plays", "0f"],
  ["Yards", "yards", "0f"],
  ["Yards per play", "yardsPerPlay", "1f"],
  ["Success", "success", "madeOf"],
  ["PPA per play (no TD plays)", "epaPerPlay", "+2f"],
  ["20+ yard plays", "explosive", "0f"],
  ["Turnovers", "turnovers", "0f"],
  ["Third down", "thirdDown", "madeOf"],
];

/** The periods the server split the game into ("Q1" .. "Q4", "OT", "2OT"), then the whole game. */
function splitPeriods(splits) {
  const periods = Array.isArray(obj(splits).periods) ? obj(splits).periods : [];
  const seen = new Set();
  for (const p of periods) if (typeof p === "string" && p.trim() && !["label", "Game"].includes(p.trim()) && !p.trim().endsWith("Short")) seen.add(p.trim());
  return [...seen, "Game"];
}

export function splitRows(splits, team) {
  const keys = splitPeriods(splits);
  const byPeriod = obj(obj(obj(splits).teams)[team]);
  return SPLIT_ROWS.map(([label, key, format]) => {
    const row = { label };
    for (const period of keys) {
      const cell = obj(byPeriod[period])[key];
      if (format === "madeOf") {
        row[period] = madeOf(cell);
        row[`${period}Short`] = madeShort(cell); // "3-8" at small
      } else row[period] = isNum(cell) ? fmtStat(cell, format) : DASH;
    }
    return row;
  });
}

/** One team's game by quarter: every period and the game at every size (each overtime adds a column); only the stat
 *  names shorten. The values sit in the stat face, right-aligned like every number. */
export function splitsTable(splits, team, { caption } = {}) {
  const keys = splitPeriods(splits);
  const columns = [{ key: "label", label: "By quarter", labelShort: "Stat", kind: "text" }, ...keys.map((k) => ({ key: k, label: k, shortKey: `${k}Short` }))];
  return statTable({ compact: true, sizes: true, sortable: false, columns, rows: splitRows(splits, team), caption: typeof caption === "string" ? caption : "By quarter" });
}

// --- tendencies by situation ----------------------------------------------------------------------------------------

// The Pre-Game Program's words for the same numbers (ui/depth2.js): the run rate to one decimal; small keeps the situation,
// the run rate and both made-of pairs ("12-20"), which carry the counts the plays column drops
const TENDENCY_COLUMNS = [
  { key: "label", label: "Situation", kind: "text" },
  { key: "plays", label: "Plays", size: "medium" },
  { key: "runRate", label: "Run rate", labelShort: "Run %", format: "pct" },
  { key: "run", label: "Run success", labelShort: "Run succ.", kind: "text", shortKey: "runShort" },
  { key: "pass", label: "Pass success", labelShort: "Pass succ.", kind: "text", shortKey: "passShort" },
];

export function tendencyRows(list) {
  return records(list).map((r) => ({
    label: text(r.label),
    plays: isNum(r.plays) && r.plays >= 0 ? r.plays : 0,
    runRate: isNum(r.passRate) && r.passRate >= 0 && r.passRate <= 1 ? 1 - r.passRate : null,
    run: madeOf(r.runSuccess),
    runShort: madeShort(r.runSuccess),
    pass: madeOf(r.passSuccess),
    passShort: madeShort(r.passSuccess),
  }));
}

export function tendencyTable(tendencies, team, { caption } = {}) {
  const rows = tendencyRows(obj(tendencies)[team]);
  if (!rows.some((r) => r.plays > 0)) return note("No snaps yet.");
  return statTable({ compact: true, sizes: true, sortable: false, columns: TENDENCY_COLUMNS, rows, caption: typeof caption === "string" ? caption : "Tendencies by situation" });
}

// --- the drive summary ----------------------------------------------------------------------------------------------

// Each row's direction, so the bar leans to the side that won it: more points and chances, fewer three-and-outs and
// turnovers; the finished drives are a count, not a grade (no bar)
export const DRIVE_ROWS = [
  ["Finished drives", "drives", "0f", undefined],
  ["Points on drives", "points", "0f", true],
  ["Points per drive", "pointsPerDrive", "2f", true],
  ["Three-and-outs", "threeAndOuts", "0f", false],
  ["Turnovers", "turnovers", "0f", false],
  ["Scoring chances", "opportunities", "0f", true],
  ["Points per scoring chance", "pointsPerOpportunity", "2f", true],
];

export function driveSummaryTable(summary, sides) {
  const s = obj(sides);
  const us = blockFor(summary, s.us);
  const them = blockFor(summary, s.them);
  if (!isNum(us.drives) && !isNum(them.drives)) return null;
  const rows = DRIVE_ROWS.map(([label, key, format, higherIsBetter]) => ({ label, format, higherIsBetter, us: { value: num(us[key]) }, them: { value: num(them[key]) } }));
  return twoTeamTable({ rows, ...sideHeads(s.us, s.them), labelHead: "Drives", tug: true, caption: "Drive summary" });
}

// --- fourth down: go or kick ----------------------------------------------------------------------------------------

// One data point per column (rule 3): the expected points (going for it: if it converts), the expected points if the try
// fails, and the chance (the conversion rate going for it needs, the field goal's chance to go in) from medium; the note
// under the table gives the break-even at every size
const FOURTH_COLUMNS = [
  { key: "option", label: "Choice", kind: "text", shortKey: "optionShort" },
  { key: "ep", label: "Expected points", labelMid: "Exp. points", labelShort: "EP" },
  { key: "epFail", label: "If it fails", labelShort: "If not" },
  { key: "chance", label: "Chance", size: "medium" },
];

const signed = (value) => (isNum(value) ? fmtStat(value, "+1f") : DASH);

export function fourthDownRows(f) {
  const d = obj(f);
  if (!isNum(d.breakEven)) return [];
  const go = obj(d.go);
  const rows = [{ option: "Go for it", optionShort: "Go", ep: signed(go.success), epFail: signed(go.fail), chance: `${fmtPct(d.breakEven, 1)} needed` }];
  const fg = d.fieldGoal && typeof d.fieldGoal === "object" && !Array.isArray(d.fieldGoal) ? d.fieldGoal : null;
  if (fg) {
    const yards = isNum(fg.distance) ? `${Math.round(fg.distance)} yd` : null;
    rows.push({ option: yards ? `Field goal, ${yards}` : "Field goal", optionShort: yards ? `FG ${yards}` : "FG", ep: signed(fg.ep), epFail: DASH, chance: isNum(fg.makeChance) ? `${fmtPct(fg.makeChance, 1)} to make` : DASH });
  }
  if (d.punt && typeof d.punt === "object" && !Array.isArray(d.punt)) rows.push({ option: "Punt (40 net)", optionShort: "Punt", ep: signed(d.punt.ep), epFail: DASH, chance: DASH });
  return rows;
}

export function fourthDownTable(f, { caption = "Go or kick: expected points" } = {}) {
  const rows = fourthDownRows(f);
  if (!rows.length) return null;
  return statTable({ compact: true, sizes: true, sortable: false, columns: FOURTH_COLUMNS, rows, caption });
}

// --- each team's play value -----------------------------------------------------------------------------------------

export const TEAM_VALUE_ROWS = [
  ["Offense, overall", "offense", "overall", true],
  ["Offense, passing", "offense", "passing", true],
  ["Offense, rushing", "offense", "rushing", true],
  ["Defense allowed, overall", "defense", "overall", false],
  ["Defense allowed, passing", "defense", "passing", false],
  ["Defense allowed, rushing", "defense", "rushing", false],
];

export function teamValueTable(teams, sides) {
  const t = obj(teams);
  const s = obj(sides);
  const value = (side, unit, key) => num(obj(obj(obj(t[side])[unit]))[key]);
  // a signed measure: the bar leans by the gap on the PPA scale, never by a share of two numbers near zero
  const rows = TEAM_VALUE_ROWS.map(([label, unit, key, higherIsBetter]) => ({ label, format: "+2f", higherIsBetter, scale: PPA_SCALE, us: { value: value("us", unit, key) }, them: { value: value("them", unit, key) } }));
  if (!rows.some((r) => r.us.value !== null || r.them.value !== null)) return note("No team values for this game yet.");
  return twoTeamTable({ rows, ...sideHeads(s.us, s.them), labelHead: "PPA per play", tug: true, caption: "Each team's play value, PPA per play" });
}

// --- the recruits on hand -------------------------------------------------------------------------------------------

// The recruit, his stars and his status at every size; the high school, hometown and class at large (the notes carry them)
const VISITOR_COLUMNS = [
  { key: "name", label: "Recruit", kind: "text", sub: "position", subLabel: "Pos", person: { notes: true } }, // wave 3 decision 1, as on the Recruiting page; the notes' words (item 6)
  { key: "stars", label: "Stars", format: "stars" },
  { key: "highSchool", label: "High school", kind: "text", size: "large" },
  { key: "hometown", label: "Hometown", kind: "text", size: "large" },
  { key: "classYear", label: "Class", size: "large" },
  { key: "status", label: "Status", kind: "text" },
];

export function visitorRows(list) {
  return records(list)
    .filter((v) => str(v.name))
    .map((v) => ({
      name: str(v.name),
      position: str(v.position),
      stars: num(v.stars),
      highSchool: str(v.highSchool),
      hometown: str(v.hometown),
      classYear: isNum(v.classYear) ? String(Math.round(v.classYear)) : null, // a year, never "2,027"
      status: str(v.status),
    }));
}

export function visitorsTable(list, { caption = "Recruits on hand" } = {}) {
  const rows = visitorRows(list);
  if (!rows.length) return note("No visitors listed.");
  return statTable({ compact: true, sizes: true, columns: VISITOR_COLUMNS, rows, caption });
}
