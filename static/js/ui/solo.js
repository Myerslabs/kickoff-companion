// One band of a page by itself (owner 2026-10-28: "I want to make sure that each band has its own flyout, and page as well
// as grouped together somewhere"; the menu's lists of ui/band-catalog.js open them). The page's own view mounts as it always
// does, from its own answer, so the band is the same table with the same sorting, links and refreshes; the holder shows that
// one band, unfolded, across the whole width, and keeps it so whatever the view redraws. A band the page does not draw just
// now (a table that waits for the final, a page that failed) says so in a line with the way to the whole page.
//
//   soloMount({ view, container, band, label, pageHref, flyout })  -> { setBand(band, label), unmount() }
//       view: a page view ({ mount, unmount }); band: { id } (the band's own id) or { select } (a selector, the first match:
//       a band whose id carries a game or a team); label: what the line says while it loads or is missing; pageHref: the
//       whole page ("#season"); flyout: true inside a wide flyout (the band's own title goes, the flyout's head says it)
//   bandNode(root, band)  the band's element under root, or null
//
// The holder marks the band "solo-target", each element above it "solo-chain" and everything beside them "solo-off"
// (components.css). Only the holder's children are watched, never its attributes, so marking never wakes the watch.

import { el, text } from "./dom.js";
import { band as bandBox } from "./states.js";

const SETTLE_MS = 8000; // a band not drawn this long after the mount (or after the page's first draw) is missing
const POLL_MS = 250; // without MutationObserver (the tests' fake DOM) the holder looks again on a timer
const MARKS = ["solo-target", "solo-chain", "solo-off"];
const LOADING = '[aria-busy="true"], .loading-sun, .skel'; // a page still drawing its loading state

function safeId(id) {
  return typeof id === "string" && /^[A-Za-z][\w-]*$/.test(id) ? id : null;
}

export function bandNode(root, which) {
  if (!root || typeof root.querySelector !== "function" || !which || typeof which !== "object") return null;
  const id = safeId(which.id);
  try {
    if (id) return root.querySelector(`[id="${id}"]`);
    if (typeof which.select === "string" && which.select) return root.querySelector(which.select);
  } catch (error) {
    console.error("A band's selector could not be read.", error);
  }
  return null;
}

function clearMarks(holder) {
  for (const mark of MARKS) for (const node of [...holder.querySelectorAll(`.${mark}`)]) node.classList.remove(mark);
}

const up = (node) => node.parentElement || node.parentNode || null;

function markChain(holder, target) {
  target.classList.add("solo-target");
  if (target.getAttribute("data-collapsed") === "true") target.setAttribute("data-collapsed", "false"); // always unfolded, never saved as a fold
  for (let node = target; node && node !== holder; node = up(node)) {
    if (node !== target) node.classList.add("solo-chain");
    const parent = up(node);
    if (!parent || !parent.children) break;
    for (const sibling of [...parent.children]) if (sibling !== node && !sibling.classList.contains("solo-chain")) sibling.classList.add("solo-off");
  }
}

export function soloMount({ view, container, band, label = "This table", pageHref = null, flyout = false } = {}) {
  if (!view || typeof view.mount !== "function" || !container) return { refresh() {}, setBand() {}, unmount() {} };
  let which = band;
  let words = label;
  let settled = false;
  let shownFor = null; // the band marked last
  let mode = null;
  const status = el("div", { class: "solo__status" });
  const holder = el("div", { class: `solo${flyout ? " solo--flyout" : ""}`, "data-solo": "waiting" });
  container.replaceChildren(status, holder);

  const whole = () => (pageHref ? el("a", { class: "btn", href: pageHref }, "Open the whole page") : null);
  function setMode(next) {
    if (mode === next) return;
    mode = next;
    holder.setAttribute("data-solo", next);
    if (next === "waiting") status.replaceChildren(bandBox({ title: text(words), collapsible: false, state: { status: "loading" } }));
    else if (next === "missing") status.replaceChildren(...[bandBox({ title: text(words), collapsible: false, state: { status: "empty", message: `Nothing to show in ${text(words)} right now: the page draws it once its data is in.` } }), pageHref ? el("p", { class: "solo__whole" }, whole()) : null].filter(Boolean)); // no page link: nothing appended (replaceChildren(null) would print "null")
    else status.replaceChildren();
  }

  function apply() {
    const target = bandNode(holder, which);
    if (target) {
      settled = true;
      clearMarks(holder); // marked again on every change: a redraw may add elements beside the band
      markChain(holder, target);
      shownFor = target;
      setMode("shown");
      return;
    }
    if (shownFor) {
      clearMarks(holder);
      shownFor = null;
    }
    // while the page still shows its loading state the band may yet come; the page's own error (it could not load) shows
    // as the page draws it, with its Try now
    const done = settled && !holder.querySelector(LOADING);
    if (done && holder.querySelector(".state-block--error")) setMode("error");
    else setMode(done ? "missing" : "waiting");
  }

  let queued = false;
  let stopped = false;
  const schedule = () => {
    if (queued || stopped) return;
    queued = true;
    Promise.resolve().then(() => {
      queued = false;
      if (!stopped) apply();
    });
  };
  const watcher = typeof MutationObserver === "function" ? new MutationObserver(schedule) : null;
  if (watcher) watcher.observe(holder, { childList: true, subtree: true });
  const poll = watcher ? null : setInterval(apply, POLL_MS);
  const settleTimer = setTimeout(() => {
    settled = true;
    apply();
  }, SETTLE_MS);
  const onRendered = () => {
    // a page drew from its answer: what it holds now is what it has (another page's draw, the one under a flyout, may come
    // first: apply() waits on while the holder still shows its loading state)
    setTimeout(() => {
      settled = true;
      apply();
    }, 0);
  };
  document.addEventListener("kickoff:rendered", onRendered);
  setMode("waiting");
  try {
    view.mount(holder);
  } catch (error) {
    console.error(`${text(words)}: the page could not be mounted.`, error);
  }
  apply();

  return {
    refresh() {
      return typeof view.refresh === "function" ? view.refresh() : null;
    },
    setBand(next, nextLabel) {
      which = next;
      if (nextLabel) words = nextLabel;
      shownFor = null;
      mode = null;
      apply();
    },
    unmount() {
      stopped = true;
      watcher?.disconnect();
      if (poll) clearInterval(poll);
      clearTimeout(settleTimer);
      document.removeEventListener("kickoff:rendered", onRendered);
      try {
        view.unmount?.();
      } catch (error) {
        console.error(`${text(words)}: the page did not unmount cleanly.`, error);
      }
    },
  };
}
