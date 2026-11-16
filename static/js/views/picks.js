// Picks of the week (FEAT-2, owner 2026-10-25: "Named with the paper's weekly name. Power: SEC, Big Ten, Big 12, ACC, Pac-12
// and independents; the rest Group of 5. Four timeslots, chosen once game and broadcast information exists"; 2026-10-30
// "Claude picks": Claude Code with web search picks every game with one line of reason, the market's line beside it).
//
// Under National in the menu. The head carries this week's paper's name (newspaper.js mastheadName) and Claude's record so
// far; Power and Group of 5 are a switch remembered on the device; the games run in their four kickoff windows (Early,
// Afternoon, Prime time, Late, by the server's clock), each a band of rows: the kickoff and TV, the game with the AP ranks
// (ours marked), the line, and the pick with its reason, marked Right or Wrong once the game is final. Until Claude Code has
// picked every game the paper's own picks fill the ranked games, and the host's Pick every game now starts the run where
// Claude Code is found. Nothing here fetches CFBD by itself: /api/picks reads what the Top 25 page caches.
//
//   createPicksView({ onStatus })
//   SCOPES, scopeOf(), gameRow(row)   exported for the tests

import { DASH, el, isNum, recall, remember, teamLink, text } from "../ui/dom.js";
import { band, note } from "../ui/states.js";
import { errorPanel, poller } from "./common.js";
import { mastheadName } from "./newspaper.js";

const RUN_POLL_MS = 20 * 1000;
const RUN_POLL_FOR_MS = 30 * 60 * 1000;
const SCOPE_KEY = "picks:scope";

export const SCOPES = [
  { id: "power", label: "Power" },
  { id: "g5", label: "Group of 5" },
];

export function scopeOf() {
  return recall(SCOPE_KEY, "power") === "g5" ? "g5" : "power";
}

function kickoffWords(row) {
  if (row.startTimeTbd) return "Time to be set";
  const when = typeof row.kickoff === "string" ? new Date(row.kickoff) : null;
  if (!when || Number.isNaN(when.getTime())) return DASH;
  const time = when.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return when.getDay() === 6 ? time : `${when.toLocaleDateString([], { weekday: "short" })} ${time}`;
}

function sideName(side) {
  const s = side && typeof side === "object" ? side : {};
  const school = typeof s.school === "string" && s.school ? s.school : null;
  if (!school) return DASH;
  const rank = isNum(s.rank) ? el("span", { class: "picks__rank" }, `#${s.rank} `) : null;
  return el("span", { class: "picks__team" }, rank, s.fbs === false ? school : teamLink(school));
}

function pickWords(row) {
  if (typeof row.pick !== "string" || !row.pick) return null;
  const side = row.home?.school === row.pick ? row.home : row.away?.school === row.pick ? row.away : null;
  return typeof side?.abbreviation === "string" && side.abbreviation ? side.abbreviation : row.pick;
}

/** One game's row: the kickoff and TV, the game, the line, the pick and its reason. Exported for the tests. */
export function gameRow(row) {
  const r = row && typeof row === "object" ? row : {};
  const final = r.final === true && isNum(r.home?.points) && isNum(r.away?.points);
  const between = r.neutralSite ? " vs " : " at ";
  const game = el(
    "div",
    { class: "picks__game" },
    sideName(r.away),
    final ? el("b", { class: "picks__score" }, ` ${r.away.points}`) : null,
    between,
    sideName(r.home),
    final ? el("b", { class: "picks__score" }, ` ${r.home.points}`) : null,
    final ? el("span", { class: "picks__final" }, " Final") : null,
  );
  const line = r.line && typeof r.line === "object" ? (typeof r.line.short === "string" && r.line.short) || (typeof r.line.formatted === "string" && r.line.formatted) || null : null;
  const pick = pickWords(r);
  const mark = r.right === true ? el("span", { class: "picks__mark picks__mark--right" }, "Right") : r.right === false ? el("span", { class: "picks__mark picks__mark--wrong" }, "Wrong") : null;
  return el(
    "li",
    { class: `picks__row${r.isUs ? " is-us" : ""}` },
    el("div", { class: "picks__when" }, el("span", {}, kickoffWords(r)), el("small", {}, typeof r.tv === "string" && r.tv ? r.tv : "TV to be set")),
    game,
    el("div", { class: "picks__line" }, el("small", {}, "Line"), el("span", {}, line || "None yet")),
    el(
      "div",
      { class: "picks__pick" },
      pick ? el("span", { class: "picks__who" }, el("small", {}, "Pick"), " ", el("b", {}, pick), mark ? " " : null, mark) : el("span", { class: "picks__who picks__who--none" }, "No pick yet"),
      typeof r.reason === "string" && r.reason.trim() ? el("p", { class: "picks__why" }, r.reason.trim()) : null,
    ),
  );
}

