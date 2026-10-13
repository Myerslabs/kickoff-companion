"""Item 6, step A (owner 2026-10-11): the way out of big screen mode, in the fake browser and in the source.

The board's "Leave big screen" chip sits outside the zoomed page, hidden until the mouse moves, a key is pressed or the
screen is tapped, and gone again after a few seconds; a press that only reveals it does not also leave. It goes back to
the app's page under the board, else replaces the board with In Game. Escape, Backspace, the browser's Back key and the TV
remotes' Back keys do the same, never while a layer the reader opened is up or while typing. A cold start at the board
puts In Game under it in the history. While the radio plays, its control sits beside the chip. Neither the "Not loaded
yet" list nor a guest's welcome shows on the board (step C made both notes above a page; the board never carries one, and
neither counts as seen there). Unmounting leaves nothing behind."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.fakedom import PROJECT_ROOT, needs_node, run_scenario

STATIC = PROJECT_ROOT / "static"

SCENARIOS = r"""
const RAW = /\b(undefined|null|NaN|Infinity)\b|\[object \w+\]/;
const ev = (type, extra = {}) => Object.assign(makeEvent(type, { bubbles: true, cancelable: true }), extra);

/** A history that keeps each entry's address, for the cold-start seeding. */
function recordingHistory(hash, state) {
  const entries = [{ state, url: hash }];
  let at = 0;
  const h = {
    entries,
    get state() { return entries[at].state; },
    replaceState(s, _title, url) { if (h.failReplace) throw new Error("refused"); entries[at] = { state: s, url: url === undefined ? entries[at].url : url }; if (url !== undefined) window.location.hash = url; },
    pushState(s, _title, url) { if (h.failPush) throw new Error("refused"); entries.splice(at + 1); entries.push({ state: s, url }); at += 1; window.location.hash = url; },
    back() { if (at > 0) at -= 1; window.location.hash = entries[at].url; h.backs = (h.backs || 0) + 1; },
  };
  globalThis.history = h;
  window.history = h;
  window.location.hash = hash;
  return h;
}

function watchReplace() {
  const replaced = [];
  window.location.replace = (url) => { replaced.push(url); window.location.hash = url; };
  return replaced;
}

class FakeAudio {
  constructor() { this.paused = true; this.handlers = {}; this.src = ""; this.preload = ""; }
  addEventListener(type, fn) { (this.handlers[type] ||= []).push(fn); }
  fire(type) { for (const fn of this.handlers[type] || []) fn({ type }); }
  play() { this.paused = false; this.fire("playing"); return Promise.resolve(); }
  pause() { this.paused = true; this.fire("pause"); }
  removeAttribute() {}
  load() {}
}

/** The board mounted against an empty server: every API answers an empty envelope. */
async function mountBoard({ depth = 1 } = {}) {
  route("/api/", () => envelope({}));
  const win = installWindow();
  win.history.replaceState({ depth });
  win.location = { hash: "#board" };
  const replaced = watchReplace();
  const { createBoardView, AWAKE_MS, REVEAL_MS } = await import(moduleUrl("views/board.js"));
  const view = createBoardView({ onStatus: () => {} });
  const main = document.createElement("main");
  document.body.append(main);
  await view.mount(main);
  await settle();
  const exit = () => document.body.querySelector(".board-exit");
  const leave = () => document.body.querySelector(".board-exit__leave");
  const radio = () => document.body.querySelector(".board-exit__radio");
  const awake = () => document.body.classList.contains("board-awake");
  return { view, main, win, replaced, exit, leave, radio, awake, AWAKE_MS, REVEAL_MS };
}

