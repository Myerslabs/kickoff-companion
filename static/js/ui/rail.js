// The rail: one short row across the cover's top (owner 2026-11-14, of the season-long line of 2026-10-30: "I want this part
// of the screen to be smaller. It is very busy, and I only want it to show where we are now, the preseason, the pregame, the
// postgame", then "only the pregame of the next game, allow it to move forward still so I can preview each game").
//
// Batch 4 (owner 2026-11-19): three stops in view, the one on screen in the middle ("when i go left, another one is added
// and left is now center"; "only show 3, not 4"), and the row slides when it moves ("Animated would be great"). Every stop
// of the walk sits on one track; the rail remembers where the last one stood, so the page drawn after an arrow slides from
// there. The Season stop reads My Team alone, and a "Now" tag sits under the stop that leads now (the line's `current`: "Now
// just says my team, and now lives under the currently scheduled item"). The Preseason Magazine and the season book are the
// walk's two ends all season ("The preseason and postseason book are the bookends"); nothing points back to Now when it is
// out of view ("just hitting the menu takes you to the right place").
//
// The arrows at the row's ends (owner 2026-11-15: "Always start on the 'now' and be able to move forward and backwards by
// clicking or tapping the arrows"): ‹ and › step one stop at a time from the page on screen, both ways, through the walk:
// the Preseason, each game's Pre-Game (a played game's as it stood at kickoff) then its Post-Game, My Team where the line
// puts it, the Pre-Games still to come, the season book. From any page not on that walk they start at My Team. An end with
// nowhere to go is drawn dim, so the row never jumps.
//
//   rail({ line, viewing })  -> <div class="rail">
//     line     the /api/stops answer (or null: a quiet strip until it comes)
//     viewing  { kind: "pre" | "post" | "season" | "preseason" | "book", gameId } the stop on screen
//   walk(line)               -> the stops in the season's order, each { kind, href, item?, state? }. Exported for the tests.
//   steps(line, viewing)     -> { prev, next }, the stops either side of the one on screen (Now when it is not on the walk),
//     each a walk entry or null. Exported for the tests.
//   railHost(viewing)        -> <div class="rail-host"> that follows the line as it changes
//   stopMarks(gameId)        -> a schedule row's three small marks (the Season stop, Wave 4)

import { loadStops, onStops, stopsNow, weekOf } from "../stops.js";
import { el, text } from "./dom.js";

const items = (line) => (line && Array.isArray(line.items) ? line.items.filter((i) => i && typeof i === "object") : []);
const weeks = (line) => items(line).filter((i) => i.kind === "week" && i.stops && typeof i.stops === "object");
const hrefOf = (stop) => (stop && typeof stop === "object" && typeof stop.href === "string" && stop.href ? stop.href : null);
const played = (item) => Boolean(item.result && typeof item.result === "object") || (item.stops.game && item.stops.game.state === "done");

function weekWord(item) {
  if (item.seasonType && item.seasonType !== "regular") return item.seasonType === "postseason" ? "Postseason" : text(item.seasonType);
  return Number.isFinite(item.week) ? `Wk ${item.week}` : "";
}

function opponentWord(item) {
  const who = text(item.opponent || "TBA");
  return item.homeAway === "away" ? `at ${who}` : who;
}

function resultWord(result) {
  if (!result || typeof result !== "object" || !Number.isFinite(result.usPoints) || !Number.isFinite(result.themPoints)) return null;
  return { mark: result.won === true ? "W" : result.won === false ? "L" : "T", tone: result.won === true ? "won" : result.won === false ? "lost" : "tied", score: `${result.usPoints}-${result.themPoints}` };
}

