// The layers a reader opens over a page (item 6, steps B and D, owner 2026-10-11): the side sheets, the player card and
// the menu. Each one takes one entry in the browser's history when it opens, so Back (or the iPad's edge swipe) closes
// the top layer and the page stays where it is; closing a layer by its own ×, Escape, the scrim or a swipe takes its
// entry back out, again without moving the page. Stacked layers own one entry each and unwind one per Back. A page change
// through a tab, the menu or a link inside a layer takes the layer's own entry, so Back from the new page lands on the
// old one; an entry left behind anyway (a layer closed in the same moment another opened, a reload with a sheet open) is
// stepped over in the direction the reader was going. On a tablet and a big screen the layers start under the top bar,
// so the Menu, Search and the tabs keep working while one is open (components.css, "item 6, step B").
//
//   holdLayer(close, { history })  a layer opened (every one but the styleguide's inline samples). close(reason) is how
//                                  this module closes it: "history" (Back) or "route" (a page change, the Menu).
//                                  { history: false } (a sheet that outlives page changes) takes no entry. Returns
//                                  release(how): "self" when the layer closed by its own hand, which takes its entry
//                                  back out; any other reason leaves the history alone.
//   closeLayers()                  every open layer closes and their entries go (the Menu button; a tab for the page
//                                  already showing).
//   goTo(hash)                     go to another page; from a layer's entry the new page replaces it.
//   placeLayers()                  where the layers start: the top bar's bottom edge, as --layer-top on <html> (0 on the
//                                  board, which hides the top bar).
//   installLayerHistory()          Back closes layers (installed by the first layer, or by app.js at start).
//   stepOverLeftovers()            a reload on a layer's entry (its layer gone with the old page) steps back over it.
//   openLayerCount()               the layers open now (tests, probes).
//
// Each entry copies the page's own history.state (the router's depth and scroll memory keep working) and adds layer (the
// id that pushed it), layers (the ids open at that entry) and layerAt (when, to tell Back from Forward over a dead entry).

const stack = []; // { id, close, history, held } in the order they opened
const later = []; // work that waits for one of our own history steps to land
let pending = 0; // our own history steps not yet answered by popstate
let pendingTimer = null;
let installed = false;
let count = 0;
let lastAt = 0;
let lastPos = null;

const SETTLE_MS = 1000; // a history step that never lands (the start of the list) stops holding the queue after this

function hist() {
  try {
    return typeof history !== "undefined" && history ? history : null;
  } catch {
    return null;
  }
}

function rawState() {
  try {
    return hist()?.state ?? null;
  } catch {
    return null;
  }
}

function readState() {
  const state = rawState();
  return state && typeof state === "object" ? state : {};
}

function chainOf(state) {
  return Array.isArray(state?.layers) ? state.layers.filter((id) => typeof id === "string" && id) : [];
}

/** An entry's place in the list: the router's depth, then (for a layer's entry) when it was pushed. */
function posOf(state) {
  const depth = Number(state?.depth);
  const at = Number(state?.layerAt);
  return [Number.isFinite(depth) ? depth : -1, Number.isFinite(at) ? at : 0];
}

/** Whether entry a lies after entry b; an entry the router has not numbered (depth -1) cannot say, so it reads as before. */
function isAfter(a, b) {
  if (a[0] < 0 || b[0] < 0) return false;
  return a[0] !== b[0] ? a[0] > b[0] : a[1] > b[1];
}

function newId() {
  count += 1;
  return `layer-${Date.now().toString(36)}-${count}`; // unique across reloads: a leftover entry never names a new layer
}

function drop(id) {
  const at = stack.findIndex((entry) => entry.id === id);
  return at >= 0 ? stack.splice(at, 1)[0] : null;
}

function settle() {
  pending = 0;
  if (pendingTimer !== null) clearTimeout(pendingTimer);
  pendingTimer = null;
  flush();
}

function flush() {
  while (pending === 0 && later.length) {
    const job = later.shift();
    try {
      job();
    } catch (error) {
      console.error("A layer's history step failed.", error);
    }
  }
}

/** Run now, or once our own history steps have landed (a push or a page change in between would land in the wrong place). */
function whenSettled(job) {
  if (pending === 0) job();
  else later.push(job);
}

function traverse(delta) {
  const h = hist();
  if (!h || !delta) return;
  pending += 1;
  if (pendingTimer !== null) clearTimeout(pendingTimer);
  pendingTimer = setTimeout(settle, SETTLE_MS);
  const before = rawState();
  try {
    if (delta === -1 && typeof h.back === "function") h.back();
    else if (delta === 1 && typeof h.forward === "function") h.forward();
    else if (typeof h.go === "function") h.go(delta);
    else settle();
  } catch (error) {
    console.warn("The history step did not run; the page keeps its place.", error?.message || error);
    settle();
    return;
  }
  // a browser steps later and says so with popstate; a history that stepped at once (a test's) has landed already
  const now = rawState();
  if (pending > 0 && now !== before) onPop({ state: now });
}

function push(entry) {
  const h = hist();
  if (!h || typeof h.pushState !== "function" || !stack.includes(entry)) return;
  const state = readState();
  const open = new Set(stack.filter((e) => e.held).map((e) => e.id));
  const layers = [...chainOf(state).filter((id) => open.has(id) && id !== entry.id), entry.id];
  lastAt = Math.max(Date.now(), lastAt + 1);
  const next = { ...state, layer: entry.id, layers, layerAt: lastAt };
  try {
    h.pushState(next, "");
    entry.held = true;
    lastPos = posOf(next);
  } catch (error) {
    console.warn("The layer has no history entry; Back changes the page instead.", error?.message || error);
  }
}

