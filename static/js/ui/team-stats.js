// The two-team stats table with sub-rows (L4 as revised 2026-09-21) and the quarter score line
// (L1). Parent rows are bold, sub-rows indent, and the side that leads a row is in chalk.
// Every value is guarded: a stat the box does not carry renders as a dash.

import { DASH, el, fmtNum, fmtPct, isNum, text } from "./dom.js";

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
    row("Attempts", "sub", rawNum(u, "rushingAttempts"), rawNum(t, "rushingAttempts"), {}),
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
  if (format === "pct") return fmtPct(value);
  if (format === "1f") return fmtNum(value, 1);
  return fmtNum(value, 0);
}

function tone(row, side) {
  if (row.higherIsBetter === undefined || !isNum(row.usValue) || !isNum(row.themValue) || row.usValue === row.themValue) return "";
  const usLeads = row.higherIsBetter ? row.usValue > row.themValue : row.usValue < row.themValue;
  const leads = side === "us" ? usLeads : !usLeads;
  return leads ? " lead" : " trail";
}

/**
 * teamStatsTable({ us: {abbr, box}, them: {abbr, box}, rows, compact })
 * `rows` defaults to teamStatRows(us.box, them.box); pass a subset for a summary.
 */
export function teamStatsTable({ us = {}, them = {}, rows, compact = true, caption = "Team stats" }) {
  const list = rows || teamStatRows(us.box || {}, them.box || {});
  const table = el(
    "table",
    { class: `stat-table${compact ? " stat-table--compact" : ""}` },
    el("caption", { class: "sr-only" }, caption),
    el("thead", {}, el("tr", {}, el("th", { scope: "col", class: "txt" }, ""), el("th", { scope: "col", class: "us" }, text(us.abbr)), el("th", { scope: "col", class: "them" }, text(them.abbr)))),
    el(
      "tbody",
      {},
      list.map((row) =>
        el(
          "tr",
          { class: row.kind === "sub" ? "is-sub" : "is-parent" },
          el("td", { class: "txt" }, row.label),
          el("td", { class: `num${tone(row, "us")}` }, row.us),
          el("td", { class: `num${tone(row, "them")}` }, row.them),
        ),
      ),
    ),
  );
  return el("div", { class: "stat-table-wrap" }, table);
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
      Array.from({ length: periods }, (_, i) => el("div", { class: "qline__val" }, isNum(side.scores?.[i]) ? side.scores[i] : DASH)),
      el("div", { class: "qline__val qline__val--tot" }, text(total(side.scores || [], side.total))),
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
