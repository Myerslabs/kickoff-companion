// The Leaders view (S6 to S9): every board with the four-way scope switch. Ours, versus the
// next opponent, conference top 10, national top 10. Our rows are marked in the wider scopes and
// our best player's rank shows in each board's summary. Row tap opens the player card.
//
// Phase 16 (stream PEOPLE):
//   LRP-01  our scope's national chip opens the board's national list, its conference chip the conference list;
//           each summary carries our best player's rank as a linked chip; the conference and national top 10 end
//           with a gap row and every one of ours below the cut, in a second tbody so the zebra never flips.
//           #leaders=<board>:<scope> (for example passing:YDS:national) opens that scope and scrolls to the
//           board, without overwriting the remembered scope: only a tap on the switch is remembered.
//   LRP-06  detail columns in a curated order with plain labels (ui/stat-labels.js).
//   LRP-10  the scope switch stays under the top bar; the next opponent's players carry the --opp edge in the
//           league lists; "vs opponent" sets ours beside the opponent (wave 3: on the two-team kit, every chip its own
//           column).
//   LRP-16b our and the vs-opponent scopes show a 28 px headshot (the local /media/headshot cache; the
//           number badge, abbreviation or initials when there is none) beside each name.
//
// Tables wave 3 (owner 2026-10-10, docs/03-DESIGN.md "Table sizes"): every board sizes itself by its own box.
//   Ours: # | Player (face and name; the name alone at small, stepping down, item 6) | Pos (large and medium, decision 1) | the value | FBS rank
//           (medium) | <conf> rank (large) | the details, each board's by the smallest size that still shows it
//           (ui/stat-labels.js BOARD_SIZES). The chips have their own columns (rule 3), never the value's cell.
//   The conference and national top 10: # (the list's own order: its chip at large and medium, a plain number at small,
//           decision 2) | Player | Pos and Team (large and medium, decision 1) | the value | FBS rank (the conference list,
//           medium) | the details.
//   vs opponent: the two-team kit, centered on the tug-of-war bar, a player column on each side (the face and name, the
//           name alone at small, stepping down; the position beside it from medium), each side's FBS rank (medium) and conference rank
//           (large, a conference opponent's only), the place in the middle; the school and mascot over each side at large.

import { confLabel, confName, usLabel, usName, usSchool } from "../identity.js";
import { DASH, el, fmtNum, fmtStat, isNum, personName, playerFace, recall, remember, text } from "../ui/dom.js";
import { nationalHref } from "../ui/national-link.js";
import { band, note, revealBand } from "../ui/states.js";
import { mountFlow, stopFlow } from "../ui/flow.js";
import { ownColumns, rankChip, statTable, statTableSkeleton } from "../ui/stat-table.js";
import { PPA_SCALE, twoTeamTable } from "../ui/two-team.js";
import { boardDetail, statLabel } from "../ui/stat-labels.js";
import { pollMs } from "../prefs.js";
import { combinedState, errorPanel, fetchJson, poller } from "./common.js";
import { openPlayer, pctLabel } from "./player.js";
import { GRADE_NOTE, gradedTable } from "../ui/grade.js";

// Public release Phase 7: the Top graded board, by position group, from /api/grades. It loads on its own (the
// grades read the national lists this page already caches) and keeps its answer per group between redraws.
const GRADE_GROUPS = [["QB", "QB"], ["RB", "RB"], ["WR", "WR"], ["TE", "TE"], ["DL", "DL"], ["LB", "LB"], ["DB", "DB"], ["PK", "K"], ["P", "P"]];
const GRADE_KEY = "leaders:gradeGroup";

