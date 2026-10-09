// The newspaper (N1 to N3): the headline digest and the day's slate as game cards.
// Headlines are links out, never body text. Our game is pinned first and outlined.

import { usSchool } from "../identity.js";
import { DASH, el, fmtDate, fmtPct, fmtTime, isNum, teamLink, teamLogo, text } from "./dom.js";
import { pollHref } from "./national-link.js";
import { pollBadge, rankChip } from "./stat-table.js";
import { nationalHref } from "./national-link.js";

export function ageOf(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const minutes = Math.round((Date.now() - d.getTime()) / 60000);
  if (minutes < 60) return `${Math.max(0, minutes)} min ago`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h ago`;
  return fmtDate(d, "short");
}

/** newsDigest({ items: [{ title, url, source, publishedAt }], note }) */
export function newsDigest({ items = [], note } = {}) {
  if (!items.length) return el("p", { class: "note" }, note || "No headlines yet.");
  return el(
    "ul",
    { class: "news" },
    items.map((item) =>
      el(
        "li",
        { class: "news__item" },
        item.url ? el("a", { href: item.url, target: "_blank", rel: "noopener" }, text(item.title)) : el("span", {}, text(item.title)),
        el("span", { class: "news__meta" }, [item.source, ageOf(item.publishedAt)].filter(Boolean).map(text).join(" · ")),
      ),
    ),
  );
}

export function newsSkeleton(rows = 5) {
  return el("div", {}, Array.from({ length: rows }, () => el("div", { class: "skel skel--row" })));
}

/** Phase 16 wave 3 (G3-10): the shared logo, from the app's own logo cache with the same fallback tile as everywhere. */
function logo(team) {
  return teamLogo(team && typeof team === "object" ? team : {}, { size: 40, className: "cover__logo" });
}

function recordText(record) {
  if (!record || !isNum(record.wins) || !isNum(record.losses)) return null;
  return record.ties ? `${record.wins}-${record.losses}-${record.ties}` : `${record.wins}-${record.losses}`;
}

/** N2 (final pass): "44.8 pts #3 · 552 yds #8", each chip opening the national list. */
function statLine(team, rows) {
  const list = Array.isArray(rows) ? rows.filter((r) => r && typeof r === "object" && isNum(r.value)) : [];
  if (!list.length) return null;
  const parts = [];
  for (const r of list) {
    if (parts.length) parts.push(" · ");
    const unit = r.key === "ppg" ? "pts" : "yds";
    const value = r.key === "ppg" ? (Math.round(r.value * 10) / 10).toFixed(1) : String(Math.round(r.value));
    let href = null;
    try {
      href = typeof r.metric === "string" ? nationalHref(r.metric, { team: team?.school }) : null;
    } catch {
      href = null;
    }
    parts.push(el("span", { class: "game-card__statpair" }, el("span", { class: "game-card__stat" }, `${value} ${unit}`), " ", isNum(r.rank) ? rankChip(r.rank, r.of, { href, label: text(r.label) }) : null)); // the number and its chip stay on one line
  }
  return el("div", { class: "game-card__stats" }, ...parts);
}

/** "Edge: Passing, SWT offense against BLUE defense, SWT by 29 ranks" from the server's biggest pairing. */
function edgeLine(game) {
  const e = game?.edge && typeof game.edge === "object" ? game.edge : null;
  if (!e || !e.stat || !isNum(e.edge)) return null;
  const home = text(game.home?.abbreviation);
  const away = text(game.away?.abbreviation);
  const homeOffense = e.side !== "defense";
  const units = homeOffense ? `${home} offense against ${away} defense` : `${away} offense against ${home} defense`;
  const who = e.edge > 0 ? home : e.edge < 0 ? away : null;
  return el("div", { class: "game-card__edge" }, el("span", { class: "game-card__edge-word" }, "Edge"), ` ${e.stat}, ${units}, ${who ? `${who} by ${Math.abs(e.edge)} ranks` : "even"}`);
}

function teamBlock(team, side, rows) {
  const rec = recordText(team?.record);
  return el(
    "div",
    { class: `game-card__team game-card__team--${side}` },
    logo(team),
    el("div", { class: "game-card__name" }, isNum(team?.apRank) ? [pollBadge(team.apRank, "AP", { href: pollHref("AP", { team: team.school }), label: text(team.school), showPoll: false }), " "] : null, teamLink(team?.school, text(team?.school)), el("small", {}, rec || DASH)),
    statLine(team, rows),
  );
}

/**
 * gameCard({ home, away, kickoff, startTimeTbd, tv, venue, line: {formatted, overUnder}, homeWinProbability, isUs, usIsHome })
 */
export function gameCard(game = {}) {
  const usSide = game.isUs ? (game.home?.school === game.usName ? "home" : "away") : null;
  const homeWp = isNum(game.homeWinProbability) ? game.homeWinProbability : null;
  return el(
    "li",
    { class: `game-card${game.isUs ? " game-card--us" : ""}` },
    game.bowl ? el("div", { class: "game-card__watch" }, text(game.bowl)) : null,
    game.watch === "next" || game.watch === "future" ? el("div", { class: "game-card__watch" }, game.watch === "next" ? "Our next opponent" : "A later opponent of ours") : null,
    el("div", { class: "game-card__teams" }, teamBlock(game.away, "away", game.stats?.away), el("span", { class: "game-card__at" }, game.neutralSite ? "vs" : "at"), teamBlock(game.home, "home", game.stats?.home)),
    edgeLine(game),
    el(
      "div",
      { class: "game-card__meta" },
      el("span", {}, game.startTimeTbd ? "Time TBD" : el("b", {}, fmtTime(game.kickoff))),
      game.tv ? el("span", {}, "TV ", el("b", {}, text(game.tv))) : null,
      game.line?.formatted ? el("span", {}, "Line ", el("b", {}, text(game.line.formatted))) : el("span", {}, "No line yet"),
      isNum(game.line?.overUnder) ? el("span", {}, "O/U ", el("b", {}, String(game.line.overUnder))) : null,
      game.venue ? el("span", {}, text(game.venue)) : null,
    ),
    homeWp !== null
      ? el(
          "div",
          {},
          el("div", { class: "wpbar", "aria-hidden": "true" }, el("div", { class: `wpbar__home${usSide === "home" ? " wpbar__home--us" : ""}`, style: { width: `${(homeWp * 100).toFixed(1)}%` } }), el("div", { class: `wpbar__away${usSide === "away" ? " wpbar__away--us" : ""}`, style: { width: `${((1 - homeWp) * 100).toFixed(1)}%` } })),
          el("div", { class: "game-card__wp" }, el("span", {}, `${text(game.away?.abbreviation)} ${fmtPct(1 - homeWp)}`), el("span", {}, "Pregame win probability"), el("span", {}, `${text(game.home?.abbreviation)} ${fmtPct(homeWp)}`)),
        )
      : el("div", { class: "game-card__wp" }, el("span", {}, "Pregame win probability not available")),
  );
}

/** slateList({ games, usName, note }) — our game first, then kickoff order. */
export function slateList({ games = [], usName = usSchool(), note } = {}) {
  const watchRank = (g) => ({ next: 0, future: 1 })[g?.watch] ?? 2;
  const ordered = [...games].sort((a, b) => Number(Boolean(b.isUs)) - Number(Boolean(a.isUs)) || watchRank(a) - watchRank(b) || String(a.kickoff || "").localeCompare(String(b.kickoff || "")));
  return el(
    "div",
    {},
    ordered.length ? el("ul", { class: "slate" }, ordered.map((game) => gameCard({ ...game, usName }))) : el("p", { class: "note" }, "No games on the slate today."),
    note ? el("p", { class: "note" }, note) : null,
  );
}

export function slateSkeleton(cards = 4) {
  return el("div", { class: "slate" }, Array.from({ length: cards }, () => el("div", { class: "skel skel--block", style: { margin: 0, height: "120px" } })));
}
