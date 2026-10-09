// The app shell: top bar with the wordmark, inline tabs on wide screens, a status pill, the
// Menu button, the menu drawer, and the radio mini-bar that survives every view change.
// Phase 17 (#25, #32): the Game program is the first tab and the wordmark's home; setLive(true) marks the
// Live sheet while our game is under way (a dot in its tab and menu item, and a LIVE flag on narrow screens).

import { icon } from "./icons.js";
import { ours } from "../identity.js";
import { el, reducedMotion, syncPageLock, text } from "./dom.js";
import { pill } from "./pills.js";

export const VIEWS = [
  { id: "program", label: "Game program" },
  { id: "newspaper", label: "Newspaper", wide: true },
  { id: "season", label: "Season" },
  { id: "live", label: "Live sheet" },
];

const liveDot = () => el("span", { class: "live-dot", "aria-hidden": "true" });

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
      { id: "review", label: "Season in review", hint: "record, streaks, best win" }, // Phase 19
      { id: "preseason", label: "Preseason", hint: "offseason, outlook, staffs" }, // Phase 17 Part 3a
      { id: "invite", label: "Invite friends", hint: "a QR code for the Wi-Fi" }, // Phase 18.6
      { id: "board", label: "Game-day board", hint: "for a big screen" },
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
 * returns { root, main, setStatus, setCurrent, setLive, openDrawer, closeDrawer, setRadio }
 */
export function shell({ current = "program", status = { kind: "quiet", label: "Connecting" }, onNavigate, onSearch, menu = MENU } = {}) {
  let currentView = current;
  let live = false;
  let lastStatus = status && typeof status === "object" ? status : { kind: "quiet", label: "Connecting" };
  let statusCard = null;
  const statusSlot = el("div", { class: "topbar__status", role: "status" });

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
        view.id === "live" ? liveDot() : null,
      ),
    ),
  );

  const liveFlag = el(
    "a",
    { class: "live-flag", href: "#live", hidden: true, title: "Our game is live", onclick: (event) => { event.preventDefault(); navigate("live"); } },
    liveDot(),
    "LIVE",
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
    el("span", { "aria-hidden": "true", class: "search-button__icon" }, icon("search")), // Phase 16 wave 3: the sprite
    el("span", { class: "search-button__label" }, "Search"),
  );

  const topbar = el(
    "header",
    { class: "topbar" },
    el("a", { class: "wordmark", href: "#program", onclick: (e) => { e.preventDefault(); navigate("program"); } }, `${ours().name || "Kickoff"} `, el("em", {}, ours().name ? "Kickoff" : "Companion", ours().name ? el("span", { class: "wordmark__long" }, " Companion") : null)),
    tabs,
    el("div", { class: "topbar__spacer" }),
    liveFlag,
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
                item.id === "live" && live ? [" ", liveDot(), el("small", {}, "our game is live")] : null,
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

  // Phase 16 wave 3 (DS-12): the pill is a button; its card says what the state means, with Retry now and the
  // server's status page. Retry asks the page to fetch again ("kickoff:retry", answered by the app).
  const STATUS_WORDS = {
    live: "The live feed is current.",
    delayed: "The live feed is running behind your spoiler delay on purpose.",
    replay: "A replay of a finished game is running.",
    quiet: "Waiting for the page's data.",
    stale: "This page shows an older copy of its data.",
    offline: "This device could not reach the app's server.",
  };

  function closeStatusCard() {
    if (!statusCard) return;
    statusCard.remove();
    statusCard = null;
    document.removeEventListener("pointerdown", onOutside, true);
    statusSlot.querySelector(".pill--button")?.setAttribute("aria-expanded", "false");
  }

  function onOutside(event) {
    if (statusCard && !statusCard.contains(event.target) && !statusSlot.contains(event.target)) closeStatusCard();
  }

  function statusCardBody() {
    const s = lastStatus || {};
    const detail = typeof s.detail === "string" && s.detail ? s.detail : STATUS_WORDS[s.kind] || STATUS_WORDS.quiet;
    const retry = el("button", { class: "btn btn--quiet status-card__retry", type: "button", onclick: () => {
      retry.disabled = true;
      retry.textContent = "Trying";
      document.dispatchEvent(new CustomEvent("kickoff:retry"));
      setTimeout(closeStatusCard, 600);
    } }, "Retry now");
    return [
      el("b", { class: "status-card__title" }, text(s.label)),
      el("p", { class: "status-card__detail" }, detail),
      el("div", { class: "status-card__actions" }, retry, el("a", { class: "btn btn--quiet", href: "/status", target: "_blank", rel: "noopener" }, "Server status")),
    ];
  }

  function toggleStatusCard() {
    if (statusCard) {
      closeStatusCard();
      return;
    }
    statusCard = el("div", { class: "status-card", role: "dialog", "aria-label": "Data status" }, statusCardBody());
    document.body.append(statusCard);
    statusSlot.querySelector(".pill--button")?.setAttribute("aria-expanded", "true");
    document.addEventListener("pointerdown", onOutside, true);
  }

  /** "Updated 4 min ago" from the time the page's data was fetched. */
  function updatedLabel(at) {
    const seconds = Math.max(0, (Date.now() - at) / 1000);
    if (seconds < 60) return "Updated just now";
    if (seconds < 3600) return `Updated ${Math.round(seconds / 60)} min ago`;
    return `Updated ${Math.round(seconds / 3600)} h ago`;
  }

  function setStatus(next) {
    lastStatus = next && typeof next === "object" ? { ...next } : { kind: "quiet" };
    if (typeof lastStatus.updatedAt === "number" && Number.isFinite(lastStatus.updatedAt)) lastStatus.label = updatedLabel(lastStatus.updatedAt);
    const button = pill({ ...lastStatus, onClick: toggleStatusCard });
    button.setAttribute("aria-expanded", statusCard ? "true" : "false");
    statusSlot.replaceChildren(button);
    if (statusCard) statusCard.replaceChildren(...statusCardBody()); // an open card follows the page's state
  }
  setStatus(lastStatus);
  // The Updated words age with the clock between refreshes; only a changed label is redrawn.
  setInterval(() => {
    if (typeof lastStatus?.updatedAt !== "number") return;
    const label = updatedLabel(lastStatus.updatedAt);
    if (label !== lastStatus.label) setStatus(lastStatus);
  }, 30000);

  /** Mark the Live sheet while our game is under way (Phase 17 #25); false clears it. */
  function setLive(on) {
    const next = on === true;
    if (next === live) return;
    live = next;
    if (live) liveFlag.removeAttribute("hidden");
    else liveFlag.setAttribute("hidden", "");
    const tab = tabs.querySelector('.tab[data-view="live"]');
    if (tab) {
      tab.classList.toggle("tab--live", live);
      tab.setAttribute("aria-label", live ? "Live sheet, our game is live" : "Live sheet");
    }
    renderDrawer();
  }

  function setRadio(state) {
    radioSlot.replaceChildren();
    if (state) radioSlot.append(radioBar(state));
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && statusCard) closeStatusCard();
    if (event.key === "Escape" && drawer.hasAttribute("open")) closeDrawer();
  });
  if (typeof window !== "undefined") window.addEventListener("hashchange", closeStatusCard);

  renderDrawer();
  const root = el("div", { class: "shell" }, topbar, main, radioSlot, drawer);
  return { root, main, setStatus, setCurrent, setLive, openDrawer, closeDrawer, setRadio };
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
      icon(state === "playing" ? "pause" : "play"),
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
