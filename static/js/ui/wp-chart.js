// Win probability (L8) as one quiet line, and the last-play success readout (L13).
// The chart is our chance, whichever side of the ball the source reports.

import { usLabel } from "../identity.js";
import { DASH, el, fmtPct, isNum, text } from "./dom.js";

const W = 600;
const H = 120;
const QUARTER = 900; // seconds in a quarter
const OT_SLOT = 300; // each overtime period gets a third of a quarter on the axis

function svgEl(tag, attrs = {}, ...children) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  for (const child of children.flat(Infinity)) if (child) node.append(child);
  return node;
}

/** Our probability per point with the point it came from, malformed points dropped. */
function usPoints(series, homeIsUs) {
  if (!Array.isArray(series)) return [];
  return series
    .filter((point) => point && typeof point === "object" && isNum(point.homeWp))
    .map((point) => ({ point, v: Math.min(1, Math.max(0, homeIsUs ? point.homeWp : 1 - point.homeWp)) }));
}

/** Turn the source series into our probability per play, dropping malformed points. */
export function usSeries(series, homeIsUs) {
  return usPoints(series, homeIsUs).map((p) => p.v);
}

/** Seconds of game time gone at a period and a clock ({minutes, seconds} or "M:SS"); null when either is missing. */
export function gameSeconds(period, clock) {
  if (!isNum(period) || period < 1) return null;
  let left = null;
  if (clock && typeof clock === "object" && isNum(clock.minutes) && isNum(clock.seconds)) left = clock.minutes * 60 + clock.seconds;
  else if (typeof clock === "string" && /^\d{1,2}:\d{2}$/.test(clock.trim())) {
    const [m, sec] = clock.trim().split(":").map(Number);
    left = m * 60 + sec;
  }
  if (period > 4) return 4 * QUARTER + (period - 5) * OT_SLOT + OT_SLOT / 2; // overtime has no game clock: the middle of its slot
  if (!isNum(left)) return null;
  return (period - 1) * QUARTER + Math.min(QUARTER, Math.max(0, QUARTER - left));
}

/**
 * The time of each point: its own period and clock (the scoreboard readings), else the play it names (CFBD's
 * post-game model carries a play id). Times never run backwards. Null when too few points have a time; the chart
 * then spaces the points evenly without quarter ticks.
 */
function timesFor(points, plays) {
  const byId = new Map();
  for (const play of Array.isArray(plays) ? plays : []) if (play && typeof play === "object" && play.id !== null && play.id !== undefined) byId.set(String(play.id), play);
  let known = 0;
  let last = 0;
  const times = points.map(({ point }) => {
    let t = gameSeconds(point.period, point.clock);
    if (t === null && point.playId !== null && point.playId !== undefined) {
      const play = byId.get(String(point.playId));
      if (play) t = gameSeconds(play.period, play.clock);
    }
    if (t === null) return null;
    known += 1;
    last = Math.max(last, t);
    return last;
  });
  if (points.length < 2 || known < points.length * 0.6) return null;
  let prev = 0; // a point with no time sits with the one before it
  return times.map((t) => (t === null ? prev : (prev = t)));
}

/** How many overtime periods the times reach. */
function overtimes(times) {
  const last = times.length ? times[times.length - 1] : 0;
  return last > 4 * QUARTER ? Math.ceil((last - 4 * QUARTER) / OT_SLOT) : 0;
}

/** Where period i (0-based) starts, in seconds of game time. */
const periodStart = (i) => (i <= 4 ? i * QUARTER : 4 * QUARTER + (i - 4) * OT_SLOT);

/**
 * winProbabilityChart({ series: [{homeWp, period?, clock?, playId?}], homeIsUs, usAbbr, pregame, final, plays })
 * `pregame` is our chance at kickoff (0 to 1) when known. `plays` lets the post-game series find each play's time.
 * Phase 16 wave 3 (owner pick 5B): drawn on game time with a tick at each quarter, the labels an HTML caption at
 * the body's size, one line and no shading.
 */
export function winProbabilityChart({ series = [], homeIsUs = true, usAbbr = usLabel(), pregame, final = false, plays = null }) {
  const points = usPoints(series, homeIsUs);
  const values = points.map((p) => p.v);
  const current = values.length ? values[values.length - 1] : null;
  const times = timesFor(points, plays);
  const ot = times ? overtimes(times) : 0;
  const periods = 4 + ot;
  const span = periodStart(periods);
  const fx = (i) => (times ? times[i] / span : values.length > 1 ? i / (values.length - 1) : 0.5); // 0 to 1 across
  const y = (v) => (1 - v) * H;

  const path = values.map((v, i) => `${i === 0 ? "M" : "L"}${(fx(i) * W).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const ticks = times ? Array.from({ length: periods - 1 }, (_, i) => {
    const at = ((periodStart(i + 1) / span) * W).toFixed(1);
    return svgEl("line", { class: "wp__tick", x1: at, x2: at, y1: 0, y2: H });
  }) : [];
  const svg = svgEl(
    "svg",
    { class: "wp__svg", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", "aria-hidden": "true", focusable: "false" },
    svgEl("rect", { class: "wp__frame", x: 0, y: 0, width: W, height: H }),
    ticks,
    svgEl("line", { class: "wp__mid", x1: 0, x2: W, y1: y(0.5), y2: y(0.5) }),
    values.length ? svgEl("path", { class: "wp__line", d: path }) : null,
  );
  const dot = values.length ? el("span", { class: "wp__dot", style: { left: `${(fx(values.length - 1) * 100).toFixed(2)}%`, top: `${((1 - current) * 100).toFixed(2)}%` } }) : null;

  // The caption: a label under each quarter on game time, else Kickoff and Now (or Final) at the ends.
  const caption = times
    ? el(
        "div",
        { class: "wp__caption", "aria-hidden": "true" },
        Array.from({ length: periods }, (_, i) => {
          const from = periodStart(i) / span;
          const to = periodStart(i + 1) / span;
          const name = i < 4 ? `Q${i + 1}` : ot === 1 ? "OT" : `${i - 3}OT`;
          return el("span", { class: "wp__cap", style: { left: `${(from * 100).toFixed(2)}%`, width: `${((to - from) * 100).toFixed(2)}%` } }, name);
        }),
      )
    : el("div", { class: "wp__caption wp__caption--ends", "aria-hidden": "true" }, el("span", {}, "Kickoff"), el("span", {}, final ? "Final" : "Now"));
  const summary = `Win probability for ${text(usAbbr)}${times ? " by game time" : ""}, ${values.length} ${values.length === 1 ? "reading" : "readings"}${isNum(current) ? `, ${final ? "final" : "now"} ${fmtPct(current)}` : ""}`;

  return el(
    "div",
    { class: "wp" },
    el(
      "div",
      { class: "wp__head" },
      el("div", { class: "wp__now" }, isNum(current) ? fmtPct(current) : DASH, el("small", {}, `${text(usAbbr)} ${final ? "final" : "to win"}`)),
      isNum(pregame) ? el("div", { class: "wp__pre" }, "At kickoff ", el("b", {}, fmtPct(pregame))) : null,
    ),
    el("div", { class: "wp__plot", role: "img", "aria-label": summary }, svg, dot, el("span", { class: "wp__half", "aria-hidden": "true" }, "50%")),
    caption,
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
      ? el("span", { class: "verdict verdict--yes" }, "Success") // Phase 16 wave 3: the mark is drawn by CSS, not a font glyph
      : verdict === false
        ? el("span", { class: "verdict verdict--no" }, "Failed")
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