function soon(job) {
  if (typeof queueMicrotask === "function") queueMicrotask(job);
  else Promise.resolve().then(job);
}

function release(id, how) {
  const entry = drop(id);
  if (!entry || !entry.history || !entry.held || how !== "self") return;
  // after the rest of this tap: a page change or another layer opened in the same moment keeps the entry (stepped over
  // later), so Back never undoes the reader's own step
  soon(() => whenSettled(() => {
    if (readState().layer === id) traverse(-1);
  }));
}

function onPop(event) {
  if (pending > 0) pending -= 1;
  if (pending === 0 && pendingTimer !== null) {
    clearTimeout(pendingTimer);
    pendingTimer = null;
  }
  const state = event && event.state && typeof event.state === "object" ? event.state : {};
  const chain = chainOf(state);
  const keep = new Set(chain);
  for (const entry of [...stack].reverse()) {
    if (!entry.history || !entry.held || keep.has(entry.id)) continue; // a layer without an entry is not History's to close
    drop(entry.id);
    try {
      entry.close("history");
    } catch (error) {
      console.error("A layer did not close on Back.", error);
    }
  }
  const pos = posOf(state);
  const before = lastPos;
  lastPos = pos;
  const open = new Set(stack.map((entry) => entry.id));
  if (chain.some((id) => !open.has(id))) {
    traverse(before && isAfter(pos, before) ? 1 : -1); // a closed layer's entry: step over it, the way the reader was going
    return;
  }
  flush();
}

/** A link inside a layer goes to its page in the layer's own entry (after the page's own handlers had their say). */
function onLinkClick(event) {
  if (!event || event.defaultPrevented || event.button > 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const link = typeof event.target?.closest === "function" ? event.target.closest("a[href]") : null;
  const href = link ? link.getAttribute("href") : null;
  if (!href || !href.startsWith("#") || href === "#" || link.getAttribute("target")) return;
  if (!link.closest(".sheet-layer, .card-layer, .drawer") || !chainOf(readState()).length) return;
  if (href === window.location.hash) return;
  event.preventDefault();
  goTo(href);
}

export function installLayerHistory() {
  if (installed || typeof window === "undefined" || typeof window.addEventListener !== "function") return false;
  installed = true;
  window.addEventListener("popstate", onPop);
  window.addEventListener("click", onLinkClick); // on the window, so a chip's own sheet or a team flyout decides first
  window.addEventListener("resize", () => {
    if (stack.length) placeLayers();
  }, { passive: true });
  if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
    document.addEventListener("kickoff:route", () => {
      lastPos = posOf(readState()); // the router has numbered the new page's entry
    });
  }
  lastPos = posOf(readState());
  return true;
}

export function holdLayer(close, { history: takesEntry = true } = {}) {
  installLayerHistory();
  const entry = { id: newId(), close: typeof close === "function" ? close : () => {}, history: takesEntry !== false, held: false };
  stack.push(entry);
  if (entry.history) whenSettled(() => push(entry));
  return (how) => release(entry.id, how);
}

export function closeLayers() {
  for (const entry of [...stack].reverse()) {
    drop(entry.id);
    try {
      entry.close("route");
    } catch (error) {
      console.error("A layer did not close.", error);
    }
  }
  whenSettled(() => {
    const ours = chainOf(readState()).length; // our entries above the page's own
    if (ours > 0) traverse(-ours);
  });
}

export function goTo(hash) {
  const target = `#${String(hash ?? "").replace(/^#/, "")}`;
  if (typeof window === "undefined" || !window.location) return;
  if (target === window.location.hash) {
    closeLayers(); // the page already showing: the layers close and their entries go
    return;
  }
  for (const entry of [...stack].reverse()) {
    if (!entry.history) continue; // a sheet that outlives page changes stays
    drop(entry.id);
    try {
      entry.close("route");
    } catch (error) {
      console.error("A layer did not close on the page change.", error);
    }
  }
  whenSettled(() => {
    if (chainOf(readState()).length && typeof window.location.replace === "function") {
      try {
        window.location.replace(target); // the layer's entry becomes the new page: Back lands on the old one
        return;
      } catch (error) {
        console.warn("Could not reuse the layer's entry; the page gets its own.", error?.message || error);
      }
    }
    window.location.hash = target;
  });
}

export function stepOverLeftovers() {
  installLayerHistory();
  const h = hist();
  if (stack.length || !chainOf(readState()).length || !h || !(Number(h.length) > 1)) return false;
  whenSettled(() => traverse(-1));
  return true;
}

export function placeLayers() {
  try {
    const root = typeof document !== "undefined" ? document.documentElement : null;
    if (!root?.style || typeof root.style.setProperty !== "function") return 0;
    const bar = document.querySelector(".topbar");
    let top = 0;
    if (bar && !document.body?.classList?.contains("board-mode") && typeof bar.getBoundingClientRect === "function") {
      const box = bar.getBoundingClientRect();
      if (box && box.height > 0 && Number.isFinite(box.bottom)) top = Math.max(0, Math.round(box.bottom));
    }
    root.style.setProperty("--layer-top", `${top}px`);
    return top;
  } catch {
    return 0; // the stylesheet's fallback (the top bar's height) applies
  }
}

export function openLayerCount() {
  return stack.length;
}
