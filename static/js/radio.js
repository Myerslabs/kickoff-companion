// The radio (X4): one controller for the whole app. The player lives in the shell's dock at the
// bottom of the page, outside the tab content, so audio keeps playing while views change. The
// control that starts it sits on the Game program (owner direction 2026-09-23). Three kinds of
// source: "stream" plays through an audio element with real play and pause; "embed" loads the
// station's own player in a frame (its play button is inside the frame); "link" opens a new tab.
// Audio cannot be delayed by the app; the spoiler delay applies to the data panels only.
// Public release Phase 5b: sources come from .env, from Settings (each with its team) and from the repo's
// station list; with none for a primary team, radioHelpBlock offers search links and the request button.

import { getPrefs, savePrefs } from "./prefs.js";
import { el, recall, remember, text } from "./ui/dom.js";
import { fetchJson } from "./views/common.js";

const SOURCE_KEY = "radio:source";
const PLAYER_KEY = "radio:playerOpen";
const STATE_TEXT = { idle: "Off", connecting: "Connecting", playing: "Playing", paused: "Paused", embedded: "Player loaded", error: "Could not play" };

const radio = {
  loaded: false,
  loadError: null,
  sources: [],
  help: [],
  note: "",
  current: null,
  state: "idle",
  detail: "",
  playerOpen: recall(PLAYER_KEY, true) !== false,
  audio: null,
  frame: null,
  dock: null,
  barSlot: null,
  playerArea: null,
};
const listeners = new Set();

function emit() {
  renderDock();
  const snap = radioSnapshot();
  for (const fn of listeners) {
    try {
      fn(snap);
    } catch {
      // a listener that throws must not stop the others or the audio
    }
  }
}

/** The state every band and bar renders from. */
export function radioSnapshot() {
  return { loaded: radio.loaded, loadError: radio.loadError, sources: radio.sources, help: radio.help, note: radio.note, current: radio.current, state: radio.state, detail: radio.detail, playerOpen: radio.playerOpen };
}

