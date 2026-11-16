// The whole field (ENH-17, the owner's board of 2026-10-30 "Build it as
// drawn"): on every team list a rank chip opens, above the list, every team as one dot placed by its value, better to the
// right (a stat where less is better flips, so right is always better), dots that would overlap stacked; us and this
// week's opponent marked larger in our colors with the value and rank; the top quarter and the bottom quarter tinted in
// the chip's own colors; a dashed line at the median; a scale under it with "worse" and "better". A tap on a dot (the
// nearest within reach) scrolls the list to that team's row. Drawn at its box's own width; the dots shrink on a phone.
// Player lists and polls keep no chart (a poll has no value to place, a player list holds hundreds of names).
//
//   fieldChart(data, scale, { onPick })   the block, or null (a player or poll list, fewer than three values, no scale)
//   swarm(xs, { r, gap })                 the vertical offsets that keep dots at these x positions from overlapping,
//                                         in order: 0, then one step down, one up, two down... Exported for the tests.
//   niceTicks(lo, hi, count)              round values for the scale (1, 2 or 5 times a power of ten)

import { el, fmtStat, isNum, ordinal, text } from "./dom.js";

const SVG = "http://www.w3.org/2000/svg";
const PAD = 16;
const TOP = 40; // the labels' room above the dots
const DEFAULT_WIDTH = 520;
const REACH = 14; // how far from a dot a tap still picks it

function svgEl(tag, attrs = {}, ...kids) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  for (const kid of kids) if (kid !== null && kid !== undefined) node.append(typeof kid === "string" ? document.createTextNode(kid) : kid);
  return node;
}

export function swarm(xs, { r = 3.4, gap = 0.6 } = {}) {
  const d = 2 * r + gap;
  const placed = [];
  const out = new Array(xs.length).fill(0);
  const order = xs.map((x, i) => [x, i]).filter(([x]) => isNum(x)).sort((a, b) => a[0] - b[0]);
  for (const [x, i] of order) {
    for (let k = 0; k < 60; k += 1) {
      const y = k === 0 ? 0 : (k % 2 ? 1 : -1) * Math.ceil(k / 2) * d;
      if (!placed.some((p) => Math.abs(p.x - x) < d && Math.abs(p.y - y) < d - 0.01)) {
        out[i] = y;
        placed.push({ x, y });
        break;
      }
    }
  }
  return out;
}

export function niceTicks(lo, hi, count = 5) {
  if (!isNum(lo) || !isNum(hi) || hi <= lo) return [];
  const raw = (hi - lo) / Math.max(1, count);
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * power).reduce((best, s) => (Math.abs(Math.log(s / raw)) < Math.abs(Math.log(best / raw)) ? s : best)); // the round step nearest the wanted one
  const out = [];
  for (let k = Math.ceil(lo / step - 1e-9); k * step <= hi + step * 1e-9; k += 1) out.push(Number((k * step).toPrecision(12)));
  return out;
}

function teamName(row) {
  return typeof row.team === "string" && row.team.trim() ? row.team.trim() : null;
}

function shortName(row) {
  const abbr = typeof row.abbreviation === "string" && row.abbreviation.trim() ? row.abbreviation.trim() : null;
  return abbr || teamName(row) || "";
}

function rankWords(row) {
  return isNum(row.rank) ? `${row.tied === true ? "T" : ""}${ordinal(row.rank)}` : null;
}