scenarios.keys = async () => {
  const { isExitKey } = await import(moduleUrl("views/board.js"));
  for (const key of ["Escape", "Esc", "Backspace", "BrowserBack", "GoBack", "XF86Back"]) assert.equal(isExitKey({ key }), true, key);
  assert.equal(isExitKey({ key: "Unidentified", keyCode: 461 }), true, "LG webOS remote Back");
  assert.equal(isExitKey({ key: "Unidentified", keyCode: 10009 }), true, "Samsung Tizen remote Back");
  for (const key of ["a", "Enter", " ", "ArrowLeft", "r", "/", "Tab"]) assert.equal(isExitKey({ key }), false, key);
  assert.equal(isExitKey({ key: "Escape", ctrlKey: true }), false, "a shortcut is not a way out");
  assert.equal(isExitKey({ key: "Backspace", altKey: true }), false);
  assert.equal(isExitKey({ key: "Escape", metaKey: true }), false);
  for (const junk of [null, undefined, 5, "Escape", {}]) assert.equal(isExitKey(junk), false, String(junk));
};

scenarios.leave = async () => {
  const { leaveBoard } = await import(moduleUrl("views/board.js"));
  const win = installWindow();
  const replaced = watchReplace();
  win.history.replaceState({ depth: 3 });
  assert.equal(leaveBoard(), "back", "the app's own page is under the board: Back");
  assert.equal(win.backs, 1);
  assert.deepEqual(replaced, []);
  for (const state of [{ depth: 0 }, null, { depth: "1" }, { depth: NaN }, { scrollY: 40 }]) {
    win.history.replaceState(state);
    assert.equal(leaveBoard(), "replace", `state ${JSON.stringify(state)}: nothing of the app's under the board`);
  }
  assert.deepEqual(replaced, ["#live", "#live", "#live", "#live", "#live"], "In Game takes the board's place");
  assert.equal(win.backs, 1, "Back never ran for a cold board");
  win.history.replaceState({ depth: 2 });
  win.history.back = () => { throw new Error("refused"); };
  assert.equal(leaveBoard(), "replace", "a refused Back still leaves");
  assert.ok(warnings.some((w) => w.includes("Back did not run")));
};

scenarios.seed = async () => {
  const { seedBoardHistory } = await import(moduleUrl("views/board.js"));
  let h = recordingHistory("#board", { depth: 0 });
  assert.equal(seedBoardHistory(), true);
  assert.deepEqual(h.entries, [{ state: { depth: 0 }, url: "#live" }, { state: { depth: 1 }, url: "#board" }], "In Game under the board");
  assert.equal(window.location.hash, "#board", "the board's address is kept");
  h.back();
  assert.equal(window.location.hash, "#live", "Back lands on In Game");
  // the board's own route keeps its query; another address seeds a plain #board
  h = recordingHistory("#board?size=tv", { depth: 0, scrollY: 12 });
  assert.equal(seedBoardHistory(), true);
  assert.deepEqual(h.entries, [{ state: { depth: 0, scrollY: 12 }, url: "#live" }, { state: { depth: 1 }, url: "#board?size=tv" }]);
  h = recordingHistory("#boarding", null);
  assert.equal(seedBoardHistory(), true);
  assert.equal(h.entries[1].url, "#board");
  // a refused push puts the board's entry back as it was
  h = recordingHistory("#board", { depth: 0 });
  h.failPush = true;
  assert.equal(seedBoardHistory(), false);
  assert.deepEqual(h.entries, [{ state: { depth: 0 }, url: "#board" }], "the board's own entry, unchanged");
  h = recordingHistory("#board", { depth: 0 });
  h.failReplace = true;
  assert.equal(seedBoardHistory(), false);
  assert.deepEqual(h.entries, [{ state: { depth: 0 }, url: "#board" }]);
  assert.ok(warnings.filter((w) => w.includes("Could not put In Game under the board")).length >= 2, "said in the log");
};

