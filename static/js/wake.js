// Keep the screen on (Phase 12): the Settings choice keepScreenOn is "off", "gameday" (the default)
// or "always". On our game day the shell holds a screen wake lock on every page, so the
// tablet does not sleep on the Newspaper or the pregame sheet before the Live sheet takes over
// (the Live sheet still holds its own lock once plays flow). A game day is a day whose
// kickoff, from /api/live/status, falls on today's local date. The lock is dropped by the browser
// whenever the page is hidden and taken again when it comes back.

import { screenLock } from "./awake.js";
import { getPrefs, subscribePrefs } from "./prefs.js";
import { fetchJson } from "./views/common.js";

const CHECK_MS = 5 * 60 * 1000;
let sentinel = null;
let gameDay = false;
let started = false;

/** Whether the choice and the day want the screen on. Exported for the tests. */
export function wantsScreenOn(mode, isGameDay) {
  if (mode === "always") return true;
  if (mode === "off") return false;
  return Boolean(isGameDay); // "gameday", and anything unknown from an older server
}

/** Whether an ISO kickoff is on the same local date as `now`. Exported for the tests. */
export function sameLocalDay(kickoff, now = new Date()) {
  if (typeof kickoff !== "string" || !kickoff) return false;
  const k = new Date(kickoff);
  return !Number.isNaN(k.getTime()) && k.getFullYear() === now.getFullYear() && k.getMonth() === now.getMonth() && k.getDate() === now.getDate();
}

async function apply() {
  const want = wantsScreenOn(getPrefs().keepScreenOn, gameDay);
  const api = screenLock();
  if (want && !sentinel && document.visibilityState === "visible" && api) {
    try {
      const lock = await api.request("screen");
      sentinel = lock;
      lock.addEventListener("release", () => {
        if (sentinel === lock) sentinel = null;
      });
    } catch (error) {
      console.warn(`Keep screen on: the browser refused the wake lock: ${error?.message || error}`);
    }
  } else if (!want && sentinel) {
    const lock = sentinel;
    sentinel = null;
    lock.release().catch(() => {});
  }
}

async function checkGameDay() {
  try {
    const envelope = await fetchJson("/api/live/status");
    gameDay = sameLocalDay(envelope?.data?.window?.kickoff);
  } catch (error) {
    console.warn(`Keep screen on: could not read the game window: ${error?.message || error}`);
  }
  await apply();
}

export function keepScreenOn() {
  if (started || typeof document === "undefined" || typeof navigator === "undefined") return;
  started = true;
  if (!screenLock()) {
    console.info("Keep screen on: this browser has no way to keep the screen on.");
    return;
  }
  checkGameDay();
  setInterval(checkGameDay, CHECK_MS);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") apply();
  });
  subscribePrefs(() => apply());
}
