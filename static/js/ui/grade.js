// Stat grades (public release Phase 7): our own 0 to 100 grade from CFBD's season stats, compared with FBS
// players at the same position. The server builds them (app/services/grades.py); this draws them.
//   gradeChip(grade)   a small number chip tinted by its band, or a dash with the reason as its title.
//   gradeBlock(grade)  the player page's breakdown: the grade, its label, its rank, what it is based on,
//                      each part with its value and percentile, and the volume it needed. Tables wave 3 (owner
//                      2026-10-10): the parts are a sized stat table (Part | Weight | Value | Percentile), the weight in
//                      its own column (rule 3), the part names shortening by size (ui/sizes.js), the bar at every size.
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

/** A part's weight as a whole percent ("20%": a set share, not a measured rate); a dash when it has none. */
function weightText(part) {
  const w = obj(part).weight;
  return isNum(w) && w >= 0 && w <= 1 ? `${Math.round(w * 100)}%` : DASH;
}

/** The parts table (wave 3): every part in its own row, in the server's weight order (never sorted: the parts are stat
 *  names), each data point in its own column. Large: the part's whole name, its weight, its value and the percentile among
 *  FBS players at the position, a bar and its number; medium: the middle names and "Percentile"; small: the short names
 *  ("Y/A", "Adj pass"), the value and the bar under "Pctl", the weight gone. Exported for the tests. */
export function gradeParts(parts, group) {
  const rows = (Array.isArray(parts) ? parts : []).filter((c) => c && typeof c === "object" && typeof c.label === "string" && c.label.trim());
  if (!rows.length) return null;
  const who = typeof group === "string" && group.trim() ? group.trim() : "players at the position";
  const columns = [
    { key: "label", label: "Part", kind: "text", term: "Part (weight)" }, // the head opens the grade's entry, as "Part (weight)" did
    { key: "weight", label: "Weight", size: "medium", render: weightText },
    { key: "value", label: "Value", render: partValue },
    { key: "percentile", label: `Percentile among FBS ${who}`, labelMid: "Percentile", labelShort: "Pctl", term: "Percentile", render: (part) => percentileBar(part.percentile) },
  ];
  const wrap = statTable({ compact: true, sizes: true, sortable: false, columns, rows, caption: "Grade parts" });
  wrap.classList.add("grade-parts");
  return wrap;
}

/** A percentile's thin bar in the rank chips' colors with the number outside it; "no number" when there is none. */
function percentileBar(pct) {
  if (!isNum(pct)) return el("span", { class: "note" }, "no number");
  const clamped = Math.max(0, Math.min(100, pct));
  return el(
    "span",
    { class: "grade-bar" },
    el("span", { class: "grade-bar__track", "aria-hidden": "true" }, el("span", { class: `grade-bar__fill grade-bar__fill--${percentileTone(clamped)}`, style: { width: `${clamped}%` } })),
    el("span", { class: "grade-bar__n" }, String(Math.round(clamped))),
  );
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
  // Phase 17 #18 (owner-approved mockup): the grade and its basis in one header; each part with its weight, its value, and a
  // thin bar in the rank chips' colors with the number outside (wave 3: the weight in its own column, gradeParts); one line
  // of fine print
  const rank = isNum(g.rank) && isNum(g.of) ? `#${g.rank} of ${g.of} FBS ${text(g.groupName)}` : null;
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
    gradeParts(parts, g.groupName),
    el("p", { class: "grade-block__fine" }, volumeLine ? `${volumeLine} ` : "", el("span", { class: "hint-term" }, "How grades work")),
  );
}

/** A list of graded players (the Leaders board's Top graded, the program's Players to watch): player, grade, position
 *  rank, team. Rows are the server's public grades; ours are marked. onTap(row) opens the player.
 *  Table sizes, wave 2 (owner 2026-10-10): the player first, so his name always shows; it sizes itself by its own box:
 *  large and medium every column and the full name, small the surname and the grade (no chips at small).
 *  Wave 3 (owner decision 1, 2026-10-10): the position is its own column after the name at large and medium, gone at
 *  small; the team shows at every size, its abbreviation (teamAbbr, still its link) at small. The name steps down with the
 *  table (item 6, owner 2026-10-11, ui/dom.js playerNames): whole at large, then "A. Passer" (at large first, so the
 *  Pre-Game Program's Players to watch on the iPad keeps its position rank), the surname and the reduced surname at small. */
export function gradedTable(rows, { onTap, us, showTeam = true, caption = "Stat grades" } = {}) {
  const shown = (Array.isArray(rows) ? rows : []).filter((r) => r && typeof r === "object" && typeof r.playerId === "string").map((r) => ({ ...r, gradeValue: gradeValue(r), isUs: Boolean(us) && r.team === us }));
  const columns = [
    { key: "name", label: "Player", kind: "text", sub: "position", subLabel: "Pos", person: true },
    { key: "gradeValue", label: "Grade", render: (r) => gradeChip(r) },
    // Phase 17 #22: the rank is among FBS players at the position, so it says so (a bare "#8" read as a jersey number),
    // its chip toned by the quartile with "N of M" as its title; the grade's word ("Very good") lives in the grade chip's title
    { key: "rank", label: "Pos. rank", kind: "rank", of: "of", size: "medium" },
    ...(showTeam ? [{ key: "team", label: "Team", kind: "text", team: true, shortKey: "teamAbbr" }] : []), // the abbreviation at small (the server's teamAbbr)
  ];
  return statTable({ compact: true, sizes: true, columns, rows: shown, sort: { key: "gradeValue", dir: "descending" }, rowClass: (r) => (r.isUs ? "is-us" : null), onRowTap: typeof onTap === "function" ? onTap : undefined, caption });
}
