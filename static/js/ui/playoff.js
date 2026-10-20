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
  if (data.picture && typeof data.picture === "object") parts.push(pictureBlock(data.picture, teamName)); // the picture, at the bottom of the band (new bands at the bottom, 2026-10-13)
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
  const line = p.picture && typeof p.picture === "object" && p.picture.us && typeof p.picture.us.line === "string" ? p.picture.us.line : "";
  if (line) return line; // the picture's one line: "Swampwater Tech: the 7th seed, hosting (10) Red Clay"
  return isNum(p.usRank) ? `${text(teamName)} #${p.usRank} in the committee's rankings` : `${text(teamName)} unranked by the committee`;
}

// --- The playoff picture (owner 2026-10-20): if the season ended today, as a bracket ---------------------------------
// A deliberate exception to tables-only: "a playoff bracket, like in most sports tournaments". Four rounds; stacked in a
// narrow band, side by side with connector lines in a wide one (components.css .pic). The field's rules are the server's
// (app/services/playoff.py picture): the five highest-ranked conference leaders in, seven at large, straight seeding,
// seeds 1 to 4 with a bye, the first round at the higher seed's home.

function moveChip(side) {
  if (!isNum(side.seed)) return null;
  if (!isNum(side.lastSeed)) return el("span", { class: "pic__move pic__move--new", title: "Not in last week's picture" }, "new");
  if (side.lastSeed === side.seed) return null;
  const up = side.lastSeed > side.seed;
  const by = Math.abs(side.lastSeed - side.seed);
  return el("span", { class: `pic__move ${up ? "pic__move--up" : "pic__move--down"}`, title: `Was the ${side.lastSeed} seed last week` }, `${up ? "up" : "down"} ${by}`);
}

/** One line of a game box: the seed, the logo and name, the champion's conference, the move since last week. */
function picTeam(side, tbd) {
  if (!side || typeof side !== "object" || !school(side)) {
    return el("div", { class: "pic__team pic__team--tbd" }, el("span", { class: "pic__seed", "aria-hidden": "true" }, ""), el("span", { class: "pic__name" }, text(tbd || "To be decided")));
  }
  const name = school(side);
  return el(
    "div",
    { class: `pic__team${side.isUs ? " pic__team--us" : ""}` },
    el("span", { class: "pic__seed", title: `Seed ${isNum(side.seed) ? side.seed : DASH}` }, isNum(side.seed) ? String(side.seed) : DASH),
    el("span", { class: "pic__name" }, logoLink(name, side)),
    side.champion ? el("span", { class: "pic__champ", title: `${text(side.champion)} leader, in as a conference champion` }, text(side.conferenceShort || "champ")) : null,
    moveChip(side),
  );
}

function picGame(top, bottom, { slot, tbdTop, tbdBottom, classes = "" } = {}) {
  return el("div", { class: `pic__game${classes ? ` ${classes}` : ""}` }, slot ? el("div", { class: "pic__slot" }, slot) : null, picTeam(top, tbdTop), picTeam(bottom, tbdBottom));
}

function picRound(title, kind, children) {
  return el("div", { class: `pic__round pic__round--${kind}` }, el("h5", { class: "pic__head" }, title), el("div", { class: "pic__games" }, children));
}

const PIC_COLUMNS = [
  { key: "conference", label: "Conference", kind: "text" },
  { key: "school", label: "Leader today", kind: "text", render: (row) => logoLink(row.school, row), renderShort: (row) => teamAbbrLink(row.school, row.abbreviation) },
  { key: "rank", label: "Rank", labelShort: "Rk", order: true, render: (row) => (isNum(row.rank) ? `${row.rank}${row.rankBasis && row.rankBasis !== "poll" ? ` (${row.rankBasis})` : ""}` : DASH) },
  { key: "in", label: "Playoff", kind: "text", render: (row) => (row.in ? `in, the ${text(row.seed)} seed` : "out") },
];

