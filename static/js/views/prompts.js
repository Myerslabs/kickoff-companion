// The Load data page (the Prompts phase, owner 2026-10-13: "one Prompts page in the menu that every dead end leads to";
// named Load data in the menu 2026-10-16, the address stays #prompts). Since 2026-10-16 the loads cover my primary and
// secondary teams and the next opponent only, and a run goes on in the background: the loading bar above the page follows
// it (ui/run-bar.js), this page redraws only its "Run them all" steps meanwhile and rebuilds once when every run is done.
// One card per prompt, in the season's order: the season load, the coaches, the roster costs, the school history and
// facts, this week's notes. Each says what it loads, when it last ran and what is missing, with Copy the prompt, Paste
// the answer and, where Claude Code's command is found on the server, Run. At the top, "Run everything that is missing"
// (the same run as `python -m app prompts`) with each step's progress, then what the schedule will run next and what it
// ran lately (moved here from Settings; the switch stays there). A guest sees the cards and no buttons.
// The layout pass, board 8 (owner 2026-10-22, https://claude.ai/artifact/Ezvp4EKTJ4Rx1YxbZaPmG3; "visually it's ok, but I
// want to do the pre-loading of the data, so the preloaded data should show its date from the data that gets downloaded
// with the program"): at a glance (five tiles: red missing, gold partly loaded or preloaded, green loaded, each with its
// day) with the one run under them; this week's notes first and largest, its five parts as checks; the four season loads
// as even cards; the schedule as a short table. A load that came with the program reads "Preloaded <day>" in gold until
// the install loads its own ("Gold until you load"); no strip of section chips over the page.
//
//   createPromptsView({ onStatus })   the shared poller view on /api/prompts (views/common.js)
//   promptCards(data, onChange)       the cards (exported for the tests)

import { DASH, el, fmtDate, fmtDateTime, isNum, obj, str, text } from "../ui/dom.js";
import { band, note, subhead } from "../ui/states.js";
import { stopFlow } from "../ui/flow.js";
import { promptPaste } from "../ui/prompt-paste.js";
import { notesPathButton } from "../ui/notes-paste.js";
import { onRunProgress, watchRun } from "../ui/run-bar.js";
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

/** The state chip: loaded (with its day), preloaded with the program (with the shipped file's day), partly loaded,
 *  missing, or nothing to load. */
function chip(state, day = null) {
  const words = { loaded: "Loaded", preloaded: "Preloaded", partial: "Partly loaded", missing: "Missing", none: "Nothing to load" };
  return el("span", { class: `pill pill--${state === "preloaded" ? "partial pill--preloaded" : state}` }, `${words[state] || text(state)}${day && (state === "loaded" || state === "preloaded") ? ` ${day}` : ""}`);
}

/** A load's state from what is saved here and what came with the program: every team loaded here is "loaded", every
 *  team loaded or shipped (some shipped) is "preloaded", some is "partial", none is "missing". */
