// Kickoff Companion, the first-run setup (/welcome; public release Phases 5a and 5b).
// Step 1 checks a CFBD key and shows the plan it brings; step 2 picks the primary teams from CFBD's FBS list in
// one picker (ENH-12, owner 2026-10-23: "Use the step 3 as the only step and use the multi-select there"): the first
// is the home team (primary #1, the only one whose colors theme the app), up to four more follow, and the order picked
// is the My Teams order; step 3 adds the secondary teams (schools, conferences, states) and step 4 sets the ticker to
// every game or my teams. Settings' "Change my teams" opens this same page. "Save and open the app" writes the setup on the server, which restarts in place
// when the key or the home team changed; the page waits for it and opens the app.
// Every value from the server is guarded and written with textContent; the key is never shown back.

import { stateName } from "./us-states.js";
import { str } from "./ui/dom.js";

const DASH = "–";
const $ = (id) => document.getElementById(id);

const els = {
  intro: $("intro"),
  keyEntry: $("key-entry"),
  keyInput: $("key-input"),
  keyShow: $("key-show"),
  keyCheck: $("key-check"),
  keyDone: $("key-done"),
  keyLocked: $("key-locked"),
  keyError: $("key-error"),
  planFacts: $("plan-facts"),
  seePlans: $("see-plans"),
  getKey: $("get-key"),
  teamSearch: $("team-search"),
  teamList: $("team-list"),
  teamOrder: $("team-order"),
  teamNote: $("team-note"),
  tickerNational: $("ticker-national"),
  tickerMine: $("ticker-mine"),
  tickerLocked: $("ticker-locked"),
  primaryLocked: $("primary-locked"),
  likedLocked: $("liked-locked"),
  likedSearch: $("liked-search"),
  likedList: $("liked-list"),
  likedChips: $("liked-chips"),
  likedConferences: $("liked-conferences"),
  likedStates: $("liked-states"),
  finish: $("finish"),
  finishNote: $("finish-note"),
  finishError: $("finish-error"),
  status: $("welcome-status"),
  backToApp: $("back-to-app"),
  importPanel: $("import-panel"),
  importFound: $("import-found"),
  importGo: $("import-go"),
  importStatus: $("import-status"),
  importError: $("import-error"),
  demoLine: $("demo-line"),
};

const MAX_PRIMARIES = 4; // after the home team: five primary teams in all
// A list of schools shows this many matches whole and says how many more typing would find: never a scroll box
// inside the page, which keeps a finger on a phone (owner 2026-10-10).
const SHOWN = 8;
const state = { info: null, teams: [], conferences: [], states: [], team: null, primaries: [], tickerMode: "national", liked: { teams: [], conferences: [], states: [] } };

const num = (value) => (typeof value === "number" && Number.isFinite(value) ? value : null);
const hex = (value) => (typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value.trim()) ? value.trim() : null);
const fmt = (value) => (num(value) === null ? DASH : num(value).toLocaleString());

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function show(node, text) {
  if (!node) return;
  if (text) {
    node.textContent = text;
    node.hidden = false;
  } else {
    node.hidden = true;
  }
}

async function call(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", headers: { "Content-Type": "application/json", Accept: "application/json" }, ...options });
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  const errors = Array.isArray(body?.errors) ? body.errors : [];
  if (!response.ok) {
    const message = str(errors[0]?.message) || `The server answered HTTP ${response.status}.`;
    throw new Error(message);
  }
  return body && typeof body.data === "object" && body.data ? body.data : {};
}

function localDate(iso) {
  if (typeof iso !== "string" || !iso) return DASH;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? DASH : d.toLocaleDateString([], { month: "long", day: "numeric" });
}

// --- step 1: the key ---------------------------------------------------------------------------------

