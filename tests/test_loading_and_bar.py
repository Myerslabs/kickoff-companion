"""Item 6, steps E to H (owner 2026-10-11), in the fake browser and in the source.

E, a loading screen you can always leave: the loading bar in index.html carries Reload from the first frame; an inline
watchdog says "Could not load" when the app has not drawn its Menu in 10 s or a file of it failed (the module script's
error event), and tries once more by itself, once per tab, only into a server that answers /api/health; Reload waits for
the server the same way. The team lookup gives up after 5 s like the settings. After a server restart the page reloads
only once the server answers.
F, the Menu never squeezed: the bar's buttons keep their width; the status pill's words shorten inside it with "…".
G, the iPad stops zooming by itself: every field is 16 px or more on a touch screen, double-tap zoom is off, and the
home-screen status bar is solid black.
H, no dead ends: "Back to the app" on the status, setup and welcome pages (welcome: once the setup is done, instead of the
demo link); the Menu's border shows in both themes."""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.fakedom import PROJECT_ROOT, needs_node, run_scenario

STATIC = PROJECT_ROOT / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
COMPONENTS = (STATIC / "css" / "components.css").read_text(encoding="utf-8")
APP_CSS = (STATIC / "css" / "app.css").read_text(encoding="utf-8")
TOKENS = (STATIC / "css" / "tokens.css").read_text(encoding="utf-8")


def _watchdog() -> str:
    """The inline watchdog script of index.html (the one <script> without a src)."""
    scripts = re.findall(r"<script>(.*?)</script>", INDEX, flags=re.S)
    assert len(scripts) == 1, "index.html has exactly one inline script, the loading watchdog"
    return scripts[0]