function gradesBand(state) {
  const host = el("div", {});
  const draw = () => {
    const group = state.gradeGroup;
    const got = state.grades[group];
    const seg = el("div", { class: "seg", role: "group", "aria-label": "Position" }, GRADE_GROUPS.map(([id, label]) => el("button", { type: "button", "aria-pressed": id === group ? "true" : "false", onclick: () => { state.gradeGroup = id; remember(GRADE_KEY, id); draw(); load(); } }, label)));
    const data = got?.data || null;
    const rows = Array.isArray(data?.rows) ? data.rows : [];
    const beyond = Array.isArray(data?.beyond) ? data.beyond : [];
    const status = got?.error ? { status: "error", message: `${got.error}.` } : !got ? { status: "loading" } : rows.length ? { status: "ready" } : { status: "empty" };
    const basis = data?.basis === "production" ? "Production only: CFBD has no targets or snaps for this position." : data?.basis === "efficiency" ? "Efficiency and production." : "";
    host.replaceChildren(band({
      id: "leaders-grades",
      title: "Top graded",
      collapsible: false,
      foldable: true,
      summary: data && typeof data.groupName === "string" ? `${isNum(data.of) ? data.of : 0} FBS ${data.groupName} graded` : "",
      state: status,
      emptyText: "No player at this position has enough plays to grade yet.",
      body: () => el("div", {},
        el("div", { class: "leaders__scope" }, seg),
        gradedTable([...rows, ...beyond], { us: usSchool(), onTap: (row) => openPlayer(row.playerId, row), caption: "Top graded" }),
        el("p", { class: "note" }, GRADE_NOTE, basis ? ` ${basis}` : ""),
      ),
    }));
  };
  const load = async () => {
    const group = state.gradeGroup;
    try {
      const envelope = await fetchJson(`/api/grades?group=${encodeURIComponent(group)}&limit=25`);
      state.grades[group] = { data: envelope?.data && typeof envelope.data === "object" ? envelope.data : null };
    } catch (error) {
      state.grades[group] = { error: error?.message || "The grades did not load" };
    }
    if (state.gradeGroup === group) draw();
  };
  draw();
  if (!state.grades[state.gradeGroup]) load();
  return host;
}


// Labels read the identity when drawn: the mascot ("Mudpuppies") and the conference ("Biscuit Belt top 10").
const SCOPES = [
  { id: "team", label: () => usName() },
  { id: "opponent", label: () => "vs opponent" },
  { id: "conference", label: () => `${confLabel()} top 10` },
  { id: "national", label: () => "National top 10" },
];
const SCOPE_KEY = "leaders:scope";
const SCOPE_IDS = new Set(SCOPES.map((s) => s.id));
const SCOPE_ALIASES = { ours: "team", us: "team", vs: "opponent", conf: "conference", nat: "national" };
const LEAGUE = new Set(["conference", "national"]);

function scopeId(value) {
  if (typeof value !== "string") return null;
  const v = value.trim().toLowerCase();
  if (SCOPE_IDS.has(v)) return v;
  return SCOPE_ALIASES[v] || null;
}

/**
 * The route arg: "<board>:<scope>" ("passing:YDS:national", "ppa:all:conference"), the scope alone, a board
 * alone, or a board's list key ("board:passing:YDS"). Exported for the tests: { board, scope } with nulls.
 */
export function parseLeadersArg(arg) {
  if (typeof arg !== "string" || !arg.trim()) return { board: null, scope: null };
  let parts = arg.trim().split(":").filter(Boolean);
  if (parts[0] === "board") parts = parts.slice(1);
  let scope = null;
  if (parts.length && scopeId(parts[parts.length - 1])) scope = scopeId(parts.pop());
  else if (parts.length && scopeId(parts[0])) scope = scopeId(parts.shift());
  let board = parts.join(":") || null;
  if (board && !board.includes(":") && board.includes("-")) board = board.replace("-", ":"); // "passing-YDS"
  return { board: board && board.length <= 60 ? board : null, scope };
}

/** A board's band id: every ':' becomes '-' ("leaders-ppa-all"). */
function bandId(board) {
  return `leaders-${String(board?.id ?? "").replace(/[^A-Za-z0-9_-]/g, "-")}`;
}

/** The list a chip opens: the row's own list key, else the board's; null (a plain chip) when there is none. */
function listHref(row, board, { team, scope } = {}) {
  const metric = typeof row?.metric === "string" && row.metric ? row.metric : board?.metric;
  return nationalHref(metric, { team, scope: scope === "conference" ? "conference" : undefined });
}

function scopeRows(board, scope) {
  return (Array.isArray(board?.[scope]) ? board[scope] : []).filter((r) => r && typeof r === "object");
}

/** A board row with its detail spread under d_<key>, so a stat key can never shadow a row field; the player's name as the
 *  label its chips read out ("Keegan Crawford: 47 of 358"). */
function flat(row, extra) {
  const detail = row.detail && typeof row.detail === "object" ? row.detail : {};
  const name = typeof row.player === "string" && row.player.trim() ? row.player.trim() : null;
  const out = { ...row, label: name, ...extra };
  for (const [k, v] of Object.entries(detail)) out[`d_${k}`] = v;
  return out;
}