function renderPlan(plan) {
  if (!plan || typeof plan !== "object") {
    els.planFacts.hidden = true;
    return;
  }
  const facts = [
    ["Plan", str(plan.tierName) || DASH],
    ["The app runs", str(plan.profileLabel) || DASH],
    ["Calls a month", fmt(plan.monthlyLimit)],
    ["Calls used this month", fmt(plan.used)],
    ["Resets", localDate(plan.resetAt)],
    ["This month", str(plan.forecast?.text) || DASH],
  ];
  const rows = facts.flatMap(([label, value]) => [el("dt", {}, label), el("dd", {}, value)]);
  if (str(plan.warning)) rows.push(el("dt", {}, "Note"), el("dd", { class: "note-bad", role: "alert" }, plan.warning)); // the key CFBD reports as out of calls
  els.planFacts.replaceChildren(...rows);
  els.planFacts.hidden = false;
  if (str(plan.plansUrl)?.startsWith("https://")) els.seePlans.href = plan.plansUrl;
  if (str(plan.keyUrl)?.startsWith("https://")) els.getKey.href = plan.keyUrl;
}

function renderKey() {
  const info = state.info || {};
  const hasKey = info.keyConfigured === true || info.keyChecked === true;
  els.keyEntry.hidden = info.canSetKey === false;
  els.keyLocked.hidden = !(info.keyConfigured === true && info.canSetKey === false);
  if (info.keyChecked === true) show(els.keyDone, `Key checked: CFBD says ${str(info.plan?.tierName) || "it works"}. It is saved with the rest of the setup.`);
  else if (info.keyConfigured === true) show(els.keyDone, "A key is set. Paste a new one only to replace it.");
  else show(els.keyDone, null);
  renderPlan(hasKey ? info.plan : null);
  if (info.setupNeeded === false) els.intro.textContent = "Change your home team, your primary and secondary teams, the ticker, or the key. The server restarts for a new home team or key.";
}

async function checkKey() {
  const key = els.keyInput.value.trim();
  show(els.keyError, null);
  if (!key) {
    show(els.keyError, "Paste the key from CFBD's email first.");
    return;
  }
  els.keyCheck.disabled = true;
  els.status.textContent = "Checking the key with CFBD";
  try {
    const before = await startedAt();
    const data = await call("/api/welcome/key", { method: "POST", body: JSON.stringify({ key }) });
    els.keyInput.value = "";
    if (data.restarting === true) {
      await waitForRestart("The new key is saved. Restarting the server", before);
      return;
    }
    state.info = data;
    renderKey();
    els.status.textContent = "Key checked.";
    await loadTeams();
  } catch (error) {
    show(els.keyError, error.message);
    els.status.textContent = "The key was not accepted.";
  } finally {
    els.keyCheck.disabled = false;
  }
}

// --- step 2: the primary teams, the home team first ------------------------------------------------------

function teamItem(team, { selected, onPick }) {
  const color = hex(team.color) || "#888888";
  return el(
    "button",
    { class: "welcome__item", type: "button", role: "option", "aria-selected": selected ? "true" : "false", onclick: () => onPick(team) },
    el("span", { class: "welcome__swatch", style: `background:${color}` }),
    el("span", {}, team.school, str(team.mascot) ? ` ${team.mascot}` : ""),
    el("span", { class: "welcome__meta" }, str(team.conference) || ""),
  );
}

function matches(team, query) {
  if (!query) return true;
  const q = query.toLowerCase();
  return [team.school, team.mascot, team.conference, team.abbreviation, team.state].some((v) => typeof v === "string" && v.toLowerCase().includes(q));
}

/** The first SHOWN items of a list of matches, then a line saying how many more there are and that typing narrows them. */
function shortList(items, draw) {
  const more = items.length - SHOWN;
  return [...items.slice(0, SHOWN).map(draw), more > 0 ? el("p", { class: "welcome__more", role: "none" }, `${more} more: type a school, mascot or conference to find them.`) : null].filter(Boolean);
}

/** The primary teams in the My Teams order: the home team, then #2 to #5. */
function primaryOrder() {
  return [state.team, ...state.primaries].filter((school) => str(school));
}

function setOrder(list) {
  const schools = list.filter((school) => str(school));
  state.team = schools[0] || null;
  state.primaries = schools.slice(1, MAX_PRIMARIES + 1);
  state.liked.teams = state.liked.teams.filter((t) => !schools.includes(t)); // a team is primary or secondary, not both
  renderTeams();
  renderLiked();
}

