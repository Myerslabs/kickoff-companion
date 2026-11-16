// The build this page was loaded with (Phase 12). Every API envelope carries meta.build and the
// live stream's hello carries build; the first one seen is this page's. When a later one differs,
// the server restarted or a file under static/ changed, so this page runs old code: one
// "kickoff:update" event goes out and the shell offers a reload.

let first = null;
let announced = false;

/** Note a build id from the server; returns true the first time it differs from this page's. */
export function noteBuild(id) {
  if (typeof id !== "string" || !id) return false;
  if (first === null) {
    first = id;
    return false;
  }
  if (id === first || announced) return false;
  announced = true;
  if (typeof document !== "undefined" && typeof CustomEvent === "function") {
    document.dispatchEvent(new CustomEvent("kickoff:update", { detail: { build: id, loaded: first } }));
  }
  return true;
}

let restartAnnounced = false;

/** Phase 16 wave 3: the server's own code changed on disk (meta.restartNeeded); one "kickoff:restart-needed" event. */
export function noteRestart(flag) {
  if (flag !== true || restartAnnounced) return false;
  restartAnnounced = true;
  if (typeof document !== "undefined" && typeof CustomEvent === "function") document.dispatchEvent(new CustomEvent("kickoff:restart-needed"));
  return true;
}

// Claude Code signed out on the server computer (owner 2026-11-15: his runs failed with "the tool exited with code 1" while
// its sign-in had expired). meta.claudeSignedOut is the ISO time it was first found signed out, or null once a run gets
// through (app/services/claude_signin.py); an answer without the key says nothing either way.
let claudeSince = null;

/** One "kickoff:claude-signin" event each time the server's word changes, its detail { since } (null: signed in again). */
export function noteClaude(since) {
  if (since === undefined) return false; // no meta, or an older server: nothing known
  const value = typeof since === "string" && since ? since : null;
  if (value === claudeSince) return false;
  claudeSince = value;
  if (typeof document !== "undefined" && typeof CustomEvent === "function") document.dispatchEvent(new CustomEvent("kickoff:claude-signin", { detail: { since: value } }));
  return true;
}

// Rollover R2: meta.seasonSwitch, {"switched": {from, to, at}} for two weeks after the app moved to the next season by itself,
// {"failed": {to, error}} while a due switch fails, null otherwise (app/services/rollover.py); an answer without it says nothing.
let seasonSaid = null;

/** One "kickoff:season-switch" event each time the server's word changes, its detail the value (null: nothing to say). */
export function noteSeasonSwitch(value) {
  if (value === undefined) return false;
  const usable = value && typeof value === "object" ? value : null;
  const key = usable ? JSON.stringify(usable) : null;
  if (key === seasonSaid) return false;
  seasonSaid = key;
  if (typeof document !== "undefined" && typeof CustomEvent === "function") document.dispatchEvent(new CustomEvent("kickoff:season-switch", { detail: usable }));
  return true;
}

/** What the last answer said about the season's switch, or null. */
export function seasonSwitchNow() {
  try {
    return seasonSaid ? JSON.parse(seasonSaid) : null;
  } catch {
    return null;
  }
}

/** The ISO time Claude Code was found signed out, as the last answer said, or null. */
export function claudeSignedOutSince() {
  return claudeSince;
}

/** The words for it, the To do's and the Data status card's alike. */
export function signedOutWords(since) {
  const d = new Date(typeof since === "string" ? since : NaN);
  const when = Number.isNaN(d.getTime()) ? "" : ` (since ${d.toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" })})`;
  return `Claude Code's sign-in on the server computer expired${when}, so Claude's notes, the paper and the other runs stop. On that computer, open a terminal, run claude and type /login. This goes once a run gets through.`;
}

/** For the tests: forget what was seen. */
export function resetBuild() {
  first = null;
  announced = false;
  restartAnnounced = false;
  claudeSince = null;
}
