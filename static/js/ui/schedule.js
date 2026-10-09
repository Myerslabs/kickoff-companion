// Season pieces: the schedule rail (S1) and the record box (S2, S3).
//
// Phase 16 (stream SEASON):
//   recordLine({ overall, conference, home, away, apRank, coachesRank, spRank, team, conferenceName })
//       the record box as a two-row grid: Overall / conference / Home / Away, then AP / Coaches / SP+, each a
//       24px value over a 13px label. A ranked AP or Coaches value links to that poll's list; SP+ is a dotted
//       link to the Ratings page (design rule 19), sorted by SP+ with the team marked.
//   scheduleList({ games, nextGameId, onSelect, context, spOf })
//       onSelect(game) makes a row a button with a trailing chevron; without it the row is plain text and
//       promises no tap (other teams' schedules, the flyout). Ranked opponents carry a poll badge. With
//       context: true a second line shows the opponent's SP+ rank (a chip linked to Ratings) and, before the
//       game, the win chance (an Elo estimate marked "est."); a played game shows its result only (Phase 17).
//       Phase 17 #37 (owner 2026-10-07: "Add the teams bye week into the schedules, so we know where it is"): a
//       regular-season week with no game between the team's first and last regular-season weeks draws as a Bye
//       row in its place, with the Saturday it falls on when the games around it have dates. Nothing to tap.
//   withByes(games)  the games with {bye: true, week, date} rows put in the gaps (exported for the tests).
//   gameHref(game)  where one of our schedule rows goes: '#archive=<id>' for a finished game the app archived,
//       else '#program=<id>'; null without a game id.
//   ratingsHref(key, team)  '#ratings=<key>?team=<school>': the Ratings page sorted on key, the team marked.

import { confName } from "../identity.js";
import { weekLong, weekShort } from "./weeks.js";
import { el, fmtDate, fmtTime, isNum, teamLink, teamLogo, text } from "./dom.js";
import { pollHref } from "./national-link.js";
import { pollBadge, rankChip } from "./stat-table.js";

function recordText(rec) {
  if (!rec || !isNum(rec.wins) || !isNum(rec.losses)) return "–";
  return rec.ties ? `${rec.wins}-${rec.losses}-${rec.ties}` : `${rec.wins}-${rec.losses}`;
}