SCENARIOS = r"""
const sessionStore = new Map();
function useSession({ blocked = false } = {}) {
  const store = {
    getItem: (k) => { if (blocked) throw new Error("blocked"); return sessionStore.has(k) ? sessionStore.get(k) : null; },
    setItem: (k, v) => { if (blocked) throw new Error("blocked"); sessionStore.set(k, String(v)); },
    removeItem: (k) => { if (blocked) throw new Error("blocked"); sessionStore.delete(k); },
  };
  window.sessionStorage = store;
  globalThis.sessionStorage = store;
}

/** index.html's loading markup, as the browser has it before app.js runs. */
function bootPage() {
  document.body.replaceChildren();
  document.getElementById = (id) => document.querySelector(`#${id}`);
  const node = (tag, attrs = {}, ...kids) => { const n = document.createElement(tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); n.append(...kids); return n; };
  const label = node("span", { class: "pill__label" }, "Loading");
  const pill = node("span", { class: "pill pill--quiet", id: "boot-pill", role: "status" }, label);
  const reload = node("button", { class: "btn boot-reload", type: "button" }, "Reload");
  const header = node("header", { class: "topbar" }, node("span", { class: "wordmark" }, "Kickoff"), node("div", { class: "topbar__status" }, pill), reload);
  const bands = [1, 2, 3].map(() => node("section", { class: "band", "aria-hidden": "true" }));
  const detail = node("p", { class: "state-block__detail", id: "boot-failed-detail" }, "Reload to try again.");
  const failed = node("section", { class: "band boot__failed", id: "boot-failed" }, detail);
  failed.hidden = true;
  const main = node("main", { class: "shell__main boot", "aria-busy": "true", "aria-label": "Loading" }, node("div", { class: "season boot__grid" }, ...bands, failed));
  const app = node("div", { id: "app", class: "shell" }, header, main);
  document.body.append(app);
  window.reloads = 0;
  window.location.reload = () => { window.reloads += 1; };
  return { app, pill, label, reload, bands, failed, detail, main };
}

function runWatchdog() {
  new Function(FIXTURE.script)();
}

/** What app.js does once it has drawn: the real bar with its Menu replaces the loading one. */
function drawApp(page) {
  const bar = document.createElement("header");
  bar.className = "topbar";
  const menu = document.createElement("button");
  menu.className = "btn menu-button";
  bar.append(menu);
  page.app.replaceChildren(bar);
}

const health = (status) => route("/api/health", () => ({ status, body: { status: "ok" } }));
const healthDown = () => route("/api/health", () => new Error("connection refused"));

scenarios.boot_waits_ten_seconds_then_retries_once = async () => {
  useSession();
  const page = bootPage();
  health(200);
  runWatchdog();
  assert.equal(page.reload.textContent, "Reload", "Reload is in the bar from the first frame");
  await advance(9900);
  assert.equal(page.label.textContent, "Loading", "nothing said before 10 s");
  assert.equal(page.failed.hidden, true);
  await advance(100);
  assert.equal(page.label.textContent, "Could not load");
  assert.ok(page.pill.className.includes("pill--offline"));
  assert.equal(page.failed.hidden, false, "the reason shows");
  assert.ok(page.bands.every((b) => b.hidden === true), "the outline gives way");
  assert.equal(page.main.getAttribute("aria-busy"), "false");
  assert.ok(page.detail.textContent.includes("tries once more"), page.detail.textContent);
  assert.equal(sessionStore.get("kickoff.bootRetry"), "1", "the one retry is remembered for this tab");
  assert.equal(window.reloads, 0, "not at once: a back-off first");
  await advance(2000);
  assert.equal(callsTo("/api/health"), 1, "the server is asked first");
  assert.equal(window.reloads, 1, "it answered: one reload");
  await advance(60000);
  assert.equal(window.reloads, 1, "only once");
};

scenarios.boot_drawn_in_time_says_nothing = async () => {
  useSession();
  const page = bootPage();
  health(200);
  runWatchdog();
  await advance(4000);
  drawApp(page);
  await advance(30000);
  assert.equal(window.reloads, 0);
  assert.equal(callsTo("/api/health"), 0);
  assert.equal(sessionStore.has("kickoff.bootRetry"), false);
  window.kickoffBootFailed(); // a late error event from a file the app no longer needs
  await advance(30000);
  assert.equal(window.reloads, 0, "a drawn app is never reloaded");
};

scenarios.boot_a_failed_file_says_so_at_once = async () => {
  useSession();
  const page = bootPage();
  health(200);
  runWatchdog();
  await advance(300);
  window.kickoffBootFailed(); // the module script's error event (index.html: onerror)
  assert.equal(page.label.textContent, "Could not load", "no 10 s wait");
  assert.equal(page.failed.hidden, false);
  await advance(2000);
  assert.equal(window.reloads, 1);
  await advance(10000);
  assert.equal(window.reloads, 1, "the 10 s watchdog adds nothing");
};

scenarios.boot_retried_already_waits_for_a_tap = async () => {
  useSession();
  sessionStore.set("kickoff.bootRetry", "1");
  const page = bootPage();
  health(200);
  runWatchdog();
  await advance(10000);
  assert.equal(page.label.textContent, "Could not load");
  assert.ok(page.detail.textContent.startsWith("Reload to try again"), page.detail.textContent);
  await advance(120000);
  assert.equal(window.reloads, 0, "never a loop");
  assert.equal(callsTo("/api/health"), 0);
  window.kickoffBootReload(); // the reader taps Reload
  assert.equal(page.label.textContent, "Waiting for the server");
  await advance(10);
  assert.equal(window.reloads, 1, "the server answered: reloaded");
};

scenarios.boot_never_reloads_into_a_dead_server = async () => {
  useSession();
  const page = bootPage();
  healthDown();
  runWatchdog();
  window.kickoffBootFailed();
  await advance(2000 + 2000 + 4000 + 8000 + 8000 + 100);
  assert.equal(callsTo("/api/health"), 5, "asked five times, each wait longer");
  assert.equal(window.reloads, 0, "never into a server that does not answer");
  assert.equal(page.label.textContent, "Server not answering");
  assert.ok(page.detail.textContent.includes("server computer"), page.detail.textContent);
  await advance(120000);
  assert.equal(callsTo("/api/health"), 5, "then it stops asking");
  // the server is back: the reader's Reload asks again and reloads
  health(200);
  window.kickoffBootReload();
  await advance(10);
  assert.equal(window.reloads, 1);
};

scenarios.boot_a_hung_health_ask_ends_at_four_seconds = async () => {
  useSession();
  const page = bootPage();
  const real = globalThis.fetch;
  let asks = 0;
  const signals = [];
  const reports = [];
  globalThis.fetch = (url, init) => {
    if (String(url).indexOf("/api/client-log") >= 0) { reports.push(JSON.parse(init.body)); return Promise.resolve({ ok: true }); } // the boot report (freeze wave F1)
    asks += 1; signals.push(init && init.signal); return new Promise(() => {});
  };
  try {
    runWatchdog();
    window.kickoffBootFailed();
    assert.equal(reports.length, 1, "the failed start is reported to the server log once");
    assert.equal(reports[0].kind, "boot");
    assert.ok(reports[0].message.indexOf("script file") >= 0 && typeof reports[0].agent === "string");
    await advance(2000);
    assert.equal(asks, 1);
    await advance(3990);
    assert.equal(asks, 1, "still waiting on the first ask");
    await advance(10);
    assert.ok(signals[0] && signals[0].aborted, "the hung ask is stopped");
    await advance(60000);
    assert.equal(window.reloads, 0);
    assert.equal(page.label.textContent, "Server not answering");
  } finally {
    globalThis.fetch = real;
  }
};

scenarios.boot_reload_tap_restarts_the_wait = async () => {
  useSession();
  const page = bootPage();
  healthDown();
  runWatchdog();
  window.kickoffBootFailed();
  await advance(2000 + 2000 + 100); // two asks missed, the third is 4 s away
  assert.equal(callsTo("/api/health"), 2);
  health(200);
  window.kickoffBootReload();
  assert.equal(page.label.textContent, "Waiting for the server");
  await advance(10);
  assert.equal(window.reloads, 1, "the tap asked at once");
  await advance(30000);
  assert.equal(window.reloads, 1, "the old wait was dropped");
};

scenarios.boot_drawn_while_waiting_cancels_the_retry = async () => {
  useSession();
  const page = bootPage();
  health(200);
  runWatchdog();
  await advance(10000);
  assert.equal(page.label.textContent, "Could not load");
  drawApp(page); // a slow start that made it after all
  await advance(30000);
  assert.equal(window.reloads, 0);
};

scenarios.boot_storage_refused_never_loops = async () => {
  useSession({ blocked: true });
  const page = bootPage();
  health(200);
  runWatchdog();
  await advance(10000);
  assert.equal(page.label.textContent, "Could not load");
  assert.ok(page.detail.textContent.startsWith("Reload to try again"));
  await advance(60000);
  assert.equal(window.reloads, 0, "it cannot remember a retry, so it makes none");
};

// --- identity.js: the 5 s limit ----------------------------------------------------------------------

scenarios.identity_gives_up_after_five_seconds = async () => {
  const { loadIdentity, ours, resetIdentity, IDENTITY_TIMEOUT_MS } = await import(moduleUrl("identity.js"));
  assert.equal(IDENTITY_TIMEOUT_MS, 5000);
  resetIdentity();
  let signal = null;
  let done = false;
  const pending = loadIdentity((url, init) => { signal = init.signal; return new Promise(() => {}); }).then((value) => { done = true; return value; });
  await advance(4990);
  assert.equal(done, false);
  await advance(10);
  const value = await pending;
  assert.equal(done, true, "the first page is never held past 5 s");
  assert.equal(value.school, "", "the blank identity: labels in plain words");
  assert.equal(ours().resolved, false);
  assert.ok(signal && signal.aborted, "the request is stopped");
  assert.ok(warnings.some((w) => w.includes("5 seconds")), warnings.join(" | "));
};

scenarios.identity_ignoring_the_abort_still_ends = async () => {
  const { loadIdentity, resetIdentity } = await import(moduleUrl("identity.js"));
  resetIdentity();
  let failLater = null;
  const pending = loadIdentity(() => new Promise((_resolve, reject) => { failLater = reject; }));
  await advance(5000);
  const value = await pending;
  assert.equal(value.school, "");
  failLater(new Error("a late failure")); // nobody is left to hear it: no unhandled rejection
  await advance(10);
};

scenarios.identity_in_time_and_its_failures = async () => {
  const { loadIdentity, ours, resetIdentity } = await import(moduleUrl("identity.js"));
  resetIdentity();
  const value = await loadIdentity(async () => ({ ok: true, status: 200, json: async () => ({ data: { school: "Swampwater Tech", mascot: "Mudpuppies", abbreviation: "SWT" } }) }));
  assert.equal(value.school, "Swampwater Tech");
  assert.equal(ours().label, "SWT");
  await advance(10000); // the limit's timer was cleared: nothing fires later
  assert.equal(ours().school, "Swampwater Tech");
  resetIdentity();
  assert.equal((await loadIdentity(async () => ({ ok: false, status: 503, json: async () => ({}) }))).school, "");
  assert.equal((await loadIdentity(async () => { throw new Error("offline"); })).school, "");
  assert.equal((await loadIdentity(async () => ({ ok: true, status: 200, json: async () => { throw new SyntaxError("not JSON"); } }))).school, "");
  assert.equal((await loadIdentity(async () => ({ ok: true, status: 200, json: async () => null }))).school, "");
  assert.equal((await loadIdentity(null)).school, "", "no fetch at all");
};

// --- restart.js: reload only into a server that answers ----------------------------------------------

scenarios.reload_waits_for_the_server = async () => {
  const { reloadWhenServerAnswers, SERVER_WAITS_MS } = await import(moduleUrl("ui/restart.js"));
  assert.deepEqual([...SERVER_WAITS_MS], [1000, 2000, 4000, 8000, 8000]);
  let asks = 0;
  route("/api/health", () => { asks += 1; return asks < 3 ? new Error("still restarting") : { status: 200, body: {} }; });
  let reloads = 0;
  const waits = [];
  const pending = reloadWhenServerAnswers({ reload: () => { reloads += 1; }, onWait: (n) => waits.push(n) });
  const again = reloadWhenServerAnswers({ reload: () => { reloads += 100; } });
  assert.equal(again, pending, "one wait at a time");
  await advance(10);
  assert.equal(reloads, 0, "the first ask missed: no reload");
  await advance(1000 + 2000);
  assert.equal(await pending, true);
  assert.equal(reloads, 1, "reloaded once the server answered");
  assert.deepEqual(waits, [1, 2]);
  assert.equal(asks, 3);
};

scenarios.reload_gives_up_and_leaves_the_page = async () => {
  const { reloadWhenServerAnswers } = await import(moduleUrl("ui/restart.js"));
  route("/api/health", () => ({ status: 503, body: {} }));
  let reloads = 0;
  let result = null;
  reloadWhenServerAnswers({ reload: () => { reloads += 1; } }).then((value) => { result = value; });
  await advance(0); // the first ask is answered at once
  await advance(1000 + 2000 + 4000 + 8000 + 8000 + 100);
  assert.equal(result, false, "the server never answered: the page stays as it is");
  assert.equal(reloads, 0);
  assert.equal(callsTo("/api/health"), 6);
  // a later call starts a new wait
  route("/api/health", () => ({ status: 200, body: {} }));
  assert.equal(await reloadWhenServerAnswers({ reload: () => { reloads += 1; } }), true);
  assert.equal(reloads, 1);
};

scenarios.reload_a_hung_ask_times_out = async () => {
  const { serverAnswers, reloadWhenServerAnswers } = await import(moduleUrl("ui/restart.js"));
  let signal = null;
  const hung = (url, init) => { signal = init.signal; return new Promise(() => {}); };
  let answer = null;
  serverAnswers({ fetchImpl: hung }).then((value) => { answer = value; });
  await advance(3990);
  assert.equal(answer, null);
  await advance(10);
  assert.equal(answer, false);
  assert.ok(signal.aborted);
  assert.equal(await serverAnswers({ fetchImpl: null }), false, "no fetch: no server");
  assert.equal(await serverAnswers({ fetchImpl: () => { throw new Error("sync throw"); } }), false);
  // a reload that throws is reported, not thrown
  assert.equal(await reloadWhenServerAnswers({ fetchImpl: async () => ({ ok: true }), reload: () => { throw new Error("no window"); } }), false);
  assert.ok(warnings.some((w) => w.includes("could not reload")));
};

// --- the status pill: words in their own box ---------------------------------------------------------

scenarios.pill_words_in_their_own_box = async () => {
  const { pill } = await import(moduleUrl("ui/pills.js"));
  const button = pill({ kind: "stale", label: "Stale 54 s, CFBD not answering", onClick: () => {} });
  const label = button.querySelector(".pill__label");
  assert.ok(label, "the words sit in .pill__label");
  assert.equal(label.textContent, "Stale 54 s, CFBD not answering");
  assert.equal(button.textContent, "Stale 54 s, CFBD not answering");
  assert.equal(button.getAttribute("title"), "Stale 54 s, CFBD not answering", "the whole label for a mouse");
  const span = pill({ kind: "nope", label: undefined });
  assert.equal(span.querySelector(".pill__label").textContent, "Connecting");
  assert.ok(span.className.includes("pill--quiet"));
  assert.equal(pill({ label: null }).textContent, "Connecting");
  assert.ok(!/undefined|null|NaN/.test(pill({ kind: "live", label: NaN }).textContent));
};

// --- welcome.js: the way back once the setup is done -------------------------------------------------

async function welcomePage(info) {
  document.body.replaceChildren();
  document.getElementById = (id) => document.querySelector(`#${id}`);
  const html = FIXTURE.welcomeIds;
  for (const id of html) {
    const tag = id.endsWith("-input") || id.endsWith("-search") || id.startsWith("ticker-") ? "input" : id === "finish" || id === "key-show" || id === "key-check" ? "button" : "div";
    const n = document.createElement(tag);
    n.setAttribute("id", id);
    document.body.append(n);
  }
  document.querySelector("#back-to-app").hidden = true; // as welcome.html has it
  route("/api/welcome/teams", () => ({ status: 200, body: { data: { teams: [], conferences: [], states: [] } } }));
  route("/api/welcome", () => (info instanceof Error ? info : { status: 200, body: { data: info } }));
  await import(moduleUrl("welcome.js") + `?${Math.random()}`);
  await advance(50);
  return { back: document.querySelector("#back-to-app"), demo: document.querySelector("#demo-line") };
}

scenarios.welcome_set_up_shows_the_way_back = async () => {
  const { back, demo } = await welcomePage({ setupNeeded: false, keyConfigured: true, team: "Swampwater Tech" });
  assert.equal(back.hidden, false, "Back to the app shows");
  assert.equal(demo.hidden, true, "the demo is no longer offered");
};

scenarios.welcome_first_setup_keeps_the_demo = async () => {
  const { back, demo } = await welcomePage({ setupNeeded: true, keyConfigured: false });
  assert.equal(back.hidden, true, "'/' leads back here during a first setup");
  assert.ok(demo.hidden !== true, "the demo stays offered");
};

scenarios.welcome_server_down_keeps_the_defaults = async () => {
  const { back, demo } = await welcomePage(new Error("offline"));
  assert.equal(back.hidden, true);
  assert.ok(demo.hidden !== true);
};
"""


