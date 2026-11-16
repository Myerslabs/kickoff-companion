// The rail: one short row across the cover's top (owner 2026-11-14, of the season-long line of 2026-10-30: "I want this part
// of the screen to be smaller. It is very busy, and I only want it to show where we are now, the preseason, the pregame, the
// postgame", then "only the pregame of the next game, allow it to move forward still so I can preview each game"). Four
// chips: the Preseason Magazine; the Post-Game of the last game played; Now, the season right now (My Team); the Pre-Game of
// the next game. The chip on screen wears the team's ring. A past week's Pre-Game or Post-Game on screen takes its chip's
// place. No week-by-week marks, byes, dates or season book (the menu has the book; the schedule's rows open any week's
// stops). On a narrow screen the row scrolls sideways, the lit chip in view (sideways, never up and down).
//
// The arrows at the row's ends (owner 2026-11-15, of the finished game's Pre-Game and Post-Game tabs above the rail:
// "Always start on the 'now' and be able to move forward and backwards by clicking or tapping the arrows"; his pick, arrows
// at the row's ends): ‹ and › step one stop at a time from the page on screen, both ways, through the season in its order:
// the Preseason, each game's Pre-Game (a played game's as it stood at kickoff) then its Post-Game, Now where the line puts
// it, then the Pre-Games still to come. From any page not on that walk they start at Now. They sit outside the row that
// scrolls, so a phone keeps both in reach; an end with nowhere to go is drawn dim, so the row never jumps. They replace the
// ‹ › that the next game's Pre-Game chip carried (2026-11-14), which only walked ahead.
//
//   rail({ line, viewing })  -> <div class="rail">
//     line     the /api/stops answer (or null: a quiet strip until it comes)
//     viewing  { kind: "pre" | "post" | "season" | "preseason", gameId } the stop on screen
//   chips(line, viewing)     -> { preseason, post, now, pre } what the row draws, each null when it has nothing to open:
//     preseason { href, lit }, now { href, lit }, post { item, href, lit }, pre { item, href, lit }. Exported for the tests.
//   walk(line)               -> the stops in the season's order, each { kind, href, item? }. Exported for the tests.
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

export function chips(line, viewing) {
  const v = viewing && typeof viewing === "object" ? viewing : {};
  const all = items(line);
  const same = (item) => v.gameId !== null && v.gameId !== undefined && String(item.gameId) === String(v.gameId);
  const magazine = all.find((i) => i.kind === "preseason" && typeof i.href === "string" && i.href);
  const preseason = magazine ? { href: magazine.href, lit: v.kind === "preseason" } : null;
  const marker = all.find((i) => i.kind === "now");
  const now = { href: (marker && typeof marker.href === "string" && marker.href) || "#season", lit: v.kind === "season" };
  const games = weeks(line);
  // the Post-Game: the one on screen, else the last game played whose Post-Game opens
  const shownPost = v.kind === "post" ? games.find((g) => same(g) && hrefOf(g.stops.post)) : null;
  const lastPost = [...games].reverse().find((g) => played(g) && hrefOf(g.stops.post));
  const postItem = shownPost || lastPost || null;
  const post = postItem ? { item: postItem, href: hrefOf(postItem.stops.post), lit: Boolean(shownPost) } : null;
  // the Pre-Game: the one on screen (a game ahead previewed, or a played game's as it stood), else the next game
  const ahead = games.filter((g) => !played(g) && hrefOf(g.stops.pre));
  const shownPre = v.kind === "pre" ? games.find((g) => same(g) && hrefOf(g.stops.pre)) : null;
  const preItem = shownPre || ahead[0] || null;
  const pre = preItem ? { item: preItem, href: hrefOf(preItem.stops.pre), lit: Boolean(shownPre) } : null;
  return { preseason, post, now, pre };
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
    } else if (item.kind === "book" && typeof item.href === "string" && item.href) {
      out.push({ kind: "book", href: item.href }); // Wave 7: the season in review, once the season's last game is closed out
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
  const v = viewing && typeof viewing === "object" ? viewing : {};
  const all = walk(line);
  const id = v.gameId !== null && v.gameId !== undefined ? String(v.gameId) : null;
  let at = all.findIndex((s) => s.kind === v.kind && (s.kind === "season" || s.kind === "preseason" || (id !== null && String(s.gameId) === id)));
  if (at < 0) at = all.findIndex((s) => s.kind === "season"); // a page not on the walk starts at Now
  return { prev: at > 0 ? all[at - 1] : null, next: at >= 0 && at < all.length - 1 ? all[at + 1] : null };
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

/** A stop's words for an arrow's label: "Post-Game Program · Wk 11 · at Kentucky", "My Team, now", "Preseason Magazine". */
function stopWords(stop) {
  if (stop.kind === "preseason") return "Preseason Magazine";
  if (stop.kind === "season") return "My Team, now";
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

export function rail({ line = null, viewing = null } = {}) {
  const root = el("div", { class: "rail", role: "navigation", "aria-label": "The season: preseason, post-game, now and pre-game" });
  if (!line) {
    root.classList.add("rail--quiet");
    root.append(el("div", { class: "rail__row" }, el("span", { class: "rail__quiet" }, "The season's line is loading.")));
    return root;
  }
  const c = chips(line, viewing);
  const around = steps(line, viewing);
  root.append(
    step("prev", around.prev),
    el(
      "div",
      { class: "rail__row" },
      c.preseason ? chip({ kind: "preseason", href: c.preseason.href, lit: c.preseason.lit, shape: "square", state: "saved", name: "Preseason", detail: ["Magazine"], label: "Preseason Magazine" }) : null,
      c.post ? postChip(c.post) : null,
      chip({ kind: "now", href: c.now.href, lit: c.now.lit, shape: "diamond", state: "now", name: "Now", detail: ["My Team"], label: "My Team, the season right now" }),
      c.pre ? preChip(c.pre) : null,
    ),
    step("next", around.next),
  );
  // the lit chip in view on a narrow screen: the row alone scrolls sideways, never the page (a redraw while reading further
  // down must not pull the page back up)
  root.scrollLit = () => {
    const row = root.querySelector(".rail__row");
    const lit = root.querySelector(".rail__chip--lit");
    if (!row || !lit || !(row.scrollWidth > row.clientWidth)) return;
    const left = lit.offsetLeft - row.offsetLeft - (row.clientWidth - lit.offsetWidth) / 2;
    if (Number.isFinite(left)) row.scrollLeft = Math.max(0, left);
  };
  // once, the first time the row is laid out narrower than its chips: the pages put the rail on screen when their data comes,
  // not when it is drawn, and its column can settle narrower after the first layout
  if (typeof ResizeObserver === "function") {
    const row = root.querySelector(".rail__row");
    const watch = new ResizeObserver(() => {
      if (!(row.clientWidth > 0) || !(row.scrollWidth > row.clientWidth)) return; // not laid out yet, or it all fits
      watch.disconnect();
      root.scrollLit();
    });
    watch.observe(row);
  }
  return root;
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
  return follow(host, () => host.replaceChildren(rail({ line: stopsNow(), viewing }))); // each rail scrolls to its lit chip itself
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
