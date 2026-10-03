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

import { ageText, append, el, frag, recall, reducedMotion, remember, teamLink, text } from "./dom.js";

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
        onclick: () => setCollapsed(section.dataset.collapsed !== "true"),
      })
    : null;

  function setCollapsed(value) {
    section.dataset.collapsed = value ? "true" : "false";
    if (toggle) {
      toggle.setAttribute("aria-expanded", value ? "false" : "true");
      toggle.setAttribute("aria-label", `${value ? "Expand" : "Collapse"} ${title}`);
    }
    if (storageKey) remember(storageKey, value);
  }

  const head = el(
    "div",
    { class: "band__head" },
    el("h2", { class: "band__title", id: id ? `${id}-title` : null }, title),
    summary ? el("span", { class: "band__summary" }, summary) : null,
    tools ? el("div", { class: "band__tools" }, tools) : null,
    toggle,
  );

  const bodyEl = el("div", { class: "band__body" });
  switch (state.status) {
    case "loading":
      append(bodyEl, [skeleton ? skeleton() : skeletonRows()]);
      break;
    case "empty":
      append(bodyEl, [note(state.message || emptyText)]);
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
  return true;
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
