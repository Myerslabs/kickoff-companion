// A pie chart, hand-drawn SVG, no library (owner 2026-10-16: "make it a pie chart instead of a list" for where a
// recruiting class is from; "do all states, make the chart bigger if room is needed"). Every slice is drawn, largest
// first from 12 o'clock, clockwise, with a 2 px gap of the panel between slices. A tap or a hover on a slice, or on its
// legend chip, says its name, value and share on the line under the pie; the legend names every slice with its value
// and share, so no slice is known by its color alone (past the few named hues the colors repeat as gray).
//
//   pieChart({ slices, label, unit, size })  -> element
//       slices: [{ key, label, short, value, color }], value > 0 (others are left out); color is any CSS color, usually
//       a token (var(--team-us)); label names it in words, short (a state's code) on the chip. unit: ["commit", "commits"].
//       size: the largest the pie is drawn, in px (it shrinks with its column).
//   arcPath(cx, cy, r, start, end)  one slice's path, angles in radians from 12 o'clock, clockwise (exported for the tests)

import { el, fmtPct, isNum, str, text } from "./dom.js";

const SVG = "http://www.w3.org/2000/svg";
const BOX = 200;
const R = 96;

function svgEl(tag, attrs = {}) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  return node;
}

const round = (n) => Math.round(n * 100) / 100;

export function arcPath(cx, cy, r, start, end) {
  const x0 = round(cx + r * Math.sin(start));
  const y0 = round(cy - r * Math.cos(start));
  const x1 = round(cx + r * Math.sin(end));
  const y1 = round(cy - r * Math.cos(end));
  const large = end - start > Math.PI ? 1 : 0;
  return `M ${cx} ${cy} L ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1} Z`;
}

/** The slices worth drawing: a positive value and a name, largest first (ties by name, so the order never jumps). */
export function cleanSlices(slices) {
  return (Array.isArray(slices) ? slices : [])
    .filter((s) => s && typeof s === "object" && isNum(s.value) && s.value > 0 && (str(s.label) || str(s.short)))
    .map((s) => ({ key: String(s.key ?? s.label ?? s.short), label: str(s.label) ? s.label.trim() : s.short.trim(), short: str(s.short) ? s.short.trim() : null, value: s.value, color: str(s.color) ? s.color : "var(--pie-other)" }))
    .sort((a, b) => b.value - a.value || a.label.localeCompare(b.label));
}

export function pieChart({ slices, label = "Pie chart", unit = ["item", "items"], size = 280 } = {}) {
  const list = cleanSlices(slices);
  const total = list.reduce((sum, s) => sum + s.value, 0);
  const [one, many] = Array.isArray(unit) && unit.length === 2 ? unit : ["item", "items"];
  const words = (s) => `${s.label}: ${s.value} ${s.value === 1 ? one : many}, ${fmtPct(total ? s.value / total : null)}`;
  if (!list.length || !total) return null;

  const svg = svgEl("svg", { class: "pie__svg", viewBox: `0 0 ${BOX} ${BOX}`, role: "img", "aria-label": `${label}. ${list.map(words).join("; ")}.` });
  const marks = new Map();
  let at = 0;
  for (const slice of list) {
    const sweep = (slice.value / total) * Math.PI * 2;
    const mark = list.length === 1
      ? svgEl("circle", { class: "pie__slice", cx: BOX / 2, cy: BOX / 2, r: R })
      : svgEl("path", { class: "pie__slice", d: arcPath(BOX / 2, BOX / 2, R, at, at + sweep) });
    mark.setAttribute("style", `fill: ${slice.color}`);
    mark.dataset.key = slice.key;
    const title = svgEl("title");
    title.textContent = words(slice);
    mark.append(title);
    svg.append(mark);
    marks.set(slice.key, mark);
    at += sweep;
  }

  const info = el("p", { class: "pie__info", "aria-live": "polite" });
  const chips = new Map();
  const legend = el(
    "ul",
    { class: "pie__legend", "aria-label": `${label}, every slice` },
    list.map((slice) => {
      const chip = el(
        "button",
        { class: "pie__chip", type: "button", title: words(slice), "aria-pressed": "false", onclick: () => select(slice.key) },
        el("span", { class: "pie__swatch", style: `background: ${slice.color}`, "aria-hidden": "true" }),
        el("span", { class: "pie__name" }, text(slice.short || slice.label)),
        el("span", { class: "pie__value" }, `${slice.value} · ${fmtPct(slice.value / total)}`),
      );
      chips.set(slice.key, chip);
      return el("li", {}, chip);
    }),
  );

  function select(key) {
    const slice = list.find((s) => s.key === key) || list[0];
    info.textContent = words(slice);
    for (const [k, mark] of marks) mark.classList.toggle("is-dim", k !== slice.key);
    for (const [k, chip] of chips) chip.setAttribute("aria-pressed", k === slice.key ? "true" : "false");
  }
  for (const [key, mark] of marks) {
    mark.addEventListener("click", () => select(key));
    mark.addEventListener("mouseenter", () => select(key));
  }
  info.textContent = words(list[0]); // the largest slice says itself until another is picked; nothing dims yet

  return el("figure", { class: "pie", style: `--pie-size: ${Math.max(140, Math.round(size))}px` }, el("div", { class: "pie__plot" }, svg), info, legend);
}
