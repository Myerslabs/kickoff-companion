// The schedule margin strip (ENH-19, chart 3 of the owner's chart ideas board): the season's shape in one look, in the Season
// page's Schedule band between the record and the games. His board of 2026-10-30,
// "Build it as drawn". One bar a game: how much we won by (above the line) or lost by (below), the margin at the bar's end; each
// bar in that opponent's own color, lightened just enough to read on the panel (a school with no color on file, the fog); the
// games to come as dashed ticks on the line, the next one marked with its day; a bye week left empty; under each slot the week
// and the opponent (@ away). A tap on a slot opens that game's program. Drawn at its box's own width.
//
//   marginStrip({ games, nextGameId, team, title, note })   the strip's block (its head, the chart, the line under it); null with
//                         no games. title names the head ("Margin by week"; a school's name on the Pre-Game Program, where two
//                         strips share a band, ENH-19 owner 2026-10-30: "Add to program"); note: false leaves the line out
//   marginChart({ games, nextGameId, team, width })  the <svg>
//   slotsOf(games, { from, to })  the slots in order: each game, a bye for a regular-season week with none (from `from` to
//                         `to` when given, so two strips line up week for week), the postseason after
//   marginOf(game)        our points minus theirs for a finished game, else null
//   barColor(opponent)    the opponent's bar color

import { readableColor } from "./colors.js";
import { el, isNum, records, text } from "./dom.js";
import { gameHref } from "./schedule.js";

const SVG = "http://www.w3.org/2000/svg";
const HEIGHT = 210;
const BASE = 104; // the line
const MAX_BAR = 70;
const WEEK_Y = 184;
const OPP_Y = 201;
const DEFAULT_WIDTH = 480;

function svgEl(tag, attrs = {}, ...kids) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  for (const kid of kids) if (kid !== null && kid !== undefined) node.append(typeof kid === "string" ? document.createTextNode(kid) : kid);
  return node;
}

export function marginOf(game) {
  if (!game || typeof game !== "object" || !game.result) return null;
  return isNum(game.usPoints) && isNum(game.themPoints) ? game.usPoints - game.themPoints : null;
}

export function barColor(opponent) {
  const light = typeof document !== "undefined" && document.documentElement?.dataset?.theme === "light";
  return readableColor([opponent?.color, opponent?.altColor], { light }); // every bar is an opponent: its own color, ours allowed
}

const isPost = (g) => Boolean(g && (g.postseason || g.playoffRound));

export function slotsOf(games, { from = null, to = null } = {}) {
  const list = records(games).filter((g) => isNum(g.week) || isPost(g));
  const regular = list.filter((g) => !isPost(g)).sort((a, b) => a.week - b.week);
  const out = [];
  const first = regular.length ? regular[0].week : null;
  let expect = isNum(from) && (first === null || from < first) ? from : first;
  for (const g of regular) {
    while (expect !== null && g.week > expect) {
      out.push({ bye: true, week: expect });
      expect += 1;
    }
    out.push({ game: g, week: g.week });
    expect = g.week + 1;
  }
  while (expect !== null && isNum(to) && expect <= to) {
    out.push({ bye: true, week: expect });
    expect += 1;
  }
  for (const g of list.filter(isPost)) out.push({ game: g, week: null, post: true });
  return out;
}

function oppWords(game) {
  const o = game?.opponent && typeof game.opponent === "object" ? game.opponent : {};
  const name = typeof o.abbreviation === "string" && o.abbreviation.trim() ? o.abbreviation.trim() : typeof o.school === "string" ? o.school.trim().slice(0, 4).toUpperCase() : "";
  return name ? `${game.homeAway === "away" ? "@" : ""}${name}` : "";
}

function slotWords(slot) {
  if (slot.bye) return `Week ${slot.week}: a bye`;
  const g = slot.game;
  const where = g.homeAway === "away" ? "at" : "vs";
  const school = text(g.opponent?.school || "the opponent");
  const when = slot.post ? text(g.postseason || "the postseason") : `Week ${slot.week}`;
  const m = marginOf(g);
  if (m === null) return `${when}, ${where} ${school}, to come`;
  const result = m > 0 ? `won by ${m}` : m < 0 ? `lost by ${-m}` : "a tie";
  return `${when}, ${where} ${school}: ${result}, ${g.usPoints}-${g.themPoints}`;
}

function dayOf(iso) {
  const d = typeof iso === "string" ? new Date(iso) : null;
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleDateString([], { weekday: "short" }) : "Next";
}