scenarios.radioControl = async () => {
  const { radioControl } = await import(moduleUrl("views/board.js"));
  const stream = { id: "s", kind: "stream", url: "https://example.test/s", name: "S" };
  assert.equal(radioControl(null), null);
  assert.equal(radioControl({ current: null, state: "idle" }), null, "nothing tuned in: no control");
  for (const state of ["playing", "connecting"]) assert.deepEqual(radioControl({ current: stream, state }), { mode: "toggle", glyph: "pause", label: "Pause radio", short: "Pause", aria: "Pause the radio" });
  for (const state of ["paused", "error", "idle", undefined]) assert.equal(radioControl({ current: stream, state }).label, "Play radio", String(state));
  assert.deepEqual(radioControl({ current: { ...stream, kind: "embed" }, state: "embedded" }), { mode: "stop", glyph: "close", label: "Stop radio", short: "Stop", aria: "Stop the radio" });
  for (const junk of [{ current: { kind: "link" } }, { current: "x" }, { current: 5 }, "x", 7, []]) assert.equal(radioControl(junk), null, JSON.stringify(junk));
  // owner 2026-10-11: always there, before the game too: nothing tuned in, it plays the station (a stream only: the dock,
  // where an embedded player shows, is hidden on the board)
  const { boardStation } = await import(moduleUrl("views/board.js"));
  const embed = { id: "e", kind: "embed", url: "https://example.test/e", name: "E" };
  const other = { id: "t", kind: "stream", url: "https://example.test/t", name: "T" };
  const idle = { current: null, state: "idle", sources: [embed, stream, other] };
  assert.deepEqual(radioControl(idle, other), { mode: "start", source: other, glyph: "play", label: "Play radio", short: "Radio", aria: "Play the radio: T" }, "the station used last");
  assert.equal(radioControl(idle, embed).source, stream, "an embedded player used last: the first stream");
  assert.equal(radioControl(idle).source, stream);
  assert.equal(radioControl({ current: null, sources: [embed, { id: "l", kind: "link", url: "https://example.test/l", name: "L" }] }), null, "no stream: no control");
  assert.equal(boardStation([null, 3, "x", { kind: "stream" }], null)?.kind, "stream");
  assert.equal(boardStation("junk", other), null, "a remembered station that is no longer configured is not played");
  assert.equal(boardStation([stream], { ...other }), stream);
};

scenarios.radioStart = async () => {
  globalThis.Audio = FakeAudio;
  const radio = await import(moduleUrl("radio.js"));
  route("/api/radio/sources", () => envelope({ sources: [{ id: "s", name: "Station", kind: "stream", url: "https://example.test/stream" }] }));
  await radio.reloadRadioSources();
  radio.stopRadio();
  const b = await mountBoard();
  assert.ok(!b.radio().hasAttribute("hidden"), "nothing playing yet: the radio's control is still there");
  assert.equal(b.radio().getAttribute("aria-label"), "Play the radio: Station");
  assert.equal(b.radio().querySelector(".board-exit__short").textContent, "Radio");
  await advance(b.REVEAL_MS + 10);
  b.radio().dispatchEvent(ev("click", { detail: 0 }));
  await settle();
  assert.equal(radio.radioSnapshot().current?.id, "s", "pressed: the station plays");
  assert.equal(b.radio().getAttribute("aria-label"), "Pause the radio");
  radio.stopRadio();
  assert.ok(!b.radio().hasAttribute("hidden"), "stopped: back to Play radio, never gone while a station exists");
  b.view.unmount();
};

