// The Prompts page (the Prompts phase, owner 2026-10-13: "one Prompts page in the menu that every dead end leads to").
// One card per prompt, in the season's order: the season load, the coaches, the roster costs, the school history and
// facts, this week's notes. Each says what it loads, when it last ran and what is missing, with Copy the prompt, Paste
// the answer and, where Claude Code's command is found on the server, Run. At the top, "Run everything that is missing"
// (the same run as `python -m app prompts`) with each step's progress, then what the schedule will run next and what it
// ran lately (moved here from Settings; the switch stays there). A guest sees the cards and no buttons.
//
//   createPromptsView({ onStatus })   the shared poller view on /api/prompts (views/common.js)
//   promptCards(data, onChange)       the cards (exported for the tests)

import { DASH, el, fmtDate, fmtDateTime, isNum, obj, str, text } from "../ui/dom.js";
import { band, note, subhead } from "../ui/states.js";
import { mountFlow, stopFlow } from "../ui/flow.js";
import { promptPaste } from "../ui/prompt-paste.js";
import { errorPanel, fetchJson, poller } from "./common.js";

const STATE_WORDS = { waiting: "waiting", skipped: "skipped", running: "running…", done: "done", failed: "failed", stopped: "stopped" };

function list(value) {
  return (Array.isArray(value) ? value : []).filter((x) => x && typeof x === "object");
}

function isGuest() {
  try {
    return document.body?.dataset?.role === "guest";
  } catch {
    return false;
  }
}

