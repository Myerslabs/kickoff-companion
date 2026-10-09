// The box score of any game this season (Phase 17 #2, owner 2026-10-07: "Each W and L should take you to the game
// box score"). A W or L square on a cover opens our own games in the Archive or the program; every other game
// opens here: #box=<game id>, from /api/box/<id>. The two teams with the final score, the score by quarter, the
// team stats, and each side's player lines. Ours on the left when the game is ours, else the visitor first.
//
//   createBoxView({ onStatus, gameId })  -> the shared poller view (views/common.js)
//   boxHead(data)                         the header: logos, names, score, date and venue (exported for the tests)

import { isUs } from "../identity.js";
import { boxTables } from "../ui/box-columns.js";
import { DASH, el, fmtDate, isNum, obj, teamLogo, text } from "../ui/dom.js";
import { backRow, band, note } from "../ui/states.js";
import { statTableSkeleton } from "../ui/stat-table.js";
import { quarterLine, teamStatRows, teamStatsTable } from "../ui/team-stats.js";
import { weekLong } from "../ui/weeks.js";
import { fillWiki, teamPageChip, wikiLink } from "../ui/wiki-links.js";
import { errorPanel, partState, poller } from "./common.js";
import { openPlayer } from "./player.js";

function abbr(team) {
  const t = obj(team);
  if (typeof t.abbreviation === "string" && t.abbreviation.trim()) return t.abbreviation.trim();
  return typeof t.school === "string" && t.school ? t.school.slice(0, 4).toUpperCase() : DASH;
}

/** [left, right] as {team, key}: ours first when the game is ours, else the visitor first (the usual way a score reads). */
function sides(data) {
  const home = { team: obj(data.home), key: "home" };
  const away = { team: obj(data.away), key: "away" };
  if (isUs(home.team.school)) return [home, away];
  return [away, home];
}

function scoreOf(team) {
  return isNum(team.points) ? String(team.points) : DASH;
}

export function boxHead(data) {
  const g = obj(data.game);
  const [left, right] = sides(data);
  const final = g.completed === true && isNum(left.team.points) && isNum(right.team.points);
  const winner = final && left.team.points !== right.team.points ? (left.team.points > right.team.points ? "left" : "right") : null;
  const block = (side, where) =>
    el(
      "div",
      { class: `box-head__side box-head__side--${where}${winner === where ? " box-head__side--won" : ""}` },
      wikiLink("football", { team: side.team.school }, teamLogo(side.team, { size: 64, lazy: false })), // Phase 17 #4
      el("div", { class: "box-head__name" }, side.team.school ? wikiLink("school", { team: side.team.school }, text(side.team.school)) : text(null)),
      el("div", { class: "box-head__score", dataset: { k: `box-${side.key}` } }, scoreOf(side.team)),
      teamPageChip(side.team.school),
    );
  const venue = typeof g.venue === "string" && g.venue.trim() ? g.venue.trim() : null;
  const when = [weekLong(g), g.kickoff ? fmtDate(g.kickoffLocal || g.kickoff, "long") : null, venue ? [wikiLink("stadium", { venue }, venue), g.neutralSite ? " (neutral site)" : null] : null, g.conferenceGame === true ? "Conference game" : null]
    .filter(Boolean)
    .flatMap((part, i) => (i ? [" · ", part] : [part]));
  const head = el(
    "section",
    { class: "box-head", "aria-label": "Box score" },
    el("div", { class: "box-head__kicker" }, final ? "Final" : g.completed === false ? "Not played yet" : "Box score"),
    el("div", { class: "box-head__faceoff" }, block(left, "left"), el("span", { class: "box-head__vs" }, g.neutralSite || left.key === "home" ? "vs" : "at"), block(right, "right")),
    when.length ? el("div", { class: "box-head__when" }, when) : null,
  );
  fillWiki(head);
  return head;
}

function render(envelope, container) {
  const data = obj(envelope?.data);
  const g = obj(data.game);
  const final = obj(data.final);
  const players = obj(final.players);
  const [left, right] = sides(data);
  const leftAbbr = abbr(left.team);
  const rightAbbr = abbr(right.team);
  const ours = g.isOurs === true;
  const programLink = ours && (isNum(g.gameId) || /^\d+$/.test(String(g.gameId ?? ""))) ? el("a", { class: "btn btn--quiet", href: `#program=${g.gameId}` }, "Open the Game program") : null;
  const boxState = partState(data.parts?.boxTeams, Boolean(final.available));
  const playerBand = (side) =>
    band({
      id: `box-players-${side.key}`,
      title: text(side.team.school),
      collapsible: true,
      foldable: true,
      summary: "player lines",
      state: g.completed === false ? { status: "empty", message: "Player lines appear after the final." } : partState(data.parts?.boxPlayers, Object.keys(obj(players[side.key])).length > 0),
      emptyText: "CFBD has no player lines for this game yet.",
      body: () => boxTables({ categories: obj(players[side.key]), onTap: (row) => openPlayer(row.playerId, { ...row, isUs: isUs(side.team.school) }) }),
    });
  container.replaceChildren(
    el(
      "div",
      { class: "page box-page" },
      backRow({ fallback: "#program" }),
      boxHead(data),
      band({
        id: "box-team",
        title: "Team stats",
        collapsible: false,
        summary: el("span", { class: "score-words" }, `${leftAbbr} ${scoreOf(left.team)}, ${rightAbbr} ${scoreOf(right.team)}`),
        state: g.completed === false ? { status: "empty", message: "The box score appears after the final." } : boxState,
        emptyText: "CFBD has not posted the box score for this game yet. The page checks again every few minutes.",
        body: () =>
          el(
            "div",
            {},
            quarterLine({ us: { abbr: leftAbbr, scores: left.team.lineScores, total: left.team.points }, them: { abbr: rightAbbr, scores: right.team.lineScores, total: right.team.points } }),
            // CFBD's box has no plays, drives or success rate (those come from the live feed): rows empty on both sides go
            teamStatsTable({ us: { abbr: leftAbbr }, them: { abbr: rightAbbr }, rows: teamStatRows(obj(final[left.key]), obj(final[right.key])).filter((row) => row.us !== DASH || row.them !== DASH), caption: `Team stats, ${leftAbbr} and ${rightAbbr}` }),
            programLink ? el("p", { class: "note" }, "This is one of our games: the Game program has the full matchup. ", programLink) : null,
          ),
      }),
      el("div", { class: "spread spread--2" }, playerBand(left), playerBand(right)),
    ),
  );
}

export function createBoxView({ onStatus, gameId } = {}) {
  const id = typeof gameId === "string" && /^\d{1,12}$/.test(gameId) ? gameId : null;
  if (!id) {
    return {
      mount(container) {
        container.replaceChildren(el("div", { class: "page" }, backRow({ fallback: "#program" }), note("No game was named. Open a box score from a W or L on a cover.")));
        if (typeof onStatus === "function") onStatus({ kind: "quiet", label: "No game" });
      },
      refresh() {},
      unmount() {},
    };
  }
  return poller({
    url: `/api/box/${id}`,
    refreshMs: 5 * 60 * 1000,
    onStatus,
    render,
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Box score", message, retry)),
    renderLoading: () => el("div", { class: "page" }, backRow({ fallback: "#program" }), band({ title: "Box score", collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(8) })),
    loadingDetail: "The final score, team stats and player lines",
  });
}

