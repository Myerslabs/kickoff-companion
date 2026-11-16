// The poll path (ENH-19, chart 2 of the owner's chart ideas board): the Résumé's poll path drawn as a line instead of a
// table. His board of 2026-10-28, his marks of 2026-10-30 ("Combine the
// AP and coaches polls"; "remove this week" on the key) and "Build it". Rank by week, 1 at the top; the color is the team
// (ours, then the next opponent in its own checked color), the line is the poll (AP solid, Coaches dotted); a week out of the
// Top 25 breaks the line, a hollow dot on the NR row marks our AP weeks out; under each week the game that led into that
// poll (W, L or T and the opponent, a bye, nothing for the preseason). The numbers stay under it in two rows. The chart is
// drawn at its box's own width, so its words keep their size on every screen.
//
//   pollPathBlock({ polls, opponent, team, short, head, both })  the Résumé's part (the head, the chart, the key, the two rows of
//                                             numbers), or with head: false and both: true the Pre-Game Program's band body
//                                             (ENH-19, owner 2026-10-30: "Yes, add it"), four rows: each side's AP and Coaches
//   pollPathChart({ us, them, width })        the <svg>: us/them { name, polls: [{ week, seasonType, ap, coaches, led }] }
//   rankY(rank)                               the y of a rank 1..25, null for anything else
//   weekLabel(row, { short })                 "Pre", "6", "Final" ("F" when short)
//   ledWords(led)                             { mark: "W" | "L" | "T" | "bye" | "", tone, opponent: "@AUB" | "MISS" | "" }
//   lineColor(team, { light })                the opponent's line color: its color or alternate, lightened (darkened on a
//                                             light page) until it holds 3:1 on the panel and stays clear of our own hues

import { readableColor } from "./colors.js";
import { el, isNum, ordinal, records, text } from "./dom.js";
import { usSchool } from "../identity.js";
import { pollHref } from "./national-link.js";

const SVG = "http://www.w3.org/2000/svg";
const HEIGHT = 258;
const LEFT = 34;
const RIGHT = 24;
const TOP = 14;
const ROW = 6.5; // one rank, so 25th sits at 170
const NR_Y = 196;
const WEEK_Y = 216;
const MARK_Y = 236;
const OPP_Y = 252;
const DEFAULT_WIDTH = 364;

function svgEl(tag, attrs = {}, ...kids) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  for (const kid of kids) if (kid !== null && kid !== undefined) node.append(typeof kid === "string" ? document.createTextNode(kid) : kid);
  return node;
}

const rankOf = (v) => (isNum(v) && v >= 1 && v <= 25 ? Math.round(v) : null);

export function rankY(rank) {
  const r = rankOf(rank);
  return r === null ? null : TOP + (r - 1) * ROW;
}

export function weekLabel(row, { short = false } = {}) {
  if (row && row.seasonType === "postseason") return short ? "F" : "Final";
  if (row && isNum(row.week)) return row.week <= 1 ? "Pre" : String(row.week);
  return "";
}

export function ledWords(led) {
  if (!led || typeof led !== "object") return { mark: "", tone: "", opponent: "" };
  if (led.bye === true) return { mark: "bye", tone: "bye", opponent: "" };
  const mark = led.result === "W" || led.result === "L" || led.result === "T" ? led.result : "";
  const name = typeof led.abbreviation === "string" && led.abbreviation.trim() ? led.abbreviation.trim() : typeof led.opponent === "string" ? led.opponent.trim().slice(0, 4).toUpperCase() : "";
  return { mark, tone: mark === "W" ? "w" : mark === "L" ? "l" : mark ? "t" : "", opponent: name ? `${led.away === true ? "@" : ""}${name}` : "" };
}

export function lineColor(team, { light = false } = {}) {
  return readableColor([team?.color, team?.altColor], { light, avoidOurs: true }); // a two-team chart: never our own hues
}

/** Runs of consecutive ranked weeks: [[[x, y], ...], ...]. */
function runs(points) {
  const out = [];
  let run = [];
  for (const p of points) {
    if (p) run.push(p);
    else if (run.length) {
      out.push(run);
      run = [];
    }
  }
  if (run.length) out.push(run);
  return out;
}

function line(run, cls, style) {
  if (run.length < 2) return null;
  return svgEl("polyline", { class: cls, points: run.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" "), style });
}

