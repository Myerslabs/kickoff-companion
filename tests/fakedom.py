"""A small fake browser for the front-end tests, lifted from test_static_10a.py (Phase 16, stream F), so
every stream can write FakeDOM scenarios in its own test file without editing a shared one.

    from tests.fakedom import NODE, needs_node, run_scenario

    SCENARIOS = r'''
    scenarios.chip = async () => { const { rankChip } = await import(moduleUrl("ui/stat-table.js")); ... };
    '''

    @needs_node
    def test_chip(tmp_path):
        run_scenario(tmp_path, SCENARIOS, "chip")

The script is FAKEDOM_JS (the clock, the DOM, fetch routes, EventSource, ResizeObserver, the wake lock,
installWindow() and touch() for scenarios that need them), then the caller's scenarios (each an async
function on `scenarios`), then RUNNER_JS, which runs the one named on the command line and prints
'ok <name>'. Scenarios run under Node with the real modules from static/js; nothing touches the network.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_JS = PROJECT_ROOT / "static" / "js"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


def harness(scenarios_js: str) -> str:
    """The whole script: the fake browser, the caller's scenarios, the runner."""
    return FAKEDOM_JS + "\nconst scenarios = {};\n" + scenarios_js + "\n" + RUNNER_JS


def run_scenario(tmp_path: Path, scenarios_js: str, scenario: str, *extra: str, timeout: int = 120) -> str:
    """Run one scenario and return its output; fails the test with the scenario's own report."""
    assert NODE is not None, "node is not installed"
    script = tmp_path / "harness.mjs"
    script.write_text(harness(scenarios_js), encoding="utf-8")
    result = subprocess.run([NODE, str(script), str(STATIC_JS), scenario, *extra], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    assert result.returncode == 0 and f"ok {scenario}" in result.stdout, result.stdout[-6000:] + result.stderr[-2000:]
    return result.stdout


FAKEDOM_JS = r"""// A small fake browser (lifted from test_static_10a.py in Phase 16): a DOM with the calls the app
// makes, a virtual clock that owns every timer, and scripted fetch, EventSource, ResizeObserver, and
// wake lock. Each scenario mounts the real modules from static/js and asserts what a tablet would show.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [, , STATIC_JS, SCENARIO, FIXTURE_PATH] = process.argv;
const FIXTURE = FIXTURE_PATH ? JSON.parse(readFileSync(FIXTURE_PATH, "utf8")) : null;
const moduleUrl = (rel) => pathToFileURL(join(STATIC_JS, rel)).href;
const clone = (value) => JSON.parse(JSON.stringify(value));
// The team the app follows, as /api/identity gives it before the first page draws (public release
// Phase 3). A scenario that renders "us" labels calls it first; without it the labels are plain words.
const TEAM = { school: "Swampwater Tech", mascot: "Mudpuppies", abbreviation: "SWT", conference: "Biscuit Belt", conferenceShort: "Biscuit Belt", color: "#1d6b5f", altColor: "#e0b23c" };
const useTeam = async (data = TEAM) => (await import(moduleUrl("identity.js"))).setIdentity(data);

// --- the virtual clock ------------------------------------------------------------------------------

let now = Date.UTC(2026, 8, 26, 18, 45, 0);
Date.now = () => now;
const timers = new Map();
let nextTimer = 1;
const realSetImmediate = setImmediate;
globalThis.setTimeout = (fn, ms = 0, ...args) => {
  const id = nextTimer++;
  timers.set(id, { fn: () => fn(...args), at: now + Math.max(0, Number(ms) || 0), every: null });
  return id;
};
globalThis.setInterval = (fn, ms = 0, ...args) => {
  const id = nextTimer++;
  const every = Math.max(1, Number(ms) || 0);
  timers.set(id, { fn: () => fn(...args), at: now + every, every });
  return id;
};
globalThis.clearTimeout = (id) => timers.delete(id);
globalThis.clearInterval = (id) => timers.delete(id);

async function settle() {
  for (let i = 0; i < 6; i += 1) await new Promise((resolve) => realSetImmediate(resolve));
}

async function advance(ms) {
  const end = now + ms;
  for (;;) {
    let due = null;
    for (const [id, timer] of timers) if (timer.at <= end && (!due || timer.at < due[1].at)) due = [id, timer];
    if (!due) break;
    const [id, timer] = due;
    now = timer.at;
    if (timer.every) timer.at += timer.every;
    else timers.delete(id);
    timer.fn();
    await settle();
  }
  now = end;
  await settle();
}

// --- the DOM ----------------------------------------------------------------------------------------

function makeEvent(type, init = {}) {
  return { type, bubbles: Boolean(init.bubbles), cancelable: Boolean(init.cancelable), key: init.key, detail: init.detail, target: null, defaultPrevented: false, _stopped: false, preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this._stopped = true; } };
}

class FakeNode {
  constructor() {
    this.parentNode = null;
    this.childNodes = [];
  }
  get children() {
    return this.childNodes.filter((n) => n instanceof FakeElement); // the availability table reads cell.children (2026-10-02)
  }
  get textContent() {
    return this.childNodes.map((n) => n.textContent).join("");
  }
  set textContent(value) {
    this.replaceChildren();
    if (value !== null && value !== undefined && String(value) !== "") this.appendChild(new FakeText(String(value)));
  }
  get nextSibling() {
    const p = this.parentNode;
    return p ? p.childNodes[p.childNodes.indexOf(this) + 1] || null : null;
  }
  get isConnected() {
    let n = this;
    while (n.parentNode) n = n.parentNode;
    return n === document;
  }
  appendChild(node) {
    return this.insertBefore(node, null);
  }
  insertBefore(node, ref) {
    if (node instanceof FakeFragment) {
      for (const child of [...node.childNodes]) this.insertBefore(child, ref);
      return node;
    }
    if (!(node instanceof FakeNode)) throw new TypeError("insertBefore: not a node");
    if (node === ref) return node;
    if (node.contains && node.contains(this)) throw new Error("HierarchyRequestError");
    if (node.parentNode) node.parentNode.removeChild(node);
    const index = ref ? this.childNodes.indexOf(ref) : -1;
    node.parentNode = this;
    if (index < 0) this.childNodes.push(node);
    else this.childNodes.splice(index, 0, node);
    return node;
  }
  removeChild(node) {
    const index = this.childNodes.indexOf(node);
    if (index >= 0) this.childNodes.splice(index, 1);
    node.parentNode = null;
    return node;
  }
  append(...nodes) {
    for (const n of nodes) this.appendChild(toNode(n));
  }
  prepend(...nodes) {
    const first = this.childNodes[0] || null;
    for (const n of nodes) this.insertBefore(toNode(n), first);
  }
  replaceChildren(...nodes) {
    for (const child of [...this.childNodes]) this.removeChild(child);
    this.append(...nodes);
  }
  remove() {
    if (this.parentNode) this.parentNode.removeChild(this);
  }
  replaceWith(...nodes) {
    const parent = this.parentNode;
    if (!parent) return;
    const next = this.nextSibling;
    parent.removeChild(this);
    for (const n of nodes) parent.insertBefore(toNode(n), next);
  }
  before(...nodes) {
    if (!this.parentNode) return;
    for (const n of nodes) this.parentNode.insertBefore(toNode(n), this);
  }
  contains(node) {
    for (let n = node; n; n = n.parentNode) if (n === this) return true;
    return false;
  }
}

class FakeText extends FakeNode {
  constructor(data) {
    super();
    this.data = String(data);
  }
  get textContent() {
    return this.data;
  }
  set textContent(value) {
    this.data = String(value);
  }
}

class FakeComment extends FakeNode {
  get textContent() {
    return "";
  }
}

class FakeFragment extends FakeNode {}

function toNode(value) {
  return value instanceof FakeNode ? value : new FakeText(String(value));
}

class FakeElement extends FakeNode {
  constructor(tag) {
    super();
    this.localName = String(tag).toLowerCase();
    this.tagName = this.localName.toUpperCase();
    this.attributes = new Map();
    this.dataset = {};
    this.style = { setProperty(key, value) { this[key] = String(value); } };
    this.listeners = new Map();
    this.scrollTop = 0;
    this.scrollLeft = 0;
    this._value = undefined;
  }
  setAttribute(key, value) {
    this.attributes.set(key, String(value));
  }
  getAttribute(key) {
    return this.attributes.has(key) ? this.attributes.get(key) : null;
  }
  hasAttribute(key) {
    return this.attributes.has(key);
  }
  removeAttribute(key) {
    this.attributes.delete(key);
  }
  get className() {
    return this.getAttribute("class") || "";
  }
  set className(value) {
    if (value) this.setAttribute("class", value);
    else this.removeAttribute("class");
  }
  get classList() {
    const list = () => this.className.split(/\s+/).filter(Boolean);
    return {
      contains: (c) => list().includes(c),
      add: (...cs) => { this.className = [...new Set([...list(), ...cs])].join(" "); },
      remove: (...cs) => { this.className = list().filter((c) => !cs.includes(c)).join(" "); },
      toggle: (c, force) => {
        const on = force === undefined ? !list().includes(c) : Boolean(force);
        if (on) this.className = [...new Set([...list(), c])].join(" ");
        else this.className = list().filter((x) => x !== c).join(" ");
        return on;
      },
    };
  }
  get value() {
    return this._value !== undefined ? this._value : this.getAttribute("value") ?? "";
  }
  set value(v) {
    this._value = String(v);
  }
  addEventListener(type, fn) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(fn);
  }
  removeEventListener(type, fn) {
    const list = this.listeners.get(type);
    if (!list) return;
    const index = list.indexOf(fn);
    if (index >= 0) list.splice(index, 1);
  }
  dispatchEvent(event) {
    if (!event.target) event.target = this;
    for (let n = this; n; n = n.parentNode) {
      const list = n.listeners?.get(event.type);
      if (list) for (const fn of [...list]) fn.call(n, event);
      if (!event.bubbles || event._stopped) break;
    }
    return !event.defaultPrevented;
  }
  click() {
    this.dispatchEvent(makeEvent("click", { bubbles: true }));
  }
  focus() {
    document.activeElement = this;
  }
  getBoundingClientRect() {
    return { width: 0, height: 0, top: 0, left: 0, right: 0, bottom: 0 };
  }
  matches(selector) {
    return matchesSelector(this, selector);
  }
  closest(selector) {
    for (let n = this; n instanceof FakeElement; n = n.parentNode) if (matchesSelector(n, selector)) return n;
    return null;
  }
  querySelectorAll(selector) {
    const out = [];
    const walk = (node) => {
      for (const child of node.childNodes) {
        if (!(child instanceof FakeElement)) continue;
        if (matchesSelector(child, selector)) out.push(child);
        walk(child);
      }
    };
    walk(this);
    return out;
  }
  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
}

function parseCompound(source) {
  const m = { tag: null, id: null, classes: [], attrs: [], nots: [] };
  let rest = source;
  const tag = rest.match(/^([a-zA-Z][\w-]*|\*)/);
  if (tag) {
    m.tag = tag[0] === "*" ? null : tag[0].toLowerCase();
    rest = rest.slice(tag[0].length);
  }
  while (rest) {
    let t;
    if ((t = rest.match(/^\.([\w-]+)/))) m.classes.push(t[1]);
    else if ((t = rest.match(/^#([\w-]+)/))) m.id = t[1];
    else if ((t = rest.match(/^\[([\w-]+)(?:="([^"]*)")?\]/))) m.attrs.push([t[1], t[2]]);
    else if ((t = rest.match(/^:not\(([^)]+)\)/))) m.nots.push(t[1]);
    else throw new Error(`harness: unsupported selector ${source}`);
    rest = rest.slice(t[0].length);
  }
  return m;
}

function attrOf(node, name) {
  if (node.attributes.has(name)) return node.attributes.get(name);
  if (name.startsWith("data-")) {
    const key = name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    if (key in node.dataset) return String(node.dataset[key]);
  }
  return null;
}

function matchCompound(node, m) {
  if (!(node instanceof FakeElement)) return false;
  if (m.tag && node.localName !== m.tag) return false;
  if (m.id && node.getAttribute("id") !== m.id) return false;
  const classes = node.className.split(/\s+/);
  if (!m.classes.every((c) => classes.includes(c))) return false;
  for (const [name, value] of m.attrs) {
    const v = attrOf(node, name);
    if (v === null || (value !== undefined && v !== value)) return false;
  }
  return !m.nots.some((s) => matchesSelector(node, s));
}

/** Split on a separator outside brackets, parentheses, and quotes. */
function splitTop(source, separator) {
  const parts = [];
  let depth = 0;
  let quote = null;
  let current = "";
  for (const ch of source) {
    if (quote) {
      if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'") quote = ch;
    else if (ch === "[" || ch === "(") depth += 1;
    else if (ch === "]" || ch === ")") depth -= 1;
    else if (depth === 0 && separator.test(ch)) {
      if (current) parts.push(current);
      current = "";
      continue;
    }
    current += ch;
  }
  if (current) parts.push(current);
  return parts;
}

function matchesSelector(node, selector) {
  return splitTop(selector, /,/).some((part) => {
    const compounds = splitTop(part.trim(), /\s/).map(parseCompound);
    if (!matchCompound(node, compounds[compounds.length - 1])) return false;
    let i = compounds.length - 2;
    for (let n = node.parentNode; i >= 0 && n; n = n.parentNode) if (matchCompound(n, compounds[i])) i -= 1;
    return i < 0;
  });
}

const document = new FakeElement("#document");
document.documentElement = new FakeElement("html");
document.body = new FakeElement("body");
document.documentElement.append(document.body);
document.append(document.documentElement);
document.visibilityState = "visible";
document.activeElement = null;
document.createElement = (tag) => {
  if (globalThis.__failTag && String(tag).toLowerCase() === globalThis.__failTag) throw new Error(`harness: injected fault building <${tag}>`);
  return new FakeElement(tag);
};
document.createElementNS = (_ns, tag) => new FakeElement(tag);
document.createTextNode = (data) => new FakeText(data);
document.createComment = () => new FakeComment();
document.createDocumentFragment = () => new FakeFragment();

globalThis.document = document;
globalThis.Node = FakeNode;
globalThis.window = { location: { hash: "" }, scrollTo() {} };
globalThis.CustomEvent = class {
  constructor(type, init = {}) {
    Object.assign(this, makeEvent(type, init));
  }
};
const storage = new Map();
globalThis.localStorage = { getItem: (k) => (storage.has(k) ? storage.get(k) : null), setItem: (k, v) => storage.set(k, String(v)), removeItem: (k) => storage.delete(k) };
globalThis.requestAnimationFrame = (fn) => setTimeout(() => fn(now), 16);
globalThis.cancelAnimationFrame = (id) => clearTimeout(id);

const observers = [];
globalThis.ResizeObserver = class {
  constructor(callback) {
    this.callback = callback;
    this.targets = [];
    this.disconnected = false;
    observers.push(this);
  }
  observe(target) {
    this.targets.push(target);
  }
  disconnect() {
    this.disconnected = true;
    this.targets = [];
  }
};

const sources = [];
class FakeEventSource {
  constructor(url) {
    this.url = url;
    this.readyState = 0;
    this.listeners = new Map();
    this.onerror = null;
    sources.push(this);
  }
  addEventListener(type, fn) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(fn);
  }
  close() {
    this.readyState = 2;
  }
  emit(type, data) {
    assert.notEqual(this.readyState, 2, `harness: ${type} on a closed stream`);
    this.readyState = 1;
    for (const fn of this.listeners.get(type) || []) fn({ type, data: typeof data === "string" ? data : JSON.stringify(data) });
  }
  fail(closed = false) {
    this.readyState = closed ? 2 : 0;
    if (typeof this.onerror === "function") this.onerror({ type: "error" });
  }
}
FakeEventSource.CONNECTING = 0;
FakeEventSource.OPEN = 1;
FakeEventSource.CLOSED = 2;
globalThis.EventSource = FakeEventSource;
const latest = () => sources[sources.length - 1];

class FakeSentinel {
  constructor() {
    this.released = false;
    this.listeners = [];
  }
  addEventListener(type, fn) {
    if (type === "release") this.listeners.push(fn);
  }
  async release() {
    if (this.released) return;
    this.released = true;
    for (const fn of this.listeners) fn({ type: "release" });
  }
}
const wake = { requests: 0, sentinels: [] };
Object.defineProperty(globalThis, "navigator", {
  configurable: true,
  writable: true,
  value: { userAgent: "harness", wakeLock: { request: async () => { wake.requests += 1; const s = new FakeSentinel(); wake.sentinels.push(s); return s; } } },
});

const routes = [];
const calls = [];
function route(prefix, handler) {
  routes.unshift([prefix, handler]);
}
const envelope = (data) => ({ status: 200, body: { data, errors: [], meta: { source: "live", fetched_at: new Date(now).toISOString(), stale: false } } });
globalThis.fetch = async (url) => {
  calls.push(String(url));
  const hit = routes.find(([prefix]) => String(url).startsWith(prefix));
  if (!hit) return { ok: false, status: 404, json: async () => ({ errors: [{ message: `harness: no route for ${url}` }] }) };
  const answer = typeof hit[1] === "function" ? hit[1](url) : hit[1];
  if (answer instanceof Error) throw answer;
  return { ok: answer.status >= 200 && answer.status < 300, status: answer.status, json: async () => answer.body };
};
const callsTo = (prefix) => calls.filter((u) => u.startsWith(prefix)).length;

const warnings = [];
const errors = [];
console.warn = (...args) => warnings.push(args.map(String).join(" "));
console.error = (...args) => errors.push(args.map(String).join(" "));

// --- opt-in pieces for scenarios that need a fuller page (Phase 16) ---------------------------------------

/** A window that takes listeners, a history with state, and a page scroll; off by default so the Phase 10a
 *  scenarios see the same bare window they always did. */
function installWindow({ scrollY = 0 } = {}) {
  const listeners = new Map();
  const win = globalThis.window;
  win.scrollY = scrollY;
  win.scrollTo = (x, y) => { win.scrollY = Number(typeof x === "object" ? x.top : y) || 0; };
  win.addEventListener = (type, fn) => { if (!listeners.has(type)) listeners.set(type, []); listeners.get(type).push(fn); };
  win.removeEventListener = (type, fn) => { const list = listeners.get(type) || []; const i = list.indexOf(fn); if (i >= 0) list.splice(i, 1); };
  win.dispatchEvent = (event) => { for (const fn of [...(listeners.get(event.type) || [])]) fn(event); return !event.defaultPrevented; };
  const entries = [{ state: null }];
  let at = 0;
  win.history = {
    get state() { return entries[at].state; },
    get length() { return entries.length; },
    replaceState(state) { entries[at].state = state; },
    pushState(state) { entries.splice(at + 1); entries.push({ state }); at += 1; },
    back() { if (at > 0) at -= 1; win.backs = (win.backs || 0) + 1; },
  };
  globalThis.history = win.history;
  return win;
}

/** A touch event for pull-to-refresh scenarios. */
function touch(type, target, y) {
  const event = makeEvent(type, { bubbles: true });
  event.target = target;
  event.touches = type === "touchend" || type === "touchcancel" ? [] : [{ clientY: y }];
  return event;
}
"""

RUNNER_JS = r"""const run = scenarios[SCENARIO];
if (!run) {
  console.log(`unknown scenario ${SCENARIO}`);
  process.exit(2);
}
try {
  await run();
  process.stdout.write(`ok ${SCENARIO}\n`);
  process.exit(0);
} catch (error) {
  process.stdout.write(`FAIL ${SCENARIO}\n${error?.stack || error}\n`);
  if (warnings.length) process.stdout.write(`warnings:\n${warnings.join("\n")}\n`);
  if (errors.length) process.stdout.write(`errors:\n${errors.join("\n")}\n`);
  process.exit(1);
}
"""