scenarios.chip = async () => {
  const b = await mountBoard();
  assert.equal(document.body.childNodes[0], b.exit(), "the chip is the body's first child: outside the zoomed page, first for Tab");
  assert.ok(!b.main.contains(b.exit()));
  assert.equal(b.exit().getAttribute("aria-label"), "Big screen");
  assert.equal(b.leave().tagName, "A");
  assert.equal(b.leave().getAttribute("href"), "#live", "a real link to In Game");
  assert.equal(b.leave().getAttribute("aria-label"), "Leave big screen");
  assert.ok(b.leave().querySelector(".board-exit__long").textContent === "Leave big screen" && b.leave().querySelector(".board-exit__short").textContent === "Leave");
  // item 7 (owner 2026-10-11): the radio sits at the left of the score strip's bar, always there; with no station to
  // play here it opens the station list
  assert.ok(b.radio().closest(".tv__radio") && !b.radio().closest(".board-exit"), "in the score bar, not with the fading chip");
  assert.ok(!b.radio().hasAttribute("hidden") && b.radio().getAttribute("aria-label") === "Radio: the stations", "no station yet: the list");
  assert.ok(document.body.querySelector(".tv__qr .board__corner"), "the QR in the board's middle cell");
  assert.ok(!RAW.test(b.exit().textContent), b.exit().textContent);
  assert.ok(document.body.classList.contains("board-mode"));
  // a moment on arrival, then gone
  assert.ok(b.awake(), "shown on arrival");
  await advance(b.AWAKE_MS - 10);
  assert.ok(b.awake());
  await advance(20);
  assert.ok(!b.awake(), "faded after a few seconds");
  // the mouse moves: shown, and every move keeps it up
  b.win.dispatchEvent(ev("pointermove", { pointerType: "mouse" }));
  assert.ok(b.awake(), "a mouse move shows it");
  await advance(2000);
  b.win.dispatchEvent(ev("pointermove", { pointerType: "mouse" }));
  await advance(2000);
  assert.ok(b.awake(), "the timer starts again with each move");
  await advance(1100);
  assert.ok(!b.awake());
  // a tap and a key show it too
  b.win.dispatchEvent(ev("pointerdown", { pointerType: "touch" }));
  assert.ok(b.awake(), "a tap shows it");
  await advance(b.AWAKE_MS + 10);
  b.win.dispatchEvent(ev("keydown", { key: "ArrowDown", target: document.body }));
  assert.ok(b.awake(), "a key shows it");
  assert.equal(b.win.backs || 0, 0, "an ordinary key does not leave");
  await advance(b.AWAKE_MS + 10);
  // a finger on the hidden chip only reveals it
  b.win.dispatchEvent(ev("pointerdown", { pointerType: "touch" }));
  const tap = ev("click", { detail: 1 });
  b.leave().dispatchEvent(tap);
  assert.ok(tap.defaultPrevented, "the link never navigates by itself");
  assert.equal(b.win.backs || 0, 0, "the press that revealed it did not leave");
  assert.deepEqual(b.replaced, []);
  await advance(b.REVEAL_MS + 10);
  b.leave().dispatchEvent(ev("click", { detail: 1 }));
  assert.equal(b.win.backs, 1, "a tap on the shown chip leaves, back to In Game under it");
  b.view.unmount();
};

scenarios.keyboardChip = async () => {
  const b = await mountBoard({ depth: 0 });
  await advance(b.AWAKE_MS + 10);
  b.win.dispatchEvent(ev("keydown", { key: "Tab", target: document.body }));
  b.leave().dispatchEvent(ev("click", { detail: 0 })); // Enter on the focused chip
  assert.deepEqual(b.replaced, ["#live"], "a key press always counts; a cold board is replaced by In Game");
  assert.equal(b.win.backs || 0, 0);
  b.view.unmount();
};

