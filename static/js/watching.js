// Another game on this device (batch 3, owner 2026-11-16: "Stays on host's game, each client can view another game"). In
// Game follows the room's game (ours, or the one the host picked for every screen); a device may watch any other game of
// the day on its own In Game, from a tap on the ticker or in Pick a game. Only this device, this visit (sessionStorage);
// the server polls that game only while a device asks for it (app/live/side.py). A choice older than MAX_AGE_MS (from when
// it was made) is dropped on load, so a tab left open for days is back on the room's game.
//
//   deviceGame()          { gameId, home, away, team, at } this device watches, or null (the room's game)
//   watchHere(game)       watch a game on this device: { gameId, home, away, team? } (team: the side to follow, else home)
//   watchRoom()           back to the room's game
//   onDeviceGame(fn)      called with deviceGame() after every change; returns the unsubscribe

const KEY = "kickoff:watch";
const MAX_AGE_MS = 24 * 3600 * 1000; // the review (2026-11-19): a game picked yesterday is not this visit's
const listeners = new Set();

const str = (value) => (typeof value === "string" ? value.trim() : "");

function clean(game) {
  if (!game || typeof game !== "object") return null;
  const id = Number(game.gameId);
  if (!Number.isInteger(id) || id <= 0 || id >= 1e12) return null;
  const home = str(game.home) || null;
  const away = str(game.away) || null;
  const team = str(game.team) || home;
  const at = Number(game.at);
  return { gameId: id, home, away, team, at: Number.isFinite(at) && at > 0 ? at : Date.now() };
}

function read() {
  try {
    const raw = globalThis.sessionStorage?.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    const at = Number(parsed?.at);
    if (parsed && (!Number.isFinite(at) || Date.now() - at > MAX_AGE_MS || at > Date.now() + MAX_AGE_MS)) {
      globalThis.sessionStorage?.removeItem(KEY); // picked too long ago, or with no time: the room's game again
      return null;
    }
    return clean(parsed);
  } catch {
    return null;
  }
}

let current = read();

function tell() {
  for (const fn of [...listeners]) {
    try {
      fn(current);
    } catch (error) {
      console.error("A page did not follow this device's game.", error);
    }
  }
  try {
    document.dispatchEvent(new CustomEvent("kickoff:device-game", { detail: current }));
  } catch {
    // no document (the tests under Node)
  }
}

export function deviceGame() {
  return current;
}

export function watchHere(game) {
  const next = clean(game && typeof game === "object" ? { ...game, at: Date.now() } : game);
  if (!next) return;
  current = next;
  try {
    globalThis.sessionStorage?.setItem(KEY, JSON.stringify(next));
  } catch {
    // no storage: the choice holds until the page reloads
  }
  tell();
}

export function watchRoom() {
  if (!current) return;
  current = null;
  try {
    globalThis.sessionStorage?.removeItem(KEY);
  } catch {
    // nothing stored
  }
  tell();
}

export function onDeviceGame(fn) {
  if (typeof fn !== "function") return () => {};
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function _resetDeviceGame({ reload = false } = {}) {
  current = reload ? read() : null;
  listeners.clear();
}
