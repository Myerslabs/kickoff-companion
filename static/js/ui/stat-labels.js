// Stat column order and plain labels (Phase 16, stream PEOPLE: LRP-06, bug 7). DOM-free, so Node tests
// read it directly.
//
// CFBD sends each stat line's keys in alphabetical order (passing: ATT, COMPLETIONS, INT, PCT, TD, YDS, YPA),
// so taking "the first four keys" showed INT but no TD on Passing yards, and dropped TFL from Sacks. Here
// every Leaders board and every player-card category has a curated order and short, plain labels. The
// labels are the ones stream NV aliases in the glossary (Cmp, Att, Y/A, Car, Y/C, Rec, Y/R, Tkl, Hurries,
// No., Inside 20, Touchbacks), so the stat hints still mark them. Unknown boards and categories fall back to
// the old behaviour: the first four keys, under their CFBD names.
//
//   boardDetail(board, rows)            detail columns for a Leaders board: [{ key, label, labelMid, labelShort, format, size }]
//                                       (tables wave 3: size is the smallest table size that still shows the column, from
//                                       BOARD_SIZES; a column with no size shows at every size)
//   categoryColumns(category, keys, { log })  the player card's columns for a stat category, in reading order:
//                                       [{ key, label, labelMid, labelShort, format, size }] (tables wave 3: size from
//                                       CATEGORY_SIZES for the Stats tab's seasons, GAME_SIZES with { log: true } for the
//                                       Game log)
//   statLabel(key, category)            one plain label ("COMPLETIONS" -> "Cmp", PCT -> "Comp %" or "FG %")
//   statFormat(key, category)           "pct", "1f" or "0f"
//   categoryTitle(category)             "defensive" -> "Defense", "kickReturns" -> "Kick returns"
//   trendKey(category)                  the stat a category's sparkline follows (pass, rush, receiving yards, tackles)
//   normalizeStat(key, value)           a box-score percentage sent as 100.0 becomes 1.0, like the season lines
//   plainChip(text)                     "64 ATT" -> "64 Att" for the impact cards' stat chips

const LABELS = {
  COMPLETIONS: "Cmp",
  ATT: "Att",
  "C/ATT": "C/Att",
  YDS: "Yds",
  YPA: "Y/A",
  TD: "TD",
  INT: "INT",
  QBR: "QBR",
  CAR: "Car",
  YPC: "Y/C",
  LONG: "Long",
  REC: "Rec",
  YPR: "Y/R",
  AVG: "Avg",
  TOT: "Tkl",
  SOLO: "Solo",
  TFL: "TFL",
  SACKS: "Sacks",
  "QB HUR": "Hurries",
  PD: "PD",
  FGM: "FGM",
  FGA: "FGA",
  FG: "FG",
  XPM: "XPM",
  XPA: "XPA",
  XP: "XP",
  PTS: "Pts",
  NO: "No.",
  YPP: "Avg",
  "IN 20": "Inside 20",
  TB: "Touchbacks",
  FUM: "Fum",
  LOST: "Lost",
};

const RATES = /^(YPA|YPC|YPR|AVG|YPP|QBR)$/i;

// Tables wave 3 (owner 2026-10-10): the shorter words of a detail head that has them ("Inside 20" is "In 20" at small).
const LABEL_FORMS = {
  "IN 20": { labelShort: "In 20" },
  TB: { labelMid: "TB", labelShort: "TB" },
};

// Leaders boards: the detail columns after the board's own stat, in reading order.
const BOARD_ORDER = {
  "passing:YDS": ["COMPLETIONS", "ATT", "YPA", "TD", "INT"],
  "rushing:YDS": ["CAR", "YPC", "TD", "LONG"],
  "receiving:YDS": ["REC", "YPR", "TD", "LONG"],
  "defensive:TOT": ["SOLO", "TFL", "SACKS", "QB HUR", "PD"],
  "defensive:SACKS": ["TFL", "QB HUR", "TOT", "SOLO"],
  "interceptions:INT": ["YDS", "AVG", "TD"],
  "kicking:FGM": ["FGA", "PCT", "LONG", "XPM", "PTS"],
  "punting:YPP": ["NO", "YDS", "In 20", "TB", "LONG"],
};

// Tables wave 3 (owner 2026-10-10): each Leaders board's detail columns by the smallest table size that still shows them
// ("large" or "medium"; a column not listed shows at every size). A phone keeps the details that say the most (passing
// TD and INT; a punter's punts), medium adds the next, large shows every one. The server's own detailColumns (play
// value, usage, the adjusted boards) are sized here too, by their keys. Measured 2026-10-11 on a phone (390 px): every
// sortable column takes at least 57 px at small, so a board holds four details at most beside the place, the name and
// the value; passing's yards per attempt waits for medium.
const BOARD_SIZES = {
  "passing:YDS": { COMPLETIONS: "large", ATT: "medium", YPA: "medium" },
  "rushing:YDS": { YPC: "medium", LONG: "large" },
  "receiving:YDS": { YPR: "medium", LONG: "large" },
  "defensive:TOT": { SOLO: "large", "QB HUR": "large", PD: "medium" },
  "defensive:SACKS": { "QB HUR": "medium", TOT: "medium", SOLO: "large" },
  "interceptions:INT": { AVG: "medium" },
  "kicking:FGM": { LONG: "medium", XPM: "large", PTS: "medium" },
  "punting:YPP": { YDS: "large", "IN 20": "medium", TB: "large", LONG: "medium" },
  "ppa:all": { PASS: "medium", RUSH: "medium" },
  "usage:overall": { THIRDDOWN: "medium" },
};