def _fixture(tmp_path: Path) -> str:
    welcome = (STATIC / "welcome.html").read_text(encoding="utf-8")
    ids = sorted(set(re.findall(r'id="([\w-]+)"', welcome)))
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps({"script": _watchdog(), "welcomeIds": ids}), encoding="utf-8")
    return str(path)


def _run(tmp_path: Path, name: str) -> None:
    run_scenario(tmp_path, SCENARIOS, name, _fixture(tmp_path))


# --- E: the loading screen ----------------------------------------------------------------------------


@needs_node
def test_watchdog_waits_ten_seconds_then_retries_once(tmp_path):
    _run(tmp_path, "boot_waits_ten_seconds_then_retries_once")


@needs_node
def test_watchdog_says_nothing_when_the_app_draws(tmp_path):
    _run(tmp_path, "boot_drawn_in_time_says_nothing")


@needs_node
def test_watchdog_a_failed_file_says_so_at_once(tmp_path):
    _run(tmp_path, "boot_a_failed_file_says_so_at_once")


@needs_node
def test_watchdog_retries_once_per_tab(tmp_path):
    _run(tmp_path, "boot_retried_already_waits_for_a_tap")


@needs_node
def test_watchdog_never_reloads_into_a_dead_server(tmp_path):
    _run(tmp_path, "boot_never_reloads_into_a_dead_server")


