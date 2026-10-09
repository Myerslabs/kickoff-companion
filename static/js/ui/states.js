// The four states every panel needs: loading, empty, stale, error. Plus the band, which is
// the section container of the call sheet: a color-coded head, a body, and a state footer.
// On narrow screens bands collapse to a summary line and remember their state on the device.
//
// Phase 16 (stream F) frozen API, added beside the band (its fold logic is unchanged):
//   band({ ..., bare: true })               no head at all, for a single panel inside a side sheet whose title
//                                           already names it (the title stays as the section's aria-label).
//   subhead(title, { team, side, level })   one sub-heading style inside bands: <h3 class="subhead">; with team
//                                           the title is that team's link; side "us" or "them" adds a team tick.
//   stateBlock({ lead, detail, action, kind })  a designed empty or error block: lead in chalk, detail in fog,
//                                           action { label, onClick } (or a node) as a quiet button under them.
//   backRow({ label, fallback })            a quiet "‹ Back" page row above the first band of a sub-route; goes
//                                           back when the app came here itself (history.state.depth > 0, set by
//                                           the router), else to `fallback` (default "#season"), never out of the app.
//   jumpList(root, { label })               'On this page' (UX-11): a page-level list of root's bands (never on a
//                                           band head); choosing one unfolds it if folded and scrolls to it.
//   revealBand(section)                     unfold a band if folded, then scroll it into view.
//   loadingSun({ lead, detail })            Phase 17 #1: the page-level loading line, a small sun that turns while a
//                                           page gathers its data ("Getting the latest"); still under reduced motion.
//   sectionChips(root, { label })           Phase 17 #5 (owner pick B): a row of section chips pinned under the top
//                                           bar, one per band of root; a tap unfolds the band and scrolls to it, and
//                                           the section on screen is outlined. Rebuilt as bands come and go.

import { ageText, append, el, frag, recall, reducedMotion, remember, teamLink, text } from "./dom.js";
import { announcer, isBlurb } from "./announcer.js";
import { icon } from "./icons.js";

export function skeletonRows(count = 4, kind = "row") {
  return frag(Array.from({ length: count }, () => el("div", { class: `skel skel--${kind}` })));
}

export function note(message, { kind = "empty", lead } = {}) {
  return el("p", { class: `note${kind === "error" ? " note--error" : ""}` }, lead ? el("strong", {}, `${lead} `) : null, message);
}

function stateFoot(state) {
  if (!state) return null;
  if (state.status === "stale") {
    const age = ageText(state.ageSeconds);
    const why = state.message ? ` ${state.message}` : " Retrying.";
    return el("div", { class: "band__foot band__foot--stale" }, `Updated ${age}.${why}`);
  }
  if (state.status === "ready" && state.updatedText) {
    return el("div", { class: "band__foot" }, state.updatedText);
  }
  return null;
}

/**
 * band({ id, title, kind: "us"|"them"|"neutral", area, collapsible, collapsed, foldable, summary, tools,
 *        state: { status, ageSeconds, message, updatedText }, body(), skeleton(), emptyText })
 * collapsible: folds on narrow screens (the call-sheet bands). foldable: folds on every width, with the
 * toggle always shown, for the long panels the owner asked to be expandable (2026-09-23).
 */
const FOLD_MS = 220;