export function subscribeRadio(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function stateText(state) {
  return STATE_TEXT[state] || text(state);
}

const HTTPS = /^https:\/\//;

/** The server's help entries, guarded: [{ school, search: [{label, url}], requestUrl }]. Only https links survive. */
export function cleanHelp(help) {
  return (Array.isArray(help) ? help : [])
    .filter((h) => h && typeof h.school === "string" && h.school.trim())
    .map((h) => ({
      school: h.school.trim(),
      search: (Array.isArray(h.search) ? h.search : []).filter((s) => s && typeof s.label === "string" && typeof s.url === "string" && HTTPS.test(s.url)),
      requestUrl: typeof h.requestUrl === "string" && HTTPS.test(h.requestUrl) ? h.requestUrl : null,
    }));
}

/** For each primary team with no station: where to find its broadcast, and the button that asks for it. */
export function radioHelpBlock(help, { settingsLink = true } = {}) {
  const entries = cleanHelp(help);
  if (!entries.length) return null;
  return el(
    "div",
    { class: "radio-help" },
    entries.map((h) =>
      el(
        "div",
        { class: "radio-help__team" },
        el("p", {}, el("strong", {}, h.school), ": no station in the app yet."),
        el(
          "p",
          { class: "radio-help__links" },
          h.search.map((s) => el("a", { class: "btn", href: s.url, target: "_blank", rel: "noopener" }, s.label)),
          h.requestUrl ? el("a", { class: "btn", href: h.requestUrl, target: "_blank", rel: "noopener" }, "Request your team's radio") : null,
        ),
      ),
    ),
    el("p", { class: "note" }, "Found the station's official player or stream? ", settingsLink ? el("a", { href: "#settings" }, "Add it in Settings") : "Add it with the form above", ". The request button opens a short form on GitHub (a free account) so the station can be added to the app for everyone."),
  );
}

/** Ask the server again (after a station is added or removed in Settings). */
export function reloadRadioSources() {
  radio.loaded = false;
  return loadRadioSources();
}

/** The configured sources from the server, once. Failure is remembered and shown, never thrown. */
export async function loadRadioSources() {
  if (radio.loaded) return radioSnapshot();
  try {
    const envelope = await fetchJson("/api/radio/sources");
    const sources = Array.isArray(envelope?.data?.sources) ? envelope.data.sources : [];
    radio.sources = sources.filter((s) => s && typeof s.id === "string" && typeof s.url === "string" && /^https?:\/\//.test(s.url) && ["stream", "embed", "link"].includes(s.kind)).map((s) => ({ id: s.id, name: typeof s.name === "string" && s.name ? s.name : "Radio", kind: s.kind, url: s.url, team: typeof s.team === "string" && s.team ? s.team : null }));
    radio.help = cleanHelp(envelope?.data?.help);
    radio.note = typeof envelope?.data?.note === "string" ? envelope.data.note : "";
    radio.loadError = null; // no station yet is not an error: the radio band offers to find or add one
  } catch (error) {
    radio.loadError = `${error?.message || "Could not load the radio sources"}.`;
  }
  radio.loaded = true;
  emit();
  return radioSnapshot();
}

/** The source the device used last, when it is still configured. */
export function rememberedSource() {
  const preferred = getPrefs().radioSourceId;
  const id = preferred || recall(SOURCE_KEY, null);
  return radio.sources.find((s) => s.id === id) || radio.sources[0] || null;
}

// --- playback ---------------------------------------------------------------------------------------

function tearDown() {
  if (radio.audio) {
    try {
      radio.audio.pause();
      radio.audio.removeAttribute("src");
      radio.audio.load();
    } catch {
      // the element is being thrown away either way
    }
  }
  radio.audio = null;
  radio.frame = null;
  if (radio.playerArea) radio.playerArea.replaceChildren();
}

export function startRadio(source) {
  if (!source) return;
  if (source.kind === "link") {
    window.open(source.url, "_blank", "noopener");
    return;
  }
  tearDown();
  radio.current = source;
  remember(SOURCE_KEY, source.id);
  if (getPrefs().radioSourceId !== source.id) savePrefs({ radioSourceId: source.id }).catch(() => {});
  if (source.kind === "stream") {
    const audio = new Audio();
    audio.preload = "none";
    audio.src = source.url;
    audio.addEventListener("playing", () => setState("playing", "Live stream"));
    audio.addEventListener("waiting", () => setState("connecting", "Buffering"));
    audio.addEventListener("pause", () => {
      if (radio.audio === audio && radio.state !== "error") setState("paused", "");
    });
    audio.addEventListener("stalled", () => {
      if (radio.audio === audio && radio.state === "playing") setState("connecting", "Stream stalled, waiting");
    });
    audio.addEventListener("error", () => setState("error", "The stream did not answer. Try the station player below."));
    radio.audio = audio;
    setState("connecting", "Connecting to the stream");
    audio.play().catch((error) => setState("error", error?.name === "NotAllowedError" ? "The browser blocked autoplay. Tap play again." : `${error?.message || "Playback failed"}.`));
    return;
  }
  const frame = el("iframe", { class: "radio-frame", src: source.url, title: source.name, allow: "autoplay", referrerpolicy: "no-referrer-when-downgrade", loading: "eager" });
  radio.frame = frame;
  radio.playerOpen = true;
  remember(PLAYER_KEY, true);
  if (radio.playerArea) radio.playerArea.replaceChildren(frame);
  setState("embedded", "Use the play button inside the player");
}

function setState(state, detail) {
  radio.state = state;
  radio.detail = detail || "";
  emit();
}

export function toggleRadio() {
  const source = radio.current;
  if (!source) return;
  if (source.kind === "stream" && radio.audio) {
    if (radio.audio.paused) {
      setState("connecting", "Connecting to the stream");
      radio.audio.play().catch((error) => setState("error", `${error?.message || "Playback failed"}.`));
    } else radio.audio.pause();
    return;
  }
  radio.playerOpen = !radio.playerOpen;
  remember(PLAYER_KEY, radio.playerOpen);
  emit();
}

export function stopRadio() {
  tearDown();
  radio.current = null;
  setState("idle", "");
}

// --- the dock at the bottom of the shell ---------------------------------------------------------------

/** Mount once into the shell's radio slot. The player area is never rebuilt, only the bar. */
export function mountRadio(slot) {
  if (!slot) return;
  radio.barSlot = el("div", { class: "radio-dock__bar" });
  radio.playerArea = el("div", { class: "radio-dock__player" });
  radio.dock = el("div", { class: "radio-dock", hidden: true }, radio.barSlot, radio.playerArea);
  slot.replaceChildren(radio.dock);
  if (radio.frame) radio.playerArea.replaceChildren(radio.frame);
  watchDockHeight(radio.dock);
  renderDock();
}

/** Publish the dock's height as --dock-h so bars stuck to the bottom (the Live sheet's remote bar,
    the update banner) sit above it instead of under it (Phase 16 hotfix). 0px while it is hidden. */
function watchDockHeight(dock) {
  if (typeof ResizeObserver === "function") new ResizeObserver(writeDockHeight).observe(dock); // the player opening and closing
}

// Also written after every dock redraw: Chrome sends no resize notice when the dock turns hidden.
function writeDockHeight() {
  const height = radio.dock && !radio.dock.hidden ? Math.round(radio.dock.getBoundingClientRect().height) : 0;
  document.documentElement.style.setProperty("--dock-h", `${height}px`);
}

function renderDock() {
  if (!radio.dock) return;
  try {
    drawDock();
  } finally {
    writeDockHeight();
  }
}

function drawDock() {
  const source = radio.current;
  if (!source) {
    radio.dock.hidden = true;
    radio.barSlot.replaceChildren();
    return;
  }
  radio.dock.hidden = false;
  const isStream = source.kind === "stream";
  const playing = radio.state === "playing" || radio.state === "connecting";
  const toggleLabel = isStream ? (playing ? "Pause" : "Play") : radio.playerOpen ? "Hide player" : "Show player";
  const stateLine = radio.detail ? `${stateText(radio.state)} · ${radio.detail}` : stateText(radio.state);
  radio.barSlot.replaceChildren(
    el(
      "div",
      { class: "radio-bar", role: "region", "aria-label": "Radio" },
      el("span", { class: "radio-bar__station" }, text(source.name)),
      el("span", { class: `radio-bar__state radio-bar__state--${radio.state}` }, stateLine),
      el("span", { class: "radio-bar__spacer" }),
      el("span", { class: "radio-bar__note" }, "Audio is not delayed"),
      el("button", { class: "btn", type: "button", "aria-label": toggleLabel, onclick: toggleRadio }, isStream ? (playing ? "‖" : "▶") : toggleLabel),
      el("button", { class: "btn btn--quiet icon-btn", type: "button", "aria-label": "Stop the radio", onclick: stopRadio }, "×"),
    ),
  );
  radio.playerArea.hidden = isStream || !radio.playerOpen;
}
