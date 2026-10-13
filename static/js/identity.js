// Who "we" are (public release Phase 3): the configured team's school, mascot, abbreviation and
// conference from /api/identity, loaded once before the first page draws. Every label for "us"
// reads ours(), so no team is written into the front end. Until it loads, or if it cannot (or it takes
// more than 5 seconds, item 6), the fields are blank and labels fall back to plain words ("Our team", "Conf").

const APP_NAME = "Kickoff Companion";

const BLANK = Object.freeze({
  school: "",
  mascot: "",
  label: "",
  name: "",
  conference: "",
  conf: "",
  color: null,
  altColor: null,
  title: APP_NAME,
  appName: APP_NAME,
  resolved: false,
});

let current = BLANK;

const str = (value) => (typeof value === "string" ? value.trim() : "");
const hex = (value) => (typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value.trim()) ? value.trim().toLowerCase() : null);

/** The identity in hand: { school, mascot, label, name, conference, conf, color, altColor, title, appName, resolved }. */
export function ours() {
  return current;
}

/** Labels for "us" that never come back empty. */
export const usSchool = () => current.school || "Our team";
export const usLabel = () => current.label || "US";
export const usName = () => current.name || current.school || "Our team";
export const confLabel = () => current.conf || current.conference || "Conf";
export const confName = () => current.conference || "the conference";

/** True when `school` is us (a blank identity matches nothing). */
export function isUs(school) {
  return Boolean(current.school) && typeof school === "string" && school.trim().toLowerCase() === current.school.toLowerCase();
}

/** Take an /api/identity answer; anything malformed leaves the blank identity. Returns ours(). */
export function setIdentity(data) {
  if (!data || typeof data !== "object") return current;
  const school = str(data.school);
  if (!school) return current;
  const mascot = str(data.mascot);
  current = Object.freeze({
    school,
    mascot,
    label: str(data.abbreviation) || school.slice(0, 4).toUpperCase(),
    name: mascot || school,
    conference: str(data.conference),
    conf: str(data.conferenceShort) || str(data.conference),
    color: hex(data.color),
    altColor: hex(data.altColor),
    title: str(data.title) || `${mascot || school} ${APP_NAME}`,
    appName: str(data.appName) || APP_NAME,
    resolved: data.resolved === true,
  });
  return current;
}

/** Forget the identity (tests). */
export function resetIdentity() {
  current = BLANK;
}

/** How long the first page waits for /api/identity (item 6, step E): the same 5 s the settings get (prefs.js). */
export const IDENTITY_TIMEOUT_MS = 5000;

const LATE = Symbol("late");

/**
 * Load /api/identity once. Never throws, and never waits longer than `timeoutMs`: a failed or hung load keeps the blank
 * identity (labels in plain words) and says so in the console, so the app always gets past 'Loading' (item 6, step E: a
 * request that never answered used to leave the loading screen up for good). The request is aborted at the limit; a
 * fetch that ignores the abort is left behind by the same timer.
 */
export async function loadIdentity(fetchImpl = globalThis.fetch, timeoutMs = IDENTITY_TIMEOUT_MS) {
  if (typeof fetchImpl !== "function") return current;
  const limit = Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : IDENTITY_TIMEOUT_MS;
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  let timer = null;
  const late = new Promise((resolve) => {
    timer = setTimeout(() => {
      if (controller) controller.abort();
      resolve(LATE);
    }, limit);
  });
  try {
    const ask = (async () => {
      const response = await fetchImpl("/api/identity", { headers: { Accept: "application/json" }, ...(controller ? { signal: controller.signal } : {}) });
      if (!response || !response.ok) throw new Error(`HTTP ${response ? response.status : "?"}`);
      return response.json();
    })();
    ask.catch(() => {}); // a load that fails after the limit has nobody left to tell
    const body = await Promise.race([ask, late]);
    if (body === LATE) {
      console.warn(`Team identity did not load within ${Math.round(limit / 1000)} seconds; labels use plain words.`);
      return current;
    }
    return setIdentity(body && body.data);
  } catch (error) {
    console.warn("Team identity unavailable; labels use plain words.", error);
    return current;
  } finally {
    clearTimeout(timer);
  }
}