function school(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** The Ratings page sorted on `key` with `team` marked (design rule 19: SP+ anywhere links there). */
export function ratingsHref(key = "sp", team) {
  const who = school(team);
  return `#ratings=${encodeURIComponent(key)}${who ? `?team=${encodeURIComponent(who)}` : ""}`;
}

/** recordLine({ overall, conference, home, away, apRank, coachesRank, spRank, team, conferenceName }) */
export function recordLine({ overall, conference, home, away, apRank, coachesRank, spRank, team, conferenceName } = {}) {
  const who = school(team);
  const cell = (label, value, key) => el("div", { class: "record-box__item" }, el("b", { class: "record-box__val", "data-k": `record:${key}` }, value), el("span", { class: "record-box__label" }, label));
  const pollValue = (rank, poll) => {
    if (!isNum(rank)) return "NR";
    const href = pollHref(poll, { team: who });
    return href ? el("a", { class: "record-box__link", href, "aria-label": `${poll} poll: No. ${rank}. Open the ${poll} poll` }, `#${rank}`) : `#${rank}`;
  };
  const conf = typeof conferenceName === "string" && conferenceName.trim() ? conferenceName.trim() : confName();
  return el(
    "div",
    { class: "record-box" },
    el("div", { class: "record-box__row record-box__row--4" }, cell("Overall", recordText(overall), "overall"), cell(conf, recordText(conference), "conference"), cell("Home", recordText(home), "home"), cell("Away", recordText(away), "away")),
    el(
      "div",
      { class: "record-box__row record-box__row--3" },
      cell("AP", pollValue(apRank, "AP"), "ap"),
      cell("Coaches", pollValue(coachesRank, "Coaches"), "coaches"),
      cell("SP+", isNum(spRank) ? el("a", { class: "record-box__link", href: ratingsHref("sp", who), title: "Every team's ratings", "aria-label": `SP+ rank ${spRank}. Open the ratings` }, `#${spRank}`) : "–", "sp"),
    ),
  );
}

/** '#archive=<id>' for a finished game the app archived, else '#program=<id>'; null without an id. */
export function gameHref(game) {
  const id = game?.gameId;
  if (!(isNum(id) || (typeof id === "string" && /^\d+$/.test(id)))) return null;
  return game.completed === true && game.archived === true ? `#archive=${id}` : `#program=${id}`;
}

function pct(value) {
  return isNum(value) && value >= 0 && value <= 1 ? `${Math.round(value * 100)}%` : null;
}

/**
 * The second line of a row: the opponent's SP+ rank and, before the game only, the win chance (GX-08).
 * A played game has its result, so it shows no chance (Phase 17, #33). Null when nothing is known.
 */
function contextLine(game, spOf) {
  const sp = game.opponentSp && typeof game.opponentSp === "object" ? game.opponentSp : null;
  const played = game.completed === true;
  const win = !played && game.winPct && typeof game.winPct === "object" ? game.winPct : null;
  const opp = school(game.opponent?.school);
  const chip = sp && isNum(sp.rank) ? rankChip(sp.rank, isNum(spOf) ? spOf : null, { href: ratingsHref("sp", opp), label: `${opp || "Opponent"} SP+` }) : null;
  const value = pct(win?.value);
  if (!chip && !value) return null;
  const estimate = win?.estimate === true;
  return el(
    "div",
    { class: "sched__ctx" },
    el("span", { class: "sched__ctx-sp" }, el("span", { class: "sched__ctx-label" }, "Opp SP+"), chip || el("span", { class: "sched__ctx-none" }, "–")),
    played
      ? null
      : el(
          "span",
          { class: "sched__ctx-win", title: value && estimate ? `An estimate from ${text(win?.source)}` : null },
          el("span", { class: "sched__ctx-label" }, "Win"),
          el("b", { "data-k": `win:${text(game.gameId)}` }, value || "–"),
          value && estimate ? el("span", { class: "sched__est" }, "est.") : null,
        ),
  );
}

/** scheduleList({ games, nextGameId, onSelect, context, spOf }) games from the season overview */
function regularWeek(game) {
  return !game.postseason && !game.playoffRound && game.seasonType !== "postseason" && Number.isInteger(game.week) && game.week >= 0 && game.week <= 20 ? game.week : null;
}

/** The Saturday of a bye, from the game before it (whole weeks later), or null without a usable date. */
function byeDate(before, weeksLater) {
  const at = before && typeof before.date === "string" && before.date ? new Date(before.date) : null;
  if (!at || Number.isNaN(at.getTime())) return null;
  const day = new Date(at.getTime() + weeksLater * 7 * 86400000);
  return day.toISOString();
}

export function withByes(games) {
  const list = (Array.isArray(games) ? games : []).filter((g) => g && typeof g === "object");
  const out = [];
  let last = null; // the last regular-season game placed
  for (const game of list) {
    const week = regularWeek(game);
    if (week !== null && last !== null && week > regularWeek(last) + 1 && week - regularWeek(last) <= 4) {
      for (let w = regularWeek(last) + 1; w < week; w += 1) out.push({ bye: true, week: w, date: byeDate(last, w - regularWeek(last)) });
    }
    if (week !== null && (last === null || week >= regularWeek(last))) last = game;
    out.push(game);
  }
  return out;
}

function byeRow(row) {
  return el(
    "li",
    { class: "sched__game sched__game--bye", "aria-label": `Week ${row.week}: bye, no game` },
    el("span", { class: "sched__wk" }, weekShort({ week: row.week })),
    el("div", { class: "sched__opp" }, el("span", { class: "sched__bye" }, "Bye"), el("small", {}, "No game this week")),
    el("span", { class: "sched__res" }, row.date ? el("small", {}, fmtDate(row.date, "short")) : null),
  );
}

export function scheduleList({ games = [], nextGameId = null, onSelect, context = false, spOf = null } = {}) {
  const list = withByes(games);
  return el(
    "ul",
    { class: "sched" },
    list.map((game) => {
      if (game.bye === true) return byeRow(game);
      const prefix = game.homeAway === "away" ? "at " : "vs ";
      const isNext = game.gameId === nextGameId;
      const tappable = typeof onSelect === "function";
      const opp = game.opponent && typeof game.opponent === "object" ? game.opponent : {};
      const oppName = school(opp.school);
      const result = game.completed && typeof game.result === "string" && game.result
        ? el("span", { class: `sched__res res--${game.result.toLowerCase()}`, "data-k": `res:${text(game.gameId)}` }, `${game.result} ${text(game.usPoints)}-${text(game.themPoints)}`)
        : el("span", { class: "sched__res" }, fmtDate(game.date, "short"), el("small", {}, game.startTimeTbd ? "time TBD" : fmtTime(game.date)));
      const href = tappable ? gameHref(game) : null;
      const where = game.completed && game.archived === true ? "Open the archived game" : "Open the game program";
      const li = el(
        "li",
        {
          class: `sched__game${isNext ? " sched__game--next" : ""}${tappable ? " sched__game--tap" : ""}`,
          "aria-current": isNext ? "true" : null,
          tabindex: tappable ? "0" : null,
          role: tappable ? "button" : null,
          "data-href": href,
          "aria-label": tappable ? `${weekLong(game)}, ${prefix}${text(oppName)}. ${where}` : null,
        },
        el("span", { class: "sched__wk" }, weekShort(game)),
        el(
          "div",
          { class: "sched__opp" },
          prefix,
          isNum(opp.apRank) ? [pollBadge(opp.apRank, "AP", { href: pollHref("AP", { team: oppName }), label: oppName, showPoll: false }), " "] : null,
          oppName ? [teamLogo(opp, { size: 20, className: "tl__logo" }), " "] : null,
          teamLink(oppName, text(oppName)),
          el("small", {}, [game.postseason ? weekLong(game) : null, game.tv ? game.tv : null, game.homeAway === "neutral" && !game.postseason ? text(game.venue) : null].filter(Boolean).join(" · ") || (game.completed ? "Final" : "TV TBD")),
        ),
        result,
        tappable ? el("span", { class: "sched__go", "aria-hidden": "true" }, "›") : null,
        context ? contextLine(game, spOf) : null,
      );
      if (tappable) {
        li.addEventListener("click", (event) => {
          // a team name, a poll badge or a rank chip inside the row does its own job, never the row's
          const inner = event.target && typeof event.target.closest === "function" ? event.target.closest("a, button") : null;
          if (inner && li.contains(inner)) return;
          onSelect(game);
        });
        li.addEventListener("keydown", (event) => {
          if (event.target && event.target !== li) return;
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onSelect(game);
          }
        });
      }
      return li;
    }),
  );
}

/** Open one of our games from a schedule row: its archive when the app watched it, else its program. */
export function openGame(game) {
  const href = gameHref(game);
  if (href && typeof window !== "undefined" && window.location) window.location.hash = href.slice(1);
}

export function scheduleSkeleton(rows = 8) {
  return el("div", {}, Array.from({ length: rows }, () => el("div", { class: "skel skel--row" })));
}