export function band(props) {
  const {
    id,
    title,
    kind = "neutral",
    area,
    collapsible = true,
    foldable = false,
    summary,
    tools,
    state = { status: "ready" },
    body,
    skeleton,
    emptyText = "Nothing here yet.",
    errorLead = "Could not load this.",
    bare = false,
  } = props;
  const storageKey = id && !bare ? `band:${id}` : null;
  const collapsed = storageKey ? recall(storageKey, Boolean(props.collapsed)) : Boolean(props.collapsed);

  const folds = !bare && (collapsible || foldable);
  const section = el("section", {
    id: id || null,
    class: `band band--${kind}${bare ? " band--bare" : ""}${folds && collapsible ? " band--collapsible" : ""}${folds && foldable ? " band--foldable" : ""}${area ? ` area-${area}` : ""}`,
    "data-collapsed": folds && collapsed ? "true" : "false",
    "aria-labelledby": id && !bare ? `${id}-title` : null,
    "aria-label": bare ? text(title) : null,
  });

  const toggle = folds
    ? el("button", {
        class: "btn btn--quiet icon-btn band__toggle",
        type: "button",
        "aria-expanded": collapsed ? "false" : "true",
        "aria-label": `${collapsed ? "Expand" : "Collapse"} ${title}`,
        onclick: (event) => {
          event.stopPropagation(); // the head's own tap handler would fold it twice
          setCollapsed(section.dataset.collapsed !== "true", { animate: true });
        },
      }, icon("chevron-down")) // Phase 16 wave 3 (owner pick 2B): a chevron instead of the minus and plus
    : null;

  /** Fold or unfold. With motion allowed and `animate`, the body slides to or from its height (Phase 16 wave 3, 2B). */
  function setCollapsed(value, { animate = false } = {}) {
    const apply = () => {
      section.dataset.collapsed = value ? "true" : "false";
      if (toggle) {
        toggle.setAttribute("aria-expanded", value ? "false" : "true");
        toggle.setAttribute("aria-label", `${value ? "Expand" : "Collapse"} ${title}`);
      }
      if (storageKey) remember(storageKey, value);
    };
    const body = [...(section.children || [])].find((n) => n.classList?.contains("band__body")) || null;
    if (!animate || reducedMotion() || !body || typeof body.getBoundingClientRect !== "function" || typeof requestAnimationFrame !== "function") {
      apply();
      return;
    }
    const slide = (from, to, after) => {
      body.style.overflow = "hidden";
      body.style.height = `${from}px`;
      void body.offsetHeight; // the starting height takes hold before the change
      body.style.transition = `height ${FOLD_MS}ms ease`;
      body.style.height = `${to}px`;
      setTimeout(() => {
        body.style.transition = "";
        body.style.height = "";
        body.style.overflow = "";
        if (after) after();
      }, FOLD_MS + 20);
    };
    if (value) {
      slide(body.getBoundingClientRect().height, 0, apply);
    } else {
      apply();
      slide(0, body.scrollHeight, null);
    }
  }

  // Phase 16 wave 3 (owner pick 2B): a tap anywhere on the head folds it, except on what has its own job there (a
  // link, a button, a stat hint, the band's tools) and the tap that closes an open hint card.
  let hintWasOpen = false;
  const onHeadDown = () => {
    hintWasOpen = Boolean(typeof document !== "undefined" && document.querySelector?.(".hint-pop"));
  };
  const onHeadTap = (event) => {
    if (!folds || !toggle) return;
    const target = event.target;
    if (target && typeof target.closest === "function" && target.closest("a, button, input, select, textarea, [data-hint], .band__tools")) return;
    if (hintWasOpen) {
      hintWasOpen = false;
      return;
    }
    if (typeof getComputedStyle === "function" && getComputedStyle(toggle).display === "none") return; // a band that only folds on narrow screens
    setCollapsed(section.dataset.collapsed !== "true", { animate: true });
  };

  const head = el(
    "div",
    { class: "band__head", onclick: onHeadTap, onpointerdown: onHeadDown },
    el("h2", { class: "band__title", id: id ? `${id}-title` : null }, title),
    summary ? el("span", { class: "band__summary" }, isBlurb(summary) ? announcer(`${id || text(title)}|${summary}`) : null, summary) : null, // Phase 17 #15
    tools ? el("div", { class: "band__tools" }, tools) : null,
    toggle,
  );

  const bodyEl = el("div", { class: "band__body" });
  switch (state.status) {
    case "loading":
      append(bodyEl, [skeleton ? skeleton() : skeletonRows()]);
      break;
    case "empty":
      append(bodyEl, [note(state.message || emptyText), state.action && typeof state.action.href === "string" && state.action.href.startsWith("#") ? el("a", { class: "btn btn--quiet state-block__action", href: state.action.href }, text(state.action.label || "Open")) : null]);
      break;
    case "error":
      append(bodyEl, [note(state.message || "The last request failed. The app keeps retrying.", { kind: "error", lead: errorLead })]);
      break;
    default:
      append(bodyEl, [body ? body() : null]);
  }

  append(section, [bare ? null : head, bodyEl, stateFoot(state)]);
  section.setCollapsed = setCollapsed;
  return section;
}

/** One sub-heading style inside bands (DS-14). A team title is that team's link (owner rule: every team name links). */
export function subhead(title, { team, side, level = 3 } = {}) {
  const tag = level === 4 ? "h4" : "h3";
  const tick = side === "us" || side === "them" ? ` subhead--${side}` : "";
  const school = typeof team === "string" && team.trim() ? team.trim() : null;
  return el(tag, { class: `subhead${tick}` }, school ? teamLink(school, text(title ?? school)) : text(title));
}

/** A designed empty or error block (DS-13): what is missing, when it will appear or what the app is doing. */
export function stateBlock({ lead, detail, action, kind = "empty" } = {}) {
  const error = kind === "error";
  const leadText = typeof lead === "string" && lead.trim() ? lead.trim() : error ? "Could not load this." : "Nothing here yet.";
  let button = null;
  if (action && typeof Node !== "undefined" && action instanceof Node) button = action;
  else if (action && typeof action === "object" && typeof action.onClick === "function") {
    button = el("button", { class: "btn btn--quiet state-block__action", type: "button", onclick: (event) => action.onClick(event) }, text(action.label || (error ? "Try now" : "Show")));
  }
  return el(
    "div",
    { class: `state-block${error ? " state-block--error" : ""}`, role: error ? "alert" : null },
    el("p", { class: "state-block__lead" }, leadText),
    typeof detail === "string" && detail.trim() ? el("p", { class: "state-block__detail" }, detail.trim()) : null,
    button,
  );
}

