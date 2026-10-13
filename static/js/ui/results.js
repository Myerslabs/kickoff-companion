// Expectations and results (the Prompts phase, wave B, owner 2026-10-13: the Pre-Game Program locked at kickoff, then
// "an identical post-game program that is just the result of the game, like a pretest, post test"). On a finished game's
// program, the first band after the cover: what the program said at kickoff beside what the game did. The line against
// the margin (and who covered), the win probability against who won, each team's season numbers against its game
// numbers, and each player to watch's season line against his game line. Expectations come from the locked file
// (/api/program/<id>/locked), results from the final box the program already carries.
//
//   resultsBand({ locked, data })   the band; locked null: a band that says the program was not locked for this game
//   resultRows(locked, data)        { measures: [{ label, us: { expected, result }, them: {...} }], players: [...] } (tests)

import { DASH, el, fmtNum, fmtStat, isNum, obj, str, text } from "./dom.js";
import { band, note } from "./states.js";

const PAIRS = [
  // profile key -> the box's number, from the team's own side; defense keys read the other team's box
  { key: "ppg", label: "Points", result: (box) => box.points, fmt: "0f" },
  { key: "ypg", label: "Yards", result: (box) => box.totalYards, fmt: "0f" },
  { key: "pass_ypg", label: "Pass yards", result: (box) => box.netPassingYards, fmt: "0f" },
  { key: "rush_ypg", label: "Rush yards", result: (box) => box.rushingYards, fmt: "0f" },
  { key: "third", label: "Third down", result: (box) => (isNum(box.thirdDown?.made) && isNum(box.thirdDown?.of) && box.thirdDown.of > 0 ? box.thirdDown.made / box.thirdDown.of : null), fmt: "pct" },
  { key: "to_lost_pg", label: "Turnovers", result: (box) => box.turnovers, fmt: "0f" },
];

function rowValue(rows, key) {
  const row = (Array.isArray(rows) ? rows : []).find((r) => r && typeof r === "object" && r.key === key);
  return row && isNum(row.value) ? { value: row.value, format: str(row.format) ? row.format : "1f", label: str(row.label) ? row.label : key } : null;
}

function show(value, fmt) {
  return isNum(value) ? fmtStat(value, fmt || "1f") : DASH;
}

/** The game line from the final box's player rows: {category: [{playerId, name, stats}]}. */
function gameLine(players, category, stat, playerId) {
  const rows = obj(players)[category];
  const row = (Array.isArray(rows) ? rows : []).find((r) => r && typeof r === "object" && String(r.playerId) === String(playerId));
  const value = row ? obj(row.stats)[stat] : null;
  return isNum(value) ? value : null;
}

export function resultRows(locked, data) {
  const L = obj(locked);
  const d = obj(data);
  const final = obj(d.final);
  const usBox = obj(final.us);
  const themBox = obj(final.them);
  const measures = PAIRS.map((pair) => {
    const us = rowValue(obj(L.profile).us, pair.key);
    const them = rowValue(obj(L.profile).them, pair.key);
    return {
      label: pair.label,
      hint: us?.label || them?.label || pair.label,
      us: { expected: show(us?.value, us?.format || pair.fmt), result: show(pair.result(usBox), pair.fmt) },
      them: { expected: show(them?.value, them?.format || pair.fmt), result: show(pair.result(themBox), pair.fmt) },
    };
  }).filter((m) => m.us.expected !== DASH || m.them.expected !== DASH || m.us.result !== DASH || m.them.result !== DASH);
  const players = [];
  for (const row of Array.isArray(L.leaders) ? L.leaders : []) {
    if (!row || typeof row !== "object") continue;
    for (const side of ["us", "them"]) {
      const p = obj(row[side]);
      if (!str(p.player)) continue;
      const line = gameLine(obj(final.players)[side], str(row.category) ? row.category : "", str(row.stat) ? row.stat : "", p.playerId);
      players.push({ side, label: str(row.label) ? row.label : text(row.stat), player: p.player, playerId: p.playerId, position: str(p.position) ? p.position : null, season: isNum(p.value) ? fmtNum(p.value) : DASH, game: isNum(line) ? fmtNum(line) : DASH });
    }
  }
  return { measures, players };
}