export function marginChart({ games, nextGameId = null, team = null, width = DEFAULT_WIDTH, weeks = {} } = {}) {
  const slots = slotsOf(games, weeks);
  const w = isNum(width) && width >= 240 ? Math.round(width) : DEFAULT_WIDTH;
  const n = Math.max(slots.length, 1);
  const slot = w / n;
  const barW = Math.max(8, Math.min(22, slot * 0.6));
  const played = slots.map((s) => (s.game ? marginOf(s.game) : null)).filter(isNum);
  const scale = MAX_BAR / Math.max(35, ...played.map((m) => Math.abs(m)));
  const short = slot < 30;
  const words = slots.map(slotWords).join("; ");
  const svg = svgEl("svg", { class: "ms__svg", viewBox: `0 0 ${w} ${HEIGHT}`, width: w, height: HEIGHT, role: "img", "aria-label": words });
  svg.append(
    svgEl("text", { class: "ms__axis ms__axis--start", x: 0, y: 12 }, "won by"),
    svgEl("text", { class: "ms__axis ms__axis--start", x: 0, y: 168 }, "lost by"),
    svgEl("line", { class: "ms__line", x1: 0, x2: w, y1: BASE, y2: BASE }),
  );
  slots.forEach((s, i) => {
    const cx = slot * i + slot / 2;
    const x = (cx - barW / 2).toFixed(1);
    const parts = [];
    const weekText = s.post ? (short ? "P" : "Post") : String(s.week ?? "");
    if (s.bye) {
      parts.push(svgEl("text", { class: "ms__axis", x: cx.toFixed(1), y: WEEK_Y }, weekText));
      if (!short) parts.push(svgEl("text", { class: "ms__axis", x: cx.toFixed(1), y: OPP_Y }, "bye"));
      svg.append(svgEl("g", { class: "ms__slot ms__slot--bye", "aria-hidden": "true" }, ...parts));
      return;
    }
    const g = s.game;
    const m = marginOf(g);
    const next = !g.result && nextGameId !== null && String(g.gameId) === String(nextGameId);
    // the whole slot is the tap target: a clear rect the slot's height, under the marks
    parts.push(svgEl("rect", { class: "ms__hit", x: (slot * i).toFixed(1), y: 0, width: slot.toFixed(1), height: HEIGHT }));
    if (m !== null) {
      const h = Math.max(4, Math.min(MAX_BAR, Math.abs(m) * scale));
      const y = m >= 0 ? BASE - h : BASE;
      parts.push(svgEl("rect", { class: `ms__bar${m === 0 ? " ms__bar--tie" : ""}`, x, y: y.toFixed(1), width: barW.toFixed(1), height: h.toFixed(1), rx: 2, style: m === 0 ? null : `fill: ${barColor(g.opponent)}` }));
      const label = m > 0 ? `+${m}` : m < 0 ? `−${-m}` : "T";
      parts.push(svgEl("text", { class: "ms__margin", x: cx.toFixed(1), y: (m >= 0 ? y - 6 : y + h + 15).toFixed(1) }, label));
    } else {
      parts.push(svgEl("rect", { class: `ms__tick${next ? " ms__tick--next" : ""}`, x, y: BASE - 5, width: barW.toFixed(1), height: 10, rx: 2 }));
      if (next) parts.push(svgEl("text", { class: "ms__day", x: cx.toFixed(1), y: BASE - 13 }, dayOf(g.date)));
    }
    parts.push(svgEl("text", { class: "ms__axis", x: cx.toFixed(1), y: WEEK_Y }, weekText));
    if (!short) parts.push(svgEl("text", { class: `ms__opp${m === null ? " ms__opp--ahead" : ""}${next ? " ms__opp--next" : ""}`, x: cx.toFixed(1), y: OPP_Y }, oppWords(g)));
    const href = gameHref(g, team);
    svg.append(href ? svgEl("a", { class: "ms__slot", href, "aria-label": slotWords(s) }, ...parts) : svgEl("g", { class: "ms__slot" }, ...parts));
  });
  return svg;
}

export function marginStrip({ games, nextGameId = null, team = null, title = "Margin by week", note = true, weeks = {} } = {}) {
  const list = records(games);
  if (!slotsOf(list).some((s) => s.game)) return null;
  const holder = el("div", { class: "ms__chart" });
  let drawn = 0;
  const draw = (width) => {
    const w = isNum(width) && width >= 240 ? Math.round(width) : DEFAULT_WIDTH;
    if (Math.abs(w - drawn) < 4) return;
    drawn = w;
    try {
      holder.replaceChildren(marginChart({ games: list, nextGameId, team, width: w, weeks }));
    } catch (error) {
      console.error("The margin strip could not be drawn; the games under it stay.", error);
      holder.replaceChildren();
    }
  };
  draw(DEFAULT_WIDTH);
  if (typeof ResizeObserver === "function") {
    new ResizeObserver((entries) => {
      const box = entries?.[0]?.contentRect;
      if (box && box.width > 0) draw(box.width);
    }).observe(holder);
  }
  return el(
    "div",
    { class: "ms" },
    el("div", { class: "ms__head" }, el("h4", { class: "d2-head" }, text(title)), el("span", { class: "ms__sub" }, "tap a bar for the game")),
    holder,
    note ? el("p", { class: "ms__note" }, "Won by above the line, lost by below, each bar in the opponent's colors. Dashed: the games to come, the next one marked.") : null,
  );
}