/** The board's details after its value, each with the smallest size that still shows it (wave 3). */
function detailColumns(board, rows) {
  return boardDetail(board, rows).map((c) => ({ key: `d_${c.key}`, label: /^PCT$/i.test(c.key) && !Array.isArray(board.detailColumns) ? pctLabel(board.category) : c.label, labelMid: c.labelMid, labelShort: c.labelShort, format: c.format, size: c.size }));
}

// The value's head in its three forms where the stat's own label is not a plain word (rule 5: PPA per play, never a
// mix of names); every other board's value keeps its stat's label at every size ("Yds", "Tkl", "Avg").
const VALUE_HEADS = { "ppa:all": ["PPA per play", "PPA/play", "PPA"] };

/** The board's value column: the stat's label, its own column (its ranks have theirs, rule 3). */
function valueColumn(board) {
  const forms = VALUE_HEADS[typeof board?.id === "string" ? board.id : ""];
  return { key: "value", label: forms ? forms[0] : statLabel(board.stat, board.category), labelMid: forms ? forms[1] : null, labelShort: forms ? forms[2] : null, format: board.format };
}

/** Ours ranked below a league list's cut, best first, with their place in that list. Exported for the tests. */
export function windowRows(board, scope) {
  if (!LEAGUE.has(scope)) return [];
  const listed = new Set(scopeRows(board, scope).map((r) => r.playerId));
  const rankKey = scope === "national" ? "nationalRank" : "conferenceRank";
  return scopeRows(board, "team")
    .filter((r) => isNum(r[rankKey]) && !listed.has(r.playerId))
    .sort((a, b) => a[rankKey] - b[rankKey])
    .map((r) => ({ ...r, isUs: true, rank: r[rankKey], windowRow: true }));
}

/** Move the window rows under a gap row in their own tbody (after the first draw and after every sort). */
function splitWindow(wrap, gapText, span) {
  const table = wrap?.querySelector?.("table");
  const main = table?.querySelector?.("tbody");
  if (!table || !main) return;
  const moved = main.querySelectorAll("tr.is-window");
  if (!moved.length) return;
  let tail = table.querySelector("tbody.stat-table__window");
  if (!tail) {
    tail = el("tbody", { class: "stat-table__window" });
    table.append(tail);
  }
  tail.replaceChildren(el("tr", { class: "gap-row" }, el("td", { class: "txt gap-row__cell", colspan: String(span) }, gapText)), ...moved);
}

/** A name with its 28 px face (our scope and vs opponent); the position has a column of its own (wave 3, decision 1: a
 *  fact once drawn under a name is its own column at large and medium, gone at small). The name is drawn in its four forms
 *  (item 6), so it steps down with the table. */
function who(row) {
  return el(
    "span",
    { class: "leader-who" },
    playerFace(row, { them: row.isUs === false, abbr: row.teamAbbr, size: 28 }),
    el("span", { class: "leader-who__text" }, el("span", { class: "leader-who__name" }, personName(row.player))),
  );
}

// final pass: a board's minimum in words ("5 punts"), never CFBD's key ("5 no")
const MINIMUM_WORDS = { NO: "punts", ATT: "attempts", CAR: "carries", REC: "catches", PLAYS: "plays", FGA: "field goal tries", TOT: "tackles" };

/** The player's columns: the name (with its face in our scope, the name alone at small; item 6: it steps down with the
 *  table) and the position beside it at large and medium (decision 1); a league list adds the team in a column of its own,
 *  also gone at small. */
function playerColumns(scope) {
  const name = { key: "player", label: "Player", kind: "text", person: true, sub: "position", subLabel: "Pos", render: scope === "team" ? who : undefined, renderShort: scope === "team" ? (row) => personName(row.player) : undefined };
  if (scope === "team") return [name];
  return [name, { key: "team", label: "Team", kind: "text", team: true, size: "medium" }];
}

/** Whether any row of the board carries a rank under this key (a board with no lists, usage, has no rank columns). */
function hasRank(rows, key) {
  return rows.some((row) => isNum(row?.[key]));
}

