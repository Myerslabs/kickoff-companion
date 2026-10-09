// The Playoff band (Phase 15): the committee's rankings and the bracket, both as tables (the owner's
// rule: no drawings). Data from /api/season/overview `playoff`: { week, rankings, usRank, rounds }.
// GX-22 (owner look, restrained): at 1100px and wider the round tables stand side by side, each game's row
// as tall as the games that feed it so it lines up with its next-round slot, our path in the team
// tint, the winner in bold; still tables, no connector lines (design rule 21).

import { usSchool } from "../identity.js";
import { DASH, el, fmtDate, isNum, records, teamLink, text } from "./dom.js";
import { note } from "./states.js";
import { statTable } from "./stat-table.js";

function school(team) {
  const t = team && typeof team === "object" ? team : {};
  return typeof t.school === "string" && t.school.trim() ? t.school.trim() : null;
}

/** "(4) Texas" with the seed in fog and the school a link (G3-07: every team name links). */
function sideCell(team, winner) {
  const t = team && typeof team === "object" ? team : {};
  const name = school(t);
  const result = winner && name ? (winner === name ? " seeded--won" : " seeded--lost") : "";
  return el("span", { class: `seeded${result}` }, isNum(t.seed) ? el("span", { class: "seeded__seed" }, `(${t.seed}) `) : null, name ? teamLink(name, name) : DASH);
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

/** One table per round: seeds, teams, score or date, the bowl. Our games carry the team row tint. */
export function playoffBlock(p, teamName = usSchool()) {
  const data = p && typeof p === "object" ? p : {};
  const rankings = records(data.rankings);
  const rounds = records(data.rounds);
  const parts = [];
  if (rounds.length) {
    const widest = Math.max(...rounds.map((round) => records(round.games).length));
    const tables = [];
    for (const round of rounds) {
      const games = records(round.games).map((g, i) => ({ g, i })).sort((a, b) => slotNumber(a.g) - slotNumber(b.g) || a.i - b.i).map(({ g }) => g);
      const span = rowSpan(games, widest);
      const rows = games.map((g) => ({
        away: school(g.away),
        awaySide: g.away,
        home: school(g.home),
        homeSide: g.home,
        result: scoreText(g),
        winner: g.completed && typeof g.winner === "string" && g.winner.trim() ? g.winner.trim() : null,
        bowl: typeof g.bowl === "string" && g.bowl.trim() ? g.bowl.trim() : null,
        isUs: Boolean(g.isUs),
        span,
      }));
      tables.push(el("div", { class: "bracket__round" }, el("h4", { class: "d2-head" }, text(round.round)), statTable({
        compact: true,
        sortable: false,
        columns: [
          { key: "away", label: "Away", kind: "text", render: (row) => sideCell(row.awaySide, row.winner) },
          { key: "result", label: "Score or date", kind: "text", sub: "bowl" },
          { key: "home", label: "Home", kind: "text", render: (row) => sideCell(row.homeSide, row.winner) },
          { key: "winner", label: "Winner", kind: "text", team: true },
          { key: "bowl", label: "Game", kind: "text" },
        ],
        rows,
        rowClass: (r) => [r.isUs ? "is-us" : null, `span-${r.span}`].filter(Boolean).join(" "),
        caption: `${text(round.round)} games`,
      })));
    }
    parts.push(el("div", { class: "bracket", style: { "--rounds": String(tables.length) } }, tables));
    parts.push(note("Seeds in parentheses, as the committee placed the field. Away team first; the score reads away-home."));
  }
  if (rankings.length) {
    parts.push(el("div", {}, el("h4", { class: "d2-head" }, `Committee rankings${isNum(data.week) ? `, week ${data.week}` : ""}`), statTable({
      compact: true,
      columns: [{ key: "rank", label: "CFP rank", sortable: true }, { key: "school", label: "Team", kind: "text", team: true, sub: "conference" }],
      rows: rankings,
      sort: { key: "rank", dir: "ascending" },
      rowClass: (r) => (r.isUs ? "is-us" : null),
      maxHeight: 520,
      caption: "College Football Playoff committee rankings",
    })));
    if (!isNum(data.usRank)) parts.push(note(`${text(teamName)} is not in the committee's Top 25.`));
  }
  return el("div", { class: "d2" }, parts);
}

export function playoffSummary(p, teamName = usSchool()) {
  if (!p || typeof p !== "object") return "";
  const rounds = records(p.rounds);
  const ours = rounds.flatMap((r) => records(r.games).filter((g) => g.isUs === true).map(() => text(r.round)));
  if (ours.length) return `${text(teamName)}: ${ours.join(", ")}`;
  return isNum(p.usRank) ? `${text(teamName)} #${p.usRank} in the committee's rankings` : `${text(teamName)} unranked by the committee`;
}
