// A trend sparkline: the last N games, current value labelled. Hand-drawn SVG, no library.

import { el, fmtStat, isNum, text } from "./dom.js";

const SVG = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs = {}) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  return node;
}

/**
 * sparkline({ values, width, height, them, results, avg }) returns an <svg>. Null points are skipped.
 * G3-12 (owner look): with `results` ("W"/"L" per game, aligned by index with the UNFILTERED values, so a
 * skipped game keeps its place) each point is a filled dot for a win and a hollow one for a loss; with `avg`,
 * a dashed line at the season average. Results whose length differs from the values draw no dots.
 */
export function sparkline({ values = [], width = 96, height = 28, them = false, results = null, avg = null }) {
  const raw = Array.isArray(values) ? values : [];
  const kept = raw.map((v, k) => [v, k]).filter(([v]) => isNum(v));
  const points = kept.map(([v]) => v);
  const svg = svgEl("svg", { class: "spark", viewBox: `0 0 ${width} ${height}`, width, height, "aria-hidden": "true" });
  if (points.length === 0) return svg;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const pad = 3;
  const step = points.length > 1 ? (width - pad * 2) / (points.length - 1) : 0;
  const coords = points.map((v, i) => [pad + i * step, height - pad - ((v - min) / span) * (height - pad * 2)]);
  if (coords.length > 1) {
    const d = coords.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
    svg.append(svgEl("path", { class: `spark__line${them ? " spark__line--them" : ""}`, d }));
  }
  if (isNum(avg) && coords.length > 1) {
    const ay = (height - pad - ((Math.min(max, Math.max(min, avg)) - min) / span) * (height - pad * 2)).toFixed(1);
    svg.append(svgEl("line", { class: "spark__avg", x1: pad, y1: ay, x2: width - pad, y2: ay }));
  }
  const marks = Array.isArray(results) && results.length === raw.length ? results : null;
  if (marks) {
    coords.forEach(([x, y], i) => {
      const res = marks[kept[i][1]];
      if (res !== "W" && res !== "L") return;
      svg.append(svgEl("circle", { class: `spark__res spark__res--${res === "W" ? "w" : "l"}`, cx: x.toFixed(1), cy: y.toFixed(1), r: 2.5 }));
    });
    return svg;
  }
  const [lx, ly] = coords[coords.length - 1];
  svg.append(svgEl("circle", { class: "spark__dot", cx: lx.toFixed(1), cy: ly.toFixed(1), r: 3 }));
  return svg;
}

/** One more decimal for an average than the stat itself shows ("24" games average "31.2"). */
const AVG_FORMAT = { "0f": "1f", "+0f": "+1f", "1f": "1f", "+1f": "+1f", "2f": "2f", "+2f": "+2f", pct: "pct" };

/** The average of the finite values, or null. Exported for the tests. */
export function average(values) {
  const points = (Array.isArray(values) ? values : []).filter(isNum);
  return points.length ? points.reduce((sum, v) => sum + v, 0) / points.length : null;
}

/**
 * trendRow({ label, values, format, them, key }): label, sparkline, and the last game's value captioned
 * "last" with the season average beside it (G3-12), so the number never reads as an average. Nulls in
 * values (a box score that did not load) are skipped. With fewer than two games the line's cell says
 * when it appears.
 */
export function trendRow({ label, values = [], format = "0f", them = false, key, results = null } = {}) {
  const points = (Array.isArray(values) ? values : []).filter(isNum);
  const current = points.length ? points[points.length - 1] : null;
  const avg = average(points);
  return el(
    "div",
    { class: "trend" },
    el("span", { class: "trend__label" }, text(label)),
    points.length >= 2 ? sparkline({ values: Array.isArray(values) ? values : [], them, results, avg }) : el("span", { class: "trend__wait" }, "Trend after game 2"),
    el(
      "span",
      { class: "trend__value" },
      el("b", { "data-k": key ? `trend:${key}` : null }, fmtStat(current, format)),
      el("small", { class: "trend__cap" }, "last"),
      points.length >= 2 ? el("small", { class: "trend__avg" }, `avg ${fmtStat(avg, AVG_FORMAT[format] || format)}`) : null,
    ),
  );
}

