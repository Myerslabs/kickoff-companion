// Stat grades (public release Phase 7): our own 0 to 100 grade from CFBD's season stats, compared with FBS
// players at the same position. The server builds them (app/services/grades.py); this draws them.
//   gradeChip(grade)   a small number chip tinted by its band, or a dash with the reason as its title.
//   gradeBlock(grade)  the player page's breakdown: the grade, its label, its rank, what it is based on,
//                      each part with its value and percentile, and the volume it needed.
//   gradeValue(grade)  the number to sort by, or null.
// Every field is guarded: a missing grade, part or rank reads as a dash, never undefined, null or NaN.

import { DASH, el, fmtStat, isNum, obj, text } from "./dom.js";
import { statTable } from "./stat-table.js";

export const GRADE_NOTE = "Stat grades are ours, from CFBD's season stats, compared with FBS players at the same position: 100 is the best, 50 the middle. They are not film grades.";
const BASIS = { efficiency: "Graded on efficiency and production", production: "Graded on production only (CFBD has no targets or snaps for this position)" };

/** A percentile's color, like the rank chips: green from 75, yellow from 40, red below (Phase 17 #18). */
export function percentileTone(pct) {
  if (!isNum(pct)) return null;
  return pct >= 75 ? "good" : pct >= 40 ? "mid" : "low";
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
    ? `${isNum(volume.perGame) ? fmtStat(volume.perGame, "1f") : DASH} ${volume.label} (${fmtStat(volume.needed, "1f")} needed).`
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
  // Phase 17 #18 (owner-approved mockup): the grade and its basis in one header; each part with its weight as a
  // small tag, its value, and a thin bar in the rank chips' colors with the number outside; one line of fine print
  const rank = isNum(g.rank) && isNum(g.of) ? `#${g.rank} of ${g.of} FBS ${text(g.groupName)}` : null;
  const group = typeof g.groupName === "string" && g.groupName.trim() ? g.groupName.trim() : "players at the position";
  const bar = (pct) => {
    if (!isNum(pct)) return el("span", { class: "note" }, "no number");
    const clamped = Math.max(0, Math.min(100, pct));
    return el(
      "span",
      { class: "grade-bar" },
      el("span", { class: "grade-bar__track", "aria-hidden": "true" }, el("span", { class: `grade-bar__fill grade-bar__fill--${percentileTone(clamped)}`, style: { width: `${clamped}%` } })),
      el("span", { class: "grade-bar__n" }, String(Math.round(clamped))),
    );
  };
  return el(
    "div",
    { class: "grade-block" },
    el(
      "div",
      { class: "grade-block__head" },
      el("span", { class: `grade-block__value grade-chip--${gradeTier(value)}` }, String(Math.round(value))),
      el(
        "div",
        { class: "grade-block__says" },
        el("div", { class: "grade-block__label" }, [text(g.label), rank ? ` · ${rank}` : null].filter(Boolean).join("")),
        el("div", { class: "grade-block__basis" }, BASIS[g.basis] || DASH),
      ),
    ),
    parts.length
      ? el(
          "table",
          { class: "grade-parts" },
          el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Part (weight)"), el("th", { scope: "col", class: "num" }, "Value"), el("th", { scope: "col" }, `Percentile among FBS ${group}`))),
          el(
            "tbody",
            {},
            parts.map((p) =>
              el(
                "tr",
                {},
                el("th", { scope: "row" }, p.label, isNum(p.weight) ? el("span", { class: "grade-weight" }, `${Math.round(p.weight * 100)}%`) : null), // the name as the cell's own text, so its hint matches
                el("td", { class: "num" }, partValue(p)),
                el("td", {}, bar(p.percentile)),
              ),
            ),
          ),
        )
      : null,
    el("p", { class: "grade-block__fine" }, volumeLine ? `${volumeLine} ` : "", el("span", { class: "hint-term" }, "How grades work")),
  );
}

/** A list of graded players (the Leaders board, players to watch): position rank, player, grade, team. Rows are the
 *  server's public grades; ours are marked. onTap(row) opens the player. */
export function gradedTable(rows, { onTap, us, showTeam = true, caption = "Stat grades" } = {}) {
  const shown = (Array.isArray(rows) ? rows : []).filter((r) => r && typeof r === "object" && typeof r.playerId === "string").map((r) => ({ ...r, gradeValue: gradeValue(r), isUs: Boolean(us) && r.team === us }));
  const columns = [
    // Phase 17 #22: the rank is among FBS players at the position, so it says so (a bare "#8" read as a jersey
    // number), and the grade's word ("Very good") lives in the chip's title, not a column repeating the number
    { key: "rank", label: "Pos. rank", kind: "rank", stick: true },
    { key: "name", label: "Player", kind: "text", sub: "position", stick: true },
    { key: "gradeValue", label: "Grade", render: (r) => gradeChip(r) }, // before the team, so a phone shows it without scrolling
    ...(showTeam ? [{ key: "team", label: "Team", kind: "text", team: true }] : []),
  ];
  return statTable({ compact: true, columns, rows: shown, sort: { key: "gradeValue", dir: "descending" }, rowClass: (r) => (r.isUs ? "is-us" : null), onRowTap: typeof onTap === "function" ? onTap : undefined, caption });
}