scenarios.exitKeys = async () => {
  const b = await mountBoard({ depth: 1 });
  const press = (key, extra = {}) => {
    const event = ev("keydown", { key, target: document.body, ...extra });
    b.win.dispatchEvent(event);
    return event;
  };
  let event = press("Escape");
  assert.equal(b.win.backs, 1, "Escape leaves");
  assert.ok(event.defaultPrevented, "the browser's own Back key must not go back a second time");
  press("Backspace");
  press("BrowserBack");
  press("Unidentified", { keyCode: 461 });
  press("Unidentified", { keyCode: 10009 });
  assert.equal(b.win.backs, 5, "Backspace, the browser's Back key and both TV remotes leave");
  // not while typing, not with a modifier, not while a layer the reader opened is up
  const input = document.createElement("input");
  document.body.append(input);
  event = press("Backspace", { target: input });
  assert.ok(!event.defaultPrevented, "Backspace in a text box deletes a letter");
  press("Escape", { ctrlKey: true });
  assert.equal(b.win.backs, 5);
  for (const layer of [{ tag: "div", attr: "data-modal" }, { tag: "div", cls: "hint-pop" }, { tag: "div", cls: "status-card" }]) {
    const node = document.createElement(layer.tag);
    if (layer.attr) node.setAttribute(layer.attr, "");
    if (layer.cls) node.className = layer.cls;
    document.body.append(node);
    event = press("Escape");
    assert.equal(b.win.backs, 5, `Escape closes the open ${layer.attr || layer.cls} first`);
    assert.ok(!event.defaultPrevented);
    node.remove();
  }
  press("Escape");
  assert.equal(b.win.backs, 6, "with the layer gone, Escape leaves");
  // a Back that went nowhere: In Game in the board's place
  await advance(800);
  assert.deepEqual(b.replaced, ["#live"], "the board was still up after Back, so In Game replaces it");
  b.view.unmount();
};

scenarios.radio = async () => {
  globalThis.Audio = FakeAudio;
  const b = await mountBoard();
  const radio = await import(moduleUrl("radio.js"));
  radio.startRadio({ id: "s", name: "Station", kind: "stream", url: "https://example.test/stream" });
  await settle();
  assert.equal(radio.radioSnapshot().state, "playing");
  assert.ok(!b.radio().hasAttribute("hidden"), "the radio's control shows beside the chip while it plays");
  assert.equal(b.radio().getAttribute("aria-label"), "Pause the radio");
  assert.equal(b.radio().querySelector(".board-exit__long").textContent, "Pause radio");
  assert.ok(b.radio().querySelector("svg.icon--pause"), "the pause mark");
  await advance(b.REVEAL_MS + 10);
  b.radio().dispatchEvent(ev("click", { detail: 1 }));
  assert.equal(radio.radioSnapshot().state, "paused", "pressed: paused");
  assert.equal(b.radio().getAttribute("aria-label"), "Play the radio");
  assert.equal(b.radio().querySelector(".board-exit__short").textContent, "Play");
  b.radio().dispatchEvent(ev("click", { detail: 0 }));
  assert.equal(radio.radioSnapshot().state, "playing", "pressed again: playing");
  // an embedded player's own button is out of reach on the board: the control stops it
  radio.startRadio({ id: "e", name: "Player", kind: "embed", url: "https://example.test/player" });
  assert.equal(b.radio().getAttribute("aria-label"), "Stop the radio");
  b.radio().dispatchEvent(ev("click", { detail: 0 }));
  assert.equal(radio.radioSnapshot().current, null, "stopped");
  assert.ok(!b.radio().hasAttribute("hidden") && b.radio().getAttribute("aria-label") === "Radio: the stations", "nothing to play here: the station list, never gone");
  assert.equal(b.win.backs || 0, 0, "the radio's control never leaves the board");
  b.view.unmount();
  radio.startRadio({ id: "s", name: "Station", kind: "stream", url: "https://example.test/stream" }); // no listener left to draw a gone control
};

scenarios.unmount = async () => {
  const b = await mountBoard();
  b.win.dispatchEvent(ev("pointermove", { pointerType: "mouse" }));
  b.win.dispatchEvent(ev("keydown", { key: "Escape", target: document.body })); // leaves; its fallback is pending
  assert.equal(b.win.backs, 1);
  b.view.unmount();
  assert.equal(document.body.querySelector(".board-exit"), null, "the chip goes with the board");
  assert.equal(document.body.querySelector(".board__corner"), null);
  assert.ok(!document.body.classList.contains("board-mode") && !document.body.classList.contains("board-awake"));
  assert.equal(timers.size, 0, `timers left after unmount: ${timers.size}`);
  b.win.dispatchEvent(ev("pointermove", { pointerType: "mouse" }));
  b.win.dispatchEvent(ev("keydown", { key: "Escape", target: document.body }));
  assert.ok(!document.body.classList.contains("board-awake"), "no listener left on the window");
  assert.equal(b.win.backs, 1, "Escape after the board is gone does nothing of the board's");
  assert.deepEqual(b.replaced, [], "the cleared fallback never ran");
};