/** Where a rank's number sits: above a peak, below a valley, beside a climb or a fall. */
function labelSpot(i, ranks, x, y) {
  const prev = i > 0 ? ranks[i - 1] : null;
  const next = i < ranks.length - 1 ? ranks[i + 1] : null;
  const r = ranks[i];
  const better = (v) => v !== null && v < r;
  if (better(next) && !better(prev) && i > 0) return { x: x - 8, y: y + 4, anchor: "end" }; // never into the axis's numbers
  if (better(prev) && better(next)) return { x, y: y + 17, anchor: "middle" };
  if (better(prev)) return { x: x + 8, y: y + 4, anchor: "start" };
  return { x, y: y - 10, anchor: "middle" };
}

function summary(name, rows) {
  const words = rows.map((row) => {
    const ap = rankOf(row.ap);
    const co = rankOf(row.coaches);
    const week = weekLabel(row) === "Pre" ? "the preseason" : weekLabel(row) === "Final" ? "the final poll" : `week ${weekLabel(row)}`;
    if (ap === null && co === null) return `not ranked in ${week}`;
    return `${ap !== null ? `${ordinal(ap)} in the AP` : "not in the AP"}${co !== null ? `, ${ordinal(co)} in the Coaches` : ""} in ${week}`;
  });
  return `${name}: ${words.join("; ")}`;
}