function hashOf(fallback) {
  return `#${String(fallback || "season").replace(/^#/, "")}`;
}

/** A quiet Back row above the first band of a sub-route (DS-03). A page element, never band-head chrome. */
export function backRow({ label = "Back", fallback = "#season" } = {}) {
  const target = hashOf(fallback);
  const go = (event) => {
    event.preventDefault();
    let inApp = false;
    try {
      const depth = typeof history !== "undefined" ? history.state?.depth : null; // the router numbers its own entries
      inApp = typeof depth === "number" && depth > 0;
    } catch {
      inApp = false;
    }
    if (inApp) history.back();
    else window.location.hash = target;
  };
  return el("nav", { class: "back-row", "aria-label": "Back" }, el("a", { class: "back-row__link", href: target, onclick: go }, `‹ ${text(label)}`));
}

function bandsIn(root) {
  if (!root || typeof root.querySelectorAll !== "function") return [];
  return [...root.querySelectorAll("section.band")]
    .map((section) => ({ section, id: section.getAttribute("id"), title: (section.querySelector(".band__title")?.textContent || section.getAttribute("aria-label") || "").trim() }))
    .filter((b) => b.id && b.title);
}

/** Scroll to a band, unfolding it first when it is folded. */
export function revealBand(section) {
  if (!section) return false;
  const folded = (section.dataset?.collapsed ?? section.getAttribute?.("data-collapsed")) === "true";
  if (folded && typeof section.setCollapsed === "function") section.setCollapsed(false);
  if (typeof section.scrollIntoView === "function") section.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
  flashBand(section);
  return true;
}

export const FLASH_MS = 1600;

/**
 * Phase 17 #39 (owner 2026-10-07: a section chip "should highlight the column on the page, and flash every time
 * you press it"): the band gets an outline that pulses, restarted on every press. With reduced motion it is a
 * steady outline for the same time.
 */
export function flashBand(section) {
  if (!section || !section.classList) return false;
  section.classList.remove("band--flash");
  void section.offsetWidth; // restart the animation when the same band is pressed again
  section.classList.add("band--flash");
  clearTimeout(section._flashTimer);
  section._flashTimer = setTimeout(() => section.classList.remove("band--flash"), FLASH_MS);
  return true;
}

const SUN_RAYS = "M28 4v7M28 45v7M4 28h7M45 28h7M11 11l5 5M40 40l5 5M11 45l5-5M40 16l5-5";

/** The page-level loading line: an animated sun, "Getting the latest", and what is coming (Phase 17 #1). */
export function loadingSun({ lead = "Getting the latest", detail = null } = {}) {
  const NS = "http://www.w3.org/2000/svg";
  let art = null;
  if (typeof document !== "undefined" && typeof document.createElementNS === "function") {
    try {
      const svg = document.createElementNS(NS, "svg");
      svg.setAttribute("viewBox", "0 0 56 56");
      svg.setAttribute("class", "loading-sun__art");
      svg.setAttribute("aria-hidden", "true");
      const glow = document.createElementNS(NS, "circle");
      for (const [k, v] of [["class", "loading-sun__glow"], ["cx", "28"], ["cy", "28"], ["r", "14"]]) glow.setAttribute(k, v);
      const rays = document.createElementNS(NS, "path");
      for (const [k, v] of [["class", "loading-sun__rays"], ["d", SUN_RAYS]]) rays.setAttribute(k, v);
      const core = document.createElementNS(NS, "circle");
      for (const [k, v] of [["class", "loading-sun__core"], ["cx", "28"], ["cy", "28"], ["r", "10"]]) core.setAttribute(k, v);
      svg.append(glow, rays, core);
      art = svg;
    } catch {
      art = null; // no SVG support (tests): the words alone
    }
  }
  return el(
    "div",
    { class: "loading-sun", role: "status", "aria-live": "polite" },
    art,
    el("div", { class: "loading-sun__words" }, el("p", { class: "loading-sun__lead" }, text(lead)), typeof detail === "string" && detail.trim() ? el("p", { class: "loading-sun__detail" }, detail.trim()) : null),
  );
}