function recordWords(record) {
  const one = (rec) => (rec && isNum(rec.right) && isNum(rec.wrong) && rec.right + rec.wrong > 0 ? `${rec.right}-${rec.wrong}` : null);
  const power = one(record?.power);
  const g5 = one(record?.g5);
  if (!power && !g5) return null;
  return `Record this week: ${[power ? `Power ${power}` : null, g5 ? `Group of 5 ${g5}` : null].filter(Boolean).join(" · ")}`;
}

function byWords(data) {
  const when = typeof data.writtenAt === "string" ? new Date(data.writtenAt) : null;
  const day = when && !Number.isNaN(when.getTime()) ? when.toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" }) : null;
  if (data.picksBy === "claude") return `Picked by Claude Code on the server${day ? `, ${day}` : ""}, the market's line beside each.`;
  if (data.picksBy === "paper") return "The paper's picks for the ranked games until Claude Code picks every game.";
  return null; // the run band below says when
}

/** The picks as one band (wave 3 of the one-column page, owner 2026-11-01: the page folded into the Top 25): the scope switch
 *  in the band's head, Claude's run line, then each kickoff window as a block. `rerender` draws it again on a switch. */
export function picksBand(data, state, rerender) {
  const scope = state.scope;
  const counts = data.counts && typeof data.counts === "object" ? data.counts : {};
  const switcher = el(
    "div",
    { class: "seg picks__scope", role: "group", "aria-label": "Which games" },
    SCOPES.map((s) => el("button", { type: "button", class: s.id === scope ? "is-on" : null, "aria-pressed": s.id === scope ? "true" : "false", onclick: () => {
      remember(SCOPE_KEY, s.id);
      state.scope = s.id;
      rerender();
    } }, `${s.label}${isNum(counts[s.id]) ? ` (${counts[s.id]})` : ""}`)),
  );
  const want = (row) => (scope === "g5" ? row && row.power === false : row && row.power !== false);
  const slots = (Array.isArray(data.slots) ? data.slots : []).filter((s) => s && typeof s === "object");
  const blocks = slots.map((s) => {
    const rows = (Array.isArray(s.games) ? s.games : []).filter(want);
    return rows.length ? el("div", { class: "picks__slot" }, el("h4", { class: "d2-head" }, `${text(s.name)} · ${text(s.hours)}`), el("ul", { class: "picks__list" }, rows.map(gameRow))) : null;
  }).filter(Boolean);
  const later = (Array.isArray(data.unscheduled) ? data.unscheduled : []).filter(want);
  if (later.length) blocks.push(el("div", { class: "picks__slot" }, el("h4", { class: "d2-head" }, "Time to be set"), el("ul", { class: "picks__list" }, later.map(gameRow))));
  const run = runBand(data, state);
  return band({
    id: "top25-picks",
    title: `${mastheadName(data.season, data.week)}'s Picks of the week`,
    collapsible: true,
    foldable: true,
    summary: [text(data.label || "This week"), byWords(data), recordWords(data.record)].filter(Boolean).join(" · "),
    tools: switcher,
    state: blocks.length ? { status: "ready" } : { status: "empty", message: data.note || (data.ready === false ? "The windows fill once the week's kickoff times and TV are set." : "No games in this group this week.") },
    body: () => el("div", { class: "box picks" }, run ? run.querySelector(".band__body") || run : null, ...blocks),
  });
}