/** The size of one detail column on a board ("large", "medium" or null for every size). */
function detailSize(board, key) {
  const sizes = BOARD_SIZES[typeof board?.id === "string" ? board.id : ""];
  const size = sizes ? sizes[upper(key)] : null;
  return size === "large" || size === "medium" ? size : null;
}

/** A detail column with its sizes: the label's shorter words and the size that still shows it. */
function sized(board, column) {
  const forms = LABEL_FORMS[upper(column.key)] || {};
  return { ...column, labelMid: forms.labelMid || null, labelShort: forms.labelShort || null, size: detailSize(board, column.key) };
}

// The player card: season lines (CFBD's season keys) and box-score lines (the game log's keys) together;
// a table keeps only the keys it has, in this order, then any others it has.
const CATEGORY_ORDER = {
  passing: ["COMPLETIONS", "ATT", "C/ATT", "PCT", "YDS", "YPA", "AVG", "TD", "INT", "QBR"],
  rushing: ["CAR", "YDS", "YPC", "AVG", "TD", "LONG"],
  receiving: ["REC", "YDS", "YPR", "AVG", "TD", "LONG"],
  defensive: ["TOT", "SOLO", "TFL", "SACKS", "QB HUR", "PD", "TD"],
  interceptions: ["INT", "YDS", "AVG", "TD"],
  kicking: ["FGM", "FGA", "FG", "PCT", "LONG", "XPM", "XPA", "XP", "PTS"],
  punting: ["NO", "YDS", "YPP", "AVG", "In 20", "TB", "LONG"],
  kickReturns: ["NO", "YDS", "AVG", "TD", "LONG"],
  puntReturns: ["NO", "YDS", "AVG", "TD", "LONG"],
  fumbles: ["FUM", "LOST", "REC"],
};

// Tables wave 3 (owner 2026-10-10): the player card's columns by the smallest table size that still shows them, per category
// (a key not listed shows at every size). The Stats tab's seasons (CFBD's season keys): small keeps what says the season
// (passing's attempts, completion rate, yards, yards per attempt, touchdowns and interceptions; a back's carries, yards,
// average and touchdowns), medium adds the next (completions, the long, solo tackles, hurries, passes defended, the
// kicker's tries), and large shows the rest (QBR, a defender's touchdowns, a punter's touchbacks).
const CATEGORY_SIZES = {
  passing: { COMPLETIONS: "medium", AVG: "medium", QBR: "large" },
  rushing: { LONG: "medium" },
  receiving: { LONG: "medium" },
  defensive: { SOLO: "medium", "QB HUR": "medium", PD: "medium", TD: "large" },
  interceptions: { AVG: "medium" },
  kicking: { PCT: "medium", LONG: "medium", XPM: "medium", XPA: "medium" },
  punting: { YDS: "medium", LONG: "medium", TB: "large" },
  kickReturns: { LONG: "medium" },
  puntReturns: { LONG: "medium" },
};

// The Game log (the box score's keys) carries three columns of its own before the stats (Wk, Opp, Result), so it holds fewer
// stats. Measured 2026-10-11 in headless Edge: a sortable column takes at least 57 px at small (its 44 px press target), so a
// phone's card (389 px) holds Wk, Opp ("at DT") and four stats, the Result waiting for medium (views/player.js); the 600 px
// card holds the Result and the same four at medium (about 570 px with whole school names and the hints), and large adds the
// rest (passing's yards per attempt and QBR, a back's long, a defender's solo tackles, hurries, passes defended and
// touchdowns, a punter's yards, touchbacks and long). A defender's medium is the Result and three: on a Windows screen the
// card's scroll bar leaves its tables 584 px, and a fourth stat with a long school name needs about 590.
const GAME_SIZES = {
  passing: { AVG: "large", QBR: "large" },
  rushing: { LONG: "large" },
  receiving: { LONG: "large" },
  defensive: { SOLO: "large", "QB HUR": "large", PD: "large", TD: "large" },
  kicking: { PCT: "medium", LONG: "large" },
  punting: { YDS: "large", TB: "large", LONG: "large" },
  kickReturns: { LONG: "large" },
  puntReturns: { LONG: "large" },
};

/** The size of one of the card's columns ("large", "medium" or null for every size). */
function categorySize(category, key, log = false) {
  const sizes = (log ? GAME_SIZES : CATEGORY_SIZES)[typeof category === "string" ? category : ""];
  const size = sizes ? sizes[upper(key)] : null;
  return size === "large" || size === "medium" ? size : null;
}

