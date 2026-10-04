// The app shell: top bar with the wordmark, inline tabs on wide screens, a status pill, the
// Menu button, the menu drawer, and the radio mini-bar that survives every view change.

import { ours } from "../identity.js";
import { el, reducedMotion, syncPageLock, text } from "./dom.js";
import { pill } from "./pills.js";

export const VIEWS = [
  { id: "newspaper", label: "Newspaper", wide: true },
  { id: "season", label: "Season" },
  { id: "program", label: "Game program" },
  { id: "live", label: "Live sheet" },
];

export const MENU = [
  { group: "Views", items: VIEWS },
  {
    group: "More",
    items: [
      { id: "leaders", label: "Leaders" },
      { id: "ratings", label: "Ratings" },
      { id: "roster", label: "Roster" },
      { id: "recruiting", label: "Recruiting" },
      { id: "radio", label: "Radio" },
      { id: "injuries", label: "Injury report" },
      { id: "archive", label: "Archive" },
      { id: "glossary", label: "Glossary" },
      { id: "settings", label: "Settings" },
      { id: "setup", label: "Device setup", href: "/setup" },
      { id: "demo", label: "Demo", href: "/demo", hint: "a made-up league" }, // public release Phase 9b
    ],
  },
];

/**
 * The menu with a "My teams" group (public release Phase 5b): the My teams page, then one entry per primary
 * team #2 to #5, each opening its team page in one tap. Without extra primaries the group holds the page only.
 */
export function menuWith(extraPrimaries = []) {
  const schools = (Array.isArray(extraPrimaries) ? extraPrimaries : []).filter((s) => typeof s === "string" && s.trim()).slice(0, 4);
  const teams = {
    group: "My teams",
    items: [
      { id: "myteams", label: "My teams", hint: "records and national ranks" },
      ...schools.map((school) => ({ id: `team:${school}`, label: school, hash: `team=${encodeURIComponent(school.trim())}` })),
    ],
  };
  return [MENU[0], teams, ...MENU.slice(1)];
}

/**
 * shell({ current, status: {kind, label}, onNavigate, menu })
 * returns { root, main, setStatus, setCurrent, openDrawer, closeDrawer, setRadio }
 */