export function pollPathChart({ us, them = null, width = DEFAULT_WIDTH } = {}) {
  const rows = records(us?.polls);
  const w = isNum(width) && width >= 240 ? Math.round(width) : DEFAULT_WIDTH;
  const n = rows.length;
  const step = n > 1 ? (w - LEFT - RIGHT) / (n - 1) : 0;
  const xAt = (i) => (n > 1 ? LEFT + i * step : (LEFT + w - RIGHT) / 2);
  const light = typeof document !== "undefined" && document.documentElement?.dataset?.theme === "light";
  const themColor = them ? lineColor(them, { light }) : null;
  const themRows = them ? records(them.polls) : [];
  const themBy = new Map(themRows.map((row) => [`${row.seasonType || "regular"}:${row.week}`, row]));
  const aria = [summary(text(us?.name || usSchool()), rows), them ? summary(text(them.name), rows.map((row) => themBy.get(`${row.seasonType || "regular"}:${row.week}`) || { ...row, ap: null, coaches: null })) : null].filter(Boolean).join(". ");
  const svg = svgEl("svg", { class: "pp__svg", viewBox: `0 0 ${w} ${HEIGHT}`, width: w, height: HEIGHT, role: "img", "aria-label": aria });

  const grid = svgEl("g", { class: "pp__grid" });
  const axis = svgEl("g", { class: "pp__axis", "text-anchor": "end" });
  for (const r of [1, 5, 10, 15, 20, 25]) {
    grid.append(svgEl("line", { x1: LEFT, x2: w - RIGHT + 12, y1: rankY(r), y2: rankY(r) }));
    axis.append(svgEl("text", { x: LEFT - 8, y: rankY(r) + 4 }, String(r)));
  }
  axis.append(svgEl("text", { x: LEFT - 8, y: NR_Y + 4 }, "NR"));
  svg.append(grid, svgEl("line", { class: "pp__nrline", x1: LEFT, x2: w - RIGHT + 12, y1: NR_Y, y2: NR_Y }), axis);

  // the opponent first, so our lines sit on top
  if (them) {
    const style = `stroke: ${themColor}`;
    const fill = `fill: ${themColor}`;
    const at = (row, key, i) => (rankOf(row?.[key]) !== null ? [xAt(i), rankY(row[key])] : null);
    const tRows = rows.map((row) => themBy.get(`${row.seasonType || "regular"}:${row.week}`) || null);
    for (const run of runs(tRows.map((row, i) => at(row, "ap", i)))) svg.append(line(run, "pp__line pp__line--them", style));
    for (const run of runs(tRows.map((row, i) => at(row, "coaches", i)))) svg.append(line(run, "pp__line pp__line--them pp__line--coaches", style));
    const dots = svgEl("g", { class: "pp__dots", style: fill });
    tRows.forEach((row, i) => {
      const ap = at(row, "ap", i);
      const co = at(row, "coaches", i);
      if (ap) dots.append(svgEl("circle", { cx: ap[0].toFixed(1), cy: ap[1].toFixed(1), r: i === n - 1 ? 4 : 3 }));
      if (co && (!ap || co[1] !== ap[1])) dots.append(svgEl("circle", { cx: co[0].toFixed(1), cy: co[1].toFixed(1), r: 2.5 }));
    });
    svg.append(dots);
    const last = rankOf(tRows[n - 1]?.ap) ?? rankOf(tRows[n - 1]?.coaches);
    if (last !== null) svg.append(svgEl("text", { class: "pp__label pp__label--them", x: (xAt(n - 1) + 10).toFixed(1), y: (rankY(last) + 4).toFixed(1), style: fill }, String(last)));
  }

  // ours: the Coaches dotted under the AP solid
  const ap = rows.map((row) => rankOf(row.ap));
  const co = rows.map((row) => rankOf(row.coaches));
  for (const run of runs(co.map((r, i) => (r !== null ? [xAt(i), rankY(r)] : null)))) svg.append(line(run, "pp__line pp__line--us pp__line--coaches"));
  for (const run of runs(ap.map((r, i) => (r !== null ? [xAt(i), rankY(r)] : null)))) svg.append(line(run, "pp__line pp__line--us"));
  const dots = svgEl("g", { class: "pp__dots pp__dots--us" });
  const hollow = svgEl("g", { class: "pp__nr" });
  const labels = svgEl("g", { class: "pp__labels" });
  rows.forEach((row, i) => {
    const x = xAt(i);
    if (co[i] !== null && co[i] !== ap[i]) dots.append(svgEl("circle", { cx: x.toFixed(1), cy: rankY(co[i]).toFixed(1), r: i === n - 1 ? 4 : 3 }));
    if (ap[i] !== null) dots.append(svgEl("circle", { cx: x.toFixed(1), cy: rankY(ap[i]).toFixed(1), r: i === n - 1 ? 6 : 4 }));
    else hollow.append(svgEl("circle", { cx: x.toFixed(1), cy: NR_Y, r: 4 }));
    if (ap[i] !== null && i < n - 1) {
      const spot = labelSpot(i, ap, x, rankY(ap[i]));
      labels.append(svgEl("text", { x: spot.x.toFixed(1), y: spot.y.toFixed(1), "text-anchor": spot.anchor }, String(ap[i])));
    }
  });
  svg.append(dots, hollow, labels);
  const nowAp = ap[n - 1];
  const nowCo = co[n - 1];
  if (nowAp !== null) svg.append(svgEl("text", { class: "pp__now", x: xAt(n - 1).toFixed(1), y: (rankY(nowAp) - 12).toFixed(1), "text-anchor": "middle" }, String(nowAp)));
  if (nowCo !== null && nowCo !== nowAp) svg.append(svgEl("text", { class: "pp__label", x: (xAt(n - 1) + 10).toFixed(1), y: (rankY(nowCo) + 4).toFixed(1) }, String(nowCo)));

  // the weeks, and the game that led into each poll (the opponent only where there is room for it)
  const short = step > 0 && step < 30;
  const weeks = svgEl("g", { class: "pp__axis", "text-anchor": "middle" });
  const marks = svgEl("g", { class: "pp__marks", "text-anchor": "middle" });
  const opps = svgEl("g", { class: "pp__axis", "text-anchor": "middle" });
  rows.forEach((row, i) => {
    const x = xAt(i).toFixed(1);
    weeks.append(svgEl("text", { x, y: WEEK_Y }, weekLabel(row, { short })));
    const led = ledWords(row.led);
    if (led.mark) marks.append(svgEl("text", { class: `pp__mark pp__mark--${led.tone}`, x, y: MARK_Y }, led.mark));
    if (led.opponent && !short) opps.append(svgEl("text", { x, y: OPP_Y }, led.opponent));
  });
  svg.append(weeks, marks, opps);
  return svg;
}

function keyItem(swatch, words) {
  return el("span", { class: "pp__keyitem" }, swatch, words);
}

function swatchSvg(kind, color = null) {
  const s = svgEl("svg", { width: kind === "team" || kind === "nr" ? 14 : 28, height: kind === "team" || kind === "nr" ? 14 : 10, "aria-hidden": "true" });
  if (kind === "team") s.append(svgEl("rect", { class: color ? null : "pp__swatch--us", x: 1, y: 1, width: 12, height: 12, rx: 2, style: color ? `fill: ${color}` : null }));
  else if (kind === "ap") s.append(svgEl("line", { class: "pp__swatch-line", x1: 0, y1: 5, x2: 28, y2: 5 }));
  else if (kind === "coaches") s.append(svgEl("line", { class: "pp__swatch-line pp__swatch-line--coaches", x1: 2, y1: 5, x2: 28, y2: 5 }));
  else s.append(svgEl("circle", { class: "pp__swatch-nr", cx: 7, cy: 7, r: 4 }));
  return s;
}