export function pictureBlock(picture, teamName = usSchool()) {
  const p = picture && typeof picture === "object" ? picture : {};
  const b = p.bracket && typeof p.bracket === "object" ? p.bracket : {};
  const first = records(b.firstRound);
  const quarters = records(b.quarterfinals);
  const byeSeed = (q) => (q.home && isNum(q.home.seed) ? q.home.seed : null);
  const firstRound = first.map((g) => picGame(g.home, g.away, { slot: typeof g.label === "string" ? g.label : null, classes: g.home?.isUs || g.away?.isUs ? "pic__game--us" : "" }));
  const quarterGames = quarters.map((q, i) => picGame(q.home, null, { slot: "Quarterfinal", tbdBottom: first[i] ? `Winner of (${text(first[i].home?.seed)}) v (${text(first[i].away?.seed)})` : "First-round winner", classes: q.home?.isUs ? "pic__game--us" : "" }));
  const quarterPairs = [el("div", { class: "pic__pair" }, quarterGames.slice(0, 2)), el("div", { class: "pic__pair" }, quarterGames.slice(2, 4))];
  const semiGames = [0, 2].map((i) => picGame(null, null, { slot: "Semifinal", tbdTop: `Winner of the (${text(byeSeed(quarters[i] || {}))}) game`, tbdBottom: `Winner of the (${text(byeSeed(quarters[i + 1] || {}))}) game` }));
  const finalGame = picGame(null, null, { slot: "National championship", tbdTop: "Semifinal 1 winner", tbdBottom: "Semifinal 2 winner" });
  const bracket = el(
    "div",
    { class: "pic__bracket", role: "group", "aria-label": "The playoff bracket if the season ended today" },
    picRound("First round", "first", firstRound.length ? firstRound : [note("No field yet.")]),
    picRound("Quarterfinals", "quarter", quarterPairs),
    picRound("Semifinals", "semi", el("div", { class: "pic__pair" }, semiGames)),
    picRound("Championship", "final", finalGame),
  );
  const champions = records(p.champions).map((row) => ({ ...row, conference: text(row.conference), rank: isNum(row.rank) ? row.rank : null }));
  const names = (list) => records(list).map((t) => `(${isNum(t.seed) ? t.seed : isNum(t.rank) ? `#${t.rank}` : DASH}) ${text(school(t))}`).join(", ");
  const lastIn = names(p.lastFourIn);
  const firstOut = names(p.firstFourOut);
  const fmt = p.format && typeof p.format === "object" ? p.format : {};
  const line = p.us && typeof p.us.line === "string" ? p.us.line : "";
  return el(
    "div",
    { class: "pic" },
    el("h4", { class: "d2-head" }, `If the season ended today${isNum(p.week) ? `, by ${text(p.sourceLabel)} of week ${p.week}` : ""}`),
    line ? el("p", { class: "pic__line" }, line) : null,
    bracket,
    el("p", { class: "note" }, `${isNum(fmt.teams) ? `${fmt.teams} teams: ` : ""}the ${isNum(fmt.autoBids) ? fmt.autoBids : "five"} highest-ranked conference leaders are in, the rest at large, seeded by the ranking; seeds 1 to ${isNum(fmt.byes) ? fmt.byes : 4} have a bye; first-round games at the higher seed's home. A leader is the best conference record today, then conference wins, then the overall record. Teams outside the Top 25 are ordered by SP+.`),
    lastIn || firstOut ? el("p", { class: "note pic__edges" }, lastIn ? el("span", {}, el("b", {}, "Last four in: "), lastIn) : null, lastIn && firstOut ? " " : null, firstOut ? el("span", {}, el("b", {}, "First four out: "), firstOut) : null) : null,
    champions.length
      ? el("div", { class: "pic__champions" }, el("h5", { class: "pic__head" }, "Conference leaders today"), statTable({ compact: true, sizes: true, sortable: false, columns: PIC_COLUMNS, rows: champions, rowClass: (r) => (r.isUs ? "is-us" : null), caption: "Conference leaders if the season ended today" }))
      : null,
  );
}