export function loadState(saved, shipped, of) {
  const have = isNum(saved) ? saved : 0;
  const came = isNum(shipped) ? Math.min(shipped, have) : 0;
  if (!isNum(of) || of <= 0) return "none";
  if (have - came >= of) return "loaded";
  if (have >= of) return "preloaded";
  return have ? "partial" : "missing";
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
    el("div", { class: "prompts__conference-head" }, el("b", {}, text(c.conference)), el("small", {}, str(c.savedAt) ? `saved ${fmtDate(c.savedAt, "short")}, ${isNum(c.saved) ? c.saved : 0} of ${isNum(c.schools) ? c.schools : DASH} teams` : isNum(c.shipped) && c.shipped > 0 ? `shipped with the app${str(c.checkedAt) ? `, checked ${fmtDate(c.checkedAt, "short")}` : ""}, ${c.shipped} of ${isNum(c.schools) ? c.schools : DASH} teams${c.stale ? "; a year old, the schedule asks again" : ""}` : "not loaded")),
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

function card({ id, title, what, state, when, missing, tools, extra, checks = null, tile = null }) {
  const section = band({
    id,
    title,
    collapsible: false,
    foldable: false,
    tools: chip(state, when), // board 8: the state with its day at the card's head
    state: { status: "ready" },
    body: () => el(
      "div",
      { class: "prompts__card" },
      missing ? el("p", { class: "prompts__missing" }, text(missing)) : null,
      el("p", { class: "note" }, what),
      checks,
      el("div", { class: "prompts__foot" }, tools, extra),
    ),
  });
  section._tile = { label: tile || title, state, day: when, cover: typeof missing === "string" ? missing.split(" · ")[0] : null };
  return section;
}

/** This week's notes' five parts as checks (board 8): what the notes hold and what they still lack. */
const NOTE_PARTS = [["Written notes", "written notes"], ["Injury report", "injury report"], ["Depth charts", "depth chart"], ["TV crew", "TV crew"], ["Coaches", "coaches"]];
function noteChecks(gaps) {
  const lacks = (needle) => gaps.some((g) => g.toLowerCase().includes(needle.toLowerCase()));
  return el("ul", { class: "load-checks", "aria-label": "What the notes hold" }, NOTE_PARTS.map(([label, needle]) => el("li", { class: `load-check${lacks(needle) ? "" : " load-check--ok"}` }, el("span", { class: "sr-only" }, lacks(needle) ? "missing: " : "loaded: "), label)));
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
  const shippedPre = pre.filter((t) => !str(t.savedAt) && t.shipped === true);
  const coachesOf = isNum(s.coachesOf) ? s.coachesOf : 0;
  const shipped = obj(s.shipped);
  const shippedAt = obj(shipped.checkedAt);
  const count = (saved) => (isNum(saved) ? saved : 0);
  const ratio = (saved) => (coachesOf ? `${count(saved)} of ${coachesOf} teams` : "");
  const latest = (rows) => list(rows).map((r) => str(r.savedAt)).filter(Boolean).sort().pop();
  const when = (iso) => (str(iso) ? fmtDate(iso, "short") : null);
  // the day a card shows: its own last load, or the shipped file's day while what shows came with the program
  const dayOf = (state, rows, kind) => (state === "preloaded" ? when(shippedAt[kind]) : when(latest(rows)));
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
        extra: [notesPathButton(n.gameId, n), ...(found ? [el("button", { class: "btn", type: "button", disabled: busy ? true : null, onclick: async () => {
          try {
            await send("/api/notes/run", { gameId: n.gameId });
          } catch (error) {
            console.warn("The notes run did not start.", error?.message || error);
          }
          if (typeof onChange === "function") onChange();
        } }, "Run with Claude Code")] : [])],
      }))
    : null;
  const seasonState = !pre.length ? "none" : savedPre.length === pre.length && loadState(s.coachesSaved, shipped.coaches, coachesOf) === "loaded" ? "loaded" : savedPre.length + shippedPre.length === pre.length && count(s.coachesSaved) >= coachesOf ? "preloaded" : savedPre.length || shippedPre.length || count(s.coachesSaved) ? "partial" : "missing";
  const coachesState = loadState(s.coachesSaved, shipped.coaches, coachesOf);
  const costsState = loadState(s.costsSaved, shipped.costs, coachesOf);
  const factsState = loadState(s.factsSaved, shipped.facts, coachesOf);
  const notesCard = card({
    id: "prompts-notes", title: isNum(n.gameId) ? `This week's notes, ${text(n.opponent)}` : "This week's notes", tile: "This week's notes",
    what: "The written notes, the injury report, both depth charts, the TV crew and the coaches for the next game. The Pre-Game Program and In Game read them.",
    state: notesState, when: when(n.writtenAt),
    missing: !isNum(n.gameId) ? (str(n.error) || str(n.none) || null) : null,
    checks: isNum(n.gameId) ? noteChecks(gaps) : null,
    tools: notesTools,
    extra: notesRun.running === true ? note("Claude Code is writing the notes now. It takes a few minutes.") : str(notesRun.error) ? el("p", { class: "note note--error" }, `The last run: ${notesRun.error}`) : null,
  });
  notesCard.classList.add("load-week");
  return [
    notesCard, // board 8: the load done every week first and largest
    card({
      id: "prompts-season", title: "The season load",
      what: "Each primary team's deep preseason (staff, birthdates for ages, offseason moves, the outlook, injuries) and the head coach and coordinators of every team you follow, in one answer.",
      state: seasonState,
      when: seasonState === "preloaded" ? when(shippedAt.preseason || shippedAt.coaches) : when(latest(pre)),
      missing: pre.length && savedPre.length + shippedPre.length < pre.length ? `Not loaded for ${pre.filter((t) => !str(t.savedAt) && t.shipped !== true).map((t) => text(t.school)).join(", ")}` : shippedPre.length ? `With the program for ${shippedPre.map((t) => text(t.school)).join(", ")} (no birthdates); load your own for the newest` : null,
      tools: seasonTools({ kind: "season", key: "all", label: "The season load", run: true, commandFound: found, running: busy, onChange }),
      extra: runRows(seasonRun, "season") || runRows(seasonRun, "preseason"),
    }),
    card({
      id: "prompts-coaches", title: "Coaches",
      what: "Head coach, offensive and defensive coordinator for your primary and secondary teams and the next opponent. The game's own notes still win when they name someone else.",
      state: coachesState, when: dayOf(coachesState, s.coaches, "coaches"), missing: coachesOf ? `${ratio(s.coachesSaved)}${coachesState === "preloaded" ? ", with the program" : ""} · one conference at a time` : null,
      tools: seasonTools({ kind: "coaches", key: "all", label: "Coaches", run: true, commandFound: found, running: busy, onChange }),
      extra: el("div", {}, conferenceRows("coaches", s.coaches, onChange), runRows(seasonRun, "coaches")),
    }),
    card({
      id: "prompts-costs", title: "Roster costs",
      what: "Rumored roster costs (revenue sharing and NIL): a total for each team you follow, position groups and players for the primary teams.",
      state: costsState, when: dayOf(costsState, s.costs, "costs"), missing: coachesOf ? `${ratio(s.costsSaved)}${count(shipped.costs) ? ` (${count(shipped.costs)} with the program)` : ""} · one conference at a time` : null,
      tools: seasonTools({ kind: "costs", key: "all", label: "Roster costs", run: true, commandFound: found, running: busy, onChange }),
      extra: el("div", {}, conferenceRows("costs", s.costs, onChange), runRows(seasonRun, "costs")),
    }),
    card({
      id: "prompts-facts", title: "School history and facts", tile: "School facts",
      what: "Founded, the stadium, titles, Heismans, the bowl record, rivalries and trophies, the fight song, alumni in the NFL, and dated events, for your primary and secondary teams and the next opponent. Shown on each team's page.",
      state: factsState, when: dayOf(factsState, s.facts, "facts"), missing: coachesOf ? `${ratio(s.factsSaved)}${factsState === "preloaded" ? ", with the program" : ""} · one prompt per conference` : null,
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
  ];
}

/** The one run's lines: how far along while it runs, each step's state, when it last finished. */
function runSteps(run) {
  const r = obj(run);
  const steps = list(r.steps);
  return [
    r.running === true ? note(`Running since ${str(r.startedAt) ? fmtDateTime(r.startedAt) : DASH}: ${isNum(r.done) ? r.done : 0} of ${isNum(r.of) ? r.of : steps.length} done. Each prompt takes a few minutes; it saves as it goes and the pages refresh once at the end.`) : null,
    steps.length && (r.running === true || str(r.finishedAt))
      ? el("ul", { class: "prompts__runlist" }, steps.map((s) => el("li", { class: `prompts__runitem is-${text(s.state)}` }, `${text(s.label)}: ${STATE_WORDS[s.state] || text(s.state)}${str(s.error) ? ` (${s.error})` : str(s.detail) ? ` (${s.detail})` : s.changed === true ? " (new information)" : s.changed === false ? " (nothing new)" : ""}`)))
      : null,
    str(r.finishedAt) && r.running !== true ? el("p", { class: "note" }, `Last run finished ${fmtDateTime(r.finishedAt)}.`) : null,
  ];
}

/** At a glance (board 8): one tile a load, its state's color and its day or coverage. */
function tally(data) {
  const cards = list(obj(data)._cards);
  return el("ul", { class: "load-tally", "aria-label": "What is loaded" }, cards.map((c) => el(
    "li",
    { class: `load-tile load-tile--${c.state}` },
    el("b", {}, c.label),
    el("span", {}, c.state === "loaded" ? `loaded${c.day ? ` ${c.day}` : ""}` : c.state === "preloaded" ? `preloaded${c.day ? ` ${c.day}` : ""}` : c.state === "partial" ? c.cover || "partly loaded" : c.state === "none" ? "nothing to load" : c.cover || "missing"),
  )));
}

/** The one run: a button for the missing, one for everything, and each step's line while it runs. The steps follow the
 *  loading bar's answers in place (2026-10-16), so the page itself is not rebuilt while the run goes. Board 8: under the
 *  five tiles, in the page's head card. */
function runBand(data, onChange) {
  const d = obj(data);
  const run = obj(d.run);
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
  }, all ? "Run everything again" : "Run everything missing");
  const buttons = [start(false), start(true)];
  const live = el("div", { class: "prompts__live" }, ...runSteps(run));
  const stop = onRunProgress((progress) => {
    if (!live.isConnected) {
      stop();
      return;
    }
    if (progress?.run && typeof progress.run === "object") live.replaceChildren(...runSteps(progress.run));
    for (const button of buttons) button.disabled = progress?.running === true; // any run on the server: one at a time
  });
  const body = () => el(
    "div",
    { class: "prompts__run" },
    d.commandFound === true
      ? (isGuest() ? note("Only the host can run the prompts.") : el("div", { class: "prompts__tools" }, ...buttons, said))
      : note(`Claude Code's command (${text(d.command || "claude")}) was not found on the server computer, so nothing runs by itself: copy each prompt into an AI chat that can search the web and paste the answer back. The same run is \`python -m app prompts\` once it is installed.`),
    live,
  );
  const who = list(obj(obj(data).season).preseason).map((t) => text(t.school));
  const opponent = str(obj(obj(data).notes).opponent) ? obj(data).notes.opponent : null;
  return band({
    id: "prompts-run",
    title: "Load data",
    collapsible: false,
    summary: run.running === true ? "running" : "",
    state: { status: "ready" },
    body: () => el("div", { class: "load-head" }, el("p", { class: "note" }, `For ${[...who.slice(0, 3), opponent ? `${opponent} (the next opponent)` : null].filter(Boolean).join(", ") || "your teams"} and the teams you follow`), tally(data), body()),
  });
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
        ? "Claude Code runs the prompts by itself: the notes when the publishers post, the season load in August, the coaches after the coaching changes, the costs after each portal window. The switch is in Profile, Claude and loading data."
        : s.commandFound === true ? "Switched off in Profile, Claude and loading data. Nothing runs by itself." : "Off: Claude Code's command is not on the server computer. Install it and the schedule turns on by itself; Profile, Claude and loading data has the switch."),
      s.pausedUntil ? el("p", { class: "note note-warn" }, `Paused until ${when(s.pausedUntil)} after three failed runs in a row.`) : null,
      s.running ? el("p", { class: "note" }, `Running now: ${text(s.running)}.`) : null,
      // board 8: a short table, what runs next and when, then what ran lately
      next.length ? el("table", { class: "load-sched" }, el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Next"), el("th", { scope: "col" }, "When"))), el("tbody", {}, next.map((n) => el("tr", {}, el("td", {}, text(n.label)), el("td", {}, `${when(n.at)}${s.enabled === true ? "" : " (off)"}`))))) : el("p", { class: "note" }, "Nothing is planned: no game on the schedule and the season's runs are done."),
      recent.length ? el("table", { class: "load-sched" }, el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Lately"), el("th", { scope: "col" }, "How it went"))), el("tbody", {}, recent.map((r) => el("tr", {}, el("td", {}, text(r.key)), el("td", {}, `${r.skipped ? "skipped, " + text(r.skipped) : r.ok ? (r.changed === true ? "done, new information" : r.changed === false ? "done, nothing new" : "done") : `failed${str(r.error) ? `, ${r.error}` : ""}`}${str(r.finishedAt) ? ` (${when(r.finishedAt)})` : ""}`))))) : null,
    ),
  });
}