/** The line against the margin: who was favored by how much, who won by how much, who covered. */
function lineVerdict(locked, data) {
  const L = obj(locked);
  const g = obj(obj(data).game);
  const usAbbr = str(obj(L.us).abbreviation) ? L.us.abbreviation : "Us";
  const themAbbr = str(obj(L.them).abbreviation) ? L.them.abbreviation : "Them";
  const line = obj(L.line);
  const expected = str(line.formatted) ? line.formatted : isNum(line.spread) ? `${L.homeIsUs ? usAbbr : themAbbr} ${line.spread > 0 ? "+" : ""}${line.spread}` : DASH;
  const margin = isNum(g.usPoints) && isNum(g.themPoints) ? g.usPoints - g.themPoints : null;
  const result = margin === null ? DASH : margin === 0 ? "Tie" : margin > 0 ? `${usAbbr} by ${margin}` : `${themAbbr} by ${-margin}`;
  let covered = null;
  if (margin !== null && isNum(line.spread)) {
    const usSpread = L.homeIsUs === false ? -line.spread : line.spread; // CFBD's spread is the home team's; negative favors it
    const against = margin + usSpread; // > 0: we beat the number
    covered = against === 0 ? "a push" : against > 0 ? `${usAbbr} covered` : `${themAbbr} covered`;
  }
  const wp = obj(L.pregame).usWinProbability;
  return { expected, result, covered, winProbability: isNum(wp) ? `${Math.round(wp * 100)}% ${usAbbr}` : DASH, winner: margin === null ? DASH : margin === 0 ? "Tie" : margin > 0 ? `${usAbbr} won` : `${themAbbr} won` };
}

export function resultsBand({ locked, data, id = "program-results" } = {}) {
  if (!locked || typeof locked !== "object") {
    return band({ id, title: "Expectations and results", collapsible: false, foldable: true, summary: "not locked", state: { status: "empty", message: "This program was not locked at kickoff, so there is nothing to hold the result against. The next game's program locks by itself when it kicks off." } });
  }
  const d = obj(data);
  const L = obj(locked);
  const usAbbr = str(obj(L.us).abbreviation) ? L.us.abbreviation : "Us";
  const themAbbr = str(obj(L.them).abbreviation) ? L.them.abbreviation : "Them";
  const { measures, players } = resultRows(locked, d);
  const verdict = lineVerdict(locked, d);
  const head = (cells) => el("thead", {}, el("tr", {}, cells.map(([label, cls]) => el("th", { scope: "col", class: cls || null }, label))));
  const cell = (value, cls) => el("td", { class: cls || null }, text(value));
  const game = el(
    "table",
    { class: "stat-table results__table", "aria-label": "The game against the program's expectations" },
    head([["", "txt"], ["Expected", null], ["Result", null]]),
    el("tbody", {},
      el("tr", {}, el("th", { scope: "row", class: "txt" }, "The line"), cell(verdict.expected), cell(verdict.covered ? `${verdict.result} (${verdict.covered})` : verdict.result)),
      el("tr", {}, el("th", { scope: "row", class: "txt" }, "Win probability"), cell(verdict.winProbability), cell(verdict.winner)),
    ),
  );
  const teams = measures.length
    ? el(
        "table",
        { class: "stat-table results__table", "aria-label": "Season numbers against the game's" },
        head([["", "txt"], [`${usAbbr} season`, null], [`${usAbbr} game`, null], [`${themAbbr} season`, null], [`${themAbbr} game`, null]]),
        el("tbody", {}, measures.map((m) => el("tr", {}, el("th", { scope: "row", class: "txt", title: m.hint }, m.label), cell(m.us.expected), cell(m.us.result, "results__result"), cell(m.them.expected), cell(m.them.result, "results__result")))),
      )
    : null;
  const watch = players.length
    ? el(
        "table",
        { class: "stat-table results__table", "aria-label": "Players to watch: the season line against the game line" },
        head([["Player", "txt"], ["", "txt"], ["Season", null], ["This game", null]]),
        el("tbody", {}, players.map((p) => el("tr", { class: p.side === "us" ? "results__us" : "results__them" }, el("th", { scope: "row", class: "txt" }, `${p.player}${p.position ? ` (${p.position})` : ""}`), el("td", { class: "txt" }, p.label), cell(p.season), cell(p.game, "results__result")))),
      )
    : null;
  return band({
    id,
    title: "Expectations and results",
    collapsible: false,
    foldable: true,
    summary: `locked at kickoff · ${verdict.result}`,
    state: { status: "ready" },
    body: () => el("div", { class: "results" }, note("What the program said at kickoff, beside what the game did. A season number is a per-game average; a player's season line is his total."), game, teams, watch, obj(L.notes).author ? el("p", { class: "note" }, `The notes were by ${text(L.notes.author)}.`) : null),
  });
}
