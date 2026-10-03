// Stat grades (public release Phase 7): our own 0 to 100 grade from CFBD's season stats, compared with FBS
// players at the same position. The server builds them (app/services/grades.py); this draws them.
//   gradeChip(grade)   a small number chip tinted by its band, or a dash with the reason as its title.
//   gradeBlock(grade)  the player page's breakdown: the grade, its label, its rank, what it is based on,
//                      each part with its value and percentile, and the volume it needed.
//   gradeValue(grade)  the number to sort by, or null.
// Every field is guarded: a missing grade, part or rank reads as a dash, never undefined, null or NaN.

import { DASH, el, fmtStat, isNum, text } from "./dom.js";
import { statTable } from "./stat-table.js";

export const GRADE_NOTE = "Stat grades are ours, from CFBD's season stats, compared with FBS players at the same position: 100 is the best, 50 the middle. They are not film grades.";
const BASIS = { efficiency: "Efficiency and production", production: "Production only (CFBD has no targets or snaps for this position)" };

function obj(value) {
  return value && typeof value === "object" ? value : {};
}

export function gradeValue(grade) {
  const g = obj(grade);
  return isNum(g.grade) ? g.grade : null;
}

export function gradeTier(value) {
  if (!isNum(value)) return null;
  return value >= 90 ? "elite" : value >= 75 ? "very-good" : value >= 60 ? "good" : value >= 40 ? "average" : value >= 25 ? "below" : "low";
}

export function gradeChip(grade) {
  const g = obj(grade);
  const value = gradeValue(g);
  if (value === null) return el("span", { class: "grade-chip grade-chip--none", title: typeof g.reason === "string" && g.reason ? g.reason : "No stat grade" }, DASH);
  const label = typeof g.label === "string" && g.label ? g.label : "";
  const rank = isNum(g.rank) && isNum(g.of) ? `#${g.rank} of ${g.of} FBS ${text(g.groupName)}` : "";
  return el("span", { class: `grade-chip grade-chip--${gradeTier(value)}`, title: [label, rank].filter(Boolean).join(", ") || null }, String(Math.round(value)));
}

function partValue(part) {
  const p = obj(part);
  if (!isNum(p.value)) return DASH;
  return p.format === "pct" ? fmtStat(p.value, "pct") : fmtStat(p.value, p.format === "0f" ? undefined : p.format || "1f");
}

export function gradeBlock(grade) {
  const g = obj(grade);
  const value = gradeValue(g);
  const parts = (Array.isArray(g.components) ? g.components : []).filter((c) => c && typeof c === "object" && typeof c.label === "string");
  const volume = obj(g.volume);
  const volumeLine = typeof volume.label === "string" && isNum(volume.needed)
    ? `${isNum(volume.perGame) ? fmtStat(volume.perGame, "1f") : DASH} ${volume.label} (${fmtStat(volume.needed, "1f")} needed, by the team's games).`
    : null;
  if (value === null) {
    return el(
      "div",
      { class: "grade-block grade-block--none" },
      el("p", { class: "grade-block__reason" }, typeof g.reason === "string" && g.reason ? g.reason : "No stat grade for this player yet."),
      volumeLine ? el("p", { class: "note" }, volumeLine) : null,
      el("p", { class: "note" }, GRADE_NOTE),
    );
  }
  const rank = isNum(g.rank) && isNum(g.of) ? `#${g.rank} of ${g.of} FBS ${text(g.groupName)}` : DASH;
  return el(
    "div",
    { class: "grade-block" },
    el(
      "div",
      { class: "grade-block__head" },
      el("span", { class: `grade-block__value grade-chip--${gradeTier(value)}` }, String(Math.round(value))),
      el("div", {}, el("div", { class: "grade-block__label" }, text(g.label)), el("div", { class: "grade-block__rank" }, rank), el("div", { class: "note" }, BASIS[g.basis] || DASH)),
    ),
    parts.length
      ? el(
          "table",
          { class: "grade-parts" },
          el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Part"), el("th", { scope: "col" }, "Value"), el("th", { scope: "col" }, "Percentile"))),
          el(
            "tbody",
            {},
            parts.map((p) =>
              el(
                "tr",
                {},
                el("th", { scope: "row" }, p.label, isNum(p.weight) ? el("small", {}, ` ${Math.round(p.weight * 100)}%`) : null),
                el("td", {}, partValue(p)),
                el("td", {}, isNum(p.percentile) ? el("span", { class: "grade-bar", style: { "--pct": `${Math.max(0, Math.min(100, p.percentile))}%` } }, el("span", {}, String(Math.round(p.percentile)))) : el("span", { class: "note" }, "no number")),
              ),
            ),
          ),
        )
      : null,
    volumeLine ? el("p", { class: "note" }, volumeLine) : null,
    el("p", { class: "note" }, GRADE_NOTE, " A part with no number is left out and the rest count for more."),
  );
}

/** A list of graded players (the Leaders board, players to watch): rank, player, team, grade. Rows are the
 *  server's public grades; ours are marked. onTap(row) opens the player. */
export function gradedTable(rows, { onTap, us, showTeam = true, caption = "Stat grades" } = {}) {
  const shown = (Array.isArray(rows) ? rows : []).filter((r) => r && typeof r === "object" && typeof r.playerId === "string").map((r) => ({ ...r, gradeValue: gradeValue(r), isUs: Boolean(us) && r.team === us }));
  const columns = [
    { key: "rank", label: "Rk", kind: "rank", stick: true },
    { key: "name", label: "Player", kind: "text", sub: "position", stick: true },
    { key: "gradeValue", label: "Grade", render: (r) => gradeChip(r) }, // before the team, so a phone shows it without scrolling
    { key: "label", label: "", kind: "text", sortable: false },
    ...(showTeam ? [{ key: "team", label: "Team", kind: "text", team: true }] : []),
  ];
  return statTable({ compact: true, columns, rows: shown, sort: { key: "gradeValue", dir: "descending" }, rowClass: (r) => (r.isUs ? "is-us" : null), onRowTap: typeof onTap === "function" ? onTap : undefined, caption });
}
