// Win probability (L8) as one quiet line, and the last-play success readout (L13).
// The chart is our chance, whichever side of the ball the source reports.

import { usLabel } from "../identity.js";
import { DASH, el, fmtPct, isNum, text } from "./dom.js";

const W = 600;
const H = 120;
const PAD = { top: 6, right: 6, bottom: 16, left: 6 };

function svgEl(tag, attrs = {}, ...children) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  for (const child of children.flat(Infinity)) if (child) node.append(child);
  return node;
}

/** Turn the source series into our probability per play, dropping malformed points. */
export function usSeries(series, homeIsUs) {
  if (!Array.isArray(series)) return [];
  return series
    .map((point) => (point && isNum(point.homeWp) ? (homeIsUs ? point.homeWp : 1 - point.homeWp) : null))
    .filter((v) => isNum(v))
    .map((v) => Math.min(1, Math.max(0, v)));
}

/**
 * winProbabilityChart({ series: [{play, homeWp}], homeIsUs, usAbbr, pregame, final })
 * `pregame` is our chance at kickoff (0 to 1) when known.
 */
export function winProbabilityChart({ series = [], homeIsUs = true, usAbbr = usLabel(), pregame, final = false }) {
  const values = usSeries(series, homeIsUs);
  const current = values.length ? values[values.length - 1] : null;
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const x = (i) => PAD.left + (values.length > 1 ? (i / (values.length - 1)) * innerW : innerW / 2);
  const y = (v) => PAD.top + (1 - v) * innerH;

  const path = values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = values.length ? `${path} L${x(values.length - 1).toFixed(1)},${y(0).toFixed(1)} L${x(0).toFixed(1)},${y(0).toFixed(1)} Z` : "";

  const svg = svgEl(
    "svg",
    { class: "wp__svg", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Win probability for ${usAbbr}, ${values.length} plays` },
    svgEl("rect", { class: "wp__frame", x: PAD.left, y: PAD.top, width: innerW, height: innerH }),
    svgEl("line", { class: "wp__mid", x1: PAD.left, x2: PAD.left + innerW, y1: y(0.5), y2: y(0.5) }),
    values.length ? svgEl("path", { class: "wp__area", d: area }) : null,
    values.length ? svgEl("path", { class: "wp__line", d: path }) : null,
    values.length ? svgEl("circle", { class: "wp__dot", cx: x(values.length - 1), cy: y(current), r: 3 }) : null,
    svgEl("text", { class: "wp__axis", x: PAD.left, y: H - 4 }, "Kickoff"),
    svgEl("text", { class: "wp__axis", x: PAD.left + innerW, y: H - 4, "text-anchor": "end" }, final ? "Final" : "Now"),
    svgEl("text", { class: "wp__axis", x: PAD.left + 4, y: y(0.5) - 3 }, "50%"),
  );

  return el(
    "div",
    { class: "wp" },
    el(
      "div",
      { class: "wp__head" },
      el("div", { class: "wp__now" }, isNum(current) ? fmtPct(current) : DASH, el("small", {}, `${text(usAbbr)} ${final ? "final" : "to win"}`)),
      isNum(pregame) ? el("div", { class: "wp__pre" }, "At kickoff ", el("b", {}, fmtPct(pregame))) : null,
    ),
    svg,
  );
}

export function winProbabilitySkeleton() {
  return el("div", { class: "wp" }, el("div", { class: "skel", style: { width: "120px", height: "30px" } }), el("div", { class: "skel skel--block" }));
}

/**
 * Judge one play by the standard success rule: half the distance on first down, 70% on second,
 * all of it on third and fourth. Touchdowns always succeed. Returns true, false, or null (not judged).
 */
export function playSuccess(play) {
  if (!play) return null;
  if (typeof play.success === "boolean") return play.success;
  const { down, distance, yardsGained } = play;
  const type = String(play.playType || "").toLowerCase();
  if (!isNum(down) || !isNum(distance) || !isNum(yardsGained)) return null;
  if (/kickoff|punt|field goal|timeout|penalty|end of|extra point/.test(type)) return null;
  if (play.scoring && type.includes("touchdown")) return true;
  const needed = ({ 1: 0.5, 2: 0.7 }[down] ?? 1) * distance;
  return yardsGained >= needed;
}

/**
 * successRow({ play, offenseAbbr, us: {abbr, rate, counts}, them: {abbr, rate, counts}, source })
 * `play` is the newest play with a verdict. Rates are 0 to 1; counts are {successes, judged} and
 * show as "n of m" only when both are numbers (CFBD's own rate carries none). `source` names
 * where the rates come from ("CFBD") and is shown beside them when given.
 */
export function successRow({ play, offenseAbbr, us, them, source } = {}) {
  play = play && typeof play === "object" ? play : null;
  us = us && typeof us === "object" ? us : {};
  them = them && typeof them === "object" ? them : {};
  const verdict = playSuccess(play);
  const verdictEl =
    verdict === true
      ? el("span", { class: "verdict verdict--yes" }, "✓ Success")
      : verdict === false
        ? el("span", { class: "verdict verdict--no" }, "✗ Failed")
        : el("span", { class: "verdict verdict--na" }, "Not judged");
  const rateEl = (side, kind) =>
    el(
      "span",
      { class: `success__rate success__rate--${kind}` },
      `${text(side.abbr)} ${isNum(side.rate) ? fmtPct(side.rate) : DASH}`,
      isNum(side.counts?.successes) && isNum(side.counts?.judged) ? el("small", {}, `${side.counts.successes} of ${side.counts.judged}`) : null,
    );
  const situation = play && isNum(play.down) && isNum(play.distance) ? `${text(offenseAbbr)} ${play.down} & ${play.distance}` : text(offenseAbbr);
  return el(
    "div",
    { class: "success" },
    el("div", { class: "success__label" }, "Last play"),
    el("div", { class: "success__play" }, el("p", {}, play ? text(play.text) : "No scrimmage play yet."), play ? el("small", {}, `${situation}${isNum(play.yardsGained) ? ` · ${play.yardsGained} yds` : ""}`) : null),
    verdictEl,
    el("div", { class: "success__rates" }, source ? el("span", { class: "success__source" }, `Success rate, ${text(source)}`) : null, rateEl(us, "us"), rateEl(them, "them")),
  );
}
