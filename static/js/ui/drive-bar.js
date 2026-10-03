// The drive bar: every drive on a 100-yard strip. our goal line on the left, the opponent's on
// the right, so our drives move right and opponent drives move left.

import { el, fmtClock, fmtDuration, isNum, period, text } from "./dom.js";

const SCORES = new Set(["TD", "FG", "RUSHING TD", "PASSING TD"]);
const TURNOVERS = new Set(["INT", "FUMBLE", "DOWNS", "INT TD", "FUMBLE TD", "FUMBLE RETURN TD", "MISSED FG", "TURNOVER ON DOWNS"]);

function outcomeClass(result) {
  const key = String(result || "").toUpperCase();
  if (SCORES.has(key)) return "drive__outcome--score";
  if (TURNOVERS.has(key)) return "drive__outcome--turnover";
  return "";
}

function pct(value) {
  return `${Math.max(0, Math.min(100, value))}%`;
}

/**
 * driveRow({ drive, us: {name, abbr}, them: {name, abbr}, current, expanded })
 * drive: {offense, startYardsToGoal, endYardsToGoal, plays, yards, result, period, startClock, elapsedSeconds}
 */
export function driveRow({ drive, us, them, current = false, expanded = false }) {
  const isUs = drive.offense === us.name;
  const start = isNum(drive.startYardsToGoal) ? drive.startYardsToGoal : null;
  const end = isNum(drive.endYardsToGoal) ? drive.endYardsToGoal : start;
  const field = el("div", { class: "field", "aria-hidden": "true" });
  if (start !== null && end !== null) {
    const x1 = isUs ? 100 - start : start;
    const x2 = isUs ? 100 - end : end;
    const left = Math.min(x1, x2);
    const width = Math.abs(x2 - x1);
    field.append(el("div", { class: `field__bar field__bar--${isUs ? "us" : "them"}`, style: { left: pct(left), width: pct(Math.max(width, 0.8)) } }));
    field.append(el("div", { class: "field__end", style: { left: `calc(${pct(x2)} - 2px)` } }));
  }
  const meta = [isNum(drive.plays) ? `${drive.plays} pl` : null, isNum(drive.yards) ? `${drive.yards} yd` : null, isNum(drive.elapsedSeconds) ? fmtDuration(drive.elapsedSeconds) : null]
    .filter(Boolean)
    .join(" · ");
  const row = el(
    "li",
    { class: `drive${current ? " drive--current" : ""}`, "aria-current": current ? "true" : null },
    el("span", { class: `drive__team${isUs ? "" : " drive__team--them"}` }, text(isUs ? us.abbr : them.abbr)),
    field,
    el(
      "div",
      { class: "drive__result" },
      el("span", { class: `drive__outcome ${outcomeClass(drive.result)}` }, current && !drive.result ? "Now" : text(drive.result)),
      el("span", { class: "drive__meta" }, meta || "–"),
    ),
  );
  if (expanded) {
    const startText = start === null ? "–" : start > 50 ? `own ${100 - start}` : `${text(isUs ? them.abbr : us.abbr)} ${start}`;
    row.append(
      el(
        "div",
        { class: "drive__detail" },
        `${period(drive.period)} ${fmtClock(drive.startClock)} · started at ${startText} · ${isNum(drive.plays) ? drive.plays : "–"} plays for ${isNum(drive.yards) ? drive.yards : "–"} yards${driveEfficiency(drive)}`,
      ),
    );
  }
  return row;
}

/** " · success 3 of 5 · EPA +0.21/play" from the server's per-drive figures (Phase 12), or nothing. */
export function driveEfficiency(drive) {
  const counts = drive?.successCounts;
  const parts = [];
  if (isNum(counts?.made) && isNum(counts?.of) && counts.of > 0) parts.push(`success ${counts.made} of ${counts.of}`);
  if (isNum(drive?.epaPerPlay)) parts.push(`EPA ${drive.epaPerPlay >= 0 ? "+" : ""}${drive.epaPerPlay.toFixed(2)}/play`);
  return parts.length ? ` · ${parts.join(" · ")}` : "";
}

/** driveList({ drives, us, them, currentId, newestFirst }) */
export function driveList({ drives = [], us, them, currentId = null, newestFirst = true }) {
  const ordered = newestFirst ? [...drives].reverse() : [...drives];
  return el(
    "ul",
    { class: "drives" },
    ordered.map((drive, index) => driveRow({ drive, us, them, current: drive.id === currentId, expanded: drive.id === currentId || (currentId === null && index === 0) })),
  );
}

export function driveListSkeleton(rows = 5) {
  return el("div", {}, Array.from({ length: rows }, () => el("div", { class: "skel skel--bar" })));
}
