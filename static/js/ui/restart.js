// Restart the server from the app (Phase 16 wave 3, owner ask 2026-09-28). Settings, the status page and the "code
// changed" banner all use this: ask the server to restart (POST /api/server/restart, JSON with a confirm), then wait
// for it to answer again with a new build and reload the page. During our game the server answers 409 first, and the
// caller asks once more before sending force.
//
//   requestRestart({ force })   -> Promise of { ok, status, message }
//   waitForServer(oldStart, { timeoutMs, everyMs })  -> Promise of true once /api/health answers with another start time
//   restartFlow({ say, confirmDuringGame })  the whole sequence; say(text) reports progress; reloads at the end

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