export function trendSkeleton(rows = 4) {
  return el("div", {}, Array.from({ length: rows }, () => el("div", { class: "skel skel--bar" })));
}

// --- GX-06 rank paths (owner look) -------------------------------------------------------------------

/**
 * The y of a rank on an inverted scale: #1 at the top, #max at the bottom, clamped. Exported for the tests.
 */
export function rankY(rank, { height = 20, max = 25, pad = 2 } = {}) {
  if (!isNum(rank)) return null;
  const r = Math.min(max, Math.max(1, rank));
  return pad + ((r - 1) / Math.max(1, max - 1)) * (height - pad * 2);
}

/**
 * rankPath(path, { width = 72, height = 20, max = 25, label }): a poll rank week by week, inverted so #1 is at
 * the top, the line broken where the team was unranked (a gap, never a drop to the bottom). An isolated week
 * is a dot; the latest ranked week carries the end dot. Null when the team was never ranked.
 */
export function rankPath(path, { width = 72, height = 20, max = 25, label = "AP" } = {}) {
  const weeks = Array.isArray(path) ? path.map((v) => (isNum(v) && v >= 1 ? v : null)) : [];
  if (!weeks.some(isNum)) return null;
  const pad = 2;
  const step = weeks.length > 1 ? (width - pad * 2) / (weeks.length - 1) : 0;
  const at = (i) => (weeks.length > 1 ? pad + i * step : width / 2);
  const svg = svgEl("svg", { class: "rankpath", viewBox: `0 0 ${width} ${height}`, width, height, "aria-hidden": "true" });
  let run = [];
  const flush = () => {
    if (run.length > 1) svg.append(svgEl("path", { class: "rankpath__line", d: run.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ") }));
    else if (run.length === 1) svg.append(svgEl("circle", { class: "rankpath__pt", cx: run[0][0].toFixed(1), cy: run[0][1].toFixed(1), r: 1.5 }));
    run = [];
  };
  weeks.forEach((rank, i) => {
    if (rank === null) flush();
    else run.push([at(i), rankY(rank, { height, max, pad })]);
  });
  flush();
  const last = weeks.reduce((found, rank, i) => (rank !== null ? i : found), -1);
  svg.append(svgEl("circle", { class: "rankpath__dot", cx: at(last).toFixed(1), cy: rankY(weeks[last], { height, max, pad }).toFixed(1), r: 2.5 }));
  const words = weeks.map((rank) => (rank === null ? "unranked" : String(rank))).join(", ");
  return el("span", { class: "rankpath-wrap", role: "img", "aria-label": `${text(label)} rank by week: ${words}`, title: `${text(label)} by week: ${words}` }, svg);
}

/**
 * eloLine(eloPath, { width = 96, height = 24 }): a team's Elo since week 1 (the pregame rating of the first
 * game, then each postgame rating) with today's value. Null without a finite point.
 */
export function eloLine(eloPath, { width = 96, height = 24 } = {}) {
  const p = eloPath && typeof eloPath === "object" ? eloPath : {};
  const points = (Array.isArray(p.points) ? p.points : []).filter((g) => g && typeof g === "object");
  const values = [];
  if (points.length && isNum(points[0].pre)) values.push(points[0].pre);
  for (const g of points) if (isNum(g.post)) values.push(g.post);
  const current = isNum(p.current) ? p.current : values.length ? values[values.length - 1] : null;
  if (!isNum(current)) return null;
  return el(
    "span",
    { class: "elo-line", title: values.length > 1 ? `Elo by game: ${values.map((v) => Math.round(v)).join(", ")}` : null },
    values.length > 1 ? sparkline({ values, width, height }) : null,
    el("b", { class: "elo-line__val" }, String(Math.round(current))),
  );
}