function kickoffWord(iso) {
  const day = typeof iso === "string" && iso.length >= 10 ? new Date(iso) : null;
  if (!day || Number.isNaN(day.getTime())) return "";
  const names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const hours = iso.length >= 16 ? Number(iso.slice(11, 13)) : NaN;
  const minutes = iso.length >= 16 ? Number(iso.slice(14, 16)) : NaN;
  // the day name from the date part alone (the server's local time), not the tablet's zone
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const weekday = names[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
  if (!Number.isFinite(hours) || !Number.isFinite(minutes) || (hours === 0 && minutes === 0)) return weekday;
  const h12 = ((hours + 11) % 12) + 1;
  return `${weekday} ${h12}${minutes ? `:${String(minutes).padStart(2, "0")}` : ""}`;
}

/** The stops in the season's order: the Preseason, each game's Pre-Game then its Post-Game (only those that open), and Now
 *  where the line's marker stands (after the last game played when the line has no marker). Byes and the book are not stops. */
export function walk(line) {
  const out = [];
  let nowAt = -1;
  for (const item of items(line)) {
    if (item.kind === "preseason" && typeof item.href === "string" && item.href) out.push({ kind: "preseason", href: item.href });
    else if (item.kind === "now" && nowAt < 0) {
      nowAt = out.length;
      out.push({ kind: "season", href: typeof item.href === "string" && item.href ? item.href : "#season" });
    } else if (item.kind === "week" && item.stops && typeof item.stops === "object") {
      const pre = hrefOf(item.stops.pre);
      const post = hrefOf(item.stops.post);
      if (pre) out.push({ kind: "pre", gameId: item.gameId, href: pre, item });
      if (post) out.push({ kind: "post", gameId: item.gameId, href: post, item });
    } else if (item.kind === "book") {
      // batch 4 (owner 2026-11-19: "The preseason and postseason book are the bookends"; "It should always exist"): the
      // season in review is the walk's last stop all season, "the season so far" until every game is closed out
      out.push({ kind: "book", href: typeof item.href === "string" && item.href ? item.href : "#review", state: text(item.state) || "to_come" });
    }
  }
  if (nowAt < 0) {
    // no marker: Now after the last game played, else after the Preseason
    let at = out.length;
    if (at > 0 && out[at - 1].kind === "book") at -= 1; // the season book stays last
    while (at > 0 && out[at - 1].kind === "pre" && !played(out[at - 1].item)) at -= 1;
    out.splice(at, 0, { kind: "season", href: "#season" });
  }
  return out;
}

export function steps(line, viewing) {
  const all = walk(line);
  if (!all.length) return { prev: null, next: null };
  const at = centerOf(all, viewing); // a page not on the walk starts at Now
  return { prev: at > 0 ? all[at - 1] : null, next: at < all.length - 1 ? all[at + 1] : null };
}

function mark(shape, state) {
  return el("span", { class: `rail__mark rail__mark--${shape} rail__mark--${text(state) || "to_come"}`, "aria-hidden": "true" });
}

function chip({ kind, href, lit, shape, state, name, detail, label }) {
  return el(
    "a",
    { class: `rail__chip rail__chip--${kind}${lit ? " rail__chip--lit" : ""}`, href, "aria-label": label, "aria-current": lit ? "page" : null },
    mark(shape, state),
    el("span", { class: "rail__words" }, el("span", { class: "rail__name" }, name), detail ? el("span", { class: "rail__detail" }, ...detail) : null),
  );
}

/** A stop's words for an arrow's label: "Post-Game Program · Wk 11 · at Kentucky", "My Team", "Preseason Magazine". */
function stopWords(stop) {
  if (stop.kind === "preseason") return "Preseason Magazine";
  if (stop.kind === "season") return "My Team";
  if (stop.kind === "book") return stop.state === "open" ? "Season book, the season final" : "Season book, the season so far";
  const name = stop.kind === "post" ? "Post-Game Program" : "Pre-Game Program";
  const item = stop.item && typeof stop.item === "object" ? stop.item : {};
  return [name, weekWord(item), opponentWord(item)].filter(Boolean).join(" · ");
}

function step(which, stop) {
  const glyph = which === "prev" ? "‹" : "›";
  if (!stop || !stop.href) return el("span", { class: `rail__step rail__step--${which} rail__step--off`, "aria-hidden": "true" }, glyph);
  const words = stopWords(stop);
  return el("a", { class: `rail__step rail__step--${which}`, href: stop.href, "aria-label": `${which === "prev" ? "Back" : "Forward"} to ${words}`, title: words }, glyph);
}

function postChip(post) {
  const item = post.item;
  const result = resultWord(item.result || item.stops.game?.result);
  const where = `${weekWord(item)} · ${opponentWord(item)}`;
  return chip({
    kind: "post",
    href: post.href,
    lit: post.lit,
    shape: "square",
    state: item.stops.post.state,
    name: "Post-Game",
    detail: [where, result ? " · " : null, result ? el("span", { class: `rail__result rail__result--${result.tone}` }, `${result.mark} ${result.score}`) : null],
    label: `Post-Game Program, ${weekWord(item)}, ${opponentWord(item)}${result ? `, ${result.mark} ${result.score}` : ""}`,
  });
}

function preChip(pre) {
  const item = pre.item;
  const when = kickoffWord(item.stops.game?.date || item.date);
  const where = `${weekWord(item)} · ${opponentWord(item)}`;
  const result = played(item) ? resultWord(item.result || item.stops.game?.result) : null;
  const tail = result ? `${result.mark} ${result.score}` : when;
  return chip({
    kind: "pre",
    href: pre.href,
    lit: pre.lit,
    shape: "square",
    state: item.stops.pre.state,
    name: "Pre-Game",
    detail: [tail ? `${where} · ${tail}` : where],
    label: `Pre-Game Program, ${weekWord(item)}, ${opponentWord(item)}${tail ? `, ${tail}` : ""}`,
  });
}

/** The index on the walk of the stop on screen (Now's place when the page is not on the walk). */
function centerOf(all, viewing) {
  const v = viewing && typeof viewing === "object" ? viewing : {};
  const id = v.gameId !== null && v.gameId !== undefined ? String(v.gameId) : null;
  let at = all.findIndex((s) => s.kind === v.kind && (s.kind === "season" || s.kind === "preseason" || s.kind === "book" || (id !== null && String(s.gameId) === id)));
  if (at < 0) at = all.findIndex((s) => s.kind === "season");
  return Math.max(0, at);
}

/** The walk entry the line's `current` names (the stop that leads now), or -1. */
function currentOf(all, line) {
  const cur = line && typeof line.current === "object" && line.current ? line.current : null;
  if (!cur) return -1;
  const id = cur.gameId !== null && cur.gameId !== undefined ? String(cur.gameId) : null;
  return all.findIndex((s) => s.kind === cur.kind && (id === null ? s.gameId === undefined || s.gameId === null : String(s.gameId) === id));
}

/** A key for a walk entry, so the next rail knows where the last one stood (the slide). */
const keyOf = (stop) => (stop ? `${stop.kind}:${stop.gameId ?? ""}` : "");

function stopChip(stop, lit) {
  if (stop.kind === "preseason") return chip({ kind: "preseason", href: stop.href, lit, shape: "square", state: "saved", name: "Preseason", detail: ["Magazine"], label: "Preseason Magazine" });
  if (stop.kind === "season") return chip({ kind: "season", href: stop.href, lit, shape: "diamond", state: "now", name: "My Team", detail: null, label: "My Team, the season right now" });
  if (stop.kind === "book") {
    const final = stop.state === "open";
    return chip({ kind: "book", href: stop.href, lit, shape: "square", state: final ? "saved" : "open", name: "Season book", detail: [final ? "The season, final" : "The season so far"], label: final ? "Season book, the season final" : "Season book, the season so far" });
  }
  const item = stop.item && typeof stop.item === "object" ? stop.item : {};
  if (!item.stops || typeof item.stops !== "object") return chip({ kind: stop.kind, href: stop.href, lit, shape: "square", state: "open", name: stop.kind === "post" ? "Post-Game" : "Pre-Game", detail: null, label: stopWords(stop) });
  return stop.kind === "post" ? postChip({ item, href: stop.href, lit }) : preChip({ item, href: stop.href, lit });
}

// Where the last rail on the page stood, so the next one (the page redrawn after an arrow, or any stop opened) slides from
// there instead of jumping. It is the rail that reached the page that counts: a copy drawn and thrown away (the finished
// game's Pre-Game builds its cover twice) never moves it (the reviewer, batch 4).
let shown = null;
const SLIDE_MS = 320;
const ATTACH_FRAMES = 30; // about half a second for a page to put its rail on screen before it is drawn in place

/** fn() once `node` is on the page, checked each frame for a while; never when it is thrown away. */
function whenAttached(node, fn) {
  if (node.isConnected) return fn();
  if (typeof requestAnimationFrame !== "function") return undefined;
  let frames = 0;
  const look = () => {
    if (node.isConnected) fn();
    else if ((frames += 1) < ATTACH_FRAMES) requestAnimationFrame(look);
  };
  requestAnimationFrame(look);
  return undefined;
}

/** Everything a rail draws from, so a new answer of the same line leaves the rail on screen (and its slide) alone. */
function signature(line, viewing) {
  try {
    return JSON.stringify([line, viewing && typeof viewing === "object" ? viewing : null]);
  } catch {
    return String(Math.random()); // an unreadable line: always drawn again
  }
}

/**
 * rail({ line, viewing }): batch 4 (owner 2026-11-19: "We want the items to be in the middle ... when i go left, another one is
 * added and left is now center"; "only show 3, not 4"; "Animated would be great"). Every stop of the walk on one track; the
 * row shows three, the stop on screen in the middle, and the track slides to it. "Now" is a tag under the stop that leads
 * now (the line's `current`), and the Season stop says My Team alone ("Now just says my team, and now lives under the
 * currently scheduled item"). No pointer back to Now when it is out of view: the menu opens the right place.
 */
export function rail({ line = null, viewing = null } = {}) {
  const root = el("div", { class: "rail", role: "navigation", "aria-label": "The season, one stop at a time: the preseason, each game's programs, My Team and the season book" });
  if (!line) {
    root.classList.add("rail--quiet");
    root.append(el("div", { class: "rail__row" }, el("span", { class: "rail__quiet" }, "The season's line is loading.")));
    return root;
  }
  const all = walk(line);
  const center = centerOf(all, viewing);
  const current = currentOf(all, line);
  const around = { prev: center > 0 ? all[center - 1] : null, next: center < all.length - 1 ? all[center + 1] : null };
  const v = viewing && typeof viewing === "object" ? viewing : {};
  const onWalk = all.some((s, i) => i === center && s.kind === v.kind);
  const slots = all.map((stop, i) => {
    const near = Math.abs(i - center) <= 1;
    const node = stopChip(stop, onWalk && i === center);
    if (!near) {
      node.setAttribute("tabindex", "-1");
      node.setAttribute("aria-hidden", "true");
    }
    return el(
      "div",
      { class: `rail__slot${i === current ? " rail__slot--now" : ""}`, "data-key": keyOf(stop), "aria-hidden": near ? null : "true" }, // out of view: not read, its Now tag with it
      node,
      i === current ? el("span", { class: "rail__now" }, el("span", { class: "rail__now-dot", "aria-hidden": "true" }), "Now") : null,
    );
  });
  const track = el("div", { class: "rail__track" }, slots);
  track.style.setProperty("--n", String(Math.max(1, all.length)));
  const place = (at) => track.style.setProperty("--at", String(at - 1)); // the leftmost slot in view: one before the center
  const key = keyOf(all[center]);
  const from = shown ? all.findIndex((s) => keyOf(s) === shown) : -1;
  const reduce = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (from >= 0 && from !== center && !reduce) {
    place(from); // drawn where the last rail stood, then slid to the stop on screen once it is on the page and laid out
    track.classList.add("rail__track--still");
    whenAttached(root, () => {
      shown = key;
      const go = () => {
        track.classList.remove("rail__track--still");
        void track.offsetWidth; // the start position is laid out before the transition begins
        place(center);
      };
      if (typeof requestAnimationFrame === "function") requestAnimationFrame(go);
      else go();
    });
  } else {
    place(center);
    whenAttached(root, () => {
      shown = key;
    });
  }
  root.append(step("prev", around.prev), el("div", { class: "rail__row" }, track), step("next", around.next));
  root.slideMs = SLIDE_MS;
  root.dataset.sig = signature(line, viewing);
  return root;
}

/** For the tests: forget where the last rail stood. */
export function _resetSlide() {
  shown = null;
}

// A page's rail, or a row's marks: drawn from the line the app holds, redrawn when a new answer comes, and dropped once the
// page is gone.
const HOSTS = new Set();
let wired = false;

function redraw() {
  for (const h of Array.from(HOSTS)) {
    if (!h.host.isConnected) {
      HOSTS.delete(h);
      continue;
    }
    h.draw(false);
  }
}

function follow(host, draw) {
  draw(true);
  HOSTS.add({ host, draw });
  if (!wired) {
    wired = true;
    onStops(redraw);
  }
  loadStops().catch(() => {});
  return host;
}

/** railHost(viewing) -> <div class="rail-host"> holding the rail for the stop on screen; it follows the line as it changes. */
export function railHost(viewing) {
  const host = el("div", { class: "rail-host" });
  return follow(host, () => {
    const line = stopsNow();
    const now = host.firstElementChild || (host.children && host.children[0]) || null;
    if (line && now && now.dataset && now.dataset.sig === signature(line, viewing)) return; // the same answer: the rail on screen (and a slide under way) stays
    host.replaceChildren(rail({ line, viewing }));
  });
}

/** The three stops of one game as small marks for a schedule row (the Season stop, Wave 4): the Pre-Game, the game and the
 *  Post-Game in the rail's shapes and states, each a link to its stop where one opens; hidden until the line has the game. */
export function stopMarks(gameId) {
  const host = el("span", { class: "stops" });
  return follow(host, () => {
    const item = weekOf(gameId);
    const stops = item && item.stops && typeof item.stops === "object" ? item.stops : null;
    if (!stops) {
      host.replaceChildren();
      host.hidden = true;
      return;
    }
    host.hidden = false;
    const one = (stop, shape, label) => {
      if (!stop || typeof stop !== "object" || stop.state === "missing") return null;
      const classes = ["rail__mark", `rail__mark--${shape}`, `rail__mark--${text(stop.state) || "to_come"}`];
      const result = stop.result || item.result;
      if (shape === "circle" && result && typeof result === "object") classes.push(result.won === true ? "rail__mark--won" : result.won === false ? "rail__mark--lost" : "rail__mark--tied");
      const mark = el("span", { class: classes.join(" "), "aria-hidden": "true" });
      const href = typeof stop.href === "string" && stop.href.startsWith("#") ? stop.href : null;
      return href ? el("a", { class: "stops__stop", href, "aria-label": label, title: label }, mark) : el("span", { class: "stops__stop stops__stop--off", title: `${label}: not yet`, "aria-hidden": "true" }, mark);
    };
    host.replaceChildren(...[one(stops.pre, "square", "Pre-Game Program"), one(stops.game, "circle", "The game"), one(stops.post, "square", "Post-Game Program")].filter(Boolean));
  });
}
