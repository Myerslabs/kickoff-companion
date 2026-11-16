// Every player's stats for the season in review (the season line's Wave 7; owner 2026-11-15, Board 5
// "Build as drawn, but make sure there are more players stats, at least every
// starter"). From /api/season/players (app/services/season_players.py): every starter of the latest depth chart, the linemen too,
// with his season line where CFBD keeps one; then every player with a stat line, a table a category, best first. A name opens
// his card.
//
//   playerBands(data, { onPlayer })   { starters: band | null, players: band | null }
//   statText(value, key)              one figure as the tables show it (a rate as a percent, a half sack as .5)

import { DASH, el, fmtPct, isNum, records, text } from "./dom.js";
import { band, note } from "./states.js";
import { statTable } from "./stat-table.js";

const RATES = new Set(["PCT"]);
const AVERAGES = new Set(["YPA", "YPC", "YPR", "AVG", "YPP"]);
// the columns every width keeps; the rest show where there is room (shortened on a phone, never cut: 1.40.8)
const KEEP = new Set(["YDS", "TD", "INT", "TOT", "TFL", "SACKS", "FGM", "FGA", "PTS", "NO", "REC", "CAR", "FUM", "LOST"]);

/** One figure as the tables show it: a rate as a percent to one decimal, an average to one, a count whole (a half sack .5). */
export function statText(value, key) {
  if (!isNum(value)) return DASH;
  if (RATES.has(key)) return fmtPct(value, 1);
  if (AVERAGES.has(key)) return value.toFixed(1);
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function chartWords(chart) {
  if (!chart || typeof chart !== "object") return "the latest depth chart";
  const week = isNum(chart.week) ? `Week ${chart.week}` : "the latest game";
  return `the depth chart for ${week}${chart.opponent ? ` against ${text(chart.opponent)}` : ""}`;
}

function startersBand(data, onPlayer) {
  const starters = records(data.starters);
  if (!starters.length) return null;
  const rows = starters.map((s, i) => ({
    n: i + 1,
    unit: s.unit || "",
    slot: s.slot || "",
    number: isNum(s.number) ? s.number : null,
    name: s.name || DASH,
    playerId: s.playerId || null,
    // shortened, never cut (owner 2026-11-15, 1.40.8: "avoid cutting anything off, and instead shortening the data"): the first
    // figure always, the rest in a column that shows only where there is room
    line: Array.isArray(s.chips) ? s.chips.filter((c) => typeof c === "string" && c.trim())[0] || "" : "",
    more: Array.isArray(s.chips) ? s.chips.filter((c) => typeof c === "string" && c.trim()).slice(1).join(" · ") : "",
  }));
  return band({
    id: "review-starters",
    title: "The starters",
    collapsible: false,
    foldable: true,
    summary: `${rows.length} from ${chartWords(data.chart)}`,
    state: { status: "ready" },
    body: () => el(
      "div",
      {},
      statTable({
        compact: true,
        sizes: true,
        columns: [
          { key: "unit", label: "Unit", kind: "text", size: "large" },
          { key: "slot", label: "Pos", kind: "text" },
          { key: "number", label: "#", dim: true, size: "medium" },
          { key: "name", label: "Player", kind: "text" },
          { key: "line", label: "Season", kind: "text", render: (row) => (row.line ? row.line : el("span", { class: "dim" }, "no stat line")) },
          { key: "more", label: "And", kind: "text", size: "large", render: (row) => row.more || "" },
        ],
        rows,
        sort: { key: "n", dir: "ascending" },
        onRowTap: onPlayer ? (row) => onPlayer(row) : undefined, // rollover R2: a past season's names stay plain
        canTap: (row) => typeof row.playerId === "string" && row.playerId !== "",
        caption: "The starters",
      }),
      el("p", { class: "note" }, `Every slot's first name on ${chartWords(data.chart)}. CFBD keeps no stat line for a lineman.`),
    ),
  });
}

function playersBand(data, onPlayer) {
  const tables = records(data.categories).filter((t) => records(t.rows).length && records(t.columns).length);
  if (!tables.length) {
    return band({ id: "review-players", title: "Every player's stats", collapsible: false, foldable: true, state: { status: "ready" }, body: () => note("No player of ours has a stat line yet this season.", { kind: "empty" }) });
  }
  const count = new Set(tables.flatMap((t) => records(t.rows).map((r) => r.playerId || r.name))).size;
  return band({
    id: "review-players",
    title: "Every player's stats",
    collapsible: false,
    foldable: true,
    summary: `${count} players with a stat line`,
    state: { status: "ready" },
    body: () => el(
      "div",
      { class: "review-players" },
      tables.map((t) => {
        const columns = records(t.columns).filter((c) => typeof c.key === "string");
        // the server's order: best first by the table's own stat (yards, tackles, points)
        const rows = records(t.rows).map((r) => ({ name: r.name || DASH, position: r.position || "", playerId: typeof r.playerId === "string" ? r.playerId : null, ...Object.fromEntries(columns.map((c) => [c.key, isNum(r.stats?.[c.key]) ? r.stats[c.key] : null])) }));
        return el(
          "section",
          { class: "review-players__table" },
          el("h3", { class: "review-players__head" }, text(t.title)),
          statTable({
            compact: true,
            sizes: true,
            columns: [
              { key: "name", label: "Player", kind: "text" },
              { key: "position", label: "Pos", kind: "text", size: "medium" },
              ...columns.map((c) => ({ key: c.key, label: text(c.label), ...(KEEP.has(c.key) ? {} : { size: "large" }), render: (row) => statText(row[c.key], c.key) })),
            ],
            rows,
            onRowTap: onPlayer ? (row) => onPlayer(row) : undefined, // rollover R2: a past season's names stay plain
            canTap: (row) => typeof row.playerId === "string" && row.playerId !== "",
            caption: text(t.title),
          }),
        );
      }),
    ),
  });
}

/** The two bands from the season's players answer; either is null when there is nothing for it. */
export function playerBands(data, { onPlayer = null } = {}) {
  const d = data && typeof data === "object" ? data : {};
  return { starters: startersBand(d, onPlayer), players: playersBand(d, onPlayer) };
}
