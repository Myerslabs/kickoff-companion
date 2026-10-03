// Settings (X6) live on the server so every device sees the same thing (owner direction
// 2026-09-23). This module loads them once, applies the theme, and saves changes. Views read
// getPrefs(); the Settings page and the live sheet's delay slider write through savePrefs().

import { ours } from "./identity.js";
import { paintTeam } from "./theme.js";
import { recall, remember } from "./ui/dom.js";
import { fetchJson } from "./views/common.js";

const DEFAULTS = { delaySeconds: 30, radioSourceId: null, theme: "dark", refreshMinutes: 15, autoStart: false, trayMode: false, hints: true, notesCommand: "claude", keepScreenOn: "gameday", openBrowser: "manual", primaryTeams: [], likedTeams: [], likedConferences: [], likedStates: [], tickerMode: "national", radioStations: [] };
const SETTINGS_TIMEOUT_MS = 5000;
const state = { loaded: false, loading: null, prefs: { ...DEFAULTS }, meta: null, error: null };
const listeners = new Set();

function emit() {
  for (const fn of listeners) {
    try {
      fn(state.prefs, state.meta);
    } catch {
      // one listener must not stop the others
    }
  }
}

export function applyTheme(theme = state.prefs.theme) {
  const mode = theme === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = mode;
  const palette = paintTeam(ours(), mode); // the team's own colors over the default tokens (public release Phase 3)
  const meta = document.querySelector('meta[name="theme-color"]'); // the browser bar and the home-screen app follow the theme (Phase 12)
  if (meta) meta.setAttribute("content", palette ? palette["--ground"] : mode === "light" ? "#EEF1F8" : "#0A1230");
}

/** Stat hints are on unless the owner switched them off; an older server without the setting leaves them on. */
export function applyHints(on = state.prefs.hints !== false) {
  document.documentElement.classList.toggle("hints-off", !on);
}

// Text size (UX-09, Phase 16): per device, because the couch tablet and the desk monitor sit at different
// distances, so it lives in this browser's storage, not on the server. The type tokens in tokens.css are
// multiplied by --ui-scale. Frozen API: TEXT_SIZES, textSize(), applyTextScale(id), setTextSize(id).
export const TEXT_SIZES = [
  { id: "standard", label: "Standard", scale: 1 },
  { id: "large", label: "Large", scale: 1.12 },
  { id: "larger", label: "Larger", scale: 1.25 },
];
const TEXT_SIZE_KEY = "ui:textSize";

function sizeFor(id) {
  return TEXT_SIZES.find((s) => s.id === id) || TEXT_SIZES[0];
}

/** The text size chosen on this device ("standard" when none, or when storage is blocked). */
export function textSize() {
  return sizeFor(recall(TEXT_SIZE_KEY, "standard")).id;
}

/** Apply a text size to the page (before the first render, so nothing reflows). Returns the size used. */
export function applyTextScale(id = textSize()) {
  const size = sizeFor(id);
  try {
    const html = document.documentElement;
    html.style.setProperty("--ui-scale", String(size.scale));
    html.dataset.textSize = size.id;
  } catch {
    // no page (tests): nothing to scale
  }
  return size;
}

/** Choose a text size on this device: stored (when storage allows) and applied at once. */
export function setTextSize(id) {
  const size = sizeFor(id);
  remember(TEXT_SIZE_KEY, size.id);
  return applyTextScale(size.id);
}

function take(data) {
  const prefs = data && typeof data.prefs === "object" && data.prefs ? data.prefs : {};
  state.prefs = { ...DEFAULTS, ...prefs };
  state.meta = data || null;
  applyTheme();
  applyHints();
}

/** Load once; later calls return the cached answer. `force` refetches. */
export async function loadPrefs(force = false) {
  if (state.loaded && !force) return state.prefs;
  if (state.loading) return state.loading;
  state.loading = (async () => {
    // A hung request must never leave the app on 'Loading' (Phase 16 hotfix): after 5 s the
    // defaults apply, exactly as they do when the request fails.
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), SETTINGS_TIMEOUT_MS) : null;
    try {
      const envelope = await fetchJson("/api/settings", controller?.signal);
      take(envelope?.data);
      state.error = null;
    } catch (error) {
      state.error = error?.name === "AbortError" ? "The settings did not load within 5 seconds; using the defaults" : error?.message || "Could not load the settings";
      applyTheme();
      applyHints();
    } finally {
      if (timer) clearTimeout(timer);
    }
    state.loaded = true;
    state.loading = null;
    emit();
    return state.prefs;
  })();
  return state.loading;
}

export function getPrefs() {
  return state.prefs;
}

export function prefsMeta() {
  return state.meta;
}

export function prefsError() {
  return state.error;
}

/** Save a partial change on the server. Resolves with the full settings answer; rejects with a readable message. */
export async function savePrefs(patch) {
  const response = await fetch("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
  let envelope = null;
  try {
    envelope = await response.json();
  } catch {
    envelope = null;
  }
  if (!response.ok) throw new Error(envelope?.errors?.[0]?.message || `The server answered ${response.status}`);
  take(envelope?.data);
  state.error = null;
  state.loaded = true;
  emit();
  return envelope;
}

export function subscribePrefs(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** The page refresh interval the owner set, in milliseconds. */
export function pollMs() {
  const minutes = Number(state.prefs.refreshMinutes);
  return (Number.isFinite(minutes) && minutes >= 1 ? minutes : 15) * 60 * 1000;
}