scenarios.notOverBoard = async () => {
  installWindow();
  window.location = { hash: "#board" };
  window.localStorage = localStorage; // the modules read the device's memory through window
  const slot = document.createElement("div");
  slot.className = "page-notes";
  document.body.append(slot);
  const items = [{ id: "season", title: "The 2026 season load", detail: "Not loaded", href: "#preseason" }];
  route("/api/readiness", () => envelope({ ready: false, items, serverStartedAt: "t1" }));
  const { startReadiness } = await import(moduleUrl("ui/readiness.js"));
  document.body.dataset.role = "host";
  document.body.classList.add("board-mode");
  const notices = [];
  assert.ok(await startReadiness({ setNotice: (n) => notices.push(n) }));
  const note = slot.querySelector(".page-note");
  assert.ok(note && note.hasAttribute("hidden"), "never shown on the board");
  assert.ok(slot.hasAttribute("hidden"), "the slot stays shut");
  assert.equal(document.body.querySelector(".sheet-layer"), null, "nothing opens over the board");
  assert.equal(localStorage.getItem("kickoff.readiness.seen"), null, "and not marked seen, so the next page shows it");
  // leaving the board for In Game: shown there (every page but the board, owner 2026-10-13) and marked seen for the day
  document.body.classList.remove("board-mode");
  document.dispatchEvent(new CustomEvent("kickoff:route", { detail: { id: "live" } }));
  assert.ok(!note.hasAttribute("hidden") && !slot.hasAttribute("hidden"), "on In Game");
  const { todayKey } = await import(moduleUrl("ui/readiness.js"));
  assert.equal(localStorage.getItem("kickoff.readiness.seen"), todayKey());
  document.dispatchEvent(new CustomEvent("kickoff:route", { detail: { id: "program" } }));
  assert.ok(!note.hasAttribute("hidden") && !slot.hasAttribute("hidden"), "on the Pre-Game Program too");
  document.dispatchEvent(new CustomEvent("kickoff:route", { detail: { id: "board" } }));
  assert.ok(note.hasAttribute("hidden") && slot.hasAttribute("hidden"), "back on the board: gone again");
};