/** Short chip names for long band titles ("Bluegrass Bottoms tendencies" -> "Tendencies"). */
function chipName(title) {
  const t = text(title);
  const trimmed = t.replace(/^.+'s opponent$/i, "Opponent").replace(/^.+ tendencies$/i, "Tendencies").replace(/^.+ players to watch$/i, "Players to watch");
  return trimmed.length > 22 ? `${trimmed.slice(0, 21)}…` : trimmed;
}

export function sectionChips(root, { label = "Sections on this page" } = {}) {
  const row = el("div", { class: "chips-row__list" });
  const nav = el("nav", { class: "chips-row", "aria-label": text(label) }, row); // placed before the page, not in it
  let current = null;
  let seen = "";
  const mark = (id) => {
    if (id === current) return;
    current = id;
    for (const chip of row.querySelectorAll(".chips-row__chip")) {
      const on = chip.dataset.band === id;
      chip.classList.toggle("is-current", on);
      if (on) chip.setAttribute("aria-current", "location");
      else chip.removeAttribute("aria-current");
    }
    const on = row.querySelector(".chips-row__chip.is-current");
    if (on && typeof on.scrollIntoView === "function" && typeof row.scrollTo === "function") {
      row.scrollTo({ left: Math.max(0, on.offsetLeft - 24), behavior: reducedMotion() ? "auto" : "smooth" });
    }
  };
  const build = () => {
    const bands = bandsIn(root);
    const key = bands.map((b) => `${b.id}:${b.title}`).join("|");
    if (key === seen) return;
    seen = key;
    row.replaceChildren(
      ...bands.map((b) =>
        el("a", {
          class: "chips-row__chip",
          href: `#${b.id}`,
          dataset: { band: b.id },
          title: b.title,
          onclick: (event) => {
            event.preventDefault(); // a band id is not a route: scroll there, never navigate
            revealBand(b.section);
            mark(b.id);
          },
        }, chipName(b.title)),
      ),
    );
    current = null;
  };
  // the section on screen: the last band whose top has passed the pinned bars
  const onScroll = () => {
    const line = (parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--topbar")) || 56) + 60;
    let id = null;
    for (const b of bandsIn(root)) if (b.section.getBoundingClientRect().top <= line) id = b.id;
    if (id) mark(id);
  };
  build();
  if (typeof MutationObserver === "function") new MutationObserver(build).observe(root, { childList: true });
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") window.addEventListener("scroll", onScroll, { passive: true });
  nav.stop = () => {
    if (typeof window !== "undefined" && typeof window.removeEventListener === "function") window.removeEventListener("scroll", onScroll);
  };
  nav.refresh = build;
  return nav;
}

/** 'On this page' (UX-11): a page-level jump list of root's bands, built when opened so it matches the page. */
export function jumpList(root, { label = "On this page" } = {}) {
  const list = el("ul", { class: "jump__list" });
  const panel = el("div", { class: "jump__panel", hidden: true }, list);
  const button = el("button", { class: "btn btn--quiet jump__button", type: "button", "aria-expanded": "false" }, text(label));
  const close = () => {
    panel.setAttribute("hidden", "");
    button.setAttribute("aria-expanded", "false");
  };
  button.addEventListener("click", () => {
    if (!panel.hasAttribute("hidden")) {
      close();
      return;
    }
    const bands = bandsIn(root);
    const items = bands.map((b) =>
      el("li", {}, el("a", {
        class: "jump__item",
        href: `#${b.id}`,
        onclick: (event) => {
          event.preventDefault(); // a band id is not a route: scroll there, never navigate
          close();
          revealBand(b.section);
        },
      }, b.title)),
    );
    list.replaceChildren(...(items.length ? items : [el("li", { class: "jump__empty" }, "No sections on this page yet.")]));
    panel.removeAttribute("hidden");
    button.setAttribute("aria-expanded", "true");
  });
  return el("nav", { class: "jump", "aria-label": text(label) }, button, panel);
}

/** A control that expands or collapses every collapsible band inside `container`. */
export function expandAllControl(container) {
  const button = el("button", { class: "btn btn--quiet", type: "button" }, "Expand all");
  let expanded = false;
  const refresh = () => {
    const bands = [...container.querySelectorAll(".band--collapsible")];
    expanded = bands.length > 0 && bands.every((b) => b.dataset.collapsed !== "true");
    button.textContent = expanded ? "Collapse all" : "Expand all";
  };
  button.addEventListener("click", () => {
    const bands = [...container.querySelectorAll(".band--collapsible")];
    for (const b of bands) if (typeof b.setCollapsed === "function") b.setCollapsed(expanded);
    refresh();
  });
  container.addEventListener("click", (event) => {
    if (event.target.closest(".band__toggle")) queueMicrotask(refresh);
  });
  refresh();
  return el("div", { class: "expand-all" }, button);
}

/** A generic panel (not a band) for the program and season pages, same four states. */
export function panel({ title, state = { status: "ready" }, body, skeleton, emptyText = "Nothing here yet.", className = "" }) {
  return band({ title, kind: "neutral", collapsible: false, state, body, skeleton, emptyText, area: null, id: null, ...(className ? { className } : {}) });
}

export { text };