function render(envelope, container, state, rerender) {
  const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
  const scope = state.scope;
  const title = `${mastheadName(data.season, data.week)}'s Picks of the week`;
  const counts = data.counts && typeof data.counts === "object" ? data.counts : {};
  const switcher = el(
    "div",
    { class: "seg picks__scope", role: "group", "aria-label": "Which games" },
    SCOPES.map((s) => el("button", { type: "button", class: s.id === scope ? "is-on" : null, "aria-pressed": s.id === scope ? "true" : "false", onclick: () => {
      remember(SCOPE_KEY, s.id);
      state.scope = s.id;
      rerender();
    } }, `${s.label}${isNum(counts[s.id]) ? ` (${counts[s.id]})` : ""}`)),
  );
  const head = el(
    "header",
    { class: "picks-head" },
    el("h1", { class: "picks-head__title" }, title),
    el("p", { class: "picks-head__sub" }, [text(data.label || "This week"), byWords(data)].filter(Boolean).join(" · ")),
    recordWords(data.record) ? el("p", { class: "picks-head__record" }, recordWords(data.record)) : null,
    switcher,
  );
  const runBox = runBand(data, state);
  const want = (row) => (scope === "g5" ? row && row.power === false : row && row.power !== false);
  const slots = (Array.isArray(data.slots) ? data.slots : []).filter((s) => s && typeof s === "object");
  const bands = slots.map((s) => {
    const rows = (Array.isArray(s.games) ? s.games : []).filter(want);
    if (!rows.length) return null;
    return band({ id: `picks-${s.id}`, title: text(s.name), collapsible: true, foldable: true, summary: `${text(s.hours)} · ${rows.length} ${rows.length === 1 ? "game" : "games"}`, state: { status: "ready" }, body: () => el("ul", { class: "picks__list" }, rows.map(gameRow)) });
  }).filter(Boolean);
  const later = (Array.isArray(data.unscheduled) ? data.unscheduled : []).filter(want);
  if (later.length) bands.push(band({ id: "picks-later", title: "Time to be set", collapsible: true, foldable: true, summary: `${later.length} ${later.length === 1 ? "game" : "games"}`, state: { status: "ready" }, body: () => el("ul", { class: "picks__list" }, later.map(gameRow)) }));
  const empty = !bands.length ? band({ id: "picks-none", title: scope === "g5" ? "Group of 5" : "Power", collapsible: false, state: { status: "empty", message: data.note || (data.ready === false ? "The windows fill once the week's kickoff times and TV are set." : "No games in this group this week.") } }) : null;
  const page = el("div", { class: "page page--wide picks" }, head, runBox, ...bands, empty);
  container.replaceChildren(page);
  return page;
}

/** Until Claude Code has picked every game: when it does, and the host's Pick every game now where the command is found. */
function runBand(data, state) {
  if (data.picksBy === "claude") state.runDone(); // written: the quick refresh stops
  if (data.picksBy === "claude" || typeof data.key !== "string") return null;
  const said = el("span", { class: "note", role: "status" }, data.running ? "Picking every game now; it takes a few minutes." : "");
  const go = data.commandFound === true && !data.running && data.ready !== false ? el("button", { class: "btn", type: "button", onclick: async () => {
    go.disabled = true;
    said.textContent = "Starting…";
    try {
      const response = await fetch(`/api/writing/picks/${encodeURIComponent(data.key)}/run`, { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true }) });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.errors?.[0]?.message || `The server answered ${response.status}`);
      said.textContent = "Picking every game now; it takes a few minutes.";
      state.watchRun();
    } catch (error) {
      said.textContent = `Not started: ${text(error?.message)}.`;
      go.disabled = false;
    }
  } }, "Pick every game now") : null;
  if (data.running) state.watchRun();
  const words = data.ready === false ? "Claude Code picks every game once the week's kickoff times and TV are set, on Thursday afternoon." : "Claude Code picks every game on Thursday afternoon, from the week's previews and news.";
  return band({ id: "picks-run", title: "Claude's picks", collapsible: false, state: { status: "ready" }, body: () => el("div", { class: "writing writing--empty" }, note(words), go || said.textContent ? el("p", {}, go, " ", said) : null) });
}

export function createPicksView({ onStatus } = {}) {
  let runTimer = null;
  let runUntil = 0;
  const state = { scope: scopeOf(), watchRun: () => {}, runDone: () => { runUntil = 0; } };
  const inner = poller({
    url: "/api/picks",
    onStatus,
    render: (envelope, container) => {
      const draw = () => render(envelope, container, state, draw);
      draw();
    },
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Picks of the week", message, retry)),
    loadingDetail: "This week's games",
    renderLoading: () => el("div", { class: "page page--wide picks" }, el("header", { class: "picks-head" }, el("div", { class: "skel", style: { width: "min(420px, 70%)", height: "32px" } })), el("div", { class: "skel skel--block" })),
  });
  state.watchRun = () => {
    if (runTimer !== null) return;
    runUntil = Date.now() + RUN_POLL_FOR_MS;
    const tick = () => {
      runTimer = null;
      if (Date.now() > runUntil) return;
      inner.refresh();
      runTimer = setTimeout(tick, RUN_POLL_MS);
    };
    runTimer = setTimeout(tick, RUN_POLL_MS);
  };
  return {
    mount: (target) => inner.mount(target),
    refresh: () => inner.refresh(),
    unmount() {
      clearTimeout(runTimer);
      runTimer = null;
      inner.unmount();
    },
  };
}