scenarios.guestNotOverBoard = async () => {
  installWindow();
  window.location = { hash: "#board" };
  window.localStorage = localStorage;
  const slot = document.createElement("div");
  slot.className = "page-notes";
  document.body.append(slot);
  route("/api/host", () => envelope({ pinSet: true, isHost: false, serverComputer: false }));
  route("/api/invite", () => envelope({ url: "http://192.168.0.20:8642/", copyUrl: null, warnings: [] }));
  const { startGuestMode } = await import(moduleUrl("ui/guest.js"));
  document.body.classList.add("board-mode");
  await startGuestMode();
  await settle();
  assert.equal(document.body.dataset.role, "guest");
  const note = slot.querySelector(".page-note");
  assert.ok(note && note.hasAttribute("hidden"), "no welcome on the board");
  assert.equal(document.body.querySelector(".sheet-layer"), null, "and never a sheet");
  assert.equal(localStorage.getItem("kickoff.guest.welcome"), null, "not marked seen: the next page greets the guest");
  // the guest leaves the board: the welcome is on that page, once
  document.body.classList.remove("board-mode");
  document.dispatchEvent(new CustomEvent("kickoff:route", { detail: { id: "live" } }));
  assert.ok(!note.hasAttribute("hidden") && note.textContent.includes("Welcome"), "the welcome on the first page off the board");
  assert.equal(localStorage.getItem("kickoff.guest.welcome"), "1");
  document.dispatchEvent(new CustomEvent("kickoff:route", { detail: { id: "season" } }));
  assert.equal(slot.querySelector(".page-note"), null, "it goes with that page");
  assert.ok(slot.hasAttribute("hidden"));
};
"""


@needs_node
@pytest.mark.parametrize("scenario", ["keys", "leave", "seed", "radioControl", "radioStart", "chip", "keyboardChip", "exitKeys", "radio", "unmount", "notOverBoard", "guestNotOverBoard"])
def test_board_exit_in_a_fake_browser(tmp_path: Path, scenario: str) -> None:
    run_scenario(tmp_path, SCENARIOS, scenario)


def test_a_cold_board_is_seeded_in_the_router():
    """app.js show(): the first entry at #board (depth 0) gets In Game under it, and the depth follows the new entry."""
    app = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
    assert 'import { createBoardView, seedBoardHistory } from "./views/board.js";' in app
    show = app[app.index("  function show(route) {"): app.index("  function refreshCurrent()")]
    seed = show.index('if (route.id === "board" && depth === 0 && seedBoardHistory()) depth = 1;')
    assert show.index("const entry = markEntry();") < seed < show.index("view.mount(page.main);"), "seeded after the entry is numbered, before the board mounts"
    assert 'document.body.classList.remove("board-mode", "board-awake")' in show, "neither class outlives the board"


def test_the_chip_hides_without_leaving_the_tab_order():
    """Hidden is opacity 0 with no taps, never display none (it stays focusable); shown by body.board-awake or keyboard focus,
    which also brings the pointer back; never shown off the board; hidden in print."""
    css = (STATIC / "css" / "components.css").read_text(encoding="utf-8")
    rule = re.search(r"\n\.board-exit > \.btn \{([^}]*)\}", css)
    assert rule and "opacity: 0" in rule.group(1) and "pointer-events: none" in rule.group(1) and "display: none" not in rule.group(1)
    assert "body.board-awake .board-exit > .btn { opacity: 1; pointer-events: auto; }" in css
    assert ".board-exit > .btn:focus-visible { opacity: 1; pointer-events: auto; }" in css, "keyboard focus shows it, in a rule of its own"
    assert "body.board-mode.board-awake .shell__main { cursor: auto; }" in css
    assert ".board-exit > .btn[hidden], body:not(.board-mode) .board-exit { display: none; }" in css, "never shown off the board"
    exit_rule = re.search(r"\n\.board-exit \{([^}]*)\}", css)
    assert exit_rule and "position: fixed" in exit_rule.group(1) and "right:" in exit_rule.group(1) and "top:" in exit_rule.group(1), "item 7: the top-right corner, clear of the bars along the bottom"
    hidden_in_print = next(line for line in css.splitlines() if line.lstrip().startswith(".topbar, .tabs, .shell__radio") and "display: none !important" in line)
    assert ".board__corner, .board-exit," in hidden_in_print, "printed pages leave the chip out with the QR corner"


def test_in_game_has_the_radio_before_the_game_too() -> None:
    """Owner 2026-10-11: the radio always within reach on In Game, before the game too: a Radio button in the tools row
    opens the same station list the Pre-Game Program's Radio band draws (ui/radio-stations.js)."""
    root = Path(__file__).resolve().parents[1] / "static" / "js"
    live = (root / "views" / "live.js").read_text(encoding="utf-8")
    assert 'openSheet({ title: "Radio", body: () => radioStations() })' in live
    assert 'el("div", { class: "live-tools" }, state.delayButton, radioButton,' in live
    program = (root / "views" / "program.js").read_text(encoding="utf-8")
    assert "radioStations({ onDraw:" in program

