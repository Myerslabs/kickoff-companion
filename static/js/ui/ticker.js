// The scoreboard ticker (L10): every FBS game, scores only, one line that scrolls right to left
// like a broadcast crawl (owner direction 2026-09-23), with each team's poll rank by the matchup.
// Collapsible, remembered per device. The crawl pauses under a finger or the pointer and stops
// for people who asked their device for less motion; when the games fit in the line it stays put.

import { el, isNum, recall, remember, replaceWith, text } from "./dom.js";

const PIXELS_PER_SECOND = 45;

function side(team, winner) {
  const rank = isNum(team?.rank) ? `#${team.rank} ` : "";
  return el("span", { class: winner ? "win" : null }, `${rank}${text(team?.abbr)} ${isNum(team?.points) ? team.points : "–"}`);
}

function gameEl(game) {
  const awayWins = isNum(game.away?.points) && isNum(game.home?.points) && game.away.points > game.home.points;
  const homeWins = isNum(game.away?.points) && isNum(game.home?.points) && game.home.points > game.away.points;
  const status = game.status === "final" ? "F" : game.status === "live" ? text(game.detail) : text(game.detail || "");
  return el("span", { class: `ticker__game${game.isUs ? " ticker__game--us" : game.isMine ? " ticker__game--mine" : ""}` }, side(game.away, game.status === "final" && awayWins), el("span", { class: "at" }, "at"), side(game.home, game.status === "final" && homeWins), el("span", { class: "st" }, status));
}

/**
 * Crawl only when the line is on screen and wider than its box; re-judged whenever either changes
 * size. Returns a stop function that disconnects the observer and cancels the pending checks.
 */
function startCrawl(list, track, half) {
  const judge = () => {
    const width = half.getBoundingClientRect().width;
    const box = list.getBoundingClientRect().width;
    if (!width || !box || width <= box) {
      track.classList.remove("ticker__track--scroll");
      return;
    }
    track.style.setProperty("--ticker-seconds", `${Math.max(20, Math.round(width / PIXELS_PER_SECOND))}s`);
    track.classList.add("ticker__track--scroll");
  };
  let observer = null;
  if (typeof ResizeObserver === "function") {
    observer = new ResizeObserver(judge);
    observer.observe(list);
    observer.observe(half);
  }
  const frame = typeof requestAnimationFrame === "function" ? requestAnimationFrame(judge) : null;
  const timers = [setTimeout(judge, 50), setTimeout(judge, 1000)]; // a background tab gets no animation frames or resize callbacks until it is shown
  return () => {
    if (observer) observer.disconnect();
    observer = null;
    if (frame !== null && typeof cancelAnimationFrame === "function") cancelAnimationFrame(frame);
    for (const timer of timers) clearTimeout(timer);
  };
}

/** The games worth drawing: a malformed record is skipped, not drawn. */
function drawable(games) {
  return Array.isArray(games) ? games.filter((game) => game && typeof game === "object") : [];
}

/**
 * ticker({ games: [{away: {abbr, points, rank}, home: {abbr, points, rank}, status: "final"|"live"|"pre", detail, isUs}], id, label })
 * The element has setGames(games, label), which swaps the games inside the running line so the
 * crawl carries on, and destroy(), which a view calls when it replaces or drops the ticker so the
 * size observer does not outlive it.
 */
export function ticker({ games = [], id = "ticker", label = "Scores" }) {
  const key = `ticker:${id}`;
  const collapsed = recall(key, false);
  let currentLabel = label;
  const list = el("div", { class: "ticker__list" });
  let stop = () => {};
  let halves = null; // { half, clone } while the line has games

  function fill(next) {
    const shown = drawable(next);
    if (shown.length && halves) {
      replaceWith(halves.half, shown.map(gameEl));
      replaceWith(halves.clone, shown.map(gameEl));
      return; // same track: the observer re-judges the width, the animation is not restarted
    }
    stop();
    stop = () => {};
    halves = null;
    if (shown.length === 0) {
      list.replaceChildren(el("span", { class: "ticker__game st" }, "No other games right now."));
      return;
    }
    const half = el("div", { class: "ticker__half" }, shown.map(gameEl));
    const clone = el("div", { class: "ticker__half ticker__half--clone", "aria-hidden": "true" }, shown.map(gameEl));
    const track = el("div", { class: "ticker__track" }, half, clone);
    list.replaceChildren(track);
    halves = { half, clone };
    stop = startCrawl(list, track, half);
  }

  fill(games);
  const root = el("div", { class: "ticker", "data-collapsed": collapsed ? "true" : "false", role: "region", "aria-label": label });
  const isCollapsed = () => root.getAttribute("data-collapsed") === "true";
  const toggle = el(
    "button",
    {
      class: "btn btn--quiet icon-btn",
      type: "button",
      "aria-expanded": collapsed ? "false" : "true",
      "aria-label": `${collapsed ? "Show" : "Hide"} ${label}`,
      onclick: () => {
        const next = !isCollapsed();
        root.setAttribute("data-collapsed", next ? "true" : "false");
        toggle.setAttribute("aria-expanded", next ? "false" : "true");
        toggle.setAttribute("aria-label", `${next ? "Show" : "Hide"} ${currentLabel}`);
        toggle.textContent = next ? "▸" : "▾";
        remember(key, next);
      },
    },
    collapsed ? "▸" : "▾",
  );
  const labelEl = el("span", { class: "ticker__label" }, label);
  root.append(labelEl, list, toggle);
  root.setGames = (next, nextLabel) => {
    if (typeof nextLabel === "string" && nextLabel !== currentLabel) {
      currentLabel = nextLabel;
      labelEl.textContent = nextLabel;
      root.setAttribute("aria-label", nextLabel);
      toggle.setAttribute("aria-label", `${isCollapsed() ? "Show" : "Hide"} ${nextLabel}`);
    }
    fill(next);
  };
  root.destroy = () => {
    stop();
    stop = () => {};
  };
  return root;
}
