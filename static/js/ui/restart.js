// Restart the server from the app (Phase 16 wave 3, owner ask 2026-09-28). Settings, the status page and the "code
// changed" banner all use this: ask the server to restart (POST /api/server/restart, JSON with a confirm), then wait
// for it to answer again with a new build and reload the page. During our game the server answers 409 first, and the
// caller asks once more before sending force.
//
//   requestRestart({ force })   -> Promise of { ok, status, message }
//   waitForServer(oldStart, { timeoutMs, everyMs })  -> Promise of true once /api/health answers with another start time
//   restartFlow({ say, confirmDuringGame })  the whole sequence; say(text) reports progress; reloads at the end
//   serverAnswers({ fetchImpl, timeoutMs })  -> Promise of true when /api/health answers within the time
//   reloadWhenServerAnswers({ waits, fetchImpl, reload, onWait })  -> Promise of true once it reloaded (item 6, step E)

async function readBody(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function requestRestart({ force = false } = {}) {
  try {
    const response = await fetch("/api/server/restart", { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true, force }) });
    const body = await readBody(response);
    const message = body?.errors?.[0]?.message || null;
    return { ok: response.ok, status: response.status, message, started: body?.data?.started || null };
  } catch (error) {
    return { ok: false, status: 0, message: `The server didn't answer (${error?.message || "no connection"}).` };
  }
}

async function currentBuild() {
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    if (!response.ok) return null;
    const body = await readBody(response);
    const started = body?.server?.started_at; // a restart builds a new app, which starts its own clock
    return typeof started === "string" && started ? started : null;
  } catch {
    return null; // down: still restarting
  }
}

const ASK_TIMEOUT_MS = 4000;

/** True when /api/health answers with a 2xx within `timeoutMs`; never throws, never waits longer. */
export function serverAnswers({ fetchImpl = globalThis.fetch, timeoutMs = ASK_TIMEOUT_MS } = {}) {
  if (typeof fetchImpl !== "function") return Promise.resolve(false);
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  return new Promise((resolve) => {
    let done = false;
    const finish = (ok) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      resolve(ok);
    };
    const timer = setTimeout(() => {
      if (controller) controller.abort();
      finish(false);
    }, timeoutMs);
    Promise.resolve()
      .then(() => fetchImpl("/api/health", { cache: "no-store", ...(controller ? { signal: controller.signal } : {}) }))
      .then((response) => finish(Boolean(response && response.ok)), () => finish(false));
  });
}

/** The waits between asks (item 6, step E): about 23 s in all, then the page stays as it is. */
export const SERVER_WAITS_MS = Object.freeze([1000, 2000, 4000, 8000, 8000]);

let waiting = null;

/**
 * Item 6, step E: reload the page only into a server that answers. After a server restart (build.js "kickoff:update") the
 * page reloads the next time it comes into view, which is the moment an iPad wakes and is still joining the Wi-Fi; a
 * reload into no server leaves the browser's own error page (in the home-screen app, with no way back). So /api/health
 * is asked first, again after each of `waits`, and the page reloads as soon as it answers. Resolves true once it
 * reloaded, false when the server never answered (the page is left as it was; ask again later). One wait at a time: a
 * call while one runs gets the same promise. onWait(n) hears each miss before its wait.
 */
export function reloadWhenServerAnswers({ waits = SERVER_WAITS_MS, fetchImpl = globalThis.fetch, reload = reloadPage, onWait } = {}) {
  if (waiting) return waiting;
  const pauses = Array.isArray(waits) ? waits.filter((ms) => Number.isFinite(ms) && ms >= 0) : [];
  waiting = (async () => {
    for (let attempt = 0; ; attempt += 1) {
      if (await serverAnswers({ fetchImpl })) {
        try {
          reload();
        } catch (error) {
          console.warn("The page could not reload itself.", error);
          return false;
        }
        return true;
      }
      if (attempt >= pauses.length) return false;
      if (typeof onWait === "function") {
        try {
          onWait(attempt + 1);
        } catch (error) {
          console.warn("A reload wait's report failed.", error);
        }
      }
      await new Promise((resolve) => setTimeout(resolve, pauses[attempt]));
    }
  })();
  const mine = waiting;
  mine.finally(() => {
    if (waiting === mine) waiting = null;
  });
  return mine;
}

function reloadPage() {
  try {
    window.location.reload();
  } catch (error) {
    console.warn("The page could not reload itself.", error);
  }
}

export async function waitForServer(oldBuild, { timeoutMs = 90000, everyMs = 1500 } = {}) {
  const until = Date.now() + timeoutMs;
  await new Promise((resolve) => setTimeout(resolve, everyMs));
  while (Date.now() < until) {
    const build = await currentBuild();
    if (build && build !== oldBuild) return true;
    await new Promise((resolve) => setTimeout(resolve, everyMs));
  }
  return false;
}

export async function restartFlow({ say = () => {}, confirmDuringGame = () => false } = {}) {
  const before = await currentBuild();
  say("Asking the server to restart…");
  let result = await requestRestart();
  if (result.status === 409) {
    if (!(await confirmDuringGame(result.message))) {
      say("Not restarted.");
      return false;
    }
    result = await requestRestart({ force: true });
  }
  if (!result.ok) {
    say(`Not restarted: ${result.message || `the server answered ${result.status}`}`);
    return false;
  }
  say("Restarting. The page reloads when the server is back (usually 10 to 20 seconds).");
  const back = await waitForServer(before);
  if (!back) {
    say("The server hasn't come back yet. Check its window on the server computer, then reload this page.");
    return false;
  }
  say("Back. Reloading…");
  try {
    window.location.reload();
  } catch {
    // no window (a test): nothing to reload
  }
  return true;
}
