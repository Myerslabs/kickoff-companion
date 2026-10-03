// Who "we" are (public release Phase 3): the configured team's school, mascot, abbreviation and
// conference from /api/identity, loaded once before the first page draws. Every label for "us"
// reads ours(), so no team is written into the front end. Until it loads, or if it cannot, the
// fields are blank and labels fall back to plain words ("Our team", "Conf").

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

/** Load /api/identity once. Never throws: a failed load keeps the blank identity and says so in the console. */
export async function loadIdentity(fetchImpl = globalThis.fetch) {
  if (typeof fetchImpl !== "function") return current;
  try {
    const response = await fetchImpl("/api/identity", { headers: { Accept: "application/json" } });
    if (!response || !response.ok) throw new Error(`HTTP ${response ? response.status : "?"}`);
    const body = await response.json();
    return setIdentity(body && body.data);
  } catch (error) {
    console.warn("Team identity unavailable; labels use plain words.", error);
    return current;
  }
}
