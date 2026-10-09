// The Settings page (X6): every option lives here and is stored on the server (owner direction
// 2026-09-23). Spoiler delay, radio source, theme, page refresh, start at login, tray mode, the
// notes command, a Desktop icon, and the quota readout. Each change saves on its own and says so.
// Public release Phase 5b: the score ticker (every game, or my teams with a Tier 2 key), radio stations
// for any team (add, remove, find the broadcast, request it), and the primary and secondary teams.
// Public release Phase 6: the notes prompt the Game program copies for an AI chat, editable here.
// Phase 17 #31 (owner pick: Steam's settings): the sections listed on the left (a chip row on a phone), the
// options grouped as Game day, Display, and Start and the server; one row per setting, its name and grey help on
// the left and the switch or picker on the right; switches instead of checkboxes; a green "saved" line.

import { cvdOn, setCvd } from "../ui/cvd.js";
import { promptPaste } from "../ui/prompt-paste.js";
import { readinessBand } from "../ui/readiness.js";
import { setSpoiler, spoilerOn } from "../ui/spoiler.js";
import { restartFlow } from "../ui/restart.js";
import { fetchJson } from "./common.js";
import { DASH, el, fmtDate, fmtDateTime, fmtNum, isNum, str, text } from "../ui/dom.js";
import { band, note, revealBand, subhead } from "../ui/states.js";
import { statTable } from "../ui/stat-table.js";
import { getPrefs, loadPrefs, prefsError, prefsMeta, savePrefs, setTextSize, TEXT_SIZES, textSize } from "../prefs.js";
import { radioHelpBlock, reloadRadioSources } from "../radio.js";
import { copyText } from "../ui/notes-paste.js";

const REPO_URL = "https://github.com/Myerslabs/kickoff-companion"; // the server's own copy wins (about.repoUrl)

const KINDS = [
  { value: "stream", label: "Stream (plays in the app)" },
  { value: "embed", label: "Station player (shown in the app)" },
  { value: "link", label: "Link (opens a tab)" },
];
function row(label, control, help) {
  return el("div", { class: "setting" }, el("div", { class: "setting__label" }, label, help ? el("small", {}, help) : null), el("div", { class: "setting__control" }, control));
}

function select(options, value, onChange, ariaLabel) {
  return el(
    "select",
    { class: "setting__select", "aria-label": ariaLabel, onchange: (event) => onChange(event.target.value) },
    options.map((o) => el("option", { value: o.value, selected: String(o.value) === String(value) ? true : null, disabled: o.disabled ? true : null }, o.label)),
  );
}

/** An on/off switch (a checkbox drawn as a switch, so it keeps the keyboard and the screen reader's checkbox). */
function toggle(checked, onChange, ariaLabel) {
  return el("label", { class: "setting__toggle" }, el("input", { type: "checkbox", role: "switch", class: "switch", checked: checked ? true : null, "aria-label": ariaLabel, onchange: (event) => onChange(event.target.checked) }), el("span", { class: "sr-only" }, checked ? "On" : "Off"));
}

/** What the Desktop icon starts: the packaged program itself (public release Phase 10), else the start script. */
function iconText(auto) {
  const what = auto.packaged ? "Kickoff Companion" : auto.system === "windows" ? "start.ps1" : "start.sh";
  return auto.system === "linux" ? `A double-click icon for ${what} on the Desktop and in the app menu (Steam's Add a Non-Steam Game lists it).` : `A double-click icon for ${what} on the Desktop.`;
}

/** What "Start at login" does on the server's system (public release Phase 4), and whether it is on. */
function loginText(auto) {
  if (!auto || !auto.supported) return "Not available on this server's system. Start it with start.ps1 or start.sh.";
  const what = typeof auto.method === "string" && auto.method ? auto.method : "a login item";
  return `Starts the server when you log in, through ${what}. ${auto.enabled ? "Currently on." : "Currently off."}`;
}