/** One picked team: its place, its name, and Move up (the order is the My Teams order; up to #1 makes it the home team). */
function pickRow(school, index, list) {
  const team = state.teams.find((t) => t.school === school) || { school };
  const color = hex(team.color) || "#888888";
  const move = index > 0 ? el("button", { class: "btn btn--quiet", type: "button", "aria-label": `Move ${school} up to #${index}`, title: "Move up", onclick: () => setOrder([...list.slice(0, index - 1), school, list[index - 1], ...list.slice(index + 1)]) }, "↑") : null;
  const remove = el("button", { class: "btn btn--quiet", type: "button", "aria-label": `Remove ${school}`, title: "Remove", onclick: () => setOrder(list.filter((t) => t !== school)) }, "×");
  return el(
    "li",
    { class: "welcome__pick" },
    el("span", { class: "welcome__pick-num" }, `#${index + 1}`),
    el("span", { class: "welcome__swatch", style: `background:${color}` }),
    el(
      "span",
      { class: "welcome__pick-name" },
      school,
      str(team.mascot) ? ` ${team.mascot}` : "",
      str(team.conference) ? el("span", { class: "welcome__meta" }, team.conference) : null,
      index === 0 ? el("span", { class: "welcome__pick-home" }, "Home team: its colors and mascot theme the app") : null,
    ),
    el("span", { class: "welcome__pick-moves" }, move, remove),
  );
}

function renderTeams() {
  const list = primaryOrder();
  const allowed = likedAllowed();
  lockNote(els.primaryLocked, "More primary teams show with a Tier 2 key.");
  const capped = !allowed && list.length >= 1; // below Tier 2 the home team is the one primary team
  const full = list.length > MAX_PRIMARIES || capped;
  els.teamSearch.disabled = !state.teams.length || full;
  els.teamSearch.placeholder = capped ? "More primary teams show with a Tier 2 key" : full ? "Five is the most; remove one to add another" : list.length ? "Add another school (optional)" : "Type a school, mascot or conference";
  const query = els.teamSearch.value.trim();
  // with no team yet the whole list shows; after the first, only what is typed
  const found = full || (list.length && !query) ? [] : state.teams.filter((t) => !list.includes(t.school) && matches(t, query));
  els.teamList.replaceChildren(...shortList(found, (team) => teamItem(team, { selected: false, onPick: pickTeam })));
  els.teamOrder.replaceChildren(...list.map((school, index) => pickRow(school, index, list)));
  renderFinish();
}

function pickTeam(team) {
  els.teamSearch.value = "";
  setOrder([...primaryOrder(), team.school]);
}

// --- steps 3 and 4: the secondary teams, the ticker (a Tier 2 key) --------------------------------------

function likedAllowed() {
  return state.info?.plan?.likedAllowed === true;
}

function lockNote(node, words) {
  const plansUrl = str(state.info?.plan?.plansUrl) || "https://collegefootballdata.com/api-tiers";
  if (likedAllowed()) {
    node.hidden = true;
    return;
  }
  node.replaceChildren(`${words} Everything else works on your plan. `, el("a", { href: plansUrl, target: "_blank", rel: "noopener" }, "See CFBD's plans"));
  node.hidden = false;
}

function renderTicker() {
  const allowed = likedAllowed();
  lockNote(els.tickerLocked, "The My teams ticker shows with a Tier 2 key; the national ticker works on every plan.");
  if (!allowed) state.tickerMode = "national";
  els.tickerMine.disabled = !allowed;
  els.tickerNational.checked = state.tickerMode !== "mine";
  els.tickerMine.checked = state.tickerMode === "mine";
}

