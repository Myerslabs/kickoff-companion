// The Preseason page (Phase 17 Part 3a, owner 2026-10-07: "One preseason prompt to load all the data, it will be a
// pretty deep look at the season and offseason"). A section per primary team: the outlook, offseason moves, injuries
// and suspensions, program facts and the staff, each with its sources. At the top, the loads: the preseason batch per
// primary team and the coaches batch per conference, with dates, a prompt to copy and a box to paste each answer, and
// "Run with Claude Code" where the command is found. From August, until this season's load is saved, it reminds.
//
//   createPreseasonView({ onStatus })  the shared poller view on /api/preseason (views/common.js)
//   loadsBand(status, run, onChange)   the loads band (exported for the tests)

import { el, fmtDate, fmtUsd, isNum, obj, str, teamLogo, text } from "../ui/dom.js";
import { band, note, subhead } from "../ui/states.js";
import { mountFlow, stopFlow } from "../ui/flow.js";
import { promptPaste } from "../ui/prompt-paste.js";
import { fillWiki, wikiLink } from "../ui/wiki-links.js";
import { errorPanel, fetchJson, poller } from "./common.js";

function list(value) {
  return (Array.isArray(value) ? value : []).filter((x) => x && typeof x === "object");
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

/** One batch's row: what's saved, then Copy the prompt and Paste the answer (Phase 19: the prompt is never shown). */
function batchRow({ kind, key, label, detail, savedAt, onSaved }) {
  return el(
    "li",
    { class: "season-load__row" },
    el("div", { class: "season-load__head" }, el("b", {}, text(label)), el("span", { class: `season-load__state${savedAt ? " season-load__state--saved" : ""}` }, savedAt ? `Saved ${fmtDate(savedAt, "short")}` : "Not loaded"), detail ? el("small", {}, detail) : null),
    promptPaste({
      label,
      getPrompt: async () => {
        const data = await fetchJson(`/api/season-notes/prompt?kind=${encodeURIComponent(kind)}&key=${encodeURIComponent(key)}`);
        return typeof data?.data?.prompt === "string" ? data.data.prompt : "";
      },
      saveAnswer: (value) => send("/api/season-notes/save", { kind, key, text: value }),
      onSaved: () => {
        if (typeof onSaved === "function") onSaved();
      },
    }),
  );
}

const STATE_WORDS = { waiting: "waiting", running: "running…", saved: "saved", failed: "failed", stopped: "stopped" };

function runBlock(run, kind, onChange) {
  const r = obj(run);
  if (r.commandFound !== true) return null; // said once at the top of the band
  const mine = r.kind === kind ? list(r.batches) : [];
  const said = el("span", { class: "note season-load__said", role: "status" }); // final pass: a refused run says why, on the page
  const start = (missingOnly) => el("button", {
    class: missingOnly ? "btn btn--primary" : "btn", type: "button", disabled: r.running ? true : null,
    onclick: async () => {
      said.textContent = "";
      try {
        await send("/api/season-notes/run", { kind, missingOnly });
      } catch (error) {
        console.warn("The run did not start.", error?.message || error);
        said.textContent = `The run did not start: ${error?.message || error}`;
      }
      if (typeof onChange === "function") onChange();
    },
  }, missingOnly ? "Run the missing with Claude Code" : "Run all again");
  return el(
    "div",
    { class: "season-load__run" },
    el("div", { class: "season-load__tools" }, start(true), start(false)),
    said,
    r.running && r.kind === kind ? el("p", { class: "note", role: "status" }, `Claude Code is working: ${isNum(r.done) ? r.done : 0} of ${isNum(r.of) ? r.of : mine.length} done. Each batch takes a few minutes.`) : null,
    mine.length ? el("ul", { class: "season-load__runlist" }, mine.map((b) => el("li", { class: `season-load__runitem is-${text(b.state)}` }, `${text(b.key)}: ${STATE_WORDS[b.state] || text(b.state)}${str(b.error) ? ` (${b.error})` : ""}`))) : null,
  );
}

/** The conferences behind one button: about a dozen rows would push the teams far down the page. */
function conferenceList(coaches, onChange, kind = "coaches") {
  const missing = coaches.filter((c) => !str(c.savedAt)).length;
  const rows = el("ul", { class: "season-load__list", hidden: "" }, coaches.map((c) => batchRow({ kind, key: c.conference, label: c.conference, savedAt: str(c.savedAt), detail: `${isNum(c.saved) ? c.saved : 0} of ${isNum(c.schools) ? c.schools : 0} teams`, onSaved: onChange })));
  const toggle = el("button", { class: "btn btn--quiet", type: "button", "aria-expanded": "false", onclick: () => {
    const opening = rows.getAttribute("hidden") !== null;
    if (opening) rows.removeAttribute("hidden");
    else rows.setAttribute("hidden", "");
    toggle.setAttribute("aria-expanded", opening ? "true" : "false");
    toggle.textContent = opening ? "Hide the conferences" : `Show each conference (${coaches.length}${missing ? `, ${missing} not loaded` : ""})`;
  } }, `Show each conference (${coaches.length}${missing ? `, ${missing} not loaded` : ""})`);
  return coaches.length ? el("div", {}, toggle, rows) : null;
}

export function loadsBand(status, run, onChange) {
  const s = obj(status);
  const pre = list(s.preseason);
  const coaches = list(s.coaches);
  const costs = list(s.costs);
  const savedTeams = pre.filter((t) => str(t.savedAt)).length;
  const allSavedAt = pre.length && savedTeams === pre.length && isNum(s.coachesSaved) && s.coachesSaved === s.coachesOf ? pre.map((t) => str(t.savedAt)).filter(Boolean).sort().pop() : null;
  const complete = savedTeams === pre.length && isNum(s.coachesSaved) && s.coachesSaved === s.coachesOf && costs.every((c) => str(c.savedAt)) && !s.remind;
  return band({
    id: "preseason-loads",
    title: "Season loads",
    collapsible: true,
    foldable: true,
    collapsed: complete, // everything loaded: folded out of the way of the teams (a remembered fold still wins)
    summary: `preseason ${savedTeams} of ${pre.length} teams · coaches ${isNum(s.coachesSaved) ? s.coachesSaved : 0} of ${isNum(s.coachesOf) ? s.coachesOf : 0} · costs ${isNum(s.costsSaved) ? s.costsSaved : 0} of ${isNum(s.coachesOf) ? s.coachesOf : 0}`,
    state: { status: "ready" },
    body: () =>
      el(
        "div",
        { class: "season-load" },
        s.remind ? el("p", { class: "season-load__remind", role: "note" }, `The ${text(s.season)} preseason load isn't saved yet for every primary team. Run it once before the season starts.`) : null,
        obj(run).commandFound !== true ? el("p", { class: "note" }, "Claude Code isn't installed on the server computer, so copy and paste each batch. (CLAUDE_COMMAND in the .env file sets its path.)") : null,
        subhead("Everything for the season, one paste"),
        el("p", { class: "note" }, "One prompt for the primary teams' deep preseason and every FBS team's head coach and coordinators. Copy it into an AI chat that can search the web, paste the answer back, done."),
        el("ul", { class: "season-load__list" }, batchRow({ kind: "season", key: "all", label: "The whole season", savedAt: allSavedAt, detail: `${savedTeams} of ${pre.length} primary teams · coaches ${isNum(s.coachesSaved) ? s.coachesSaved : 0} of ${isNum(s.coachesOf) ? s.coachesOf : 0}`, onSaved: onChange })),
        runBlock(run, "season", onChange),
        el("details", { class: "season-load__more" },
          el("summary", {}, "Or one batch at a time"),
          subhead("Preseason, one batch per primary team"),
        el("p", { class: "note" }, "Staff, players' birthdates (for ages), offseason moves, the outlook, injuries and suspensions, and program facts."),
        el("ul", { class: "season-load__list" }, pre.map((t) => batchRow({ kind: "preseason", key: t.school, label: t.school, savedAt: str(t.savedAt), detail: t.counts ? `${obj(t.counts).birthdates ?? 0} birthdates, ${obj(t.counts).staff ?? 0} staff` : null, onSaved: onChange }))),
        runBlock(run, "preseason", onChange),
        subhead("Coaches, one batch per conference"),
        el("p", { class: "note" }, "Head coach, offensive and defensive coordinator for every FBS team. A game's own notes still win when they name someone else."),
        conferenceList(coaches, onChange),
        runBlock(run, "coaches", onChange),
        subhead("Roster costs, one batch per conference"),
        el("p", { class: "note" }, "Rumored figures from a shallow search: each team's total, and for your primary teams position groups and players where reported."),
        conferenceList(costs, onChange, "costs"),
        runBlock(run, "costs", onChange),
        ),
      ),
  });
}

function items(rows, { title = "title", detail = "detail" } = {}) {
  const good = list(rows).filter((r) => str(r[title]));
  if (!good.length) return null;
  return el("ul", { class: "preseason__items" }, good.map((r) => el("li", {}, el("b", {}, r[title]), str(r[detail]) ? ` ${r[detail]}` : null)));
}

function moves(rows) {
  const good = list(rows).filter((r) => str(r.name));
  if (!good.length) return null;
  return el("ul", { class: "preseason__items" }, good.map((r) => el("li", {}, el("b", {}, r.name), str(r.position) ? ` (${r.position})` : null, str(r.kind) ? `: ${r.kind}` : null, str(r.detail) ? `, ${r.detail}` : null)));
}

function injuries(rows) {
  const good = list(rows).filter((r) => str(r.name));
  if (!good.length) return null;
  return el("ul", { class: "preseason__items" }, good.map((r) => el("li", {}, el("b", {}, r.name), str(r.position) ? ` (${r.position})` : null, `: ${str(r.status) || "Status not reported"}`, str(r.detail) ? `, ${r.detail}` : null, str(r.expectedReturn) ? `. Back: ${r.expectedReturn}` : null)));
}

function block(title, node) {
  return node ? el("div", { class: "preseason__block" }, el("h4", { class: "preseason__h" }, title), node) : null;
}

function teamBand(team) {
  const t = obj(team);
  const p = t.preseason ? obj(t.preseason) : null;
  const outlook = obj(p?.outlook);
  const c = obj(t.coaches);
  const staff = list(p?.staff).filter((m) => str(m.name));
  const sources = list(p?.sources).filter((s) => str(s.label) || str(s.url));
  const coachLine = [["HC", c.headCoach], ["OC", c.offensiveCoordinator], ["DC", c.defensiveCoordinator]].filter(([, v]) => str(v)).map(([k, v]) => `${k} ${v}`).join(" · ");
  return band({
    id: `preseason-${String(t.school || "team").toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
    title: text(t.school),
    collapsible: true,
    foldable: true,
    summary: p ? `loaded ${fmtDate(t.savedAt, "short")}` : "not loaded",
    state: p ? { status: "ready" } : { status: "empty", message: "Not loaded yet. Copy the prompt in Season loads above, or run it with Claude Code." },
    body: () =>
      el(
        "div",
        { class: "preseason__team" },
        el("div", { class: "preseason__top" }, teamLogo(t, { size: 48 }), el("div", {}, el("div", { class: "preseason__conf" }, text(t.conference)), coachLine ? el("div", { class: "preseason__coaches" }, coachLine) : null)),
        str(outlook.summary) ? el("p", { class: "preseason__summary" }, outlook.summary) : null,
        block("Predictions", items(outlook.predictions)),
        block("Storylines", items(outlook.storylines)),
        block("Position battles", items(outlook.positionBattles)),
        block("Who left", moves(p?.departures)),
        block("Who arrived", moves(p?.arrivals)),
        block("Coaching changes", items(p?.coachingChanges)),
        block("Injuries and suspensions", injuries(p?.injuries)),
        block("Program facts", items(p?.programFacts)),
        block("Roster cost (rumored)", isNum(obj(t.costs).totalUsd) ? el("p", { class: "preseason__cost" }, el("b", {}, fmtUsd(t.costs.totalUsd)), str(t.costs.note) ? ` ${t.costs.note}` : null, el("small", {}, " See the team page for positions and players.")) : null),
        block("Staff", staff.length ? el("ul", { class: "preseason__items preseason__items--cols" }, staff.map((m) => el("li", {}, el("b", {}, wikiLink("coach", { person: m.name, team: str(t.school) }, m.name)), str(m.role) ? `, ${m.role}` : null))) : null),
        sources.length ? el("p", { class: "note" }, "Sources: ", sources.map((s, i) => [i ? ", " : null, str(s.url) && /^https?:\/\//.test(s.url) ? el("a", { href: s.url, target: "_blank", rel: "noopener" }, str(s.label) || s.url) : text(s.label)])) : null,
        str(t.author) ? el("p", { class: "note" }, `Written by ${t.author}.`) : null,
      ),
  });
}

export function createPreseasonView({ onStatus } = {}) {
  const ui = { run: null, timer: null, status: null, loads: null };
  let view = null;
  const refreshRun = async () => {
    try {
      const envelope = await fetchJson("/api/season-notes/run");
      ui.run = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
    } catch {
      ui.run = null;
    }
  };
  const again = async () => {
    await refreshRun();
    if (ui.loads && ui.loads.isConnected !== false) {
      const fresh = loadsBand(ui.status, ui.run, again); // the run's progress, without redrawing the teams
      ui.loads.replaceWith(fresh);
      ui.loads = fresh;
    }
    if (view) view.refresh(); // a saved batch changes the teams: the poller redraws when the data differ
    clearTimeout(ui.timer);
    if (ui.run?.running) ui.timer = setTimeout(again, 15000); // a run in progress: check every 15 s
  };
  view = poller({
    url: "/api/preseason",
    refreshMs: 5 * 60 * 1000,
    onStatus,
    render: (envelope, container) => {
      const data = obj(envelope?.data);
      const teams = list(data.teams);
      ui.status = data.status;
      ui.loads = loadsBand(data.status, ui.run, again);
      const page = el(
          "div",
          { class: "page preseason" },
          el("h1", { class: "page-title flow-full" }, `${text(data.season)} preseason`),
          ui.loads,
          teams.length ? teams.map(teamBand) : note("No primary teams yet. Pick them on the setup page."),
      );
      mountFlow(ui, container, page); // final pass: the flowing page with its section chips
      fillWiki(container); // Phase 19: the staff's names open their Wikipedia pages
    },
    renderError: (message, container, retry) => container.replaceChildren(errorPanel("Preseason", message, retry)),
    renderLoading: () => el("div", { class: "page" }, band({ title: "Preseason", collapsible: false, state: { status: "loading" } })),
    loadingDetail: "The season loads and each primary team's preseason notes",
  });
  const mount = view.mount;
  view.mount = (container) => {
    mount.call(view, container);
    again();
  };
  const unmount = view.unmount;
  view.unmount = (...args) => {
    clearTimeout(ui.timer);
    stopFlow(ui); // final pass: the layout's observers go with the page
    return unmount.apply(view, args);
  };
  return view;
}