export function createSettingsView({ onStatus } = {}) {
  let container = null;
  const setStatus = (kind, label) => {
    if (typeof onStatus === "function") onStatus({ kind, label });
  };
  const saved = el("p", { class: "note setting__saved", "aria-live": "polite" }, "");

  async function change(patch, label) {
    saved.textContent = `Saving ${label}…`;
    saved.classList.remove("note--error", "setting__saved--ok");
    try {
      const envelope = await savePrefs(patch);
      const problem = envelope?.errors?.find((e) => e.code === "autostart_failed");
      saved.textContent = problem ? `${label} saved, but: ${problem.message}` : `${label} saved.`;
      saved.classList.add(problem ? "note--error" : "setting__saved--ok");
      render();
    } catch (error) {
      saved.textContent = `${label} was not saved: ${error?.message || "unknown error"}.`;
      saved.classList.add("note--error");
    }
  }

  async function makeShortcut(button) {
    button.disabled = true;
    saved.textContent = "Creating the Desktop icon…";
    try {
      const response = await fetch("/api/settings/desktop-shortcut", { method: "POST" });
      const envelope = await response.json();
      if (!response.ok) throw new Error(envelope?.errors?.[0]?.message || `The server answered ${response.status}`);
      saved.textContent = `Desktop icon created at ${envelope.data?.path || "the Desktop"}.`;
      saved.classList.remove("note--error");
    } catch (error) {
      saved.textContent = `No Desktop icon: ${error?.message || "unknown error"}.`;
      saved.classList.add("note--error");
    }
    button.disabled = false;
  }

  /** The three option sections share their inputs (built per draw from the saved prefs). */
  function optionRows() {
    const p = getPrefs();
    const meta = prefsMeta() || {};
    const sources = Array.isArray(meta.radioSources) ? meta.radioSources.filter((s) => s && typeof s.id === "string") : [];
    const tier2 = meta.plan?.likedAllowed === true;
    const delayValue = el("b", {}, `${p.delaySeconds} s`);
    const slider = el("input", { type: "range", min: "0", max: "120", step: "5", value: String(p.delaySeconds), "aria-label": "Spoiler delay in seconds", oninput: (event) => { delayValue.textContent = `${event.target.value} s`; }, onchange: (event) => change({ delaySeconds: Number(event.target.value) }, "Spoiler delay") });
    const shortcutButton = el("button", { class: "btn", type: "button", onclick: (event) => makeShortcut(event.currentTarget) }, "Create a Desktop icon");
    const auto = meta.autoStart || {};
    const notes = meta.notes || {};
    return {
      problems: [
        prefsError() ? note(`${prefsError()}. Showing defaults.`, { kind: "error", lead: "Settings could not be loaded." }) : null,
        meta.prefsError ? note(`${meta.prefsError}.`, { kind: "error", lead: "Settings file problem." }) : null,
      ],
      gameday: [
        row("Spoiler delay", el("div", { class: "setting__slider" }, slider, delayValue), "Every live panel and our line in the ticker run this far behind the broadcast. Audio cannot be delayed."),
        row("Keep the screen on", select([{ value: "gameday", label: "On our game days (default)" }, { value: "always", label: "Always" }, { value: "off", label: "Never" }], p.keepScreenOn || "gameday", (value) => change({ keepScreenOn: value }, "Keep the screen on"), "Keep the screen on"), "Stops the tablet from sleeping on any page. Game day means a day we play; the Live sheet also keeps the screen on while plays come in."),
        row("Radio source", select([{ value: "", label: "First station in the list" }, ...sources.map((s) => ({ value: s.id, label: `${text(s.name)}${str(s.team) ? `, ${s.team}` : ""} (${text(s.kind)})` }))], p.radioSourceId || "", (value) => change({ radioSourceId: value || null }, "Radio source"), "Radio source"), "The station the Play button on the Game program uses first. Add stations for any team under Radio stations."),
        row("Score ticker", select([{ value: "national", label: "National: every FBS game (default)" }, { value: "mine", label: tier2 ? "My teams: primary and secondary teams only" : "My teams (shows with a Tier 2 key)", disabled: !tier2 }], p.tickerMode === "mine" && tier2 ? "mine" : "national", (value) => change({ tickerMode: value }, "Score ticker"), "Score ticker"), tier2 ? "My teams shows only your primary and secondary teams' games; when none of them play, every game shows. Pick the teams on the setup page." : "Every plan shows every FBS game. A Tier 2 key adds a ticker of just your teams."),
      ],
      display: [
        row("Theme", select([{ value: "dark", label: "Dark (default)" }, { value: "light", label: "Light" }], p.theme, (value) => change({ theme: value }, "Theme"), "Theme"), "Charcoal or light; the team's colors mark what is ours either way."),
        row("Text size", select(TEXT_SIZES.map((s) => ({ value: s.id, label: `${s.label} (${Math.round(s.scale * 100)}%)` })), textSize(), (value) => {
          const size = setTextSize(value);
          saved.classList.remove("note--error");
          saved.classList.add("setting__saved--ok");
          saved.textContent = `Text size ${size.label.toLowerCase()} on this device.`;
        }, "Text size"), "This device only, so the couch tablet and the desk screen can differ. Saved in this browser."),
        row("Stat hints", toggle(p.hints !== false, (value) => change({ hints: value }, "Stat hints"), "Stat hints"), "Stat names with a dotted underline explain themselves when tapped. The Glossary in the menu lists every one."),
        row("Color-blind friendly colors", toggle(cvdOn(), (value) => setCvd(value), "Color-blind friendly colors"), "Blue and orange instead of green and red, and a shape on every rank chip (up for the top quarter, a dot for the middle, down for the bottom). Only this device."),
        row("Spoiler mode", toggle(spoilerOn(), (value) => setSpoiler(value), "Spoiler mode"), "For a recorded game: this device hides the scores, results, win chance and plays until you tap them. Only this device; the host and other devices are not affected."),
        row("Announcer", toggle(p.announcer !== false, (value) => change({ announcer: value }, "Announcer"), "Announcer"), "A little announcer in a headset calls out each section's stat line the first time it scrolls into view. Nothing moves when the device asks for reduced motion."),
        row("Page refresh", select([1, 5, 10, 15, 30, 60].map((m) => ({ value: m, label: `every ${m} min` })), p.refreshMinutes, (value) => change({ refreshMinutes: Number(value) }, "Page refresh"), "Page refresh"), "How often Season, Program and Newspaper ask the server again. The live sheet streams regardless."),
      ],
      start: [
        row("Start at login", toggle(p.autoStart, (value) => change({ autoStart: value }, "Start at login"), "Start at login"), loginText(auto)),
        row("Open the app on start", select([{ value: "manual", label: "When started by hand (default)" }, { value: "always", label: "Always, at login too" }, { value: "never", label: "Never" }], p.openBrowser || "manual", (value) => change({ openBrowser: value }, "Open the app on start"), "Open the app on start"), "Opens this app in the server computer's browser once the server is up. Phones and tablets connect from the QR code on the status page."),
        auto.tray ? row("Tray mode", toggle(p.trayMode, (value) => change({ trayMode: value }, "Tray mode"), "Tray mode"), "The server's window hides behind a tray icon (Open the app, Status, Log, Quit). Takes effect on the next start from the Desktop icon or at login.") : null,
        row("Desktop icon", shortcutButton, iconText(auto)),
        row("Nightly backup", toggle(p.backups !== false, (value) => change({ backups: value }, "Nightly backup"), "Nightly backup"), backupText(meta.housekeeping)),
        row("Restart the server", restartControl(), "Starts the server over in the same window, for a changed setting or an update pulled while it runs. The page reloads when it's back, usually 10 to 20 seconds."),
        row("Check for updates", toggle(p.updateCheck !== false, (value) => change({ updateCheck: value }, "Check for updates"), "Check for updates"), "Once a day the server asks GitHub whether a newer release is out and says so under About. It never downloads anything by itself."),
        row("Claude Code", el("span", { class: "setting__value" }, notes.commandFound ? "Found" : "Not found"), notes.commandFound ? `Found: ${notes.commandPath}. The Game program also offers to write the notes with it. Only Claude Code runs, and only to answer the prompt.` : "Optional. Claude Code is not installed on the server computer, so copy and paste each prompt. To use it, install it, or set CLAUDE_COMMAND in the .env file to its full path."),
      ],
    };
  }

  function backupText(h) {
    const hk = h && typeof h === "object" ? h : {};
    const awake = hk.keepAwake && hk.keepAwake.supported === true ? "The computer is kept awake while a game is on." : "Turn off this computer's sleep timer on game days: keeping it awake is not supported here.";
    if (hk.enabled === false) return `Off. ${awake}`;
    const last = typeof hk.last === "string" ? `Last backup ${fmtDateTime(hk.last)}.` : "No backup yet; the first one is made soon after the server starts.";
    const problem = typeof hk.error === "string" && hk.error ? ` Problem: ${hk.error}` : "";
    return `Each night a zip of the Archive, notes and settings goes to ${text(hk.folder)}; the newest ${isNum(hk.keep) ? hk.keep : 7} are kept. ${last}${problem} ${awake}`;
  }

  function section(id, title, rows, summary = null) {
    return band({ id, title, collapsible: false, summary, state: { status: "ready" }, body: () => el("div", { class: "settings" }, rows) });
  }

  function quotaBand() {
    // Public release Phase 5a: the plan behind the key in plain words, this month's calls with a forecast,
    // and every feature with what shows it. Nothing is hidden for the plan; a locked feature says which
    // plan shows it.
    const meta = prefsMeta() || {};
    const q = meta.quota || {};
    const plan = meta.plan && typeof meta.plan === "object" ? meta.plan : {};
    const plansUrl = typeof plan.plansUrl === "string" && plan.plansUrl.startsWith("https://") ? plan.plansUrl : "https://collegefootballdata.com/api-tiers";
    const rows = [
      { label: "Plan", value: text(plan.tierName || q.tierName) },
      { label: "The app runs", value: text(plan.profileLabel) },
      { label: "Calls used this month", value: isNum(plan.used) ? fmtNum(plan.used) : isNum(q.used) ? fmtNum(q.used) : DASH },
      { label: "Calls left", value: isNum(plan.remaining) ? fmtNum(plan.remaining) : DASH },
      { label: "Calls a month", value: isNum(plan.monthlyLimit) ? fmtNum(plan.monthlyLimit) : DASH },
      { label: "This month", value: text(plan.forecast?.text) },
      { label: "Resets", value: text(fmtDate(plan.resetAt || q.resetAt)) },
      { label: "Last checked with CFBD", value: text(fmtDateTime(plan.checkedAt || q.reconciledAt)) },
    ];
    const features = (Array.isArray(plan.features) ? plan.features : []).filter((f) => f && typeof f.label === "string");
    const featureRows = features.map((f) => el("li", { class: "plan-feature" }, el("strong", {}, f.label), " ", f.available === true ? el("span", { class: "note note-good" }, "included") : el("span", { class: "note" }, text(f.note || "not on this plan")), el("div", { class: "note" }, text(f.what))));
    const changeKey = meta.canChangeKey === true ? el("a", { class: "btn", href: "/welcome" }, "Replace the CFBD key") : el("span", { class: "note" }, "The key can be replaced from the server computer.");
    return band({
      id: "settings-quota",
      title: "Your CFBD plan",
      collapsible: false,
      summary: isNum(plan.remaining) ? `${fmtNum(plan.remaining)} calls left` : "",
      state: { status: "ready" },
      body: () => el("div", {},
        statTable({ compact: true, columns: [{ key: "label", label: "", kind: "text", sortable: false }, { key: "value", label: "", kind: "text", sortable: false }], rows }),
        el("ul", { class: "plain-list plan-features" }, featureRows),
        el("p", { class: "note plan-note" }, "Every feature your plan includes is on. A bigger plan adds the rest; nothing else changes. ", el("a", { href: plansUrl, target: "_blank", rel: "noopener" }, "See CFBD's plans")),
        el("p", { class: "settings__actions" }, el("a", { class: "btn", href: "/welcome" }, "Change my teams"), " ", changeKey),
      ),
    });
  }

  function serverBand() {
    const meta = prefsMeta() || {};
    const s = meta.server || {};
    const rows = [
      { label: "Team", value: text(s.team) },
      { label: "Season", value: text(s.season) },
      { label: "Conference", value: text(s.conference) },
      { label: "Time zone", value: text(s.timezone) },
      { label: "Port", value: text(s.port) },
      { label: "Live poll", value: isNum(s.livePollSeconds) ? `every ${s.livePollSeconds} s` : DASH },
      { label: "Data folder", value: text(s.dataDir) },
      { label: "Log folder", value: text(s.logDir) },
    ];
    const prefs = getPrefs();
    const set = meta.teamSet && typeof meta.teamSet === "object" ? meta.teamSet : {};
    const names = (list) => (Array.isArray(list) ? list.filter((v) => typeof v === "string" && v) : []);
    const extra = names(set.extraPrimaries);
    const secondary = [...names(prefs.likedTeams), ...names(prefs.likedConferences), ...names(prefs.likedStates)];
    const locked = set.allowed === false && (names(prefs.primaryTeams).length || secondary.length) ? " (saved; shows with a Tier 2 key)" : "";
    rows[0] = { label: "Home team", value: text(s.team) };
    rows.splice(1, 0, { label: "More primary teams", value: extra.length ? extra.join(", ") : names(prefs.primaryTeams).length ? `${names(prefs.primaryTeams).join(", ")}${locked}` : DASH });
    rows.splice(2, 0, { label: "Secondary teams", value: secondary.length ? `${secondary.join(", ")}${locked}` : DASH });
    return band({ id: "settings-server", title: "Server", collapsible: false, summary: "teams from the setup page; the rest from .env", state: { status: "ready" }, body: () => el("div", {}, statTable({ compact: true, columns: [{ key: "label", label: "", kind: "text", sortable: false }, { key: "value", label: "", kind: "text", sortable: false }], rows }), el("p", { class: "note" }, "Change the home team and the primary and secondary teams on the setup page (the server restarts for a new home team). Only the home team's colors and mascot theme the app. The CFBD key and the network settings live in .env and never show here. The status page has the rest.")) });
  }

  async function saveStations(next, label) {
    await change({ radioStations: next }, label);
    reloadRadioSources(); // the player and the Game program pick up the new list
  }

  function radioBand() {
    // Public release Phase 5b: radio for any team. Stations added here follow RADIO_SOURCES from .env; for a
    // primary team with none, search links and the GitHub request form (radioHelpBlock).
    const p = getPrefs();
    const meta = prefsMeta() || {};
    const saved = (Array.isArray(p.radioStations) ? p.radioStations : []).filter((s) => s && str(s.name) && str(s.url));
    const fromEnv = (Array.isArray(meta.radioSources) ? meta.radioSources : []).filter((s) => s && s.origin === "env").length;
    const fromList = (Array.isArray(meta.radioSources) ? meta.radioSources : []).filter((s) => s && s.origin === "list");
    const teams = Array.isArray(meta.teamSet?.primaries) ? meta.teamSet.primaries.filter((t) => str(t)) : [];
    const team = select(teams.map((t) => ({ value: t, label: t })), teams[0] || "", () => {}, "Station's team");
    const name = el("input", { type: "text", class: "input", maxlength: "60", placeholder: "Station or network name", "aria-label": "Station name" });
    const kind = select(KINDS, "link", () => {}, "How it plays");
    const url = el("input", { type: "url", class: "input", maxlength: "500", placeholder: "https://", spellcheck: "false", "aria-label": "Station address" });
    const problem = el("p", { class: "note note--error", role: "alert", hidden: true });
    const add = () => {
      const entry = { team: team.value || null, name: name.value.trim(), kind: kind.value, url: url.value.trim() };
      const wrong = !entry.name ? "Give the station a name." : !/^https?:\/\//.test(entry.url) ? "The address must start with https:// (or http://)." : saved.some((s) => s.url === entry.url) ? "That station is already in the list." : null;
      problem.hidden = !wrong;
      problem.textContent = wrong || "";
      if (!wrong) saveStations([...saved, entry], "Radio station");
    };
    const list = saved.length
      ? el("ul", { class: "station-list" }, saved.map((s, index) => el("li", {}, el("span", { class: "grow" }, el("strong", {}, text(s.name)), str(s.team) ? `, ${s.team}` : "", ` · ${KINDS.find((k) => k.value === s.kind)?.label || text(s.kind)}`, el("br"), el("small", { class: "mono" }, text(s.url))), el("button", { class: "btn", type: "button", onclick: () => saveStations(saved.filter((_, i) => i !== index), "Radio stations") }, "Remove"))))
      : el("p", { class: "note" }, "No stations added here yet.");
    return band({
      id: "settings-radio",
      title: "Radio stations",
      collapsible: false,
      summary: `${saved.length + fromEnv + fromList.length} in the list`,
      state: { status: "ready" },
      body: () =>
        el(
          "div",
          {},
          list,
          fromEnv ? el("p", { class: "note" }, `${fromEnv} more ${fromEnv === 1 ? "comes" : "come"} from RADIO_SOURCES in the server's .env file.`) : null,
          fromList.length ? el("p", { class: "note" }, `From the app's station list: ${fromList.map((s) => `${text(s.name)}${str(s.team) ? ` (${s.team})` : ""}`).join(", ")}.`) : null,
          el("div", { class: "station-form" }, el("label", {}, "Team", team), el("label", {}, "Name", name), el("label", {}, "How it plays", kind), el("label", {}, "Address", url), el("button", { class: "btn btn--primary", type: "button", onclick: add }, "Add the station")),
          problem,
          el("p", { class: "note" }, "Use the station's official player page, stream address or web page; the app never pulls streams out of other sites. A stream plays in the bar at the bottom of every page; a station player shows inside the app; a link opens a new tab. Audio cannot follow the spoiler delay."),
          radioHelpBlock(meta.radioHelp, { settingsLink: false }),
        ),
    });
  }

  // --- the prompts (Phase 19, owner 2026-10-08: "I don't want the prompt text to be visible. You can't edit it since it has
  // to go into the program"). Each prompt is a card with Copy the prompt and Paste the answer; the text is never shown and
  // there is no template editor. The same buttons sit on the Game program and the Preseason page.
  let drawn = false; // kept: the settings page draws only once its own settings have loaded

  async function api(url, options = {}) {
    const response = await fetch(url, { cache: "no-store", headers: { "Content-Type": "application/json" }, ...options });
    let envelope = null;
    try {
      envelope = await response.json();
    } catch {
      envelope = null;
    }
    if (!response.ok) throw new Error(envelope?.errors?.[0]?.message || `The server answered ${response.status}`);
    return envelope?.data && typeof envelope.data === "object" ? envelope.data : {};
  }

  function promptCard({ id, title, intro, getPrompt, saveAnswer }) {
    return {
      load() {},
      view: () => band({ id, title, collapsible: true, foldable: true, summary: "copy and paste", state: { status: "ready" }, body: () => el("div", { class: "settings" }, el("p", { class: "note" }, intro), promptPaste({ label: title, getPrompt, saveAnswer })) }),
    };
  }

  let notesGame = null; // the game the notes prompt was written for, so a pasted answer saves to the same one
  const prompts = [
    promptCard({
      id: "settings-notes-prompt",
      title: "Notes prompt",
      intro: "This week's notes for the next game: the program notes, injury report, depth charts, TV crew and coaches. Copy the prompt into an AI chat that can search the web, copy its whole answer, and tap Paste the answer.",
      getPrompt: async () => {
        const data = await api("/api/notes/prompt");
        notesGame = data.gameId;
        return data.prompt;
      },
      saveAnswer: async (value) => {
        if (!notesGame) notesGame = (await api("/api/notes/prompt")).gameId;
        return api("/api/notes/save", { method: "POST", body: JSON.stringify({ gameId: notesGame, text: value }) });
      },
    }),
    promptCard({
      id: "settings-coaches-prompt",
      title: "Coaches prompt",
      intro: "Every FBS team's head coach and offensive and defensive coordinators, all conferences in one paste. The Season prompt asks for these too; use this one to refresh only the coaches.",
      getPrompt: async () => (await api("/api/season-notes/prompt?kind=coaches&key=all")).prompt,
      saveAnswer: (value) => api("/api/season-notes/save", { method: "POST", body: JSON.stringify({ kind: "coaches", key: "all", text: value }) }),
    }),
    promptCard({
      id: "settings-costs-prompt",
      title: "Roster costs prompt",
      intro: "Rumored roster costs from a shallow search: every team's total, and your primary teams' positions and players, all conferences in one paste.",
      getPrompt: async () => (await api("/api/season-notes/prompt?kind=costs&key=all")).prompt,
      saveAnswer: (value) => api("/api/season-notes/save", { method: "POST", body: JSON.stringify({ kind: "costs", key: "all", text: value }) }),
    }),
    promptCard({
      id: "settings-season-prompt",
      title: "Season prompt",
      intro: "The whole season in one paste: your primary teams' deep preseason look and every FBS team's head coach and coordinators. The coaches and the roster costs have their own prompts below.",
      getPrompt: async () => (await api("/api/season-notes/prompt?kind=season&key=all")).prompt,
      saveAnswer: (value) => api("/api/season-notes/save", { method: "POST", body: JSON.stringify({ kind: "season", key: "all", text: value }) }),
    }),
  ];

  // --- Phase 16 wave 3: restart from here, and the update check ----------------------------------------
  function restartControl() {
    const said = el("span", { class: "note", role: "status" }, "");
    const sure = el("span", { class: "restart__confirm", hidden: "" },
      el("button", { class: "btn btn--primary", type: "button", onclick: async (event) => {
        event.currentTarget.disabled = true;
        await restartFlow({ say: (words) => { said.textContent = words; }, confirmDuringGame: async () => window.confirm("Our game is under way: the Live sheet drops for about 15 seconds while the server restarts. Restart anyway?") });
      } }, "Restart now"),
      " ",
      el("button", { class: "btn", type: "button", onclick: () => { sure.setAttribute("hidden", ""); start.removeAttribute("hidden"); said.textContent = ""; } }, "Cancel"),
    );
    const start = el("button", { class: "btn", type: "button", onclick: () => { start.setAttribute("hidden", ""); sure.removeAttribute("hidden"); said.textContent = "Every device's page reloads once it's back."; } }, "Restart the server");
    return el("div", { class: "restart" }, start, sure, " ", said);
  }

  const update = { data: null, error: null, checking: false };
  async function loadUpdate(force = false) {
    update.checking = true;
    if (drawn) render();
    try {
      const envelope = await fetchJson(`/api/updates${force ? "?force=1" : ""}`);
      update.data = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
      update.error = null;
    } catch (error) {
      update.error = error?.message || "The update check didn't answer";
    }
    update.checking = false;
    if (drawn) render();
  }

  function updateLine() {
    const u = update.data && typeof update.data === "object" ? update.data : null;
    const again = el("button", { class: "btn btn--quiet", type: "button", disabled: update.checking ? true : null, onclick: () => loadUpdate(true) }, update.checking ? "Checking…" : "Check now");
    if (update.error) return el("p", { class: "note" }, `Update check: ${update.error}. `, again);
    if (!u) return el("p", { class: "note" }, "Update check: not asked yet. ", again);
    if (u.enabled === false) return el("p", { class: "note" }, `You run version ${text(u.current)}. Checking for updates is off (Start and the server).`);
    const when = typeof u.checkedAt === "string" ? ` Checked ${fmtDate(u.checkedAt, "short")}.` : "";
    if (u.newer) {
      const link = typeof u.url === "string" && u.url.startsWith("https://github.com/") ? el("a", { href: u.url, target: "_blank", rel: "noopener" }, "What's new and how to update") : null;
      return el("p", { class: "about__update about__update--new" }, el("strong", {}, `Version ${text(u.latest)} is out`), ` (you run ${text(u.current)}${u.prerelease ? "; it's a pre-release" : ""}). `, link, `${when} `, again);
    }
    return el("p", { class: "note" }, `You run version ${text(u.current)}, the newest${u.latest ? "" : " the app knows of"}.${u.error ? ` ${u.error}` : when} `, again);
  }

  function claudeBand() {
    // Phase 18.7: Claude Code runs the game-week prompts by itself, a few times a week, at the hours each source publishes.
    const slot = el("div", {}, el("p", { class: "note" }, "Checking…"));
    const when = (iso) => (typeof iso === "string" ? fmtDateTime(iso) : DASH);
    async function draw() {
      let s = {};
      try {
        s = (await fetchJson("/api/claude-schedule"))?.data || {};
      } catch (error) {
        slot.replaceChildren(el("p", { class: "note" }, `Could not read the schedule: ${text(error?.message || "no answer")}.`));
        return;
      }
      const p = getPrefs();
      const next = (Array.isArray(s.next) ? s.next : []).filter((n) => n && typeof n === "object");
      const recent = (Array.isArray(s.recent) ? s.recent : []).filter((r) => r && typeof r === "object");
      slot.replaceChildren(...[
        el("div", { class: "settings" },
          row("Run the prompts by themselves", toggle(p.scheduledRuns === true, (value) => { change({ scheduledRuns: value }, "Scheduled runs"); setTimeout(draw, 600); }, "Run the prompts by themselves"), s.commandFound === true ? "About three runs a game week (Monday's notes, then the first and the final availability report) and a few a year (the season load, the coaches, the roster costs). Nothing runs after the game. Each run uses your Claude plan like the buttons do." : "Claude Code is not installed on the server computer (CLAUDE_COMMAND in the .env file sets its path), so nothing can run by itself. Copy and paste works without it."),
        ),
        s.pausedUntil ? el("p", { class: "note note-warn" }, `Paused until ${when(s.pausedUntil)} after three failed runs in a row.`) : null,
        s.running ? el("p", { class: "note" }, `Running now: ${text(s.running)}.`) : null,
        next.length ? el("div", {}, subhead("Next"), el("ul", { class: "plain-list" }, next.map((n) => el("li", {}, el("b", {}, text(n.label)), ` from ${when(n.at)}${p.scheduledRuns === true ? "" : " (off)"}`)))) : el("p", { class: "note" }, "Nothing is planned: no game this week and no season run due."),
        recent.length ? el("div", {}, subhead("Lately"), el("ul", { class: "plain-list" }, recent.map((r) => el("li", {}, `${text(r.key)}: ${r.skipped ? "skipped, " + r.skipped : r.ok ? (r.changed === true ? "done, new information" : r.changed === false ? "done, nothing new" : "done") : "failed" + (typeof r.error === "string" ? ` (${r.error})` : "")} · ${when(r.finishedAt)}`)))) : null,
      ].filter(Boolean));  // replaceChildren would write a null as the word "null"
    }
    draw();
    return band({ id: "settings-claude", title: "Claude on a schedule", collapsible: false, summary: "", state: { status: "ready" }, body: () => slot });
  }

  function friendsBand() {
    // Phase 18.6: the host PIN that makes guests view-only, and the game-day board on a monitor of the server computer.
    const slot = el("div", { class: "settings" }, el("p", { class: "note" }, "Checking…"));
    const send = async (url, body, method = "POST") => {
      const response = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
      let envelope = null;
      try {
        envelope = await response.json();
      } catch {
        envelope = null;
      }
      if (!response.ok) throw new Error(envelope?.errors?.[0]?.message || `The server answered ${response.status}`);
      return envelope?.data || {};
    };
    async function draw() {
      let host = {};
      let screens = {};
      try {
        host = (await fetchJson("/api/host"))?.data || {};
        screens = (await fetchJson("/api/board/screens"))?.data || {};
      } catch (error) {
        slot.replaceChildren(el("p", { class: "note" }, `Could not read these settings: ${text(error?.message || "no answer")}.`));
        return;
      }
      const said = el("p", { class: "note", role: "status" }, "");
      const pin = el("input", { class: "setting__text", type: "password", inputmode: "numeric", autocomplete: "off", maxlength: "8", "aria-label": "New host PIN", placeholder: "4 to 8 digits" });
      const mayEdit = host.isHost === true;
      const setPin = el("button", { class: "btn", type: "button", disabled: mayEdit && (host.pinSet || host.serverComputer) ? null : true, onclick: async () => {
        try {
          await send("/api/host/pin", { pin: pin.value });
          said.textContent = "Saved. Other devices are now view-only.";
          pin.value = "";
          draw();
        } catch (error) {
          said.textContent = error?.message || "Not saved.";
        }
      } }, host.pinSet ? "Change the PIN" : "Set the PIN");
      const removePin = host.pinSet ? el("button", { class: "btn btn--quiet", type: "button", disabled: mayEdit ? null : true, onclick: async () => {
        try {
          await send("/api/host", undefined, "DELETE");
          said.textContent = "Removed. Every device can change settings again.";
          draw();
        } catch (error) {
          said.textContent = error?.message || "Not removed.";
        }
      } }, "Remove the PIN") : null;
      const list = Array.isArray(screens.screens) ? screens.screens : [];
      const pick = el("select", { class: "setting__select", "aria-label": "Screen for the board" }, list.length ? list.map((s) => el("option", { value: String(s.index) }, text(s.name))) : [el("option", { value: "" }, "The default screen")]);
      const boardSaid = el("p", { class: "note", role: "status" }, "");
      const open = el("button", { class: "btn btn--primary", type: "button", disabled: screens.serverComputer === true && screens.browser === true ? null : true, onclick: async () => {
        try {
          const r = await send("/api/board/open", { screen: pick.value === "" ? null : Number(pick.value) });
          boardSaid.textContent = r.screen ? `Opened on ${r.screen}. Press Alt+F4 on it, or Close, to leave.` : "Opened. Press Alt+F4 on it, or Close, to leave.";
        } catch (error) {
          boardSaid.textContent = error?.message || "It did not open.";
        }
      } }, "Open the board there");
      const close = el("button", { class: "btn btn--quiet", type: "button", disabled: screens.serverComputer === true ? null : true, onclick: async () => {
        try {
          await send("/api/board/close", {});
          boardSaid.textContent = "Closed.";
        } catch (error) {
          boardSaid.textContent = error?.message || "It did not close.";
        }
      } }, "Close the board");
      slot.replaceChildren(
        row("Host PIN", el("div", { class: "setting__stack" }, pin, setPin, removePin), host.pinSet ? "A PIN is set: other devices are view-only. Your own tablet signs in once with it (the \"I'm the host\" link at the top). This computer is always the host." : "No PIN yet, so every device that joins can change settings. Set one (from this computer) to make guests view-only."),
        row("Invite friends", el("a", { class: "btn", href: "#invite" }, "Show the QR code"), "A full-screen QR code by IP number, and a guide for watching away from home."),
        row("Big screen", el("div", { class: "setting__stack" }, pick, open, close), screens.serverComputer === true ? (screens.browser === true ? "Opens the game-day board full screen on the monitor you pick (Edge or Chrome, kiosk mode). Alt+F4 on it leaves." : "No Edge or Chrome was found on this computer, so the board cannot open itself. Open the address /#board in any browser, full screen.") : "Open the board from the server computer; this device cannot start a window there. You can still open #board in any browser, even to cast it."),
        said,
        boardSaid,
      );
    }
    draw();
    return band({ id: "settings-friends", title: "Friends and the big screen", collapsible: false, summary: "", state: { status: "ready" }, body: () => slot });
  }

  function aboutBand() {
    // Public release Phase 8: where the app comes from, the link to copy for a friend, and CFBD's credit.
    const a = prefsMeta()?.about && typeof prefsMeta().about === "object" ? prefsMeta().about : {};
    const repo = typeof a.repoUrl === "string" && a.repoUrl.startsWith("https://") ? a.repoUrl : REPO_URL;
    const dataUrl = typeof a.dataUrl === "string" && a.dataUrl.startsWith("https://") ? a.dataUrl : "https://collegefootballdata.com";
    const said = el("span", { class: "note", role: "status" }, "");
    const box = el("textarea", { class: "input about__box", readonly: true, rows: "1", hidden: true, "aria-label": "The link to copy" });
    const copy = el("button", { class: "btn", type: "button", onclick: async () => {
      const done = await copyText(repo, box);
      if (!done) {
        box.value = repo;
        box.hidden = false;
      }
      said.textContent = done ? " Copied." : " Select the link and copy it.";
    } }, "Copy the link");
    // Public release Phase 10: where this install keeps its files, and an Open button on the server computer itself.
    const files = prefsMeta()?.files && typeof prefsMeta().files === "object" ? prefsMeta().files : {};
    const canOpen = prefsMeta()?.canChangeKey === true;
    const opened = el("span", { class: "note", role: "status" }, "");
    const openButton = el("button", { class: "btn", type: "button", onclick: async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const response = await fetch("/api/settings/open-folder", { method: "POST" });
        const body = await response.json().catch(() => ({}));
        opened.textContent = response.ok ? " Opened on the server computer." : ` ${text(body?.errors?.[0]?.message) || "Could not open the folder."}`;
      } catch (error) {
        opened.textContent = " Could not reach the server.";
      } finally {
        button.disabled = false;
      }
    } }, "Open the folder");
    const where = files.packaged ? (files.portable ? " Beside the program, as the file named portable there asks." : " Your app-data folder: a new version of the program finds them there.") : " The project folder.";
    const filesLine = el("p", { class: "note about__files" }, el("strong", {}, "Your files: "), text(files.install) || "-", ".", where, canOpen ? " " : "", canOpen ? openButton : null, opened);
    return band({
      id: "settings-about",
      title: "About",
      collapsible: false,
      summary: typeof a.version === "string" ? `version ${a.version}` : "",
      state: { status: "ready" },
      body: () => el(
        "div",
        { class: "settings" },
        el("p", {}, el("strong", {}, `${text(a.name || "Kickoff Companion")} is available for free from ${text(a.publisher || "Myers Labs")}.`), " Share it with anyone who follows a team:"),
        el("p", { class: "about__link" }, el("a", { href: repo, target: "_blank", rel: "noopener" }, repo), " ", copy, said),
        box,
        filesLine,
        updateLine(),
        el("p", { class: "note" }, el("a", { href: dataUrl, target: "_blank", rel: "noopener" }, text(a.dataCredit || "Data provided by CollegeFootballData.com")), ". Not affiliated with any school, conference, the NCAA or CollegeFootballData.com."),
      ),
    });
  }

  function render() {
    if (!container) return;
    const o = optionRows();
    const sections = [
      section("settings-gameday", "Game day", [...o.problems, ...o.gameday], "saved on the server for every device"),
      readinessBand(),
      section("settings-display", "Display", o.display),
      section("settings-start", "Start and the server", o.start),
      claudeBand(),
      friendsBand(),
      radioBand(),
      ...prompts.map((p) => p.view()),
      quotaBand(),
      serverBand(),
      aboutBand(),
    ];
    const nav = el(
      "nav",
      { class: "settings-nav", "aria-label": "Settings sections" },
      sections.map((b) => {
        const title = b.querySelector?.(".band__title")?.textContent || "";
        const id = b.getAttribute?.("id");
        if (!id || !title) return null;
        const link = el("a", { class: "settings-nav__item", href: `#${id}` }, title);
        link.addEventListener("click", (event) => {
          event.preventDefault(); // a section id is not a route
          revealBand(b);
          for (const a of nav.querySelectorAll(".settings-nav__item")) a.classList.toggle("is-current", a === link);
        });
        return link;
      }),
    );
    container.replaceChildren(el("div", { class: "page settings-page" }, nav, el("div", { class: "settings-main" }, saved, ...sections)));
  }

  return {
    async mount(target) {
      container = target;
      container.replaceChildren(el("div", { class: "page settings-page" }, el("div", { class: "settings-main" }, band({ title: "Settings", collapsible: false, state: { status: "loading" } }))));
      setStatus("quiet", "Loading");
      for (const p of prompts) p.load();
      loadUpdate();
      await loadPrefs(true);
      setStatus(prefsError() ? "offline" : "quiet", prefsError() ? "Offline" : "Settings");
      drawn = true;
      render();
    },
    refresh() {
      return loadPrefs(true).then(render);
    },
    unmount() {
      container = null;
    },
  };
}