async function send(url, body) {
  const response = await fetch(url, { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  let envelope = null;
  try {
    envelope = await response.json();
  } catch {
    envelope = null;
  }
  if (!response.ok) throw new Error(envelope?.errors?.[0]?.message || `The server answered ${response.status}`);
  return envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
}

/** The state chip: loaded, partly loaded, or missing. */
function chip(state) {
  const words = { loaded: "Loaded", partial: "Partly loaded", missing: "Missing", none: "Nothing to load" };
  return el("span", { class: `pill pill--${state}` }, words[state] || text(state));
}

/** A season prompt's Copy and Paste (kind, key) and its Run (kind, missing or all). */
function seasonTools({ kind, key, label, run, commandFound, running, onChange }) {
  if (isGuest()) return null;
  const said = el("span", { class: "note prompts__said", role: "status" });
  const start = (missingOnly) => el("button", {
    class: "btn", type: "button", disabled: running ? true : null,
    onclick: async () => {
      said.textContent = "";
      try {
        await send("/api/season-notes/run", { kind, missingOnly });
      } catch (error) {
        said.textContent = `The run did not start: ${error?.message || error}`;
      }
      if (typeof onChange === "function") onChange();
    },
  }, missingOnly ? "Run the missing with Claude Code" : "Run all again");
  return el(
    "div",
    { class: "prompts__tools" },
    promptPaste({
      label,
      getPrompt: async () => {
        const data = await fetchJson(`/api/season-notes/prompt?kind=${encodeURIComponent(kind)}&key=${encodeURIComponent(key)}`);
        return typeof data?.data?.prompt === "string" ? data.data.prompt : "";
      },
      saveAnswer: (value) => send("/api/season-notes/save", { kind, key, text: value }),
      onSaved: () => { if (typeof onChange === "function") onChange(); },
      extra: commandFound && run ? [start(true), start(false)] : [],
    }),
    said,
  );
}

/** One conference at a time, behind a button, for the prompts that go conference by conference. */
function conferenceRows(kind, rows, onChange) {
  const items = list(rows);
  if (!items.length || isGuest()) return null;
  const missing = items.filter((c) => !str(c.savedAt)).length;
  const ul = el("ul", { class: "prompts__conferences", hidden: "" }, items.map((c) => el(
    "li",
    { class: "prompts__conference" },
    el("div", { class: "prompts__conference-head" }, el("b", {}, text(c.conference)), el("small", {}, str(c.savedAt) ? `saved ${fmtDate(c.savedAt, "short")}, ${isNum(c.saved) ? c.saved : 0} of ${isNum(c.schools) ? c.schools : DASH} teams` : "not loaded")),
    promptPaste({
      label: `${text(c.conference)} ${kind}`,
      getPrompt: async () => {
        const data = await fetchJson(`/api/season-notes/prompt?kind=${encodeURIComponent(kind)}&key=${encodeURIComponent(String(c.conference))}`);
        return typeof data?.data?.prompt === "string" ? data.data.prompt : "";
      },
      saveAnswer: (value) => send("/api/season-notes/save", { kind, key: String(c.conference), text: value }),
      onSaved: () => { if (typeof onChange === "function") onChange(); },
    }),
  )));
  const label = (open) => (open ? "Hide the conferences" : `One conference at a time (${items.length}${missing ? `, ${missing} not loaded` : ""})`);
  const toggle = el("button", { class: "btn btn--quiet", type: "button", "aria-expanded": "false", onclick: () => {
    const opening = ul.hasAttribute("hidden");
    if (opening) ul.removeAttribute("hidden");
    else ul.setAttribute("hidden", "");
    toggle.setAttribute("aria-expanded", opening ? "true" : "false");
    toggle.textContent = label(opening);
  } }, label(false));
  return el("div", {}, toggle, ul);
}

/** The run's own rows under a card: the batches of the season runner for this kind, while or after it runs. */
function runRows(seasonRun, kind) {
  const r = obj(seasonRun);
  if (r.kind !== kind) return null;
  const mine = list(r.batches);
  if (!mine.length) return null;
  return el("ul", { class: "prompts__runlist" }, mine.map((b) => el("li", { class: `prompts__runitem is-${text(b.state)}` }, `${text(b.key)}: ${STATE_WORDS[b.state] || text(b.state)}${str(b.error) ? ` (${b.error})` : ""}`)));
}

function card({ id, title, what, state, when, missing, tools, extra }) {
  return band({
    id,
    title,
    collapsible: false,
    foldable: false,
    summary: when ? `last loaded ${when}` : "",
    state: { status: "ready" },
    body: () => el(
      "div",
      { class: "prompts__card" },
      el("div", { class: "prompts__state" }, chip(state), missing ? el("span", { class: "prompts__missing" }, text(missing)) : null),
      el("p", { class: "note" }, what),
      tools,
      extra,
    ),
  });
}

export function promptCards(data, onChange) {
  const d = obj(data);
  const s = obj(d.season);
  const seasonRun = obj(d.seasonRun);
  const notesRun = obj(d.notesRun);
  const found = d.commandFound === true;
  const busy = obj(d.run).running === true || seasonRun.running === true || notesRun.running === true;
  const pre = list(s.preseason);
  const savedPre = pre.filter((t) => str(t.savedAt));
  const coachesOf = isNum(s.coachesOf) ? s.coachesOf : 0;
  const count = (saved) => (isNum(saved) ? saved : 0);
  const ratio = (saved) => (coachesOf ? `${count(saved)} of ${coachesOf} teams` : "");
  const stateOf = (saved, of) => (!of ? "none" : count(saved) >= of ? "loaded" : count(saved) ? "partial" : "missing");
  const latest = (rows) => list(rows).map((r) => str(r.savedAt)).filter(Boolean).sort().pop();
  const when = (iso) => (str(iso) ? fmtDate(iso, "short") : null);
  const n = obj(d.notes);
  const gaps = Array.isArray(n.missing) ? n.missing.filter((x) => typeof x === "string") : [];
  const notesState = !isNum(n.gameId) ? "none" : !gaps.length ? "loaded" : str(n.writtenAt) ? "partial" : "missing";
  const notesTools = isNum(n.gameId) && !isGuest()
    ? el("div", { class: "prompts__tools" }, promptPaste({
        label: "This week's notes",
        getPrompt: async () => {
          const got = await fetchJson(`/api/notes/prompt?gameId=${n.gameId}`);
          return typeof got?.data?.prompt === "string" ? got.data.prompt : "";
        },
        saveAnswer: (value) => send("/api/notes/save", { gameId: n.gameId, text: value }),
        onSaved: () => { if (typeof onChange === "function") onChange(); },
        extra: found ? [el("button", { class: "btn", type: "button", disabled: busy ? true : null, onclick: async () => {
          try {
            await send("/api/notes/run", { gameId: n.gameId });
          } catch (error) {
            console.warn("The notes run did not start.", error?.message || error);
          }
          if (typeof onChange === "function") onChange();
        } }, "Run with Claude Code")] : [],
      }))
    : null;
  return [
    card({
      id: "prompts-season", title: "The season load",
      what: "Each primary team's deep preseason (staff, birthdates for ages, offseason moves, the outlook, injuries) and every FBS team's head coach and coordinators, in one answer.",
      state: pre.length ? (savedPre.length === pre.length && count(s.coachesSaved) >= coachesOf ? "loaded" : savedPre.length || count(s.coachesSaved) ? "partial" : "missing") : "none",
      when: when(latest(pre)),
      missing: pre.length && savedPre.length < pre.length ? `not loaded for ${pre.filter((t) => !str(t.savedAt)).map((t) => text(t.school)).join(", ")}` : null,
      tools: seasonTools({ kind: "season", key: "all", label: "The season load", run: true, commandFound: found, running: busy, onChange }),
      extra: runRows(seasonRun, "season") || runRows(seasonRun, "preseason"),
    }),
    card({
      id: "prompts-coaches", title: "Coaches",
      what: "Head coach, offensive and defensive coordinator for every FBS team. The game's own notes still win when they name someone else.",
      state: stateOf(s.coachesSaved, coachesOf), when: when(latest(s.coaches)), missing: coachesOf && count(s.coachesSaved) < coachesOf ? ratio(s.coachesSaved) : null,
      tools: seasonTools({ kind: "coaches", key: "all", label: "Coaches", run: true, commandFound: found, running: busy, onChange }),
      extra: el("div", {}, conferenceRows("coaches", s.coaches, onChange), runRows(seasonRun, "coaches")),
    }),
    card({
      id: "prompts-costs", title: "Roster costs",
      what: "Rumored roster costs (revenue sharing and NIL): a total for every team, position groups and players for the primary teams.",
      state: stateOf(s.costsSaved, coachesOf), when: when(latest(s.costs)), missing: coachesOf && count(s.costsSaved) < coachesOf ? ratio(s.costsSaved) : null,
      tools: seasonTools({ kind: "costs", key: "all", label: "Roster costs", run: true, commandFound: found, running: busy, onChange }),
      extra: el("div", {}, conferenceRows("costs", s.costs, onChange), runRows(seasonRun, "costs")),
    }),
    card({
      id: "prompts-facts", title: "School history and facts",
      what: "Founded, the stadium, titles, Heismans, the bowl record, rivalries and trophies, the fight song, alumni in the NFL, and dated events, for every FBS team. Shown on each team's page.",
      state: stateOf(s.factsSaved, coachesOf), when: when(latest(s.facts)), missing: coachesOf && count(s.factsSaved) < coachesOf ? ratio(s.factsSaved) : null,
      tools: found && !isGuest() ? el("div", { class: "prompts__tools" }, el("button", { class: "btn", type: "button", disabled: busy ? true : null, onclick: async () => {
        try {
          await send("/api/season-notes/run", { kind: "facts", missingOnly: true });
        } catch (error) {
          console.warn("The facts run did not start.", error?.message || error);
        }
        if (typeof onChange === "function") onChange();
      } }, "Run the missing with Claude Code")) : null,
      extra: el("div", {}, note("One prompt per conference: copy it, paste the answer, done."), conferenceRows("facts", s.facts, onChange), runRows(seasonRun, "facts")),
    }),
    card({
      id: "prompts-notes", title: isNum(n.gameId) ? `This week's notes, ${text(n.opponent)}` : "This week's notes",
      what: "The written notes, the injury report, both depth charts, the TV crew and the coaches for the next game. The Pre-Game Program reads them.",
      state: notesState, when: when(n.writtenAt),
      missing: !isNum(n.gameId) ? (str(n.error) || str(n.none) || null) : gaps.length ? `missing: ${gaps.join(", ")}` : null,
      tools: notesTools,
      extra: notesRun.running === true ? note("Claude Code is writing the notes now. It takes a few minutes.") : str(notesRun.error) ? el("p", { class: "note note--error" }, `The last run: ${notesRun.error}`) : null,
    }),
  ];
}

/** The one run: a button for the missing, one for everything, and each step's line while it runs. */
function runBand(data, onChange) {
  const d = obj(data);
  const run = obj(d.run);
  const steps = list(run.steps);
  const said = el("span", { class: "note prompts__said", role: "status" });
  const start = (all) => el("button", {
    class: all ? "btn" : "btn btn--primary", type: "button", disabled: run.running ? true : null,
    onclick: async () => {
      said.textContent = "";
      try {
        await send("/api/prompts/run", { all });
      } catch (error) {
        said.textContent = `The run did not start: ${error?.message || error}`;
      }
      if (typeof onChange === "function") onChange();
    },
  }, all ? "Run everything again" : "Run everything that is missing");
  const body = () => el(
    "div",
    { class: "prompts__run" },
    d.commandFound === true
      ? (isGuest() ? note("Only the host can run the prompts.") : el("div", { class: "prompts__tools" }, start(false), start(true), said))
      : note(`Claude Code's command (${text(d.command || "claude")}) was not found on the server computer, so nothing runs by itself: copy each prompt into an AI chat that can search the web and paste the answer back. The same run is \`python -m app prompts\` once it is installed.`),
    run.running === true ? note(`Running since ${str(run.startedAt) ? fmtDateTime(run.startedAt) : DASH}: ${isNum(run.done) ? run.done : 0} of ${isNum(run.of) ? run.of : steps.length} done. Each prompt takes a few minutes.`) : null,
    steps.length && (run.running === true || str(run.finishedAt))
      ? el("ul", { class: "prompts__runlist" }, steps.map((s) => el("li", { class: `prompts__runitem is-${text(s.state)}` }, `${text(s.label)}: ${STATE_WORDS[s.state] || text(s.state)}${str(s.error) ? ` (${s.error})` : str(s.detail) ? ` (${s.detail})` : s.changed === true ? " (new information)" : s.changed === false ? " (nothing new)" : ""}`)))
      : null,
    str(run.finishedAt) && run.running !== true ? el("p", { class: "note" }, `Last run finished ${fmtDateTime(run.finishedAt)}.`) : null,
  );
  return band({ id: "prompts-run", title: "Run them all", collapsible: false, summary: run.running === true ? "running" : "", state: { status: "ready" }, body });
}

/** What the schedule runs next and what it ran lately (from Settings; the switch stays there). */
function scheduleBand(data) {
  const s = obj(obj(data).schedule);
  const when = (iso) => (str(iso) ? fmtDateTime(iso) : DASH);
  const next = list(s.next);
  const recent = list(s.recent);
  return band({
    id: "prompts-schedule",
    title: "On a schedule",
    collapsible: false,
    foldable: true,
    summary: s.enabled === true ? "on" : "off",
    state: { status: "ready" },
    body: () => el(
      "div",
      { class: "prompts__schedule" },
      el("p", { class: "note" }, s.enabled === true
        ? "Claude Code runs the prompts by itself: the notes when the publishers post, the season load in August, the coaches after the coaching changes, the costs after each portal window. The switch is in Settings."
        : s.commandFound === true ? "Switched off in Settings. Nothing runs by itself." : "Off: Claude Code's command is not on the server computer. Install it and the schedule turns on by itself."),
      s.pausedUntil ? el("p", { class: "note note-warn" }, `Paused until ${when(s.pausedUntil)} after three failed runs in a row.`) : null,
      s.running ? el("p", { class: "note" }, `Running now: ${text(s.running)}.`) : null,
      next.length ? el("div", {}, subhead("Next"), el("ul", { class: "plain-list" }, next.map((n) => el("li", {}, el("b", {}, text(n.label)), ` from ${when(n.at)}${s.enabled === true ? "" : " (off)"}`)))) : el("p", { class: "note" }, "Nothing is planned: no game on the schedule and the season's runs are done."),
      recent.length ? el("div", {}, subhead("Lately"), el("ul", { class: "plain-list" }, recent.map((r) => el("li", {}, `${text(r.key)}: ${r.skipped ? "skipped, " + text(r.skipped) : r.ok ? (r.changed === true ? "done, new information" : r.changed === false ? "done, nothing new" : "done") : `failed${str(r.error) ? `, ${r.error}` : ""}`}${str(r.finishedAt) ? ` (${when(r.finishedAt)})` : ""}`)))) : null,
    ),
  });
}

export function createPromptsView({ onStatus } = {}) {
  const ui = {};
  const view = poller({
    url: "/api/prompts",
    refreshMs: 15000, // a run under way moves every few seconds; the page follows it
    onStatus,
    render: (envelope, container) => {
      const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
      const again = () => view.refresh();
      const page = el("div", { class: "page" }, runBand(data, again), ...promptCards(data, again), scheduleBand(data));
      mountFlow(ui, container, page, { full: ["prompts-run", "prompts-schedule"] });
    },
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Prompts", message, retry)),
    renderLoading: () => el("div", { class: "page" }, band({ title: "Prompts", collapsible: false, state: { status: "loading" } })),
    loadingDetail: "Each prompt and what it has loaded",
  });
  return { ...view, unmount() { stopFlow(ui); view.unmount(); } };
}
