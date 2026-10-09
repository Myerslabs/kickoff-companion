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
//           league lists; "vs opponent" sets ours beside the opponent, value and chip in one cell a side.
//   LRP-16b our and the vs-opponent scopes show a 28 px headshot (the local /media/headshot cache; the
//           number badge, abbreviation or initials when there is none) beside each name.

import { confLabel, confName, usLabel, usName, usSchool } from "../identity.js";
import { DASH, el, fmtNum, fmtStat, isNum, playerFace, recall, remember, text } from "../ui/dom.js";
import { nationalHref } from "../ui/national-link.js";
import { band, note, revealBand } from "../ui/states.js";
import { mountFlow, stopFlow } from "../ui/flow.js";
import { rankChip, statTable, statTableSkeleton } from "../ui/stat-table.js";
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

/** A board row with its detail spread under d_<key>, so a stat key can never shadow a row field. */
function flat(row, extra) {
  const detail = row.detail && typeof row.detail === "object" ? row.detail : {};
  const out = { ...row, ...extra };
  for (const [k, v] of Object.entries(detail)) out[`d_${k}`] = v;
  return out;
}

function detailColumns(board, rows) {
  return boardDetail(board, rows).map((c) => ({ key: `d_${c.key}`, label: /^PCT$/i.test(c.key) && !Array.isArray(board.detailColumns) ? pctLabel(board.category) : c.label, format: c.format }));
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

/** A name with its 28 px face and position under it (the team scopes). */
function who(row) {
  return el(
    "span",
    { class: "leader-who" },
    playerFace(row, { them: row.isUs === false, abbr: row.teamAbbr, size: 28 }),
    el("span", { class: "leader-who__text" }, el("span", { class: "leader-who__name" }, text(row.player)), row.position ? el("small", {}, text(row.position)) : null),
  );
}

// final pass: a board's minimum in words ("5 punts"), never CFBD's key ("5 no")
const MINIMUM_WORDS = { NO: "punts", ATT: "attempts", CAR: "carries", REC: "catches", PLAYS: "plays", FGA: "field goal tries", TOT: "tackles" };

function playerCell(scope) {
  if (scope === "team" || scope === "opponent") return { key: "player", label: "Player", kind: "text", render: who };
  return { key: "player", label: "Player", kind: "text", sub: "team", subTeam: true };
}

function leagueTable(board, scope, ctx) {
  const top = scopeRows(board, scope);
  const extra = windowRows(board, scope);
  const rows = [
    ...top.map((row, index) => flat(row, { place: scope === "team" ? index + 1 : row.rank })),
    ...extra.map((row) => flat(row, { place: row.rank })),
  ];
  const columns = [
    { key: "place", label: "#", dim: true },
    playerCell(scope),
    {
      key: "value",
      label: statLabel(board.stat, board.category),
      format: board.format,
      rank: scope === "team" ? { key: "nationalRank", of: "nationalOf", link: (row) => listHref(row, board, { team: ctx.us }), placeholder: true } : null,
    },
    ...detailColumns(board, [...top, ...extra]),
  ];
  if (scope === "team") columns.splice(3, 0, { key: "conferenceRank", label: `${confLabel()} rank`, kind: "rank", of: "conferenceOf", link: (row) => listHref(row, board, { team: ctx.us, scope: "conference" }) });
  const rowClass = (row) => {
    const classes = [];
    if (row.isUs) classes.push("is-us");
    else if (ctx.opp && row.team === ctx.opp && LEAGUE.has(scope)) classes.push("is-next", "is-opp");
    if (row.windowRow) classes.push("is-window");
    return classes.join(" ") || null;
  };
  const gapText = `${text(ctx.us)} below the top ${top.length}`;
  let wrap = null;
  wrap = statTable({
    compact: true,
    columns,
    rows,
    rowClass,
    onSort: () => splitWindow(wrap, gapText, columns.length),
    onRowTap: (row) => openPlayer(row.playerId, row),
    caption: `${text(board.label)}, ${scope}`,
  });
  splitWindow(wrap, gapText, columns.length);
  return el("div", { class: `leaders-table leaders-table--${scope}` }, wrap);
}

/** Ours beside the next opponent (S7): rank by rank, value and national chip in one cell a side, a divider between. */
function versusTable(board, ctx) {
  const us = scopeRows(board, "team");
  const them = scopeRows(board, "opponent");
  if (!us.length && !them.length) return null;
  const rows = Array.from({ length: Math.max(us.length, them.length) }, (_, i) => {
    const a = us[i] || null;
    const b = them[i] || null;
    return {
      place: i + 1,
      usRow: a,
      themRow: b,
      usPlayer: a?.player ?? null,
      usPosition: a?.position ?? null,
      usValue: a?.value ?? null,
      usRank: a?.nationalRank ?? null,
      usOf: a?.nationalOf ?? null,
      themPlayer: b?.player ?? null,
      themPosition: b?.position ?? null,
      themValue: b?.value ?? null,
      themRank: b?.nationalRank ?? null,
      themOf: b?.nationalOf ?? null,
    };
  });
  const whoButton = (side) => (row) => {
    const player = row[side];
    if (!player) return null;
    return el("button", { class: "leader-who--btn", type: "button", onclick: () => openPlayer(player.playerId, player) }, who(player));
  };
  const columns = [
    { key: "place", label: "#", dim: true },
    { key: "usPlayer", label: text(ctx.usAbbr), kind: "text", render: whoButton("usRow") },
    { key: "usValue", label: statLabel(board.stat, board.category), format: board.format, rank: { key: "usRank", of: "usOf", link: (row) => (row.usRow ? listHref(row.usRow, board, { team: ctx.us }) : null), placeholder: true } },
    { key: "themPlayer", label: text(ctx.oppAbbr), kind: "text", divider: true, render: whoButton("themRow") },
    { key: "themValue", label: statLabel(board.stat, board.category), format: board.format, rank: { key: "themRank", of: "themOf", link: (row) => (row.themRow ? listHref(row.themRow, board, { team: ctx.opp }) : null), placeholder: true } },
  ];
  return el(
    "div",
    { class: "leaders-table leaders-table--versus" },
    statTable({ compact: true, sortable: false, columns, rows, caption: `${text(board.label)}, ${text(ctx.usAbbr)} and ${text(ctx.oppAbbr)}` }),
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
  const ctx = {
    us: typeof data.team?.school === "string" ? data.team.school : usSchool(),
    usAbbr: data.team?.abbreviation || usLabel(),
    conference: data.team?.conference || confName(),
    opp: typeof data.opponent?.school === "string" ? data.opponent.school : null,
    oppAbbr: data.opponent?.abbreviation || data.opponent?.school || null,
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