export function createPromptsView({ onStatus } = {}) {
  const ui = {};
  const view = poller({
    url: "/api/prompts",
    refreshMs: 60000, // a run's progress comes with the loading bar (ui/run-bar.js); the page rebuilds once it ends
    onStatus,
    render: (envelope, container) => {
      const data = envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
      const again = () => {
        watchRun(); // a button may have started a run: the bar shows at once
        return view.refresh();
      };
      const cards = promptCards(data, again);
      const [week, ...season] = cards;
      const page = el(
        "div",
        { class: "page load-page" },
        runBand({ ...data, _cards: cards.map((c) => c._tile).filter(Boolean) }, again),
        el("p", { class: "load-label" }, "This week"),
        week,
        el("p", { class: "load-label" }, "The season"),
        el("div", { class: "load-season" }, season),
        el("p", { class: "load-label" }, "On a schedule"),
        scheduleBand(data),
      );
      stopFlow(ui); // board 8: one column of its own, no strip of section chips over the page
      container.replaceChildren(page);
    },
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Load data", message, retry)),
    renderLoading: () => el("div", { class: "page" }, band({ title: "Load data", collapsible: false, state: { status: "loading" } })),
    loadingDetail: "Each prompt and what it has loaded",
  });
  return { ...view, unmount() { stopFlow(ui); view.unmount(); } };
}