@needs_node
def test_watchdog_a_hung_health_ask_ends(tmp_path):
    _run(tmp_path, "boot_a_hung_health_ask_ends_at_four_seconds")


@needs_node
def test_watchdog_reload_tap_asks_at_once(tmp_path):
    _run(tmp_path, "boot_reload_tap_restarts_the_wait")


@needs_node
def test_watchdog_a_late_draw_cancels_the_retry(tmp_path):
    _run(tmp_path, "boot_drawn_while_waiting_cancels_the_retry")


@needs_node
def test_watchdog_without_storage_never_loops(tmp_path):
    _run(tmp_path, "boot_storage_refused_never_loops")


@needs_node
def test_identity_gives_up_after_five_seconds(tmp_path):
    _run(tmp_path, "identity_gives_up_after_five_seconds")


@needs_node
def test_identity_ignoring_the_abort_still_ends(tmp_path):
    _run(tmp_path, "identity_ignoring_the_abort_still_ends")


@needs_node
def test_identity_in_time_and_its_failures(tmp_path):
    _run(tmp_path, "identity_in_time_and_its_failures")


@needs_node
def test_reload_waits_for_the_server(tmp_path):
    _run(tmp_path, "reload_waits_for_the_server")


@needs_node
def test_reload_gives_up_and_leaves_the_page(tmp_path):
    _run(tmp_path, "reload_gives_up_and_leaves_the_page")


