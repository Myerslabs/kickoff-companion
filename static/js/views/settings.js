// The Profile page, once the Settings page (X6; the layout pass, owner 2026-10-22: "a Profile that shows your settings and
// setup information"; #profile, and #settings and #setup still open it): every option lives here and is stored on the server (owner direction
// 2026-09-23). Spoiler delay, radio source, theme, page refresh, start at login, tray mode, the
// notes command, a Desktop icon, and the quota readout. Each change saves on its own and says so.
// Public release Phase 5b: the score ticker (every game, or my teams with a Tier 2 key), radio stations
// for any team (add, remove, find the broadcast, request it), and the primary and secondary teams.
// Public release Phase 6: the notes prompt the Game program copies for an AI chat, editable here.
// Phase 17 #31 (owner pick: Steam's settings): one row per setting, its name and grey help on the left and the switch or
// picker on the right; switches instead of checkboxes; a green "saved" line.
// The layout pass, board 7 (owner 2026-10-22, https://claude.ai/artifact/QtUh4cS1MsSdwc11fjevCj; "Put the Tier 2 Key info
// in about and help. Change Start and Server to Server Settings. Everything else is good."): a short page. Who and what at
// the top (the team, host or guest, the server, and four facts that open their sections: the CFBD plan with the month's
// calls, the version, the address, the friends); the four settings changed on game day on the page itself (the spoiler
// delay, the theme, keeping the screen on, the text size); then every section a tile saying what is set now, opening its
// settings in the wide flyout (about 83%): Game day, Trivia, Display, Your teams, Friends and the big screen, Radio
// stations, Claude and loading data (gold while something is not loaded), Server Settings, About and help (the CFBD key
// and plan with the version and the files), Setup. #profile=radio (and the old #settings=radio) opens a section's flyout.

import { cvdOn, setCvd } from "../ui/cvd.js";
import { readinessBand } from "../ui/readiness.js";
import { icon } from "../ui/icons.js";
import { ours, usSchool } from "../identity.js";
import { openSheet } from "../ui/remote.js";
import { setSpoiler, spoilerOn } from "../ui/spoiler.js";
import { restartFlow } from "../ui/restart.js";
import { fetchJson } from "./common.js";
import { setupBand } from "./setup-page.js";
import { DASH, el, fmtDate, fmtDateTime, fmtNum, isNum, str, teamLogo, text } from "../ui/dom.js";
import { band, note, subhead } from "../ui/states.js";
import { getPrefs, loadPrefs, prefsError, prefsMeta, savePrefs, setTextSize, TEXT_SIZES, textSize } from "../prefs.js";
import { radioHelpBlock, reloadRadioSources, startRadio } from "../radio.js";
import { copyText } from "../ui/notes-paste.js";
import { feedbackBand, logsLine } from "../ui/feedback.js";

const REPO_URL = "https://github.com/Myerslabs/kickoff-companion"; // the server's own copy wins (about.repoUrl)