export function shell({ current = "season", status = { kind: "quiet", label: "Connecting" }, onNavigate, onSearch, menu = MENU } = {}) {
  let currentView = current;
  const statusSlot = el("div", { class: "topbar__status" }, pill(status));

  const tabs = el(
    "nav",
    { class: "tabs", "aria-label": "Main views" },
    VIEWS.map((view) =>
      el(
        "a",
        {
          class: `tab${view.wide ? " tab--wide" : ""}`,
          href: `#${view.id}`,
          "aria-current": view.id === currentView ? "page" : null,
          dataset: { view: view.id },
          onclick: (event) => {
            event.preventDefault();
            navigate(view.id);
          },
        },
        view.label,
      ),
    ),
  );

  const menuButton = el(
    "button",
    { class: "btn menu-button", type: "button", "aria-haspopup": "dialog", "aria-expanded": "false", onclick: () => openDrawer() },
    "Menu",
  );

  // Phase 15: search any team or player; the "/" key opens it too (app.js).
  const searchButton = el(
    "button",
    { class: "btn search-button", type: "button", "aria-label": "Search teams and players", title: "Search (/)", onclick: () => { if (typeof onSearch === "function") onSearch(); } },
    el("span", { "aria-hidden": "true", class: "search-button__icon" }, "\u2315"),
    el("span", { class: "search-button__label" }, "Search"),
  );

  const topbar = el(
    "header",
    { class: "topbar" },
    el("a", { class: "wordmark", href: "#season", onclick: (e) => { e.preventDefault(); navigate("season"); } }, `${ours().name || "Kickoff"} `, el("em", {}, ours().name ? "Kickoff" : "Companion", ours().name ? el("span", { class: "wordmark__long" }, " Companion") : null)),
    tabs,
    el("div", { class: "topbar__spacer" }),
    statusSlot,
    typeof onSearch === "function" ? searchButton : null,
    menuButton,
  );

  const main = el("main", { class: "shell__main", id: "main" });
  const radioSlot = el("div", { class: "shell__radio" });

  const drawerList = el("div", {});
  const drawer = el(
    "div",
    { class: "drawer", role: "dialog", "aria-modal": "true", "aria-label": "Menu" },
    el("div", { class: "drawer__scrim", onclick: () => closeDrawer() }),
    el(
      "aside",
      { class: "drawer__panel" },
      el(
        "div",
        { class: "drawer__head" },
        el("h2", {}, "Menu"),
        el("button", { class: "btn btn--quiet icon-btn", type: "button", "aria-label": "Close menu", onclick: () => closeDrawer() }, "×"),
      ),
      drawerList,
    ),
  );

  function renderDrawer() {
    drawerList.replaceChildren();
    for (const group of menu) {
      drawerList.append(el("div", { class: "drawer__group" }, group.group));
      drawerList.append(
        el(
          "ul",
          { class: "drawer__list" },
          group.items.map((item) =>
            el(
              "li",
              {},
              el(
                "a",
                {
                  class: "drawer__item",
                  href: item.href || `#${item.hash || item.id}`,
                  "aria-current": item.id === currentView ? "page" : null,
                  onclick: (event) => {
                    if (item.hash) { // a route with an argument (a primary team's page): close the drawer and go
                      event.preventDefault();
                      closeDrawer();
                      window.location.hash = item.hash;
                      return;
                    }
                    if (item.href) return; // a real page, let the browser go there
                    event.preventDefault();
                    navigate(item.id);
                  },
                },
                item.label,
                item.hint ? el("small", {}, item.hint) : null,
              ),
            ),
          ),
        ),
      );
    }
  }

  function navigate(id) {
    setCurrent(id);
    closeDrawer();
    if (typeof onNavigate === "function") onNavigate(id);
  }

  function setCurrent(id) {
    currentView = id;
    for (const tab of tabs.querySelectorAll(".tab")) {
      if (tab.dataset.view === id) tab.setAttribute("aria-current", "page");
      else tab.removeAttribute("aria-current");
    }
    renderDrawer();
  }

  // Phase 16 (stream F): the panel slides in and out, and the page underneath does not scroll while it is open.
  let closingTimer = null;
  function openDrawer() {
    if (closingTimer) clearTimeout(closingTimer);
    closingTimer = null;
    drawer.classList.remove("is-closing");
    drawer.setAttribute("open", "");
    drawer.setAttribute("data-modal", "");
    syncPageLock();
    menuButton.setAttribute("aria-expanded", "true");
    const first = drawer.querySelector(".drawer__item");
    if (first) first.focus();
  }

  function closeDrawer() {
    const wasOpen = drawer.hasAttribute("open");
    drawer.removeAttribute("open");
    drawer.removeAttribute("data-modal");
    syncPageLock();
    menuButton.setAttribute("aria-expanded", "false");
    if (!wasOpen || reducedMotion() || typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    drawer.classList.add("is-closing"); // keeps it drawn while the panel slides out
    if (closingTimer) clearTimeout(closingTimer);
    closingTimer = setTimeout(() => {
      closingTimer = null;
      drawer.classList.remove("is-closing");
    }, 220);
  }

  function setStatus(next) {
    statusSlot.replaceChildren(pill(next));
  }

  function setRadio(state) {
    radioSlot.replaceChildren();
    if (state) radioSlot.append(radioBar(state));
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && drawer.hasAttribute("open")) closeDrawer();
  });

  renderDrawer();
  const root = el("div", { class: "shell" }, topbar, main, radioSlot, drawer);
  return { root, main, setStatus, setCurrent, openDrawer, closeDrawer, setRadio };
}

/** The pinned mini-bar shown while the radio plays: station, state, play or pause, close. */
export function radioBar({ station, state = "playing", detail, onToggle, onClose, note }) {
  const stateText = { playing: "Playing", paused: "Paused", connecting: "Connecting", error: "Could not play" }[state] || text(state);
  return el(
    "div",
    { class: "radio-bar", role: "region", "aria-label": "Radio" },
    el("span", { class: "radio-bar__station" }, text(station)),
    el("span", { class: "radio-bar__state" }, detail ? `${stateText} · ${detail}` : stateText),
    el("span", { class: "radio-bar__spacer" }),
    note ? el("span", { class: "radio-bar__note" }, note) : null,
    el(
      "button",
      { class: "btn icon-btn", type: "button", "aria-label": state === "playing" ? "Pause" : "Play", onclick: onToggle },
      state === "playing" ? "‖" : "▶",
    ),
    el("button", { class: "btn btn--quiet icon-btn", type: "button", "aria-label": "Close radio", onclick: onClose }, "×"),
  );
}

/** The radio panel opened from the menu: ordered sources, one tap to switch. */
export function radioPanel({ sources = [], currentId, onSelect, note }) {
  return el(
    "div",
    { class: "radio-panel" },
    note ? el("p", { class: "note" }, note) : null,
    sources.length === 0 ? el("p", { class: "note" }, "No radio station yet. Add one in Settings.") : null,
    sources.map((source) =>
      el(
        "div",
        { class: "radio-source", "aria-current": source.id === currentId ? "true" : null },
        el(
          "div",
          {},
          el("div", { class: "radio-source__name" }, text(source.name)),
          el("div", { class: "radio-source__kind" }, source.kind === "embed" ? "Plays inside the app" : "Opens in a new tab"),
        ),
        el(
          "button",
          { class: `btn${source.id === currentId ? " btn--primary" : ""}`, type: "button", onclick: () => onSelect && onSelect(source) },
          source.id === currentId ? "Playing" : source.kind === "embed" ? "Play" : "Open",
        ),
      ),
    ),
  );
}
