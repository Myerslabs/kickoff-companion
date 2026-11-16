// A past season, read from what was kept when the app moved on (rollover R2, owner 2026-11-15: "A Seasons list", "The book
// and its games"). Nothing here asks CFBD: the book is /api/seasons/<year>/book/<part>; a game's stops are its kickoff and
// Post-Game locks read with ?season=<year>, and its Archive game, which never depended on the season.
//
//   pastYear(value)                  a season's year from an address (2000 to 2999), else null
//   bookUrl(season, part)            "/api/seasons/2026/book/overview"
//   withSeason(url, season)          an /api/ address with season=<year> added; unchanged when season is null
//   pastHref(kind, gameId, season)   "pre" -> "#program=<id>?tab=pre&season=<year>", "post" -> "#postgame=<id>?season=<year>",
//                                    "game" -> "#archive=<id>"
//   pastMarks(line, gameId, season)  a past schedule row's three marks from the kept line, each leading to its kept stop
//   pastNote(season)                 the line under a past page's head: what it is and where this season is

import { el, text } from "./dom.js";

export function pastYear(value) {
  const n = typeof value === "number" ? value : /^\d{4}$/.test(String(value ?? "")) ? Number(value) : NaN;
  return Number.isInteger(n) && n >= 2000 && n <= 2999 ? n : null;
}

export function bookUrl(season, part) {
  return `/api/seasons/${encodeURIComponent(String(season))}/book/${encodeURIComponent(String(part))}`;
}

export function withSeason(url, season) {
  if (pastYear(season) === null || typeof url !== "string") return url;
  return `${url}${url.includes("?") ? "&" : "?"}season=${season}`;
}

export function pastHref(kind, gameId, season) {
  const id = encodeURIComponent(text(gameId));
  if (kind === "game") return `#archive=${id}`;
  if (kind === "pre") return `#program=${id}?tab=pre&season=${season}`;
  return `#postgame=${id}?season=${season}`;
}

function weekIn(line, gameId) {
  const items = line && Array.isArray(line.items) ? line.items : [];
  return items.find((item) => item && item.kind === "week" && String(item.gameId) === String(gameId)) || null;
}

export function pastMarks(line, gameId, season) {
  const item = weekIn(line, gameId);
  const stops = item && item.stops && typeof item.stops === "object" ? item.stops : null;
  if (!stops) return [];
  const one = (stop, kind, shape, label) => {
    if (!stop || typeof stop !== "object" || stop.state === "missing") return null;
    const classes = ["rail__mark", `rail__mark--${shape}`, `rail__mark--${text(stop.state) || "to_come"}`];
    const result = stop.result || item.result;
    if (shape === "circle" && result && typeof result === "object") classes.push(result.won === true ? "rail__mark--won" : result.won === false ? "rail__mark--lost" : "rail__mark--tied");
    const mark = el("span", { class: classes.join(" "), "aria-hidden": "true" });
    const opened = typeof stop.href === "string" && stop.href.startsWith("#"); // the stop had a page when the book was kept
    return opened ? el("a", { class: "stops__stop", href: pastHref(kind, gameId, season), "aria-label": label, title: label }, mark) : el("span", { class: "stops__stop stops__stop--off", title: `${label}: not kept`, "aria-hidden": "true" }, mark);
  };
  return [one(stops.pre, "pre", "square", "Pre-Game Program, as it stood at kickoff"), one(stops.game, "game", "circle", "The game, from the Archive"), one(stops.post, "post", "square", "Post-Game Program, as closed out")].filter(Boolean);
}

export function pastNote(season) {
  return el("p", { class: "note past-note" }, `The ${season} season, as kept when the app moved on. `, el("a", { href: "#seasons" }, "Seasons"), " lists every season; ", el("a", { href: "#season" }, "My Team"), " is this one.");
}
