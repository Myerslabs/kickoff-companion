// The app's own numbers (FEAT-8, owner 2026-10-25: every team as deep as ours): one team's success rate, explosive plays,
// havoc and red-zone finishing, offense and defense with national ranks, then success by down and distance, from every
// play of every final game the nightly sweep has read (/api/numbers/<school>). The measure sits in the middle, offense
// on the left and defense on the right (design rule: comparison data pulled to the middle); rates are whole percents.
//
//   numbersBand(school, { id })   the band; it loads its own answer, so the page it sits on stays as fast as before
//   summaryRows(line, rankOf)     the first table's rows (exported for the tests)

import { fetchJson } from "../views/common.js";
import { DASH, el, fmtNum, isNum, text } from "./dom.js";
import { rankChip, statTable } from "./stat-table.js";
import { band, note } from "./states.js";

const pct = (value) => (isNum(value) ? `${Math.round(value * 100)}%` : DASH);
const per = (value) => (isNum(value) ? fmtNum(value, 2) : DASH);

const MEASURES = [ // label, path, format, the defense's word when it differs
  ["Success rate", "successRate", pct],
  ["Explosive plays (20+ yards)", "explosiveRate", pct],
  ["Havoc (TFL, sacks, takeaways)", "havocRate", pct, "Havoc made"],
  ["Red-zone touchdowns", "redZone.tdRate", pct],
  ["Red-zone points a trip", "redZone.pointsPerTrip", per],
];

function at(side, path) {
  let value = side;
  for (const part of path.split(".")) value = value && typeof value === "object" ? value[part] : undefined;
  return value;
}

export function summaryRows(line, rankOf = {}) {
  const off = line?.offense && typeof line.offense === "object" ? line.offense : {};
  const def = line?.defense && typeof line.defense === "object" ? line.defense : {};
  const cell = (side, name, path, format) => {
    const rank = side?.ranks && typeof side.ranks === "object" ? side.ranks[path] : null;
    const of = isNum(rankOf?.[`${name}.${path}`]) ? rankOf[`${name}.${path}`] : null;
    return el("span", { class: "numbers__cell" }, el("b", {}, format(at(side, path))), isNum(rank) ? rankChip(rank, of, { label: `${name} ${path}` }) : null);
  };
  return MEASURES.map(([label, path, format, defWord]) => ({
    key: path,
    measure: defWord ? `${label}; ${defWord} on defense` : label,
    offense: cell(off, "offense", path, format),
    defense: cell(def, "defense", path, format),
  }));
}

function downsRows(line) {
  const off = Array.isArray(line?.offense?.downs) ? line.offense.downs : [];
  const def = Array.isArray(line?.defense?.downs) ? line.defense.downs : [];
  const byKey = (list) => Object.fromEntries(list.filter((d) => d && typeof d === "object" && typeof d.key === "string").map((d) => [d.key, d]));
  const o = byKey(off);
  const d = byKey(def);
  const shown = (row) => (row && isNum(row.of) && row.of > 0 ? `${pct(row.rate)} (${isNum(row.made) ? row.made : DASH}/${row.of})` : DASH);
  return off.filter((row) => row && typeof row === "object" && typeof row.key === "string").map((row) => ({ key: row.key, measure: text(row.label), offense: shown(o[row.key]), defense: shown(d[row.key]) }));
}

const COLUMNS = [
  { key: "offense", label: "Offense", render: (row) => row.offense },
  { key: "measure", label: "", render: (row) => el("span", { class: "numbers__measure" }, row.measure) },
  { key: "defense", label: "Defense", render: (row) => row.defense },
];

export function numbersBand(school, { id = "numbers", bare = false } = {}) {
  // bare (the Season stop's The numbers, Wave 4): the body alone, no band of its own; the states as notes
  const host = el("div", { class: bare ? "numbers-bare" : null }, bare ? el("div", { class: "skel skel--block" }) : band({ id, title: "The app's numbers", collapsible: false, state: { status: "loading" }, skeleton: () => el("div", { class: "skel skel--block" }) }));
  if (typeof school !== "string" || !school) return null;
  fetchJson(`/api/numbers/${encodeURIComponent(school)}`)
    .then((envelope) => {
      const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
      const line = data.team && typeof data.team === "object" ? data.team : null;
      const games = isNum(line?.games) ? line.games : 0;
      if (bare) {
        host.replaceChildren(line && games ? numbersBody(school, line, data.rankOf) : note("The app reads every play of every final game each night; this team's numbers show after its first game is read.", { kind: "empty" }));
        return;
      }
      host.replaceChildren(band({
        id,
        title: "The app's numbers",
        collapsible: false,
        foldable: true,
        summary: games ? `${games} ${games === 1 ? "game" : "games"}, every play` : "after the first nightly sweep",
        state: { status: line && games ? "ready" : "empty" },
        emptyText: "The app reads every play of every final game each night; this team's numbers show after its first game is read.",
        body: () => numbersBody(school, line, data.rankOf),
      }));
    })
    .catch((error) => host.replaceChildren(bare ? note(`${text(error?.message || "no answer")}.`, { kind: "error" }) : band({ id, title: "The app's numbers", collapsible: false, state: { status: "error", message: `${text(error?.message || "no answer")}.` } })));
  return host;
}

function numbersBody(school, line, rankOf) {
  return el(
    "div",
    { class: "numbers" },
    statTable({ compact: true, columns: COLUMNS, rows: summaryRows(line, rankOf), caption: `${school}: the app's numbers` }),
    statTable({ compact: true, columns: COLUMNS, rows: downsRows(line), caption: `${school}: success by down and distance` }),
    note("The app's own count from CFBD's plays: a snap succeeds with half the distance on 1st down, 70% on 2nd, all of it on 3rd and 4th. Ranks are among FBS teams with 100 snaps or more; on defense the best rank allows the least."),
  );
}
