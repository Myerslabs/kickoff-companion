// The Settings page (X6): every option lives here and is stored on the server (owner direction
// 2026-09-23). Spoiler delay, radio source, theme, page refresh, start at login, tray mode, the
// notes command, a Desktop icon, and the quota readout. Each change saves on its own and says so.
// Public release Phase 5b: the score ticker (every game, or my teams with a Tier 2 key), radio stations
// for any team (add, remove, find the broadcast, request it), and the primary and secondary teams.
// Public release Phase 6: the notes prompt the Game program copies for an AI chat, editable here.

import { DASH, el, fmtDate, fmtDateTime, fmtNum, isNum, text } from "../ui/dom.js";
import { band, note } from "../ui/states.js";
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
const str = (value) => (typeof value === "string" && value.trim() ? value.trim() : null);

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

function toggle(checked, onChange, ariaLabel) {
  return el("label", { class: "setting__toggle" }, el("input", { type: "checkbox", checked: checked ? true : null, "aria-label": ariaLabel, onchange: (event) => onChange(event.target.checked) }), el("span", {}, checked ? "On" : "Off"));
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
    saved.classList.remove("note--error");
    try {
      const envelope = await savePrefs(patch);
      const problem = envelope?.errors?.find((e) => e.code === "autostart_failed");
      saved.textContent = problem ? `${label} saved, but: ${problem.message}` : `${label} saved.`;
      if (problem) saved.classList.add("note--error");
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

  function optionsBand() {
    const p = getPrefs();
    const meta = prefsMeta() || {};
    const sources = Array.isArray(meta.radioSources) ? meta.radioSources.filter((s) => s && typeof s.id === "string") : [];
    const tier2 = meta.plan?.likedAllowed === true;
    const delayValue = el("b", {}, `${p.delaySeconds} s`);
    const slider = el("input", { type: "range", min: "0", max: "120", step: "5", value: String(p.delaySeconds), "aria-label": "Spoiler delay in seconds", oninput: (event) => { delayValue.textContent = `${event.target.value} s`; }, onchange: (event) => change({ delaySeconds: Number(event.target.value) }, "Spoiler delay") });
    const notesInput = el("input", { type: "text", class: "setting__text", value: p.notesCommand || "claude", "aria-label": "Notes command", spellcheck: "false", onchange: (event) => change({ notesCommand: event.target.value }, "Notes command") });
    const shortcutButton = el("button", { class: "btn", type: "button", onclick: (event) => makeShortcut(event.currentTarget) }, "Create a Desktop icon");
    const auto = meta.autoStart || {};
    const notes = meta.notes || {};
    return band({
      id: "settings-options",
      title: "Options",
      collapsible: false,
      summary: "saved on the server for every device",
      state: { status: "ready" },
      body: () =>
        el(
          "div",
          { class: "settings" },
          prefsError() ? note(`${prefsError()}. Showing defaults.`, { kind: "error", lead: "Settings could not be loaded." }) : null,
          meta.prefsError ? note(`${meta.prefsError}.`, { kind: "error", lead: "Settings file problem." }) : null,
          row("Spoiler delay", el("div", { class: "setting__slider" }, slider, delayValue), "Every live panel and our line in the ticker run this far behind the broadcast. Audio cannot be delayed."),
          row("Radio source", select([{ value: "", label: "First station in the list" }, ...sources.map((s) => ({ value: s.id, label: `${text(s.name)}${str(s.team) ? `, ${s.team}` : ""} (${text(s.kind)})` }))], p.radioSourceId || "", (value) => change({ radioSourceId: value || null }, "Radio source"), "Radio source"), "The station the Play button on the Game program uses first. Add stations for any team under Radio stations below."),
          row("Score ticker", select([{ value: "national", label: "National: every FBS game (default)" }, { value: "mine", label: tier2 ? "My teams: primary and secondary teams only" : "My teams (shows with a Tier 2 key)", disabled: !tier2 }], p.tickerMode === "mine" && tier2 ? "mine" : "national", (value) => change({ tickerMode: value }, "Score ticker"), "Score ticker"), tier2 ? "My teams shows only your primary and secondary teams' games; when none of them play, every game shows. Pick the teams on the setup page." : "Every plan shows every FBS game. A Tier 2 key adds a ticker of just your teams."),
          row("Theme", select([{ value: "dark", label: "Dark (default)" }, { value: "light", label: "Light" }], p.theme, (value) => change({ theme: value }, "Theme"), "Theme")),
          row("Text size", select(TEXT_SIZES.map((s) => ({ value: s.id, label: `${s.label} (${Math.round(s.scale * 100)}%)` })), textSize(), (value) => {
            const size = setTextSize(value);
            saved.classList.remove("note--error");
            saved.textContent = `Text size ${size.label.toLowerCase()} on this device.`;
          }, "Text size"), "This device only, so the couch tablet and the desk screen can differ. Saved in this browser."),
          row("Keep the screen on", select([{ value: "gameday", label: "On our game days (default)" }, { value: "always", label: "Always" }, { value: "off", label: "Never" }], p.keepScreenOn || "gameday", (value) => change({ keepScreenOn: value }, "Keep the screen on"), "Keep the screen on"), "Stops the tablet from sleeping on any page. Game day means a day we play; the Live sheet also keeps the screen on while plays come in."),
          row("Stat hints", toggle(p.hints !== false, (value) => change({ hints: value }, "Stat hints"), "Stat hints"), "Stat names with a dotted underline explain themselves when tapped. The Glossary in the menu lists every one."),
          row("Page refresh", select([1, 5, 10, 15, 30, 60].map((m) => ({ value: m, label: `every ${m} min` })), p.refreshMinutes, (value) => change({ refreshMinutes: Number(value) }, "Page refresh"), "Page refresh"), "How often Season, Program and Newspaper ask the server again. The live sheet streams regardless."),
          row("Start at login", toggle(p.autoStart, (value) => change({ autoStart: value }, "Start at login"), "Start at login"), loginText(auto)),
          row("Open the app on start", select([{ value: "manual", label: "When started by hand (default)" }, { value: "always", label: "Always, at login too" }, { value: "never", label: "Never" }], p.openBrowser || "manual", (value) => change({ openBrowser: value }, "Open the app on start"), "Open the app on start"), "Opens this app in the server computer's browser once the server is up. Phones and tablets connect from the QR code on the status page."),
          auto.tray ? row("Tray mode", toggle(p.trayMode, (value) => change({ trayMode: value }, "Tray mode"), "Tray mode"), "The start script hides its window behind a tray icon (Open the app, Status, Log, Quit). Takes effect on the next start.") : null,
          row("Desktop icon", shortcutButton, iconText(auto)),
          row("Notes command", notesInput, notes.commandFound ? `Found: ${notes.commandPath}. The Game program also offers to write the notes with it.` : "Optional. Where Claude Code's command-line tool is installed on the server computer, the Game program also offers to write the notes with it. Copy and paste works without it."),
          saved,
        ),
    });
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

  // --- the notes prompt (public release Phase 6) ------------------------------------------------------
  const prompt = { status: "loading", data: null, error: null, message: "" };
  let drawn = false; // the prompt answer may come back before the settings: it draws only once they have

  async function promptCall(method, body) {
    const response = await fetch("/api/notes/template", { method, cache: "no-store", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
    let envelope = null;
    try {
      envelope = await response.json();
    } catch {
      envelope = null;
    }
    if (!response.ok) throw new Error(envelope?.errors?.[0]?.message || `The server answered ${response.status}`);
    return envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
  }

  async function loadPrompt() {
    try {
      prompt.data = await promptCall("GET");
      prompt.status = prompt.data && typeof prompt.data.template === "string" ? "ready" : "error";
      prompt.error = prompt.status === "error" ? "The server sent no prompt" : null;
    } catch (error) {
      prompt.status = "error";
      prompt.error = error?.message || "The prompt did not load";
    }
    if (drawn) render();
  }

  async function savePrompt(method, body, label) {
    prompt.message = `${label}…`;
    render();
    try {
      prompt.data = await promptCall(method, body);
      prompt.message = `${label}: done.`;
    } catch (error) {
      prompt.message = `${label} failed: ${error?.message || "unknown error"}.`;
    }
    render();
  }

  function promptBand() {
    const d = prompt.data && typeof prompt.data === "object" ? prompt.data : {};
    const placeholders = (Array.isArray(d.placeholders) ? d.placeholders : []).filter((p) => typeof p === "string").map((p) => `{${p}}`);
    const box = el("textarea", { class: "input notes-paste__prompt settings__prompt", rows: "14", spellcheck: "false", maxlength: String(isNum(d.maxChars) ? d.maxChars : 20000), "aria-label": "The notes prompt" });
    box.value = typeof d.template === "string" ? d.template : "";
    return band({
      id: "settings-notes-prompt",
      title: "Notes prompt",
      collapsible: false,
      foldable: true,
      summary: prompt.status === "ready" ? (d.custom ? "edited" : "the default") : "",
      state: prompt.status === "loading" ? { status: "loading" } : prompt.status === "error" ? { status: "error", message: `${prompt.error}.` } : { status: "ready" },
      body: () =>
        el(
          "div",
          { class: "settings" },
          el("p", { class: "note" }, "The Game program copies this prompt, filled in for the game, for you to paste into an AI chat; Claude Code on the server gets the same one. Words in braces are filled in for each game: ", placeholders.join(" "), ". {shape} is the notes layout the answer must follow, so keep it."),
          box,
          el(
            "p",
            { class: "settings__actions" },
            el("button", { class: "btn btn--primary", type: "button", onclick: () => savePrompt("PUT", { template: box.value }, "Saving the prompt") }, "Save the prompt"),
            " ",
            el("button", { class: "btn", type: "button", disabled: d.custom ? null : true, onclick: () => savePrompt("DELETE", null, "Back to the default") }, "Back to the default"),
          ),
          prompt.message ? el("p", { class: "note", role: "status" }, prompt.message) : null,
          typeof d.file === "string" && d.file ? el("p", { class: "note" }, `An edited prompt is kept in ${d.file}.`) : null,
        ),
    });
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
        el("p", { class: "note" }, el("a", { href: dataUrl, target: "_blank", rel: "noopener" }, text(a.dataCredit || "Data provided by CollegeFootballData.com")), ". Not affiliated with any school, conference, the NCAA or CollegeFootballData.com."),
      ),
    });
  }

  function render() {
    if (!container) return;
    container.replaceChildren(el("div", { class: "season", style: { gridTemplateColumns: "minmax(0, 1fr)" } }, optionsBand(), radioBand(), promptBand(), el("div", { class: "spread spread--2" }, quotaBand(), serverBand()), aboutBand()));
  }

  return {
    async mount(target) {
      container = target;
      container.replaceChildren(el("div", { class: "season", style: { gridTemplateColumns: "minmax(0, 1fr)" } }, band({ title: "Settings", collapsible: false, state: { status: "loading" } })));
      setStatus("quiet", "Loading");
      loadPrompt();
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
