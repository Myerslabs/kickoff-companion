// The Playoff band (Phase 15): the committee's rankings and the bracket, both as tables (the owner's
// rule: no drawings). Data from /api/season/overview `playoff`: { week, rankings, usRank, rounds }.
// GX-22 (owner look, restrained): in a band 1,000 px wide and wider the round tables stand side by side, each game's row
// as tall as the games that feed it so it lines up with its next-round slot, our path in the team
// tint, the winner in bold; still tables, no connector lines (design rule 21).
// Tables wave 3 (owner 2026-10-10): every table here sizes itself by its own box, never the screen. A round: Away | Score
// or date | Home | Winner (large) | Game (from medium), each side its seed and school (its abbreviation at small, still
// its link). The committee's rankings: its own order as the CFP badge at large and medium and a plain number at small, the
// team, its conference in a column of its own (its short name at medium, gone at small).

import { usSchool } from "../identity.js";
import { DASH, el, fmtDate, isNum, records, teamLink, text } from "./dom.js";
import { note } from "./states.js";
import { pollBadge, sizedText, statTable } from "./stat-table.js";
import { conferenceColumn, logoLink, teamAbbrLink } from "./team-page.js";

function school(team) {
  const t = team && typeof team === "object" ? team : {};
  return typeof t.school === "string" && t.school.trim() ? t.school.trim() : null;
}

function abbreviation(team) {
  const t = team && typeof team === "object" ? team : {};
  return typeof t.abbreviation === "string" && t.abbreviation.trim() ? t.abbreviation.trim() : null;
}

/** "(4) Texas" with the seed in fog and the school a link (G3-07: every team name links); in a sized table the school
 *  turns to its abbreviation at small inside the same link, so the seed and the won or lost mark stay. */
function sideCell(team, winner) {
  const t = team && typeof team === "object" ? team : {};
  const name = school(t);
  const result = winner && name ? (winner === name ? " seeded--won" : " seeded--lost") : "";
  return el("span", { class: `seeded${result}` }, isNum(t.seed) ? el("span", { class: "seeded__seed" }, `(${t.seed}) `) : null, name ? teamLink(name, sizedText(name, null, abbreviation(t) || name)) : DASH);
}

/** The bracket slot's number ("QF3" -> 3), for ordering a round's games; Infinity when there is none. */
export function slotNumber(game) {
  const m = typeof game?.slot === "string" ? /(\d+)$/.exec(game.slot) : null;
  return m ? Number(m[1]) : Infinity;
}

/** How many rows of the widest round a game in this round stands beside (1, 2, 4), so it meets its slot. */
export function rowSpan(games, widest) {
  const n = Array.isArray(games) ? games.length : 0;
  return n > 0 && widest > n && widest % n === 0 ? widest / n : 1;
}

function scoreText(game) {
  if (!game.completed) return fmtDate(game.date, "short");
  const a = game.away || {};
  const h = game.home || {};
  return isNum(a.points) && isNum(h.points) ? `${a.points}-${h.points}` : "Final";
}

const ROUND_COLUMNS = [
  { key: "away", label: "Away", kind: "text", render: (row) => sideCell(row.awaySide, row.winner) },
  { key: "result", label: "Score or date", labelMid: "Score", kind: "text" },
  { key: "home", label: "Home", kind: "text", render: (row) => sideCell(row.homeSide, row.winner) },
  { key: "winner", label: "Winner", kind: "text", team: true, shortKey: "winnerAbbr", size: "large" },
  { key: "bowl", label: "Game", kind: "text", size: "medium" },
];

const RANKING_COLUMNS = [
  { key: "rank", label: "CFP rank", labelShort: "CFP", order: true, render: (row) => pollBadge(row.rank, "CFP", { label: school({ school: row.school }), showPoll: false }) },
  { key: "school", label: "Team", kind: "text", render: (row) => logoLink(row.school, row), renderShort: (row) => teamAbbrLink(row.school, row.abbreviation) },
  conferenceColumn(),
].map((column) => ({ ...column, tieKey: "school" }));

