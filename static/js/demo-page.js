// The demo page (/demo; public release Phase 9b). In the demo: what it is, what a CFBD key does, that nothing goes
// to Myers Labs and nothing is paid to it, and "Use my own team" (or "Back to my team" when this install is set up).
// In the app: "Show the demo". A switch saves the choice on the server, which restarts in place; the page waits for
// the new start and then opens the setup page (no key yet) or the app.

const $ = (id) => document.getElementById(id);
const els = { lead: $("demo-lead"), explore: $("explore"), switchButton: $("switch"), note: $("switch-note"), status: $("demo-status"), keyPanel: $("demo-key") };

async function call(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", headers: { "Content-Type": "application/json", Accept: "application/json" }, ...options });
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const message = typeof body?.errors?.[0]?.message === "string" ? body.errors[0].message : `The server answered HTTP ${response.status}.`;
    throw new Error(message);
  }
  return body && typeof body.data === "object" && body.data ? body.data : {};
}

function say(text) {
  els.note.textContent = text;
  els.note.hidden = !text;
}

async function startedAt() {
  try {
    return (await call("/api/health")).server?.started_at || null;
  } catch {
    return null;
  }
}

/** Wait for the server to come back from its restart, then go to `target`. */
async function waitThenGo(before, target) {
  const deadline = Date.now() + 90000;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    try {
      const started = (await call("/api/health")).server?.started_at || null;
      if (started && started !== before) {
        window.location.href = target;
        return;
      }
    } catch {
      // between the old server's stop and the new one's start
    }
  }
  say("The server is taking longer than usual to restart. Check its window, then reload this page.");
}

let state = { demo: true, configured: false };

function render() {
  if (state.demo) {
    els.explore.hidden = false;
    els.switchButton.textContent = state.configured ? "Back to my team" : "Use my own team";
    els.keyPanel.hidden = state.configured === true;
    els.status.textContent = state.configured ? "The demo is running. Your team, key and settings are untouched." : "The demo is running: no key needed.";
  } else {
    els.lead.textContent = "The demo runs a made-up league with a game under way, handy for showing someone the app. The server switches to it in a few seconds, and back the same way; your team, key and settings are untouched.";
    els.explore.textContent = "Back to the app";
    els.switchButton.textContent = "Show the demo";
    els.keyPanel.hidden = true;
    els.status.textContent = "Your own team is running.";
  }
}

async function switchOver() {
  els.switchButton.disabled = true;
  say(state.demo ? "Switching to your own team. The server restarts; this takes a few seconds." : "Switching to the demo. The server restarts; this takes a few seconds.");
  try {
    const before = await startedAt();
    const data = await call(state.demo ? "/api/demo/leave" : "/api/demo/enter", { method: "POST" });
    const target = state.demo ? (state.configured || data.configured ? "/" : "/welcome") : "/demo";
    await waitThenGo(before, target);
  } catch (error) {
    say(`Not switched: ${error.message}`);
    els.switchButton.disabled = false;
  }
}

async function load() {
  try {
    const data = await call("/api/demo");
    state = { demo: data.demo === true, configured: data.configured === true };
    for (const [id, key] of [["get-key", "keyUrl"], ["see-plans", "plansUrl"]]) {
      if (typeof data[key] === "string" && data[key].startsWith("https://")) $(id).href = data[key];
    }
    render();
  } catch (error) {
    els.status.textContent = `Could not reach the server: ${error.message}`;
  }
}

els.switchButton.addEventListener("click", switchOver);
void load();