function renderLiked() {
  const allowed = likedAllowed();
  lockNote(els.likedLocked, "Secondary teams, conferences and states show with a Tier 2 key.");
  els.likedSearch.disabled = !allowed || !state.teams.length;
  const query = els.likedSearch.value.trim();
  const candidates = query ? state.teams.filter((t) => t.school !== state.team && !state.primaries.includes(t.school) && !state.liked.teams.includes(t.school) && matches(t, query)) : [];
  els.likedList.replaceChildren(...shortList(candidates, (team) => teamItem(team, { selected: false, onPick: (t) => { state.liked.teams.push(t.school); els.likedSearch.value = ""; renderLiked(); } })));
  els.likedChips.replaceChildren(...state.liked.teams.map((school) => el("button", { class: "chip", type: "button", disabled: !allowed, "aria-label": `Remove ${school}`, onclick: () => { state.liked.teams = state.liked.teams.filter((t) => t !== school); renderLiked(); } }, school, " ×")));
  const checks = (values, list, key, label = (v) => v) => values.map((value) => el("label", {}, el("input", { type: "checkbox", disabled: !allowed, checked: list.includes(value), onchange: (event) => { state.liked[key] = event.target.checked ? [...list, value] : list.filter((v) => v !== value); renderLiked(); } }), label(value)));
  els.likedConferences.replaceChildren(...checks(state.conferences, state.liked.conferences, "conferences"));
  els.likedStates.replaceChildren(...checks([...state.states].sort((a, b) => stateName(a).localeCompare(stateName(b))), state.liked.states, "states", stateName));
}

async function loadTeams() {
  els.teamNote.textContent = "Loading every FBS school from CFBD";
  try {
    const data = await call("/api/welcome/teams");
    state.teams = (Array.isArray(data.teams) ? data.teams : []).filter((t) => t && str(t.school));
    state.conferences = (Array.isArray(data.conferences) ? data.conferences : []).filter((c) => str(c));
    state.states = (Array.isArray(data.states) ? data.states : []).filter((s) => str(s));
    els.teamSearch.disabled = false;
    els.teamNote.textContent = `${state.teams.length} FBS schools. Type to narrow the list.`;
  } catch (error) {
    els.teamNote.textContent = `The team list did not load: ${error.message}`;
  }
  renderTeams();
  renderLiked();
  renderTicker();
}

// --- finish -----------------------------------------------------------------------------------------

function renderFinish() {
  const info = state.info || {};
  const ready = (info.keyConfigured === true || info.keyChecked === true) && Boolean(state.team);
  els.finish.disabled = !ready;
  els.finishNote.textContent = ready ? "The server restarts with the new setup and the app opens." : "Check a key and pick your home team first.";
  if (info.envWritable === false) els.finishNote.textContent = "This server reads its settings from environment variables; set CFBD_API_KEY, TEAM and CONFERENCE there.";
}

/** When the running server started, read before asking it to restart (it can restart within the request). */
async function startedAt() {
  try {
    return (await call("/api/health")).server?.started_at || null;
  } catch {
    return null;
  }
}

async function waitForRestart(message, before) {
  els.status.textContent = message;
  els.finish.disabled = true;
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    try {
      const health = await call("/api/health");
      const started = health.server?.started_at || null;
      if (health.setup_needed === false && started && started !== before) {
        window.location.href = "/";
        return;
      }
    } catch {
      // the server is between its stop and its start
    }
    els.status.textContent = `${message}…`;
  }
  show(els.finishError, "The server is taking longer than usual to restart. Check its window, then reload this page.");
}

async function finish() {
  show(els.finishError, null);
  els.finish.disabled = true;
  try {
    const allowed = likedAllowed();
    const liked = allowed ? state.liked : { teams: [], conferences: [], states: [] };
    const payload = { team: state.team, primaryTeams: allowed ? state.primaries : [], liked, tickerMode: allowed ? state.tickerMode : "national" };
    const before = await startedAt();
    const data = await call("/api/welcome/finish", { method: "POST", body: JSON.stringify(payload) });
    if (data.restarting === true) await waitForRestart("Saved. Starting the app with your team", before);
    else window.location.href = "/";
  } catch (error) {
    show(els.finishError, error.message);
    renderFinish();
  }
}

// Item 6, step H: a set-up app is one tap away ("Back to the app" in the header) and the demo link goes; during a first
// setup "/" leads back here, so the way back stays hidden and the demo stays offered.
function renderWayBack() {
  const done = state.info?.setupNeeded === false;
  if (els.backToApp) els.backToApp.hidden = !done;
  if (els.demoLine) els.demoLine.hidden = done;
}

// --- bring over the packaged install (FEAT-13) ----------------------------------------------------------------------