@needs_node
def test_reload_a_hung_ask_times_out(tmp_path):
    _run(tmp_path, "reload_a_hung_ask_times_out")


def test_the_loading_bar_has_reload_and_the_module_reports_its_failure() -> None:
    header = INDEX[INDEX.index('<header class="topbar">') : INDEX.index("</header>")]
    assert re.search(r'<button class="btn boot-reload" type="button" onclick="[^"]*kickoffBootReload[^"]*">Reload</button>', header), "Reload in the loading bar, a 44 px .btn"
    assert '<span class="pill__label">Loading</span>' in header and 'id="boot-pill"' in header and 'class="topbar__status"' in header
    module = re.search(r'<script type="module" src="/static/js/app.js"([^>]*)>', INDEX)
    assert module and "kickoffBootFailed" in module.group(1) and "onerror=" in module.group(1), "a failed import anywhere in the tree fires the script's error event"
    assert INDEX.index("<script>") < INDEX.index('<script type="module"'), "the watchdog is defined before the module can fail"
    assert 'id="boot-failed"' in INDEX and re.search(r'<section class="band boot__failed"[^>]*hidden>', INDEX)
    script = _watchdog()
    for needle in ('"kickoff.bootRetry"', "WAIT_MS = 10000", '"/api/health"', 'querySelector("#app .menu-button")', "sessionStorage", "Could not load"):
        assert needle in script, needle
    assert ".boot [hidden] { display: none !important; }" in COMPONENTS and ".boot__failed { grid-column: 1 / -1; }" in COMPONENTS