function draw(rows, scale, d, width) {
  const w = isNum(width) && width >= 240 ? Math.round(width) : DEFAULT_WIDTH;
  const r = Math.max(2.4, Math.min(3.4, w / 150));
  const big = r + 2.6;
  const span = w - 2 * PAD;
  const xOf = (v) => PAD + scale.frac(v) * span;
  const xs = rows.map((row) => xOf(row.value));
  const ys = swarm(xs, { r });
  const deepest = Math.max(r * 3, ...ys.map((y) => Math.abs(y) + r));
  const cy = TOP + deepest + 4;
  const axis = cy + deepest + 8;
  const height = Math.round(axis + 38);
  const format = typeof d.format === "string" ? d.format : "2f";
  const svg = svgEl("svg", { class: "fc__svg", viewBox: `0 0 ${w} ${height}`, width: w, height });
  // the quarters: the zone spans from the edge to the last dot inside it
  const ranked = rows.map((row, i) => ({ row, x: xs[i] })).sort((a, b) => b.x - a.x);
  const quarter = Math.max(1, Math.ceil(ranked.length / 4));
  if (ranked.length >= 8) {
    const topEdge = ranked[quarter - 1].x - r - 2;
    const lowEdge = ranked[ranked.length - quarter].x + r + 2;
    svg.append(
      svgEl("rect", { class: "fc__zone fc__zone--top", x: topEdge.toFixed(1), y: TOP, width: (w - PAD - topEdge).toFixed(1), height: (axis - TOP - 4).toFixed(1) }),
      svgEl("rect", { class: "fc__zone fc__zone--low", x: PAD, y: TOP, width: Math.max(0, lowEdge - PAD).toFixed(1), height: (axis - TOP - 4).toFixed(1) }),
      svgEl("text", { class: "fc__zone-words fc__zone-words--low", x: PAD + 4, y: axis - 8 }, "bottom quarter"),
      svgEl("text", { class: "fc__zone-words fc__zone-words--top", x: w - PAD - 4, y: axis - 8, "text-anchor": "end" }, "top quarter"),
    );
  }
  if (isNum(scale.medianFrac)) {
    const mx = (PAD + scale.medianFrac * span).toFixed(1);
    svg.append(svgEl("line", { class: "fc__median", x1: mx, x2: mx, y1: TOP + 4, y2: axis - 4 }), svgEl("text", { class: "fc__median-words", x: mx, y: TOP, "text-anchor": "middle" }, "median"));
  }
  const field = svgEl("g", { class: "fc__field" });
  const marked = [];
  rows.forEach((row, i) => {
    const kind = row.isUs === true ? "us" : row.isNext === true ? "next" : null;
    if (kind) {
      marked.push({ row, kind, x: xs[i], y: cy + ys[i] });
      return;
    }
    field.append(svgEl("circle", { class: "fc__dot", cx: xs[i].toFixed(1), cy: (cy + ys[i]).toFixed(1), r: r.toFixed(1) }, svgEl("title", {}, `${text(teamName(row))} ${fmtStat(row.value, format)}${rankWords(row) ? `, ${rankWords(row)}` : ""}`)));
  });
  svg.append(field);
  // us and this week's opponent: on top, larger, each with its value and rank above; a second label row when they meet
  marked.sort((a, b) => (a.kind === "us" ? 1 : 0) - (b.kind === "us" ? 1 : 0));
  const labelled = [];
  for (const m of marked) {
    const words = `${shortName(m.row)} ${fmtStat(m.row.value, format)}${rankWords(m.row) ? ` · ${rankWords(m.row)}` : ""}`;
    const near = labelled.some((l) => Math.abs(l.x - m.x) < 120);
    const ly = near ? 12 : 26;
    const anchor = m.x < PAD + 60 ? "start" : m.x > w - PAD - 60 ? "end" : "middle";
    labelled.push({ x: m.x });
    svg.append(
      svgEl("line", { class: `fc__lead fc__lead--${m.kind}`, x1: m.x.toFixed(1), x2: m.x.toFixed(1), y1: (ly + 4).toFixed(1), y2: (m.y - big).toFixed(1) }),
      svgEl("circle", { class: `fc__dot fc__dot--${m.kind}`, cx: m.x.toFixed(1), cy: m.y.toFixed(1), r: big.toFixed(1) }, svgEl("title", {}, words)),
      svgEl("text", { class: "fc__label", x: m.x.toFixed(1), y: ly, "text-anchor": anchor }, words),
    );
  }
  // the scale: round values placed where they fall, so a list where less is better reads right to left
  svg.append(svgEl("line", { class: "fc__axis", x1: PAD, x2: w - PAD, y1: axis, y2: axis }));
  for (const v of niceTicks(Math.min(scale.lo, scale.hi), Math.max(scale.lo, scale.hi), w < 400 ? 3 : 5)) {
    const x = xOf(v);
    if (x < PAD - 0.5 || x > w - PAD + 0.5) continue;
    svg.append(svgEl("line", { class: "fc__axis", x1: x.toFixed(1), x2: x.toFixed(1), y1: axis, y2: axis + 4 }), svgEl("text", { class: "fc__tick", x: x.toFixed(1), y: axis + 18, "text-anchor": "middle" }, fmtStat(v, Number.isInteger(v) && ["1f", "2f", "3f", "4f"].includes(format) ? "0f" : format)));
  }
  svg.append(svgEl("text", { class: "fc__end", x: PAD, y: axis + 34 }, "worse"), svgEl("text", { class: "fc__end", x: w - PAD, y: axis + 34, "text-anchor": "end" }, "better →"));
  return { svg, points: rows.map((row, i) => ({ team: teamName(row), x: xs[i], y: cy + ys[i] })) };
}