/** The rows under the chart: AP and Coaches for each side given ({ name, short, rows }), the first side alone on the Season
 *  page, both on the Pre-Game Program (each row then led by the school's abbreviation). */
function numbersTable(rows, sides) {
  // a rank opens that poll's national list, as the poll path's badges did (Phase 16); NR is plain
  const cell = (v, last, poll, team) => {
    const r = rankOf(v);
    return el("td", { class: r === null ? "nr" : last ? "now" : null }, r === null ? "NR" : el("a", { class: "pp__link", href: pollHref(poll, { team }), "aria-label": `${text(team)}, ${poll} ${ordinal(r)}` }, String(r)));
  };
  const keyOf = (row) => `${row?.seasonType || "regular"}:${row?.week}`;
  const lines = [];
  for (const side of sides) {
    const by = new Map(records(side.rows).map((row) => [keyOf(row), row]));
    for (const poll of ["AP", "Coaches"]) {
      const field = poll === "AP" ? "ap" : "coaches";
      const head = sides.length > 1 ? `${text(side.short || side.name)} ${poll}` : poll;
      lines.push(el("tr", {}, el("th", { scope: "row" }, head), rows.map((row, i) => cell(by.get(keyOf(row))?.[field], i === rows.length - 1, poll, side.name))));
    }
  }
  return el(
    "div",
    { class: "pp__table" },
    el(
      "table",
      { class: "pp__weeks" },
      el("caption", { class: "sr-only" }, "Poll path by week"),
      el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Week"), rows.map((row) => el("th", { scope: "col" }, weekLabel(row))))),
      el(
        "tbody",
        {},
        lines,
      ),
    ),
  );
}

/** head: false inside a band of its own (the Pre-Game Program's), whose title already says it; both: the opponent's rows of
 *  numbers too; short: our abbreviation for those rows. */
export function pollPathBlock({ polls, opponent = null, team = usSchool(), short = null, head = true, both = false } = {}) {
  const rows = records(polls).filter((row) => isNum(row.week) || row.seasonType === "postseason");
  const them = opponent && typeof opponent === "object" && records(opponent.polls).length ? { name: text(opponent.school || ""), short: opponent.abbreviation, color: opponent.color, altColor: opponent.altColor, polls: opponent.polls } : null;
  const us = { name: text(team || usSchool()), short, polls: rows };
  const holder = el("div", { class: "pp__chart" });
  let drawn = 0;
  const draw = (width) => {
    const w = isNum(width) && width >= 240 ? Math.round(width) : DEFAULT_WIDTH;
    if (Math.abs(w - drawn) < 4) return;
    drawn = w;
    try {
      holder.replaceChildren(pollPathChart({ us, them, width: w }));
    } catch (error) {
      console.error("The poll path could not be drawn; the numbers under it stay.", error);
      holder.replaceChildren();
    }
  };
  draw(DEFAULT_WIDTH);
  if (typeof ResizeObserver === "function") {
    const watch = new ResizeObserver((entries) => {
      const box = entries?.[0]?.contentRect;
      if (box && box.width > 0) draw(box.width);
    });
    watch.observe(holder);
  }
  const color = them ? lineColor(them, { light: typeof document !== "undefined" && document.documentElement?.dataset?.theme === "light" }) : null;
  return el(
    "div",
    { class: "pp" },
    head ? el("div", { class: "pp__head" }, el("h4", { class: "d2-head" }, "Poll path"), el("span", { class: "pp__sub" }, "AP and Coaches together")) : null,
    holder,
    el(
      "div",
      { class: "pp__key" },
      keyItem(swatchSvg("team"), us.name),
      them ? keyItem(swatchSvg("team", color), them.name) : null,
      keyItem(swatchSvg("ap"), "AP"),
      keyItem(swatchSvg("coaches"), "Coaches"),
      keyItem(swatchSvg("nr"), "not ranked"),
    ),
    numbersTable(rows, [{ name: us.name, short: us.short, rows }, ...(both && them ? [{ name: them.name, short: them.short, rows: records(them.polls) }] : [])]),
    el("p", { class: "pp__note" }, "1 at the top. Solid is the AP poll, dotted the Coaches. A break in a line is a week out of the Top 25. Under each week, the game that led into that poll."),
  );
}
