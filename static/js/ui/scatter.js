// GX-14 (owner look, restrained): every FBS team on one small chart, SP+ offense against SP+ defense.
// 280px square, drawn only at 1100px and wider (the CSS hides it below), inside the SP+ band on Ratings.
// Better offense is to the right, better defense (fewer points) is up. We are the accent-colored dot, the next
// opponent a ring; they are the only two labels. A tap on any dot opens that team (the flyout, or our
// page), through the same "kickoff:team" event every team name uses. Hand-drawn SVG, no library.
//
//   spScatter(rows, { us, next, size = 280 })  rows: [{ team, off, def }] (SP+ offense and defense ratings)
//   scatterScale(rows, { size, pad })           { x(off), y(def), domain } for the tests; null without two teams

import { usSchool } from "../identity.js";
import { el, isNum, text } from "./dom.js";

const SVG = "http://www.w3.org/2000/svg";
const PAD = 14;

function svgEl(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  for (const child of children) if (child !== null && child !== undefined) node.append(typeof child === "string" ? document.createTextNode(child) : child);
  return node;
}

function points(rows) {
  return (Array.isArray(rows) ? rows : []).filter((r) => r && typeof r === "object" && typeof r.team === "string" && r.team.trim() && isNum(r.off) && isNum(r.def));
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** x grows with the offense rating; y grows downward with the defense rating (points allowed), so up is better. */
export function scatterScale(rows, { size = 280, pad = PAD } = {}) {
  const list = points(rows);
  if (list.length < 2) return null;
  const offs = list.map((r) => r.off);
  const defs = list.map((r) => r.def);
  const [x0, x1] = [Math.min(...offs), Math.max(...offs)];
  const [y0, y1] = [Math.min(...defs), Math.max(...defs)];
  const span = size - pad * 2;
  return {
    domain: { off: [x0, x1], def: [y0, y1] },
    x: (v) => pad + ((v - x0) / (x1 - x0 || 1)) * span,
    y: (v) => pad + ((v - y0) / (y1 - y0 || 1)) * span,
  };
}

function openTeam(school) {
  document.dispatchEvent(new CustomEvent("kickoff:team", { detail: school }));
}

export function spScatter(rows, { us = usSchool(), next = null, size = 280 } = {}) {
  const list = points(rows);
  const scale = scatterScale(list, { size });
  if (!scale) return null;
  const svg = svgEl("svg", { class: "scatter__svg", viewBox: `0 0 ${size} ${size}`, width: size, height: size, role: "img", "aria-label": `SP+ offense against defense for ${list.length} teams` });
  const mx = scale.x(median(list.map((r) => r.off)));
  const my = scale.y(median(list.map((r) => r.def)));
  svg.append(
    svgEl("rect", { class: "scatter__frame", x: 0.5, y: 0.5, width: size - 1, height: size - 1 }),
    svgEl("line", { class: "scatter__median", x1: mx.toFixed(1), y1: 4, x2: mx.toFixed(1), y2: size - 4 }),
    svgEl("line", { class: "scatter__median", x1: 4, y1: my.toFixed(1), x2: size - 4, y2: my.toFixed(1) }),
    svgEl("text", { class: "scatter__axis", x: size - 6, y: size - 6, "text-anchor": "end" }, "Better offense"),
    svgEl("text", { class: "scatter__axis", x: 6, y: 12 }, "Better defense"),
  );
  const marked = [];
  for (const row of list) {
    const cx = scale.x(row.off).toFixed(1);
    const cy = scale.y(row.def).toFixed(1);
    const isUs = row.team === us;
    const isNext = !isUs && row.team === next;
    if (isUs || isNext) {
      marked.push({ row, cx, cy, isUs });
      continue;
    }
    svg.append(svgEl("circle", { class: "scatter__dot", cx, cy, r: 2.5 }));
  }
  // the next opponent, then us, over the other dots, each with the chart's only labels
  marked.sort((a, b) => Number(a.isUs) - Number(b.isUs)); // ours drawn last, on top of everything
  for (const { row, cx, cy, isUs } of marked) {
    svg.append(svgEl("circle", { class: isUs ? "scatter__dot scatter__dot--us" : "scatter__ring", cx, cy, r: isUs ? 5 : 5.5 }));
    const right = Number(cx) < size - 70;
    svg.append(svgEl("text", { class: `scatter__label${isUs ? " scatter__label--us" : ""}`, x: (Number(cx) + (right ? 9 : -9)).toFixed(1), y: (Number(cy) + 4).toFixed(1), "text-anchor": right ? "start" : "end" }, text(row.team)));
  }
  // invisible, finger-sized targets over every dot (drawn last so a tap lands on one)
  for (const row of list) {
    const hit = svgEl("circle", { class: "scatter__hit", cx: scale.x(row.off).toFixed(1), cy: scale.y(row.def).toFixed(1), r: 7, tabindex: "-1", "data-team": row.team }, svgEl("title", {}, `${row.team}: offense ${row.off.toFixed(1)}, defense ${row.def.toFixed(1)}`));
    hit.addEventListener("click", (event) => {
      event.stopPropagation();
      openTeam(row.team);
    });
    svg.append(hit);
  }
  return el("figure", { class: "scatter" }, svg, el("figcaption", { class: "scatter__cap" }, "SP+ offense (across) against defense (up is fewer points allowed). Dashed lines are the medians. Tap a dot for that team."));
}