/**
 * The board's table for our scope and the league lists (wave 3, sized by its own box): our scope's # is our own order, a
 * plain number; a league list's # is the list's own order (its chip at large and medium, a plain number at small,
 * decision 2) linking to that list with the row's team marked. The FBS rank is its own column from medium (ours; the
 * conference list's), our conference rank at large.
 */
function leagueTable(board, scope, ctx) {
  const top = scopeRows(board, scope);
  const extra = windowRows(board, scope);
  const rows = [
    ...top.map((row, index) => flat(row, { place: scope === "team" ? index + 1 : row.rank })),
    ...extra.map((row) => flat(row, { place: row.rank })),
  ];
  const listScope = scope === "conference" ? "conference" : undefined;
  const place = scope === "team"
    ? { key: "place", label: "#", dim: true }
    : { key: "place", label: "#", kind: "rank", order: true, of: scope === "conference" ? "conferenceOf" : "nationalOf", link: (row) => listHref(row, board, { team: row.team, scope: listScope }) };
  const fbs = { key: "nationalRank", label: "FBS rank", labelMid: "FBS", kind: "rank", of: "nationalOf", size: "medium", link: (row) => listHref(row, board, { team: scope === "team" ? ctx.us : row.team }) };
  const conf = { key: "conferenceRank", label: `${confLabel()} rank`, kind: "rank", of: "conferenceOf", size: "large", link: (row) => listHref(row, board, { team: ctx.us, scope: "conference" }) };
  const columns = [
    place,
    ...playerColumns(scope),
    valueColumn(board),
    // the chips in columns of their own (rule 3): ours carry both, the conference list gains the FBS rank (owner 2026-10-10)
    scope !== "national" && hasRank(rows, "nationalRank") ? fbs : null,
    scope === "team" && hasRank(rows, "conferenceRank") ? conf : null,
    ...detailColumns(board, [...top, ...extra]),
  ].filter(Boolean);
  const rowClass = (row) => {
    const classes = [];
    if (row.isUs) classes.push("is-us");
    else if (ctx.opp && row.team === ctx.opp && LEAGUE.has(scope)) classes.push("is-next", "is-opp");
    if (row.windowRow) classes.push("is-window");
    return classes.join(" ") || null;
  };
  const gapText = `${text(ctx.us)} below the top ${top.length}`;
  const span = ownColumns(columns).length; // every column the table draws (the position its own), whichever size shows
  let wrap = null;
  wrap = statTable({
    compact: true,
    sizes: true,
    columns,
    rows,
    rowClass,
    onSort: () => splitWindow(wrap, gapText, span),
    onRowTap: (row) => openPlayer(row.playerId, row),
    caption: `${text(board.label)}, ${scope}`,
  });
  splitWindow(wrap, gapText, span);
  return el("div", { class: `leaders-table leaders-table--${scope}` }, wrap);
}

/** One team's side of a vs-opponent row: the player (face and name, the name alone at small, a button to his card), his
 *  position, the value, the FBS rank and, for a player ranked in our conference, the conference rank; a dash side when
 *  the team has no player at this place. */
function versusSide(row, board, team) {
  if (!row) return { value: null };
  const listed = (scope) => listHref(row, board, { team, scope });
  return {
    value: isNum(row.value) ? row.value : null,
    rank: isNum(row.nationalRank) ? row.nationalRank : null,
    of: isNum(row.nationalOf) ? row.nationalOf : null,
    href: listed(),
    conf: isNum(row.conferenceRank) ? { rank: row.conferenceRank, of: isNum(row.conferenceOf) ? row.conferenceOf : null, conference: confLabel(), href: listed("conference") } : null,
    who: who(row),
    whoName: typeof row.player === "string" ? row.player : null,
    whoSub: typeof row.position === "string" && row.position.trim() ? row.position.trim() : null,
    onWho: () => openPlayer(row.playerId, row),
  };
}

/**
 * Ours beside the next opponent (S7), place by place, on the two-team kit (wave 3, rule 9): centered on the tug-of-war
 * bar, each side's player outermost, then his position (from medium), his FBS rank (medium) and conference rank (large),
 * his value against the bar; the place in the middle. Every board is higher-is-more, so the bar leans to the bigger
 * number (on the usage board that is the bigger share, not a better player).
 */