/**
 * One table per round (seeds, teams, score or date, the winner, the bowl; our games carry the team row tint), then the
 * committee's rankings. Every table sized by its own box (wave 3). playoffBlock(p, teamName, { sorts }): sorts is a plain
 * object the rankings keep their order in across a refresh. A bracket keeps its slot order (sorting would break the rows
 * that line up with the next round).
 */
export function playoffBlock(p, teamName = usSchool(), { sorts } = {}) {
  const data = p && typeof p === "object" ? p : {};
  const state = sorts && typeof sorts === "object" ? sorts : {};
  const rankings = records(data.rankings).map((row) => ({ ...row, rank: isNum(row.rank) ? row.rank : null })); // a damaged rank sorts last, never first
  const rounds = records(data.rounds);
  const parts = [];
  if (rounds.length) {
    const widest = Math.max(...rounds.map((round) => records(round.games).length));
    const tables = [];
    for (const round of rounds) {
      const games = records(round.games).map((g, i) => ({ g, i })).sort((a, b) => slotNumber(a.g) - slotNumber(b.g) || a.i - b.i).map(({ g }) => g);
      const span = rowSpan(games, widest);
      const rows = games.map((g) => {
        const winner = g.completed && typeof g.winner === "string" && g.winner.trim() ? g.winner.trim() : null;
        const won = winner ? [g.away, g.home].find((side) => school(side) === winner) : null;
        return {
          away: school(g.away),
          awaySide: g.away,
          home: school(g.home),
          homeSide: g.home,
          result: scoreText(g),
          winner,
          winnerAbbr: won ? abbreviation(won) : null,
          bowl: typeof g.bowl === "string" && g.bowl.trim() ? g.bowl.trim() : null,
          isUs: Boolean(g.isUs),
          span,
        };
      });
      tables.push(el("div", { class: "bracket__round" }, el("h4", { class: "d2-head" }, text(round.round)), statTable({
        compact: true,
        sizes: true,
        sortable: false,
        columns: ROUND_COLUMNS,
        rows,
        rowClass: (r) => [r.isUs ? "is-us" : null, `span-${r.span}`].filter(Boolean).join(" "),
        caption: `${text(round.round)} games`,
      })));
    }
    parts.push(el("div", { class: "bracket", style: { "--rounds": String(tables.length) } }, tables));
    parts.push(note("Seeds in parentheses, as the committee placed the field. Away team first; the score reads away-home."));
  }
  if (rankings.length) {
    parts.push(el("div", { class: "playoff__rankings" }, el("h4", { class: "d2-head" }, `Committee rankings${isNum(data.week) ? `, week ${data.week}` : ""}`), statTable({
      compact: true,
      sizes: true,
      columns: RANKING_COLUMNS,
      rows: rankings,
      sort: state.cfp && typeof state.cfp.key === "string" ? state.cfp : { key: "rank", dir: "ascending" },
      onSort: (sort) => {
        state.cfp = sort; // the reader's order survives a refresh
      },
      rowClass: (r) => (r.isUs ? "is-us" : null),
      caption: "College Football Playoff committee rankings",
    })));
    if (!isNum(data.usRank)) parts.push(note(`${text(teamName)} is not in the committee's Top 25.`));
  }
  return el("div", { class: "d2 playoff" }, parts);
}

export function playoffSummary(p, teamName = usSchool()) {
  if (!p || typeof p !== "object") return "";
  const rounds = records(p.rounds);
  const ours = rounds.flatMap((r) => records(r.games).filter((g) => g.isUs === true).map(() => text(r.round)));
  if (ours.length) return `${text(teamName)}: ${ours.join(", ")}`;
  return isNum(p.usRank) ? `${text(teamName)} #${p.usRank} in the committee's rankings` : `${text(teamName)} unranked by the committee`;
}
