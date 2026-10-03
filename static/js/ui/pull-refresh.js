// Pull down to refresh (UX-04, Phase 16 stream F). As a home-screen app the tablet has no reload button,
// so pulling down at the very top of a page asks the server again. A thin orange line under the top bar
// shows the pull and then the request; nothing spins in the middle of the screen (design brief, States 1).
// The desktop gets the same through the 'r' key (wired in app.js).
//
// Frozen API:
//   pullAllowed(target, scrollY)   whether a touch starting at `target` may start a pull: only at the top of
//       the page, never inside a sideways-scrolling table, the ticker, the remote bar, a side sheet, the player
//       card, the menu, the play log or a form field, and never while an overlay is open.
//   installPullToRefresh({ root, host, onRefresh, threshold = 72 }) -> { line, trigger(), destroy() }
//       root: where touches count (the page's main area); host: where the line is drawn; onRefresh() may
//       return a promise, which the line waits on (at most 20 s). trigger() runs a refresh now.

import { el, isNum } from "./dom.js";

const BLOCKERS = ".stat-table-wrap, .ticker, .remote, .sheet-layer, .card-layer, .player-card, .drawer, .plays, .hint-pop, input, select, textarea, [data-no-pull]";
const WAIT_MS = 20000;

export function pullAllowed(target, scrollY) {
  if (!isNum(scrollY) || scrollY > 0) return false;
  let node = target || null;
  if (node && typeof node.closest !== "function") node = node.parentNode || null; // a text node
  if (node && typeof node.closest === "function" && node.closest(BLOCKERS)) return false;
  try {
    if (document.querySelector("[data-modal]")) return false;
  } catch {
    return false;
  }
  return true;
}

export function installPullToRefresh({ root, host, onRefresh, threshold = 72 } = {}) {
  const line = el("div", { class: "pull-line", "aria-hidden": "true" });
  (host || document.body).append(line);
  const area = root || document;
  let startY = null;
  let progress = 0;
  let busy = false;

  const show = (value) => {
    progress = Math.max(0, Math.min(1, value));
    line.style.setProperty("--pull", String(progress));
    if (progress > 0) line.classList.add("is-pulling");
    else line.classList.remove("is-pulling");
  };
  const reset = () => {
    startY = null;
    show(0);
  };

  function trigger() {
    if (busy) return Promise.resolve(false);
    busy = true;
    line.classList.add("is-busy");
    let timer = null;
    const limit = new Promise((resolve) => {
      timer = setTimeout(resolve, WAIT_MS);
    });
    return Promise.race([Promise.resolve().then(() => (typeof onRefresh === "function" ? onRefresh() : null)), limit])
      .catch((error) => console.error("Pull to refresh: the refresh failed.", error))
      .then(() => true)
      .finally(() => {
        clearTimeout(timer);
        busy = false;
        line.classList.remove("is-busy");
      });
  }

  const onStart = (event) => {
    if (busy || !event.touches || event.touches.length !== 1) return;
    if (!pullAllowed(event.target, typeof window !== "undefined" ? window.scrollY : NaN)) return;
    startY = event.touches[0].clientY;
  };
  const onMove = (event) => {
    if (startY === null || !event.touches || !event.touches.length) return;
    const dy = event.touches[0].clientY - startY;
    if (dy <= 0 || (typeof window !== "undefined" && window.scrollY > 0)) {
      reset(); // an ordinary scroll up the page
      return;
    }
    show(dy / threshold);
  };
  const onEnd = () => {
    if (startY === null) return;
    const go = progress >= 1;
    reset();
    if (go) trigger();
  };

  area.addEventListener("touchstart", onStart, { passive: true });
  area.addEventListener("touchmove", onMove, { passive: true });
  area.addEventListener("touchend", onEnd, { passive: true });
  area.addEventListener("touchcancel", reset, { passive: true });

  return {
    line,
    trigger,
    destroy() {
      area.removeEventListener("touchstart", onStart);
      area.removeEventListener("touchmove", onMove);
      area.removeEventListener("touchend", onEnd);
      area.removeEventListener("touchcancel", reset);
      line.remove();
    },
  };
}