function versusTable(board, ctx) {
  const us = scopeRows(board, "team");
  const them = scopeRows(board, "opponent");
  if (!us.length && !them.length) return null;
  const rows = Array.from({ length: Math.max(us.length, them.length) }, (_, i) => ({
    label: String(i + 1),
    format: typeof board.format === "string" ? board.format : "0f",
    higherIsBetter: true,
    // wave 3 review: a signed per-play value (PPA, adjusted EPA) leans by its gap on the PPA scale when a side has no
    // national rank (a backup under the national cut), never by the share, which made +0.05 against -0.03 a full lean
    scale: board.category === "ppa" || board.format === "+2f" ? PPA_SCALE : undefined,
    us: versusSide(us[i] || null, board, ctx.us),
    them: versusSide(them[i] || null, board, ctx.opp),
  }));
  return el(
    "div",
    { class: "leaders-table leaders-table--versus" },
    twoTeamTable({
      rows,
      usAbbr: text(ctx.usAbbr),
      themAbbr: text(ctx.oppAbbr),
      usTeam: ctx.us,
      themTeam: ctx.opp,
      usName: ctx.usFull,
      themName: ctx.oppFull,
      usConf: confLabel(),
      themConf: confLabel(),
      centered: true,
      labelHead: "#",
      caption: `${text(board.label)}, ${text(ctx.usAbbr)} and ${text(ctx.oppAbbr)}`,
    }),
    them.length ? null : note(`No ${text(ctx.oppAbbr)} lines on this board yet.`),
  );
}

function emptyWhy(board, scope, ctx) {
  if (scope === "opponent" && !ctx.opp) return "The next opponent is not known yet.";
  if (LEAGUE.has(scope) && board.conferenceOf == null && board.nationalOf == null) return "Team and opponent only for this board.";
  if (board.minimum && typeof board.minimum === "object" && isNum(board.minimum.value)) return `No one has ${board.minimum.value} ${MINIMUM_WORDS[text(board.minimum.stat)] || text(board.minimum.stat).toLowerCase()} yet.`;
  return "No stat lines yet.";
}

function boardTable(board, scope, ctx) {
  if (scope === "opponent") return ctx.opp ? versusTable(board, ctx) || note(emptyWhy(board, scope, ctx)) : note(emptyWhy(board, scope, ctx));
  if (!scopeRows(board, scope).length) return note(emptyWhy(board, scope, ctx));
  return leagueTable(board, scope, ctx);
}

/** The band summary: our best player's rank as a chip that opens the list it ranks in. Exported for the tests. */
export function summaryFor(board, scope, ctx = {}) {
  const best = board?.usBest && typeof board.usBest === "object" ? board.usBest : {};
  const conference = text(ctx.conference || confName());
  const chip = (rank, of, listScope) => rankChip(rank, of, { href: nationalHref(board?.metric, { team: ctx.us, scope: listScope }), label: text(board?.label) });
  if (scope === "conference" && isNum(best.conferenceRank)) return el("span", { class: "leaders-sum" }, `best of ${usName()} `, chip(best.conferenceRank, board.conferenceOf, "conference"), isNum(board.conferenceOf) ? ` of ${board.conferenceOf} in the ${conference}` : ` in the ${conference}`);
  if ((scope === "national" || scope === "team") && isNum(best.nationalRank)) return el("span", { class: "leaders-sum" }, scope === "team" ? "best " : `best of ${usName()} `, chip(best.nationalRank, board.nationalOf), isNum(board.nationalOf) ? ` of ${board.nationalOf} nationally` : " nationally");
  return "";
}

function scopeHas(board, scope) {
  if (scope === "opponent") return scopeRows(board, "team").length + scopeRows(board, "opponent").length > 0;
  return scopeRows(board, scope).length > 0;
}