def test_the_app_forgets_the_retry_once_drawn_and_waits_for_the_server_after_a_restart() -> None:
    app = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
    assert 'const BOOT_RETRY_KEY = "kickoff.bootRetry";' in app
    drawn = app.index("root.replaceChildren(page.root);")
    assert app.index("forgetBootRetry();", drawn) - drawn < 200, "forgotten right after the real bar is drawn"
    watch = app[app.index("function watchForUpdates") : app.index("const BOOT_RETRY_KEY")]
    assert "window.location.reload()" not in watch, "no reload straight into a server that may not be back"
    assert watch.count("reloadWhenServerAnswers(") == 4, "the banner's Reload, the reload at once (owner bug 2026-10-13), the reload on coming back into view, and the board's look every minute once the game is over (freeze wave F1, F3)"
    assert 'if (!looping && document.visibilityState === "visible" && !holdsAViewer()) {' in watch, "a visible page reloads as soon as the server answers"
    assert re.search(r'"visibilitychange", \(\) => \{\s*//[^\n]*\n\s*if \(pending && document\.visibilityState === "visible" && !holdsAViewer\(\) && !reloadedJustNow\(\)\) \{\s*rememberReload\(\);\s*reloadWhenServerAnswers\(\);', watch)
    # owner bug 2026-10-13 ("the page refreshes every 5 seconds"): one reload a minute, never a loop
    guard = app[app.index("function reloadedJustNow") : app.index("function watchForUpdates")]
    assert "Date.now() - at < RELOAD_LOOP_MS" in guard and "window.sessionStorage.getItem(RELOADED_AT_KEY)" in guard and "RELOAD_LOOP_MS = 60000" in app
    assert "two different builds within a minute" in watch and watch.count("rememberReload();") == 3  # at once, on coming back into view, and the board's look every minute (freeze wave F1, F3)
    assert "UPDATE_RETRY_MS = 60000" in app and "const armRetry" in watch and "if (!looping) armRetry();" in watch, "the board reloads once the game is over"
    hold = app[app.index("function holdsAViewer") : app.index("function watchForUpdates")]
    assert 'gameUnderWay && ["live", "board"].includes(viewInAddress())' in hold, "only In Game and the board during our game keep the banner instead"
    live = app[app.index("function watchLiveGame") : app.index("function viewInAddress")]
    assert "retry = setTimeout(check, wait);" in live and "DOWN_RETRY_MS = Object.freeze([2000, 4000, 8000])" in app, "a server that does not answer is asked again in seconds"
    identity = (STATIC / "js" / "identity.js").read_text(encoding="utf-8")
    assert "export const IDENTITY_TIMEOUT_MS = 5000;" in identity and "controller.abort()" in identity


# --- F: the top bar -----------------------------------------------------------------------------------