const TITLES = {
  passing: "Passing",
  rushing: "Rushing",
  receiving: "Receiving",
  defensive: "Defense",
  interceptions: "Interceptions",
  kicking: "Kicking",
  punting: "Punting",
  kickReturns: "Kick returns",
  puntReturns: "Punt returns",
  fumbles: "Fumbles",
};

// The sparkline beside a category heading on the Stats tab (GX-13 restrained, LRP-16 c).
const TRENDS = {
  passing: { key: "YDS", label: "pass yds" },
  rushing: { key: "YDS", label: "rush yds" },
  receiving: { key: "YDS", label: "rec yds" },
  defensive: { key: "TOT", label: "tackles" },
};

function upper(key) {
  return String(key ?? "").trim().toUpperCase();
}

function isKicking(category) {
  return String(category || "").toLowerCase() === "kicking";
}

/** A plain label for one stat key. PCT is completions in passing and field goals made in kicking. */
export function statLabel(key, category) {
  const k = upper(key);
  if (!k) return "–";
  if (k === "PCT") return isKicking(category) ? "FG %" : "Comp %";
  return LABELS[k] || String(key).trim();
}

export function statFormat(key, category) {
  const k = upper(key);
  if (k === "PCT") return "pct";
  if (RATES.test(k)) return "1f";
  if (k === "SACKS" || (k === "TFL" && String(category || "").toLowerCase() === "defensive")) return "1f"; // halves count
  return "0f";
}

export function categoryTitle(category) {
  const c = typeof category === "string" ? category.trim() : "";
  if (!c) return "Stats";
  return TITLES[c] || c.charAt(0).toUpperCase() + c.slice(1);
}

export function trendKey(category) {
  return TRENDS[typeof category === "string" ? category : ""] || null;
}

function ordered(keys, order) {
  const list = [...new Set((Array.isArray(keys) ? keys : []).filter((k) => typeof k === "string" && k.trim()))];
  const byUpper = new Map(list.map((k) => [upper(k), k]));
  const out = [];
  for (const want of order) {
    const hit = byUpper.get(upper(want));
    if (hit !== undefined && !out.includes(hit)) out.push(hit);
  }
  for (const k of list) if (!out.includes(k)) out.push(k);
  return out;
}

/** The player card's columns for one category, in reading order: [{ key, label, labelMid, labelShort, format, size }]
 *  (the label's shorter words and the smallest table size that still shows the column, tables wave 3; { log: true } sizes
 *  them for the Game log). */
export function categoryColumns(category, keys, { log = false } = {}) {
  const order = CATEGORY_ORDER[typeof category === "string" ? category : ""] || [];
  return ordered(keys, order).map((key) => {
    const forms = LABEL_FORMS[upper(key)] || {};
    return { key, label: statLabel(key, category), labelMid: forms.labelMid || null, labelShort: forms.labelShort || null, format: statFormat(key, category), size: categorySize(category, key, log === true) };
  });
}

/**
 * The Leaders detail columns for a board. The server's own detailColumns win (play value, usage, the
 * adjusted boards); a known board takes its curated order (only the keys some row has); an unknown board
 * falls back to the first four keys under their CFBD names, as before.
 */
export function boardDetail(board, rows) {
  if (!board || typeof board !== "object") return [];
  if (Array.isArray(board.detailColumns)) {
    return board.detailColumns.filter((c) => c && typeof c === "object" && typeof c.key === "string").map((c) => sized(board, { key: c.key, label: typeof c.label === "string" && c.label ? c.label : statLabel(c.key, board.category), format: typeof c.format === "string" ? c.format : "0f" }));
  }
  const seen = [];
  for (const row of Array.isArray(rows) ? rows : []) {
    const detail = row && typeof row === "object" && row.detail && typeof row.detail === "object" ? row.detail : {};
    for (const k of Object.keys(detail)) if (!seen.includes(k)) seen.push(k);
  }
  const order = BOARD_ORDER[typeof board.id === "string" ? board.id : ""];
  if (!order) return seen.slice(0, 4).map((key) => sized(board, { key, label: upper(key) === "PCT" ? statLabel(key, board.category) : key, format: statFormat(key, board.category) }));
  const have = new Map(seen.map((k) => [upper(k), k]));
  return order.filter((k) => have.has(upper(k))).map((k) => {
    const key = have.get(upper(k));
    return sized(board, { key, label: statLabel(key, board.category), format: statFormat(key, board.category) });
  });
}

/** Box scores send percentages as 100.0; the season lines as 1.0. One scale for both. */
export function normalizeStat(key, value) {
  if (upper(key) === "PCT" && typeof value === "number" && Number.isFinite(value) && value > 1.5) return value / 100;
  return value;
}

/** "64 ATT" -> "64 Att", "3 QB HUR" -> "3 Hurries"; anything else stays as it is. */
export function plainChip(chip) {
  if (typeof chip !== "string") return "";
  const m = /^([−+-]?[\d.,]+%?)\s+(.+)$/.exec(chip.trim());
  if (!m) return chip.trim();
  const label = LABELS[upper(m[2])];
  return label ? `${m[1]} ${label}` : chip.trim();
}