function render(envelope, container, state) {
  const data = envelope.data || {};
  const boards = [...(Array.isArray(data.boards) ? data.boards : []), ...(Array.isArray(data.extraBoards) ? data.extraBoards : [])].filter((b) => b && typeof b === "object" && typeof b.id === "string");
  // a team's school and mascot for the vs board's large head ("Swampwater Tech Mudpuppies"), the school alone without one
  const fullName = (team) => [team?.school, team?.mascot].filter((s) => typeof s === "string" && s.trim()).map((s) => s.trim()).join(" ") || null;
  const ctx = {
    us: typeof data.team?.school === "string" ? data.team.school : usSchool(),
    usAbbr: data.team?.abbreviation || usLabel(),
    usFull: fullName(data.team) || usSchool(),
    conference: data.team?.conference || confName(),
    opp: typeof data.opponent?.school === "string" ? data.opponent.school : null,
    oppAbbr: data.opponent?.abbreviation || data.opponent?.school || null,
    oppFull: fullName(data.opponent),
  };
  const pick = (id) => {
    state.scope = id;
    remember(SCOPE_KEY, id); // only a tap on the switch is remembered; a link arrival never is
    render(envelope, container, state);
  };
  const buttons = SCOPES.map((scope) => el("button", { type: "button", "aria-pressed": scope.id === state.scope ? "true" : "false", onclick: () => pick(scope.id) }, scope.id === "opponent" && data.opponent ? `vs ${text(ctx.oppAbbr)}` : scope.label()));
  const parts = data.parts || {};
  const partsFor = (scope) => (scope === "national" ? Object.keys(parts).filter((k) => k.startsWith("national_")).map((k) => parts[k]) : scope === "conference" ? [parts.conference] : scope === "opponent" ? [parts.team, parts.opponent || parts.conference] : [parts.team]);
  // a board with no league lists (usage) shows its team table when a link asks for a league scope
  const scopeOf = (board) => (LEAGUE.has(state.scope) && board.id === state.focus && board.nationalOf == null && board.conferenceOf == null ? "team" : state.scope);
  const grades = gradesBand(state);
  if (grades && grades.classList) grades.classList.add("flow-wide"); // the graded table takes two columns
  const page = el(
      "div",
      { class: "page leaders" },
      el("div", { class: "leaders__scope flow-full" }, el("div", { class: "seg", role: "group", "aria-label": "Scope" }, buttons)),
        boards.map((board) => {
          const scope = scopeOf(board);
          return band({
            id: bandId(board),
            title: text(board.label),
            collapsible: false,
            foldable: true, // each board shows whole and folds; no table scrolls inside the page (owner 2026-10-10, his phone)
            summary: summaryFor(board, scope, ctx),
            state: combinedState(partsFor(scope), scopeHas(board, scope)),
            emptyText: emptyWhy(board, scope, ctx),
            body: () => el("div", {}, boardTable(board, scope, ctx), board.note ? el("p", { class: "note" }, text(board.note)) : null),
          });
        }),
      boards.length ? null : note("No boards yet. Leaders appear after the first game."),
      grades,
  );
  state.ui ??= {};
  mountFlow(state.ui, container, page); // final pass: the boards flow into 1 to 4 columns under the pinned chips
  if (state.focus && !state.revealed) {
    const target = boards.find((b) => b.id === state.focus);
    const section = target ? container.querySelector(`#${bandId(target)}`) : null;
    if (section) {
      state.revealed = true;
      revealBand(section);
      section.classList.add("flash");
    }
  }
}

/** The view. `arg` is the route's "<board>:<scope>"; without one the remembered scope (or ours) shows. */
export function createLeadersView({ onStatus, arg } = {}) {
  const asked = parseLeadersArg(arg);
  const remembered = recall(SCOPE_KEY, "team");
  const group = recall(GRADE_KEY, "QB");
  const state = { scope: asked.scope || (SCOPE_IDS.has(remembered) ? remembered : "team"), focus: asked.board, revealed: false, gradeGroup: GRADE_GROUPS.some(([id]) => id === group) ? group : "QB", grades: {} };
  const view = poller({
    url: "/api/season/leaders",
    refreshMs: pollMs(),
    onStatus,
    render: (envelope, container) => render(envelope, container, state),
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Leaders", message, retry)),
    renderLoading: () =>
      el(
        "div",
        { class: "page leaders" },
        el("div", { class: "leaders__scope" }, el("div", { class: "seg", role: "group", "aria-label": "Scope" }, SCOPES.map((s) => el("button", { type: "button", disabled: true, "aria-pressed": s.id === state.scope ? "true" : "false" }, s.label())))),
        el("div", { class: "spread spread--2" }, ["Passing yards", "Rushing yards", "Receiving yards", "Tackles"].map((title) => band({ title, collapsible: false, state: { status: "loading" }, skeleton: () => statTableSkeleton(5, 6) }))),
      ),
  });
  return { ...view, unmount() { stopFlow(state.ui); view.unmount(); } };
}

export { rankChip, fmtNum, fmtStat, DASH };