@needs_node
def test_pill_words_sit_in_their_own_box(tmp_path):
    _run(tmp_path, "pill_words_in_their_own_box")


def _top_level(css: str) -> str:
    """The CSS outside any @media block (the rules that hold at every width)."""
    out, i = [], 0
    while i < len(css):
        if css.startswith("@media", i):
            j = css.index("{", i)
            depth_here, k = 1, j + 1
            while depth_here:
                depth_here += {"{": 1, "}": -1}.get(css[k], 0)
                k += 1
            i = k
            continue
        out.append(css[i])
        i += 1
    return "".join(out)


def test_the_menu_is_never_squeezed_and_the_pill_gives_way() -> None:
    top = _top_level(COMPONENTS)
    assert ".topbar > .btn { flex: none; }" in top, "Menu, Search, Reload and a page's way back keep their width"
    assert ".topbar__status { min-width: 0; }" in top
    assert ".topbar__status .pill { max-width: 100%; }" in top
    assert ".topbar__status .pill::before { flex: none; }" in top
    assert ".topbar__status .pill__label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }" in top
    # the press area: nothing around the pill's words clips its 44 px ::after
    for rule in re.findall(r"\.topbar__status(?: \.pill)? \{[^}]*\}", COMPONENTS):
        assert "overflow" not in rule, rule
    assert "@media (max-width: 899px) { .search-button__label { display: none; } }" in COMPONENTS
    assert "@media (max-width: 699px) { .search-button__label" not in COMPONENTS
    assert ".topbar [hidden] { display: none; }" in COMPONENTS


def test_the_menu_border_shows_in_both_themes() -> None:
    rule = re.search(r"\.menu-button \{([^}]*)\}", COMPONENTS)
    assert rule and "border-color: color-mix(in srgb, var(--chalk) 35%, transparent)" in rule.group(1)
    assert "rgba(242, 244, 250, 0.35)" not in COMPONENTS


# --- G: the iPad stops zooming by itself --------------------------------------------------------------


def _no_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _coarse_block(css: str) -> str:
    start = css.index("@media (pointer: coarse) {")
    depth = 0
    for end in range(css.index("{", start), len(css)):
        depth += {"{": 1, "}": -1}.get(css[end], 0)
        if depth == 0:
            return css[start : end + 1]
    raise AssertionError("the touch-screen block is not closed")


def _field_classes() -> dict[str, set[str]]:
    """Every class put on a text field, drop-down or text area in the front end, with the other classes beside it."""
    found: dict[str, set[str]] = {}
    sources = [*sorted((STATIC / "js").rglob("*.js")), *sorted(STATIC.glob("*.html"))]
    for path in sources:
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(r'el\(\s*"(input|select|textarea)",\s*\{(.*?)\}', source, flags=re.S):
            attrs = match.group(2)
            kind = re.search(r'type:\s*"(\w+)"', attrs)
            if kind and kind.group(1) in {"range", "checkbox", "radio"}:
                continue
            cls = re.search(r'class:\s*"([^"]+)"', attrs)
            if cls:
                names = set(cls.group(1).split())
                for name in names:
                    found.setdefault(name, set()).update(names)
        for match in re.finditer(r"<(input|select|textarea)\b([^>]*)>", source):
            attrs = match.group(2)
            kind = re.search(r'type="(\w+)"', attrs)
            if kind and kind.group(1) in {"range", "checkbox", "radio"}:
                continue
            cls = re.search(r'class="([^"]+)"', attrs)
            if cls:
                names = set(cls.group(1).split())
                for name in names:
                    found.setdefault(name, set()).update(names)
    return found