/** "12 games in the archive, notes for 9 games": what the packaged install holds, in words. */
function importWords(found) {
  const bits = [];
  if (typeof found.team === "string" && found.team) bits.push(`${found.team} as the team`);
  if (found.hasKey === true) bits.push("its CFBD key");
  if (Number.isFinite(found.archive) && found.archive > 0) bits.push(`${found.archive} ${found.archive === 1 ? "game" : "games"} in the archive`);
  if (Number.isFinite(found.notes) && found.notes > 0) bits.push(`notes for ${found.notes} ${found.notes === 1 ? "game" : "games"}`);
  const size = Number.isFinite(found.bytes) && found.bytes > 0 ? ` (${found.files} files, ${(found.bytes / 1e6).toFixed(1)} MB)` : "";
  return `Kickoff Companion is installed on this computer, in ${found.path}. Bring over its settings and data${bits.length ? `: ${bits.join(", ")}` : ""}${size}? It is copied, not moved, and the steps below are filled in for you.`;
}

function renderImport() {
  const found = state.info?.publicInstall;
  const shown = Boolean(found && typeof found === "object" && typeof found.path === "string" && state.info?.setupNeeded === true);
  els.importPanel.hidden = !shown;
  if (shown) els.importFound.textContent = importWords(found);
}

async function bringOver() {
  show(els.importError, null);
  els.importGo.disabled = true;
  els.importStatus.textContent = "Copying…";
  try {
    const before = await startedAt();
    const data = await call("/api/welcome/import", { method: "POST", body: JSON.stringify({ confirm: true }) });
    els.importStatus.textContent = `Copied ${data.copied} files. Starting the app with them…`;
    await waitForRestart("Copied. Starting the app with Kickoff Companion's settings", before);
  } catch (error) {
    els.importStatus.textContent = "";
    show(els.importError, error.message);
    els.importGo.disabled = false;
  }
}

// --- start ------------------------------------------------------------------------------------------

async function load() {
  try {
    state.info = await call("/api/welcome");
    state.team = str(state.info.team);
    const liked = state.info.liked && typeof state.info.liked === "object" ? state.info.liked : {};
    for (const key of ["teams", "conferences", "states"]) state.liked[key] = (Array.isArray(liked[key]) ? liked[key] : []).filter((v) => str(v));
    state.primaries = (Array.isArray(state.info.primaryTeams) ? state.info.primaryTeams : []).filter((v) => str(v)).slice(0, MAX_PRIMARIES);
    state.tickerMode = state.info.tickerMode === "mine" ? "mine" : "national";
    renderWayBack();
    renderImport();
    renderKey();
    renderTeams();
    renderLiked();
    renderTicker();
    els.status.textContent = state.info.setupNeeded === false ? "Set up. Change anything below." : "Waiting for a key and a team.";
    if (state.info.keyConfigured === true || state.info.keyChecked === true) await loadTeams();
  } catch (error) {
    els.status.textContent = `Could not reach the server: ${error.message}`;
  }
}

els.keyCheck.addEventListener("click", checkKey);
els.keyInput.addEventListener("keydown", (event) => { if (event.key === "Enter") checkKey(); });
els.keyShow.addEventListener("click", () => {
  const visible = els.keyInput.type === "text";
  els.keyInput.type = visible ? "password" : "text";
  els.keyShow.textContent = visible ? "Show" : "Hide";
  els.keyShow.setAttribute("aria-pressed", visible ? "false" : "true");
});
els.teamSearch.addEventListener("input", renderTeams);
els.likedSearch.addEventListener("input", renderLiked);
for (const radio of [els.tickerNational, els.tickerMine]) radio.addEventListener("change", (event) => { if (event.target.checked) state.tickerMode = event.target.value === "mine" ? "mine" : "national"; });
els.finish.addEventListener("click", finish);
els.importGo.addEventListener("click", bringOver);

/** A key pasted on the demo page (static/js/demo-page.js HANDED_KEY) is checked here at once, then forgotten. */
async function pickUpHandedKey() {
  let key = null;
  try {
    key = window.sessionStorage.getItem("kickoff.setup.key");
    if (key) window.sessionStorage.removeItem("kickoff.setup.key");
  } catch {
    key = null;
  }
  if (!key || els.keyInput.value || els.keyEntry.hidden) return;
  els.keyInput.value = key;
  await checkKey();
}

load().then(pickUpHandedKey).catch(() => {});