const KINDS = [
  { value: "link", label: "Link (opens a tab)" },
  { value: "embed", label: "Station player (shown in the app)" },
  { value: "stream", label: "Stream (plays in the bar)" },
];
// The station guide (2026-10-16): what each kind needs, and a made-up address of that kind.
const STATION_HELP = {
  link: "The station's Listen live page. Always works; it opens in a new tab.",
  embed: "A page that is only the station's player. Plays inside the app when the station allows it.",
  stream: "A direct audio address, often ending in .mp3, .aac, .m3u8 or .pls. Plays in the bar at the bottom of every page.",
};
const STATION_EXAMPLES = {
  link: "https://www.example-station.com/listen-live/",
  embed: "https://player.example-station.com/",
  stream: "https://stream.example-station.com/live.mp3",
};
/** Whether an address looks like a direct audio stream (a hint only: the station's own word wins). */
export function looksLikeAudio(address) {
  return typeof address === "string" && /\.(mp3|aac|m3u8?|pls|ogg|opus)(?:[?#]|$)|\/(?:stream|live|listen)(?:[/?#]|$)|icecast|shoutcast|streamon|streamtheworld/i.test(address.trim());
}
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

export function createSettingsView({ onStatus, arg = null } = {}) {
  let focus = typeof arg === "string" && /^[a-z-]{1,30}$/.test(arg) ? arg : null; // #settings=radio (2026-10-16), #profile=radio: that section's flyout
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
        row("Keep the screen on", select([{ value: "gameday", label: "On our game days (default)" }, { value: "always", label: "Always" }, { value: "off", label: "Never" }], p.keepScreenOn || "gameday", (value) => change({ keepScreenOn: value }, "Keep the screen on"), "Keep the screen on"), "Stops the tablet from sleeping on any page. Game day means a day we play; the In Game sheet also keeps the screen on while plays come in."),
        row("Radio source", select([{ value: "", label: "First station in the list" }, ...sources.map((s) => ({ value: s.id, label: `${text(s.name)}${str(s.team) ? `, ${s.team}` : ""} (${text(s.kind)})` }))], p.radioSourceId || "", (value) => change({ radioSourceId: value || null }, "Radio source"), "Radio source"), "The station the Play button on the Pre-Game Program uses first. Add stations for any team under Radio stations."),
        row("Announcer", toggle(p.announcer !== false, (value) => change({ announcer: value }, "Announcer"), "Announcer"), "A little announcer in a headset calls out each section's stat line the first time it scrolls into view. Nothing moves when the device asks for reduced motion."),
        row("Score ticker", select([{ value: "national", label: "National: every FBS game (default)" }, { value: "mine", label: tier2 ? "My teams: primary and secondary teams only" : "My teams (shows with a Tier 2 key)", disabled: !tier2 }], p.tickerMode === "mine" && tier2 ? "mine" : "national", (value) => change({ tickerMode: value }, "Score ticker"), "Score ticker"), tier2 ? "My teams shows only your primary and secondary teams' games; when none of them play, every game shows. Pick the teams with Change my teams on the Season page." : "Every plan shows every FBS game. A Tier 2 key adds a ticker of just your teams."),
      ],
      trivia: [
        row("Trivia during the game", toggle(p.trivia !== false, (value) => change({ trivia: value }, "Trivia"), "Trivia during the game"), "Three-choice questions from the schools' facts in a small popup in the corner of any page, for the tablets that joined with a team name; each tablet is asked when it connects on a game day. Off is off for every tablet."),
        row("Leaderboard", toggle(p.triviaBoard !== false, (value) => change({ triviaBoard: value }, "Leaderboard"), "Leaderboard"), "The room's standings by team name, in the popup between questions and on the Trivia page. Off, every tablet keeps its own score."),
        row("Before and after our game", select([{ value: "15", label: "A question every 15 minutes (default)" }, { value: "30", label: "A question every 30 minutes" }, { value: "game", label: "Only during our game" }], p.triviaPace || "15", (value) => change({ triviaPace: value }, "Before and after our game"), "Before and after our game"), "Game day runs from the first join to the last tablet. Before kickoff and after the final the questions are about the teams in the games on, from the ticker; during our game one at each break (the end of the 1st quarter, halftime, the end of the 3rd and the end of the game), whatever the pace."),
      ],
      display: [
        row("Theme", select([{ value: "dark", label: "Dark (default)" }, { value: "light", label: "Light" }], p.theme, (value) => change({ theme: value }, "Theme"), "Theme"), "Charcoal or light; the team's colors mark what is ours either way."),
        row("Text size", select(TEXT_SIZES.map((s) => ({ value: s.id, label: `${s.label} (${Math.round(s.scale * 100)}%)` })), textSize(), (value) => {
          const size = setTextSize(value);
          saved.classList.remove("note--error");
          saved.classList.add("setting__saved--ok");
          saved.textContent = `Text size ${size.label.toLowerCase()} on this device.`;
        }, "Text size"), "This device only, so the couch tablet and the desk screen can differ. Saved in this browser."),
        row("Stat hints", toggle(p.hints !== false, (value) => change({ hints: value }, "Stat hints"), "Stat hints"), "A small question mark after a stat's name explains it when tapped. The Glossary in the menu lists every one."),
        row("Color-blind friendly colors", toggle(cvdOn(), (value) => setCvd(value), "Color-blind friendly colors"), "Blue and orange instead of green and red, and a shape on every rank chip (up for the top quarter, a dot for the middle, down for the bottom). Only this device."),
        row("Spoiler mode", toggle(spoilerOn(), (value) => setSpoiler(value), "Spoiler mode"), "For a recorded game: this device hides the scores, results, win chance and plays until you tap them. Only this device; the host and other devices are not affected."),
        row("Page refresh", select([1, 5, 10, 15, 30, 60].map((m) => ({ value: m, label: `every ${m} min` })), p.refreshMinutes, (value) => change({ refreshMinutes: Number(value) }, "Page refresh"), "Page refresh"), "How often Season, Program and Newspaper ask the server again. The In Game sheet streams regardless."),
      ],
      setup: [
        // owner 2026-10-10: Device setup is First time setup, here in the Profile (board 7: in the Setup section)
        row("First time setup", el("a", { class: "btn", href: "/setup" }, "Open"), "Connect a phone, a tablet or a TV: the QR code and the address to open, and, with HTTPS on, trusting the certificate once. Nothing to install."),
      ],
      start: [
        row("Start at login", toggle(p.autoStart, (value) => change({ autoStart: value }, "Start at login"), "Start at login"), loginText(auto)),
        row("Open the app on start", select([{ value: "manual", label: "When started by hand (default)" }, { value: "always", label: "Always, at login too" }, { value: "never", label: "Never" }], p.openBrowser || "manual", (value) => change({ openBrowser: value }, "Open the app on start"), "Open the app on start"), "Opens this app in the server computer's browser once the server is up. Phones and tablets connect from the QR code on the status page."),
        auto.tray ? row("Tray mode", toggle(p.trayMode !== "off", (value) => change({ trayMode: value ? "on" : "off" }, "Tray mode"), "Tray mode"), "On by default: the server's window hides behind a tray icon by the clock (double-click it to open the app; its menu has Status, Log and Quit). Off keeps the window on the taskbar. Takes effect on the next start.") : null, // on by default (owner 2026-10-23)
        row("Desktop icon", shortcutButton, iconText(auto)),
        row("Nightly backup", toggle(p.backups !== false, (value) => change({ backups: value }, "Nightly backup"), "Nightly backup"), backupText(meta.housekeeping)),
        row("HTTPS for my devices", httpsControl(meta.network), `${meta.network?.https ? "On: this server also answers https://." : "Off: plain HTTP only."} On, your own devices trust the certificate once on First time setup and then get the screen lock without the video, one-tap paste of the answer and the home-screen app; guests keep http:// and need nothing. Switching restarts the server.`),
        row("Restart the server", restartControl(), "Starts the server over in the same window, for a changed setting or an update pulled while it runs. The page reloads when it's back, usually 10 to 20 seconds."),
        row("Check for updates", toggle(p.updateCheck !== false, (value) => change({ updateCheck: value }, "Check for updates"), "Check for updates"), "Once a day the server asks GitHub whether a newer release is out and says so under About and help. It never downloads anything by itself."),
      ],
      claude: [
        row("Claude Code", el("span", { class: "setting__value" }, notes.commandFound ? "Found" : "Not found"), notes.commandFound ? `Found: ${notes.commandPath}. The Pre-Game Program also offers to write the notes with it. Only Claude Code runs, and only to answer the prompt.` : "Optional. Claude Code is not installed on the server computer, so copy and paste each prompt. To use it, install it, or set CLAUDE_COMMAND in the .env file to its full path."),
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

  /** Label-and-value facts as a plain list, as on the status page (tables wave 3, owner 2026-10-10): never a table under
   *  an empty head row. The value wraps (a sentence, a list of teams, a folder's path breaks anywhere). */
  function factList(rows, label) {
    return el("dl", { class: "facts settings-facts", "aria-label": label }, rows.map((r) => [el("dt", {}, text(r.label)), el("dd", {}, text(r.value))]));
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
        factList(rows, "Your CFBD plan"),
        typeof plan.warning === "string" && plan.warning ? el("p", { class: "note note-bad", role: "alert" }, plan.warning) : null, // a key CFBD reports as out of calls
        el("ul", { class: "plain-list plan-features" }, featureRows),
        el("p", { class: "note plan-note" }, "Every feature your plan includes is on. A bigger plan adds the rest; nothing else changes. ", el("a", { href: plansUrl, target: "_blank", rel: "noopener" }, "See CFBD's plans")),
        el("p", { class: "settings__actions" }, changeKey),
      ),
    });
  }

  /** The teams the install follows (which only Settings knows): the home team, more primary teams, the secondary ones. */
  function teamsOf() {
    const meta = prefsMeta() || {};
    const prefs = getPrefs();
    const set = meta.teamSet && typeof meta.teamSet === "object" ? meta.teamSet : {};
    const names = (list) => (Array.isArray(list) ? list.filter((v) => typeof v === "string" && v) : []);
    const extra = names(set.extraPrimaries);
    const saved = names(prefs.primaryTeams);
    const secondary = [...names(prefs.likedTeams), ...names(prefs.likedConferences), ...names(prefs.likedStates)];
    const locked = set.allowed === false && (saved.length || secondary.length);
    return { home: text(meta.server?.team), primary: extra.length ? extra : saved, secondary, locked };
  }

  function teamsBand() {
    // freeze wave F3 (one fact, one source): the season, conference, time zone, port and live poll are the status page's
    // Configuration panel; this keeps the teams. Board 7: the CFBD key and plan moved to About and help.
    const t = teamsOf();
    const lock = t.locked ? " (saved; shows with a Tier 2 key)" : "";
    const rows = [
      { label: "Home team", value: t.home },
      { label: "More primary teams", value: t.primary.length ? `${t.primary.join(", ")}${lock}` : DASH },
      { label: "Secondary teams", value: t.secondary.length ? `${t.secondary.join(", ")}${lock}` : DASH },
    ];
    return band({ id: "settings-teams", title: "Your teams", collapsible: false, state: { status: "ready" }, body: () => el("div", {}, factList(rows, "Your teams"), el("p", { class: "note" }, "Only the home team's colors and mascot theme the app; a new home team restarts the server. More primary and secondary teams need a Tier 2 key."), el("p", { class: "settings__actions" }, el("a", { class: "btn", href: "/welcome" }, "Change my teams"), " ", el("a", { class: "btn btn--quiet", href: "#season" }, "Their seasons"))) });
  }

  /** The folders this install keeps (About and help): where the data and the logs are. */
  function foldersBand() {
    const s = prefsMeta()?.server || {};
    return band({ id: "settings-folders", title: "The data and the logs", collapsible: false, state: { status: "ready" }, body: () => el("div", {}, factList([{ label: "Data folder", value: text(s.dataDir) }, { label: "Log folder", value: text(s.logDir) }], "Folders"), el("p", { class: "note" }, "The season, the time zone, the port, the live poll and the network name are on the ", el("a", { href: "/status" }, "status page"), "; the key and the network settings live in .env and never show here.")) });
  }

  async function saveStations(next, label) {
    await change({ radioStations: next }, label);
    reloadRadioSources(); // the player and the Game program pick up the new list
  }

  function radioBand() {
    // Public release Phase 5b: radio for any team. Stations added here follow RADIO_SOURCES from .env; for a
    // primary team with none, search links and the GitHub request form (radioHelpBlock). 2026-10-16 (owner: "when looking
    // to load a station, it needs much better instructions"): the steps first, a help line under each field that follows
    // the kind picked, a Try it that plays or opens the address before it is saved, and a warning for a stream address
    // that does not look like audio.
    const p = getPrefs();
    const meta = prefsMeta() || {};
    const saved = (Array.isArray(p.radioStations) ? p.radioStations : []).filter((s) => s && str(s.name) && str(s.url));
    const fromEnv = (Array.isArray(meta.radioSources) ? meta.radioSources : []).filter((s) => s && s.origin === "env").length;
    const fromList = (Array.isArray(meta.radioSources) ? meta.radioSources : []).filter((s) => s && s.origin === "list");
    const sample = (Array.isArray(meta.radioSources) ? meta.radioSources : []).find((s) => s && s.origin === "sample");
    const teams = Array.isArray(meta.teamSet?.primaries) ? meta.teamSet.primaries.filter((t) => str(t)) : [];
    const team = select(teams.map((t) => ({ value: t, label: t })), teams[0] || "", () => {}, "Station's team");
    const name = el("input", { type: "text", class: "input", maxlength: "60", placeholder: "e.g. Station 101.5 FM", "aria-label": "Station name" });
    const url = el("input", { type: "url", class: "input", maxlength: "500", placeholder: STATION_EXAMPLES.link, spellcheck: "false", "aria-label": "Station address" });
    const kindHelp = el("small", { class: "station-form__help" }, STATION_HELP.link);
    const problem = el("p", { class: "note note--error", role: "alert", hidden: true });
    const warn = el("p", { class: "note note-warn", role: "status", hidden: true });
    let kind = null;
    const entry = () => ({ team: team.value || null, name: name.value.trim(), kind: kind?.value || "link", url: url.value.trim() });
    const checkAddress = () => {
      const e = entry();
      const odd = e.kind === "stream" && /^https?:\/\//.test(e.url) && !looksLikeAudio(e.url);
      warn.hidden = !odd;
      warn.textContent = odd ? "That address does not look like a direct audio stream (they usually end in .mp3, .aac, .m3u8 or .pls). If Try it stays silent, save it as a Link instead." : "";
    };
    kind = select(KINDS, "link", (value) => {
      kindHelp.textContent = STATION_HELP[value] || "";
      url.setAttribute("placeholder", STATION_EXAMPLES[value] || "https://");
      checkAddress();
    }, "How it plays");
    url.addEventListener("input", checkAddress);
    const say = (message) => {
      problem.hidden = !message;
      problem.textContent = message || "";
    };
    const add = () => {
      const e = entry();
      const wrong = !e.name ? "Give the station a name." : !/^https?:\/\//.test(e.url) ? "The address must start with https:// (or http://). Copy it from the browser's address bar." : saved.some((s) => s.url === e.url) ? "That station is already in the list." : null;
      say(wrong);
      if (!wrong) saveStations([...saved, e], "Radio station");
    };
    const tryIt = () => {
      const e = entry();
      if (!/^https?:\/\//.test(e.url)) {
        say("Paste the address first: it must start with https:// (or http://).");
        return;
      }
      say(null);
      startRadio({ id: "try-station", name: e.name || "Trying a station", kind: e.kind, url: e.url, team: e.team }, { keep: false });
      warn.hidden = false;
      warn.textContent = e.kind === "link"
        ? "The station's page opened in a new tab. If it plays there, this Link works."
        : e.kind === "embed"
          ? "The station's player is in the bar at the bottom. If it shows blank, the station does not allow it inside other apps: pick Link."
          : "Listen in the bar at the bottom. Silent after a few seconds? Pick Station player or Link instead.";
    };
    const list = saved.length
      ? el("ul", { class: "station-list" }, saved.map((s, index) => el("li", {}, el("span", { class: "grow" }, el("strong", {}, text(s.name)), str(s.team) ? `, ${s.team}` : "", ` · ${KINDS.find((k) => k.value === s.kind)?.label || text(s.kind)}`, el("br"), el("small", { class: "mono" }, text(s.url))), el("button", { class: "btn", type: "button", onclick: () => saveStations(saved.filter((_, i) => i !== index), "Radio stations") }, "Remove"))))
      : el("p", { class: "note" }, "No stations added here yet.");
    const steps = el(
      "ol",
      { class: "station-steps" },
      el("li", {}, el("b", {}, "Find your team's radio network. "), "Every school has a flagship station that carries its games. The search buttons below look for it; the school's athletics site usually names it too."),
      el("li", {}, el("b", {}, "Open the station's own Listen live page "), "and copy its address from the browser's address bar."),
      el("li", {}, el("b", {}, "Pick how it plays. "), "Link always works: it opens the station's page in a new tab. Station player plays that page's player inside the app, when the station allows it. Stream is only for a direct audio address, and plays in the bar at the bottom of every page."),
      el("li", {}, el("b", {}, "Fill in the form and tap Try it. "), "When it plays, tap Add the station. You can add more than one (a stream and a link, say); the Pre-Game Program lists them all."),
    );
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
          sample ? el("p", { class: "note" }, `Until you add one, the radio offers a sample station so you can hear how it works: ${text(sample.name)}${str(sample.team) ? ` (${sample.team})` : ""}.`) : null,
          subhead("How to add your team's station"),
          steps,
          el(
            "div",
            { class: "station-form" },
            el("label", {}, "Team", team, el("small", { class: "station-form__help" }, "Whose games the station carries.")),
            el("label", {}, "Name", name, el("small", { class: "station-form__help" }, "What the radio list will call it.")),
            el("label", {}, "How it plays", kind, kindHelp),
            el("label", {}, "Address", url, el("small", { class: "station-form__help" }, "Paste it from the browser's address bar.")),
            el("div", { class: "station-form__buttons" }, el("button", { class: "btn", type: "button", onclick: tryIt }, "Try it"), el("button", { class: "btn btn--primary", type: "button", onclick: add }, "Add the station")),
          ),
          problem,
          warn,
          el("p", { class: "note" }, "Use the station's own player page, stream address or web page; the app never pulls streams out of other sites. Audio cannot follow the spoiler delay."),
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

  // Freeze wave F3 (one fact, one source): the four prompt cards that were here (the notes, the coaches, the costs, the
  // season) live on the Load data page, with their Copy, Paste and Run; Settings keeps one pointer.
  const prompts = [
    {
      load() {},
      view: () => band({ id: "settings-prompts", title: "Prompts", collapsible: false, summary: "on the Load data page", state: { status: "ready" }, body: () => el("div", { class: "settings" }, el("p", { class: "note" }, "This week's notes, the season load, the coaches and the roster costs: copy each prompt, paste the answer, or run it with Claude Code, on the Load data page."), el("p", { class: "settings__actions" }, el("a", { class: "btn", href: "#prompts" }, "Open Load data"))) }),
    },
  ];

  // --- Phase 16 wave 3: restart from here, and the update check ----------------------------------------
  /** Group five: the HTTPS switch. Server computer only; the server restarts and this page moves to the right address. */
  function httpsControl(network) {
    const n = network && typeof network === "object" ? network : {};
    const said = el("span", { class: "note", role: "status" }, n.canSwitch ? "" : "Switch it from the server computer.");
    const ask = async (value, force) => {
      const response = await fetch("/api/settings/https", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ on: value, force }) });
      let body = null;
      try {
        body = await response.json();
      } catch {
        body = null;
      }
      return { status: response.status, ok: response.ok, body };
    };
    const control = toggle(n.https === true, async (value) => {
      said.textContent = "Switching…";
      let r = await ask(value, false);
      if (r.status === 409 && window.confirm("Our game is under way: the In Game sheet drops for about 15 seconds while the server restarts. Switch now?")) r = await ask(value, true);
      if (!r.ok) {
        said.textContent = r.body?.errors?.[0]?.message || `Not switched: the server answered ${r.status}.`;
        setTimeout(render, 1200);
        return;
      }
      if (!r.body?.data?.restarting) {
        said.textContent = value ? "Already on." : "Already off.";
        return;
      }
      said.textContent = value
        ? "Restarting. In 20 seconds this page opens First time setup over http://, which walks this device through trusting the certificate and shows the https:// address."
        : "Restarting. This page reloads over http:// in 20 seconds.";
      setTimeout(() => {
        try {
          window.location.href = `http://${window.location.host}/${value ? "setup" : "#settings"}`;
        } catch {
          // no window (a test): nothing to move
        }
      }, 20000);
    }, "HTTPS for my devices");
    if (!n.canSwitch) control.querySelector("input")?.setAttribute("disabled", "");
    return el("div", { class: "restart" }, control, " ", said);
  }

  function restartControl() {
    const said = el("span", { class: "note", role: "status" }, "");
    const sure = el("span", { class: "restart__confirm", hidden: "" },
      el("button", { class: "btn btn--primary", type: "button", onclick: async (event) => {
        event.currentTarget.disabled = true;
        await restartFlow({ say: (words) => { said.textContent = words; }, confirmDuringGame: async () => window.confirm("Our game is under way: the In Game sheet drops for about 15 seconds while the server restarts. Restart anyway?") });
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
    if (u.enabled === false) return el("p", { class: "note" }, `You run version ${text(u.current)}. Checking for updates is off (Server Settings).`);
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
          row("Run the prompts by themselves", toggle(s.enabled === true, (value) => { change({ scheduledRuns: value }, "Scheduled runs"); setTimeout(draw, 600); }, "Run the prompts by themselves"), s.commandFound === true ? `On by itself while Claude Code is found on the server computer (owner 2026-10-13)${p.scheduledRuns === false ? ", switched off here" : ""}. Once a day it runs everything that is missing; a game week adds Monday's notes and the availability reports; the season load, the coaches and the roster costs come at their times. Nothing runs after the game. Each run uses your Claude plan like the buttons do. The Load data page shows what is next and what ran.` : "Claude Code is not installed on the server computer (CLAUDE_COMMAND in the .env file sets its path), so nothing can run by itself. Copy and paste works without it, on the Load data page."),
        ),
        s.pausedUntil ? el("p", { class: "note note-warn" }, `Paused until ${when(s.pausedUntil)} after three failed runs in a row.`) : null,
        s.running ? el("p", { class: "note" }, `Running now: ${text(s.running)}.`) : null,
        // freeze wave F3 (one fact, one source): the Next and Lately lists live on the Load data page, once
        el("p", { class: "settings__actions" }, el("a", { class: "btn", href: "#prompts" }, "Open Load data"), " ", el("span", { class: "note" }, next.length ? `Next: ${text(next[0].label)} from ${when(next[0].at)}${s.enabled === true ? "" : " (off)"}${recent.length ? `; the last run ${when(recent[0].finishedAt)}` : ""}. The whole schedule and what ran are there.` : "Nothing is planned: no game this week and no season run due. The schedule and what ran are there.")),
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
          boardSaid.textContent = r.screen ? `Opened on ${r.screen}. Escape on it goes back to In Game; Alt+F4 on it, or Close, shuts the window.` : "Opened. Escape on it goes back to In Game; Alt+F4 on it, or Close, shuts the window.";
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
      // freeze wave F5 (owner 2026-10-20): the name on the notes you write, "Note from Pat"
      const nameInput = el("input", { class: "setting__text", type: "text", maxlength: "40", autocomplete: "name", value: typeof prefsMeta()?.prefs?.hostName === "string" ? prefsMeta().prefs.hostName : "", placeholder: "the host", "aria-label": "Your name", onchange: (event) => change({ hostName: event.target.value.trim() }, "Your name") });
      slot.replaceChildren(
        row("Your name", nameInput, "On the notes you write on the Pre-Game Program and In Game: \"Note from Pat\". Blank reads \"the host\"."),
        row("Host PIN", el("div", { class: "setting__stack" }, pin, setPin, removePin), host.pinSet ? "A PIN is set: other devices are view-only. Your own tablet signs in once with it (the \"I'm the host\" link at the top). This computer is always the host." : "No PIN yet, so every device that joins can change settings. Set one (from this computer) to make guests view-only."),
        row("Invite friends", el("a", { class: "btn", href: "#invite" }, "Show the QR code"), "A full-screen QR code by IP number, and a guide for watching away from home."),
        row("Away from home", toggle((prefsMeta()?.prefs?.awayFromHome) === true, (value) => change({ awayFromHome: value }, "Away from home"), "Away from home"), "For a venue's or a hotspot's Wi-Fi. On: the network name is not announced, and only devices that scan your code (or open its exact address) can watch; everyone else sees a short page saying the companion is away. Your own devices keep working. Off at home."),
        row("Big screen", el("div", { class: "setting__stack" }, pick, open, close), screens.serverComputer === true ? (screens.browser === true ? "Opens the game-day board full screen on the monitor you pick (Edge or Chrome, kiosk mode). Escape on it goes back to In Game; Alt+F4 on it closes the window." : "No Edge or Chrome was found on this computer, so the board cannot open itself. Open the address /#board in any browser, full screen.") : "Open the board from the server computer; this device cannot start a window there. You can still open #board in any browser, even to cast it."),
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
        logsLine(), // owner 2026-10-23: the logs, to download or copy
        updateLine(),
        el("p", { class: "note" }, el("a", { href: dataUrl, target: "_blank", rel: "noopener" }, text(a.dataCredit || "Data provided by CollegeFootballData.com")), ". Not affiliated with any school, conference, the NCAA or CollegeFootballData.com."),
      ),
    });
  }

  // --- the page (board 7): who and what, the game-day four, the tiles; each section in a wide flyout ----------------------
  const SECTIONS = [
    { id: "gameday", title: "Game day", icon: "live" },
    { id: "trivia", title: "Trivia", icon: "trivia" },
    { id: "display", title: "Display", icon: "sun" },
    { id: "teams", title: "Your teams", icon: "shield" },
    { id: "friends", title: "Friends and the big screen", icon: "person" },
    { id: "radio", title: "Radio stations", icon: "radio" },
    { id: "claude", title: "Claude and loading data", icon: "sparkle" },
    { id: "server", title: "Server Settings", icon: "bars" },
    { id: "about", title: "About and help", icon: "book" },
    { id: "setup", title: "Setup", icon: "program" },
    { id: "feedback", title: "Feedback", icon: "page" }, // owner 2026-10-23: the reports with their logs (new: at the end)
  ];
  // the old section names of #settings=... (saved links, the radio's "Add it in Settings") lead to their new homes
  const ALIASES = { start: "server", quota: "about", plan: "about", prompts: "claude", folders: "about", teams: "teams", logs: "about" };
  const sectionOf = (name) => {
    const key = typeof name === "string" ? name.replace(/^settings-/, "") : "";
    const id = ALIASES[key] || key;
    return SECTIONS.find((sec) => sec.id === id) || null;
  };
  let flyout = null; // { id, handle } while a section is open
  const extras = { host: null, invite: null, readiness: null, asked: false }; // the facts read after the page is drawn

  function sectionBody(id) {
    const o = optionRows();
    const rows = (list) => el("div", { class: "settings" }, list);
    switch (id) {
      case "gameday": return [rows([...o.problems, ...o.gameday])];
      case "trivia": return [rows(o.trivia)];
      case "display": return [rows(o.display)];
      case "teams": return [teamsBand()];
      case "friends": return [friendsBand()];
      case "radio": return [radioBand()];
      case "claude": return [rows(o.claude), claudeBand(), readinessBand(), ...prompts.map((pr) => pr.view())];
      case "server": return [rows(o.start)];
      case "about": return [quotaBand(), aboutBand(), foldersBand()];
      case "setup": return [rows(o.setup), setupBand()];
      case "feedback": return [feedbackBand()];
      default: return [note("Nothing here.")];
    }
  }

  function flyoutContent(id) {
    return el("div", { class: "profile-flyout" }, saved, ...sectionBody(id));
  }

  function openSection(id) {
    const sec = SECTIONS.find((x) => x.id === id);
    if (!sec) return null;
    if (flyout && flyout.id === id) return flyout.handle;
    if (flyout) flyout.handle.close();
    saved.textContent = "";
    const handle = openSheet({
      title: sec.title,
      wide: true,
      className: "profile-sheet",
      body: flyoutContent(id),
      onClose: () => {
        if (flyout && flyout.handle === handle) flyout = null;
        render(); // the tiles say what is set now
      },
    });
    flyout = { id, handle };
    return handle;
  }

  const onOff = (on) => (on ? "on" : "off");

  /** What each tile says is set now, in one line. */
  function tileLine(id) {
    const p = getPrefs();
    const meta = prefsMeta() || {};
    const sources = Array.isArray(meta.radioSources) ? meta.radioSources.filter((x) => x && typeof x.id === "string") : [];
    const radio = sources.find((x) => x.id === p.radioSourceId) || sources[0];
    const plan = meta.plan && typeof meta.plan === "object" ? meta.plan : {};
    const auto = meta.autoStart || {};
    switch (id) {
      case "gameday": return `Radio ${radio ? (radio.origin === "sample" ? "a sample station" : text(radio.name)) : "none yet"} · ticker ${p.tickerMode === "mine" && plan.likedAllowed === true ? "my teams" : "every FBS game"} · announcer ${onOff(p.announcer !== false)}`;
      case "trivia": return `${p.trivia !== false ? "On" : "Off"} · leaderboard ${onOff(p.triviaBoard !== false)} · ${p.triviaPace === "30" ? "every 30 min" : p.triviaPace === "game" ? "only during our game" : "every 15 min"} before and after our game`;
      case "display": return `Stat hints ${onOff(p.hints !== false)} · color-blind colors ${onOff(cvdOn())} · spoiler mode ${onOff(spoilerOn())} · refresh ${isNum(p.refreshMinutes) ? `${p.refreshMinutes} min` : DASH}`;
      case "teams": {
        const t = teamsOf();
        return `${t.home || "No home team"} · ${t.primary.length} more primary · ${t.secondary.length} secondary`;
      }
      case "friends": return extras.host ? `Host PIN ${extras.host.pinSet === true ? "set" : "not set"} · invite with the QR code · the big screen` : "The host PIN, inviting friends, the big screen";
      case "radio": {
        const n = sources.filter((x) => x.origin !== "sample").length;
        return n ? `${n === 1 ? "1 station" : `${n} stations`}${radio ? ` (${text(radio.name)})` : ""} · how to add yours` : "No station yet · how to add yours";
      }
      case "claude": {
        const missing = Array.isArray(extras.readiness?.items) ? extras.readiness.items.length : null;
        return `Claude Code ${meta.notes?.commandFound ? "found" : "not found"} · schedule ${onOff(p.scheduledRuns !== false && meta.notes?.commandFound === true)}${missing ? ` · ${missing} ${missing === 1 ? "load" : "loads"} missing` : missing === 0 ? " · everything loaded" : ""}`;
      }
      case "server": return `Start at login ${onOff(p.autoStart === true && auto.supported !== false)} · backups ${onOff(p.backups !== false)} · ${meta.network?.https ? "HTTPS" : "HTTP"} · restart, updates`;
      case "about": return `${text(plan.tierName || meta.quota?.tierName)} key · ${isNum(plan.used) ? fmtNum(plan.used) : DASH} of ${isNum(plan.monthlyLimit) ? fmtNum(plan.monthlyLimit) : DASH} calls · version ${text(meta.about?.version)}`;
      case "setup": return "First time setup · the demo · the Archive · the Season in review";
      case "feedback": return typeof document !== "undefined" && document.body?.dataset?.role === "guest" ? "Send it from the menu; it goes to the host" : "The reports sent from the menu, each with its logs";
      default: return "";
    }
  }

  function tile(sec) {
    const warn = sec.id === "claude" && Array.isArray(extras.readiness?.items) && extras.readiness.items.length > 0;
    return el(
      "button",
      { type: "button", class: `profile-tile${warn ? " profile-tile--warn" : ""}`, dataset: { section: sec.id }, "aria-haspopup": "dialog", onclick: () => openSection(sec.id) },
      el("span", { class: "profile-tile__icon", "aria-hidden": "true" }, icon(sec.icon)),
      el("span", { class: "profile-tile__words" }, el("b", {}, sec.title), el("small", {}, tileLine(sec.id))),
      el("span", { class: "profile-tile__go", "aria-hidden": "true" }, icon("wide")),
    );
  }

  /** One fact at the top that opens its section. */
  function fact(label, value, sub, section) {
    return el("button", { type: "button", class: "profile-fact", onclick: () => openSection(section) }, el("small", {}, label), el("b", {}, value), el("span", {}, sub));
  }

  function helloCard() {
    const meta = prefsMeta() || {};
    const me = ours();
    const plan = meta.plan && typeof meta.plan === "object" ? meta.plan : {};
    const guest = typeof document !== "undefined" && document.body?.dataset?.role === "guest";
    const u = update.data && typeof update.data === "object" ? update.data : null;
    let address = null;
    try {
      address = extras.invite?.url ? new URL(extras.invite.url) : null;
    } catch {
      address = null;
    }
    return el(
      "section",
      { class: "profile-hello", "aria-label": "This install" },
      el("div", { class: "profile-hello__logo" }, teamLogo({ school: usSchool(), abbreviation: me.label, color: me.color, altColor: me.altColor }, { size: 64, lazy: false })),
      el("div", { class: "profile-hello__words" }, el("h1", {}, text(me.school ? `${me.school}${me.name && me.name !== me.school ? ` ${me.name}` : ""}` : "Kickoff Companion")), el("p", {}, me.conference ? `${me.conference} · the team this install follows and colors` : "The team this install follows and colors")),
      el("div", { class: "profile-hello__chips" }, el("span", { class: "profile-chip profile-chip--role" }, guest ? "Guest" : "Host"), el("span", { class: `profile-chip${prefsError() ? " profile-chip--bad" : " profile-chip--good"}` }, prefsError() ? "Server not answering" : "Server running")),
      el(
        "div",
        { class: "profile-facts" },
        fact("CFBD plan", text(plan.tierName || meta.quota?.tierName), isNum(plan.used) && isNum(plan.monthlyLimit) ? `${fmtNum(plan.used)} of ${fmtNum(plan.monthlyLimit)} calls` : "this month's calls", "about"),
        fact("Version", text(meta.about?.version), u ? (u.newer ? `${text(u.latest)} is out` : "up to date") : "checking", "about"),
        fact("Address", address ? address.hostname : DASH, address ? (address.port ? `port ${address.port}` : address.protocol.replace(":", "")) : "the home network", "friends"),
        fact("Friends", extras.host ? (extras.host.pinSet === true ? "PIN set" : "No PIN") : DASH, extras.host ? (extras.host.pinSet === true ? "guests view only" : "every device can change settings") : "the host PIN", "friends"),
      ),
    );
  }

  /** The four settings changed on game day, on the page itself (board 7). */
  function quickCard() {
    const p = getPrefs();
    const delayValue = el("b", { class: "profile-quick__value" }, `${p.delaySeconds} s`);
    const slider = el("input", { type: "range", min: "0", max: "120", step: "5", value: String(p.delaySeconds), "aria-label": "Spoiler delay in seconds", oninput: (event) => { delayValue.textContent = `${event.target.value} s`; }, onchange: (event) => change({ delaySeconds: Number(event.target.value) }, "Spoiler delay") });
    const seg = (label, options, value, pick) => el(
      "div",
      { class: "seg profile-seg", role: "group", "aria-label": label },
      options.map((o) => el("button", { type: "button", class: o.value === value ? "is-on" : null, "aria-pressed": o.value === value ? "true" : "false", "aria-label": o.aria || null, onclick: () => pick(o.value) }, o.label)),
    );
    const item = (label, help, control) => el("div", { class: "profile-quick__row" }, el("span", { class: "profile-quick__label" }, el("b", {}, label), el("small", {}, help)), control);
    return el(
      "section",
      { class: "profile-quick", "aria-label": "On game day" },
      item("Spoiler delay", "scores wait for your TV", el("span", { class: "profile-quick__slider" }, slider, delayValue)),
      item("Theme", "the team's colors either way", seg("Theme", [{ value: "dark", label: "Dark" }, { value: "light", label: "Light" }], p.theme === "light" ? "light" : "dark", (value) => change({ theme: value }, "Theme"))),
      item("Keep the screen on", "so the tablet never sleeps", seg("Keep the screen on", [{ value: "gameday", label: "Game days" }, { value: "always", label: "Always" }, { value: "off", label: "Never" }], p.keepScreenOn || "gameday", (value) => change({ keepScreenOn: value }, "Keep the screen on"))),
      item("Text size", "this device only", seg("Text size", TEXT_SIZES.map((x, i) => ({ value: x.id, label: ["A", "A+", "A++"][i] || x.label, aria: x.label })), textSize(), (value) => {
        const size = setTextSize(value);
        saved.classList.remove("note--error");
        saved.classList.add("setting__saved--ok");
        saved.textContent = `Text size ${size.label.toLowerCase()} on this device.`;
        render();
      })),
    );
  }

  /** The host, the address and what is not loaded: read once after the page is drawn, then the tiles and facts say so. */
  function askExtras() {
    if (extras.asked) return;
    extras.asked = true;
    const take = (key, url) => fetchJson(url).then((envelope) => {
      extras[key] = envelope?.data && typeof envelope.data === "object" ? envelope.data : null;
      if (container) render();
    }).catch(() => {});
    take("host", "/api/host");
    take("invite", "/api/invite");
    take("readiness", "/api/readiness");
  }

  function render() {
    if (!container) return;
    if (flyout) {
      try {
        flyout.handle.update(flyoutContent(flyout.id)); // an open section follows a saved setting, where the reader is
      } catch (error) {
        console.error("The open section could not be redrawn.", error);
      }
    }
    container.replaceChildren(
      el(
        "div",
        { class: "page profile-page" },
        flyout ? null : saved,
        helloCard(),
        el("p", { class: "profile-label" }, "On game day"),
        quickCard(),
        el("p", { class: "profile-label" }, "Everything else"),
        el("div", { class: "profile-tiles" }, SECTIONS.map(tile)),
        el("p", { class: "note profile-foot" }, "Each tile opens its section in a wide flyout; Back or › closes it."),
      ),
    );
    askExtras();
    const target = focus ? sectionOf(focus) : null;
    if (target) {
      focus = null; // once: a later redraw (a saved setting) leaves the reader where they are
      openSection(target.id);
    }
  }

  return {
    async mount(target) {
      container = target;
      container.replaceChildren(el("div", { class: "page profile-page" }, band({ title: "Profile", collapsible: false, state: { status: "loading" } })));
      setStatus("quiet", "Loading");
      for (const p of prompts) p.load();
      loadUpdate();
      await loadPrefs(true);
      setStatus(prefsError() ? "offline" : "quiet", prefsError() ? "Offline" : "Profile");
      drawn = true;
      render();
    },
    refresh() {
      return loadPrefs(true).then(render);
    },
    unmount() {
      container = null;
      if (flyout) flyout.handle.close("route");
      flyout = null;
    },
  };
}