export function fieldChart(data, scale, { onPick } = {}) {
  const d = data && typeof data === "object" ? data : {};
  if (!scale || typeof scale.frac !== "function" || d.unit === "player" || d.family === "poll") return null;
  const rows = (Array.isArray(d.rows) ? d.rows : []).filter((row) => row && typeof row === "object" && isNum(row.value) && teamName(row));
  if (rows.length < 3) return null;
  const format = typeof d.format === "string" ? d.format : "2f";
  const us = rows.find((row) => row.isUs === true);
  const them = rows.find((row) => row.isNext === true && row.isUs !== true);
  const spoken = [us, them].filter(Boolean).map((row) => `${text(teamName(row))} ${fmtStat(row.value, format)}${rankWords(row) ? `, ${rankWords(row)}` : ""}`);
  if (isNum(scale.median)) spoken.push(`the median ${fmtStat(scale.median, format)}`);
  const holder = el("div", { class: "fc__chart", role: "img", "aria-label": `Every team as a dot, better to the right${spoken.length ? `: ${spoken.join("; ")}` : ""}.` });
  let drawn = 0;
  let points = [];
  const paint = (width) => {
    const w = isNum(width) && width >= 240 ? Math.round(width) : DEFAULT_WIDTH;
    if (Math.abs(w - drawn) < 4) return;
    drawn = w;
    try {
      const out = draw(rows, scale, d, w);
      points = out.points;
      holder.replaceChildren(out.svg);
    } catch (error) {
      console.error("The field chart could not be drawn; the list under it stays.", error);
      holder.replaceChildren();
    }
  };
  paint(DEFAULT_WIDTH);
  if (typeof ResizeObserver === "function") {
    new ResizeObserver((entries) => {
      const box = entries?.[0]?.contentRect;
      if (box && box.width > 0) paint(box.width);
    }).observe(holder);
  }
  holder.addEventListener("click", (event) => {
    if (typeof onPick !== "function" || !points.length) return;
    const svg = holder.querySelector("svg");
    const box = svg && typeof svg.getBoundingClientRect === "function" ? svg.getBoundingClientRect() : null;
    if (!box || !box.width) return;
    const sx = drawn / box.width;
    const px = (event.clientX - box.left) * sx;
    const py = (event.clientY - box.top) * sx;
    let best = null;
    for (const p of points) {
      const dist = Math.hypot(p.x - px, p.y - py);
      if (dist <= REACH && (!best || dist < best.dist)) best = { team: p.team, dist };
    }
    if (best) onPick(best.team);
  });
  const what = d.scope === "conference" ? "every team in the conference" : "every FBS team";
  return el("div", { class: "fc" }, el("p", { class: "fc__sub" }, `${what}, one dot · tap a dot for its row`), holder);
}