def test_every_field_is_16px_on_a_touch_screen() -> None:
    block = _coarse_block(APP_CSS)
    assert APP_CSS.index(block) > APP_CSS.index(".input { min-height"), "after .input's own rule, so it wins on order"
    assert re.search(r':where\(input:not\(\[type="range"\], \[type="checkbox"\], \[type="radio"\][^)]*\), select, textarea\) \{ font-size: max\(16px, 1em\); \}', block), "a field no class sizes"
    assert ".notes-paste .input { font-size: max(16px, calc(14px * var(--ui-scale))); }" in block
    assert ".depth-card__pick { font-size: max(16px, calc(15px * var(--ui-scale))); }" in block
    inside = block[block.index("{") + 1 : -1]
    raised = {s.strip() for rule in re.findall(r"([^{}]+)\{[^}]*font-size: max\(16px", inside) for s in rule.split(",")}
    for selector in (".input", ".form-field input", ".setting__select", ".setting__text", ".search__input", ".prompt-paste__fallback", ".notes-paste .input", ".depth-card__pick"):
        assert selector in raised, selector
    # every class rule that sizes a field's text is raised here by the same selector (a type selector alone loses to it);
    # a one-class rule in components.css on a field that is also .input loses to .input on order already
    outside = _no_comments(COMPONENTS + APP_CSS.replace(block, ""))
    for cls, beside in _field_classes().items():
        for selectors, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", outside):
            if not re.search(r"(?:^|;|\s)font(?:-size)?\s*:", body):
                continue
            for selector in (s.strip() for s in selectors.split(",")):
                last = selector.split()[-1] if selector else ""
                if not re.search(rf"\.{re.escape(cls)}(?![\w-])", last):
                    continue
                if "input" in beside and selector == f".{cls}" and selector in COMPONENTS and cls != "input":
                    continue
                assert selector in raised, f"{selector} sizes a field's text but is not raised to 16 px on touch screens"


def test_copy_hidden_box_is_16px_and_double_tap_zoom_is_off() -> None:
    paste = (STATIC / "js" / "ui" / "prompt-paste.js").read_text(encoding="utf-8")
    hidden = paste[paste.index("export async function copyHidden") : paste.index("export async function readClipboard")]
    assert 'box.style.fontSize = "16px";' in hidden and 'box.style.top = "0";' in hidden and 'box.style.left = "0";' in hidden
    html = re.search(r"\nhtml \{([^}]*)\}", TOKENS)
    assert html and "touch-action: manipulation;" in html.group(1), "no double-tap zoom; pinch zoom stays"
    assert "user-scalable" not in INDEX and "maximum-scale" not in INDEX, "pinch zoom stays for small print"


def test_the_home_screen_status_bar_is_solid_black() -> None:
    for name in ("index.html", "status.html", "setup.html", "welcome.html", "demo.html"):
        page = (STATIC / name).read_text(encoding="utf-8")
        assert '<meta name="apple-mobile-web-app-status-bar-style" content="black">' in page, name
        assert "black-translucent" not in page, name
        assert "viewport-fit=cover" not in page, f"{name}: the page would run under the clock"


# --- H: no dead ends ----------------------------------------------------------------------------------


def test_the_standalone_pages_lead_back_to_the_app() -> None:
    for name in ("status.html", "setup.html", "welcome.html"):
        page = (STATIC / name).read_text(encoding="utf-8")
        header = page[page.index('<header class="topbar">') : page.index("</header>")]
        link = re.search(r'<a class="btn back-to-app" href="/"[^>]* aria-label="Back to the app"[^>]*><span class="btn__long">Back to the app</span><span class="btn__short">The app</span></a>', header)
        assert link, f"{name}: Back to the app, relative, in the header (in a word on a phone)"
        # every header button but the way back keeps its whole name too when it says it in a word
        for button in re.findall(r'<a class="btn"[^>]*>.*?</a>', header):
            if "btn__short" in button:
                assert "aria-label=" in button and "btn__long" in button, button
    welcome = (STATIC / "welcome.html").read_text(encoding="utf-8")
    assert re.search(r'<a class="btn back-to-app" href="/" id="back-to-app" aria-label="Back to the app" hidden>', welcome), "hidden until the setup is done"
    assert ".btn__short { display: none; }" in COMPONENTS
    assert "@media (max-width: 479px) { .topbar .btn__long { display: none; } .topbar .btn__short { display: inline; } }" in COMPONENTS
    assert '<p class="note" id="demo-line"><a href="/demo" id="back-to-demo">' in welcome
    script = (STATIC / "js" / "welcome.js").read_text(encoding="utf-8")
    assert "const done = state.info?.setupNeeded === false;" in script
    assert "els.backToApp.hidden = !done;" in script and "els.demoLine.hidden = done;" in script


@needs_node
def test_welcome_set_up_shows_the_way_back(tmp_path):
    _run(tmp_path, "welcome_set_up_shows_the_way_back")


@needs_node
def test_welcome_first_setup_keeps_the_demo(tmp_path):
    _run(tmp_path, "welcome_first_setup_keeps_the_demo")


@needs_node
def test_welcome_server_down_keeps_the_defaults(tmp_path):
    _run(tmp_path, "welcome_server_down_keeps_the_defaults")
