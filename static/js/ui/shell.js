// The app shell: top bar with the wordmark, inline tabs on wide screens, a status pill, the
// Menu button, the menu drawer, and the radio mini-bar that survives every view change.
// Phase 17 (#25, #32): the Game program is the first tab and the wordmark's home; setLive(true) marks the
// Live sheet while our game is under way (a dot in its tab and menu item, and a LIVE flag on narrow screens).
// Item 6 (owner 2026-10-11): the top bar stays above the side sheets and the player card from 700 px up, so the Menu,
// Search and the tabs work with a sheet open; the Menu closes every open layer, then opens the drawer. The drawer takes a
// history entry like a sheet (Back closes it and stays on the page), closes on any page change, keeps Tab inside itself
// and hands focus back to the Menu button. One Escape closes one layer: the status card, else the drawer when no sheet or
// card is open over it. setNotice() puts a dot on the status pill and a list in its card ("Not loaded yet"), and the
// .page-notes slot above the page holds the notes that once opened by themselves as sheets (ui/page-notes.js).

import { icon } from "./icons.js";
import { ours } from "../identity.js";
import { el, reducedMotion, replaceWith, syncPageLock, text } from "./dom.js";
import { closeLayers, goTo, holdLayer, placeLayers } from "./layers.js";
import { pill } from "./pills.js";

// The owner's order (2026-10-10): Newspaper, Pre-Game Program, In Game, Season; then Top 25 (item 11, owner 2026-10-13:
// "ON the top menu, right beside season"). The addresses stay #program and #live, so saved links and home-screen icons
// keep working; only the names changed. Every view is in the menu's Views too (owner 2026-10-13: "everything should
// always be accessible from the menu"; a phone has no tabs).
export const VIEWS = [
  { id: "newspaper", label: "Newspaper", wide: true },
  { id: "program", label: "Pre-Game Program" },
  { id: "live", label: "In Game" },
  { id: "season", label: "Season" },
  { id: "top25", label: "Top 25" },
];

const liveDot = () => el("span", { class: "live-dot", "aria-hidden": "true" });

// The menu (owner 2026-10-10): the views with the Preseason Magazine; My Teams (the teams the app keeps loaded) with our
// team's Injury Report, Roster and Recruiting under it; National; then Invite friends, the Setup page (the demo, the
// archive, the season in review, the radio), the Glossary and Settings (First time setup lives there). The game-day board
// is a button on the In Game sheet, not a menu item; the other primary teams are reached from the My Teams page.
export const MENU = [
  { group: "Views", items: [...VIEWS, { id: "preseason", label: "Preseason Magazine", hint: "offseason, outlook, staffs" }] },
  {
    group: "My Teams",
    items: [
      { id: "myteams", label: "My Teams", hint: "the teams the app keeps loaded" },
      { id: "injuries", label: "Injury Report" },
      { id: "prompts", label: "Load data", hint: "copy, paste or run the prompts" }, // the Prompts phase (2026-10-13): every dead end leads here; "Load data" since 2026-10-16 (owner), the address stays #prompts
      { id: "roster", label: "Roster" },
      { id: "recruiting", label: "Recruiting" },
    ],
  },
  { group: "National", items: [{ id: "leaders", label: "Leaders" }, { id: "ratings", label: "Advanced Team Ratings" }] },
  {
    group: "App",
    items: [
      { id: "invite", label: "Invite friends", hint: "a QR code for the Wi-Fi" }, // Phase 18.6
      { id: "setup", label: "Setup", hint: "demo, archive, season in review, radio" },
      { id: "glossary", label: "Glossary" },
      { id: "settings", label: "Settings" },
    ],
  },
];

/**
 * shell({ current, status: {kind, label}, onNavigate, menu, inlineDrawer })
 * returns { root, main, notes, setStatus, setNotice, setCurrent, setLive, openDrawer, closeDrawer, setRadio }
 * inlineDrawer: the styleguide's sample, drawn open inside the page: no history entry, no Tab trap, no page lock.
 * setNotice({ dot, title, body(), onOpen }) or null: a dot on the status pill while `dot`, and the card lists body()
 * under its title; opening the card calls onOpen (it clears the dot).
 */
export function shell({ current = "program", status = { kind: "quiet", label: "Connecting" }, onNavigate, onSearch, menu = MENU, inlineDrawer = false } = {}) {
  let currentView = current;
  let live = false;
  let lastStatus = status && typeof status === "object" ? status : { kind: "quiet", label: "Connecting" };
  let statusCard = null;
  let notice = null;
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

  // item 6: with a sheet or the card open (the top bar stays above them from 700 px up) a tap closes them first
  const menuButton = el(
    "button",
    {
      class: "btn menu-button",
      type: "button",
      "aria-haspopup": "dialog",
      "aria-expanded": "false",
      onclick: () => {
        if (drawer.hasAttribute("open")) {
          closeDrawer();
          return;
        }
        closeStatusCard();
        if (!inlineDrawer) closeLayers();
        openDrawer();
      },
    },
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

  const notes = el("div", { class: "page-notes", hidden: true }); // item 6, step C: notes above the page (ui/page-notes.js)
  const main = el("main", { class: "shell__main", id: "main" });
  const radioSlot = el("div", { class: "shell__radio" });

  const drawerList = el("div", {});
  const panel = el(
    "aside",
    { class: "drawer__panel" },
    el(
      "div",
      { class: "drawer__head" },
      el("h2", {}, "Menu"),
      el("button", { class: "btn btn--quiet icon-btn", type: "button", "aria-label": "Close menu", onclick: () => closeDrawer() }, "×"),
    ),
    drawerList,
  );
  const drawer = el(
    "div",
    { class: "drawer", role: "dialog", "aria-modal": inlineDrawer ? null : "true", "aria-label": "Menu" },
    el("div", { class: "drawer__scrim", onclick: () => closeDrawer() }),
    panel,
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
                      closeDrawer("route");
                      goTo(item.hash); // in the drawer's own history entry
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
    closeDrawer("route"); // the new page takes the drawer's history entry (app.js onNavigate, ui/layers.js goTo); first,
    setCurrent(id); //       so focus goes back to the Menu before the menu's items are redrawn
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
  // Item 6: the open drawer holds one history entry (ui/layers.js); closeDrawer(reason) is "self" (its ×, the scrim,
  // Escape: the entry goes back out), "route" (a page change takes it) or "history" (Back already took it).
  let closingTimer = null;
  let releaseDrawer = null;
  function openDrawer() {
    if (closingTimer) clearTimeout(closingTimer);
    closingTimer = null;
    drawer.classList.remove("is-closing");
    drawer.setAttribute("open", "");
    if (!inlineDrawer) {
      drawer.setAttribute("data-modal", "");
      syncPageLock();
      if (!releaseDrawer) releaseDrawer = holdLayer((why) => closeDrawer(why));
    }
    menuButton.setAttribute("aria-expanded", "true");
    const first = drawer.querySelector(".drawer__item");
    if (first && !inlineDrawer) first.focus();
  }

  function closeDrawer(reason) {
    const wasOpen = drawer.hasAttribute("open");
    const at = document.activeElement;
    const focusInside = wasOpen && Boolean(at) && drawer.contains(at);
    drawer.removeAttribute("open");
    drawer.removeAttribute("data-modal");
    syncPageLock();
    menuButton.setAttribute("aria-expanded", "false");
    const release = releaseDrawer;
    releaseDrawer = null;
    if (release) release(typeof reason === "string" ? reason : "self"); // a click hands in an event: by hand
    if (focusInside && typeof menuButton.focus === "function") menuButton.focus(); // never left on a hidden item
    if (!wasOpen || reducedMotion() || typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    drawer.classList.add("is-closing"); // keeps it drawn while the panel slides out
    if (closingTimer) clearTimeout(closingTimer);
    closingTimer = setTimeout(() => {
      closingTimer = null;
      drawer.classList.remove("is-closing");
    }, 220);
  }

  /** Tab and Shift+Tab stay inside the open drawer: its × through its last item, round and round. */
  function trapTab(event) {
    if (event.key !== "Tab" || inlineDrawer || !drawer.hasAttribute("open")) return;
    const stops = [...panel.querySelectorAll("a, button")].filter((node) => !node.disabled && node.getAttribute("tabindex") !== "-1" && !node.hasAttribute("hidden"));
    if (!stops.length) return;
    const first = stops[0];
    const last = stops[stops.length - 1];
    const at = document.activeElement;
    const inside = Boolean(at) && panel.contains(at);
    if (event.shiftKey ? !inside || at === first : !inside || at === last) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    }
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

  /** The notice's list for the card (item 6, step C: "Not loaded yet"), or null; a list that will not draw is left out. */
  function noticeBlock() {
    if (!notice || typeof notice.body !== "function") return null;
    let body = null;
    try {
      body = notice.body();
    } catch (error) {
      console.error("The status card's list could not be drawn.", error);
      return null;
    }
    if (!body) return null;
    return el("div", { class: "status-card__notice" }, el("b", { class: "status-card__subtitle" }, text(notice.title)), body);
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
      noticeBlock(),
    ].filter(Boolean);
  }

  function toggleStatusCard() {
    if (statusCard) {
      closeStatusCard();
      return;
    }
    placeLayers(); // the card hangs from the top bar's bottom edge, wherever the bar sits now
    statusCard = el("div", { class: "status-card", role: "dialog", "aria-label": "Data status" }, statusCardBody());
    document.body.append(statusCard);
    statusSlot.querySelector(".pill--button")?.setAttribute("aria-expanded", "true");
    document.addEventListener("pointerdown", onOutside, true);
    if (notice && typeof notice.onOpen === "function") {
      try {
        notice.onOpen(); // the reader has seen the list: the dot goes
      } catch (error) {
        console.error("The status card's notice did not take the opening.", error);
      }
    }
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
    drawPill();
    if (statusCard) replaceWith(statusCard, statusCardBody()); // an open card follows the page's state
  }

  function drawPill() {
    const button = pill({ ...lastStatus, onClick: toggleStatusCard });
    button.setAttribute("aria-expanded", statusCard ? "true" : "false");
    if (notice && notice.dot === true) {
      const words = text(button.textContent);
      button.classList.add("pill--notice");
      button.append(el("span", { class: "pill__notice", "aria-hidden": "true" })); // item 6, step C: something to look at
      button.setAttribute("aria-label", `${words}. ${text(notice.title)}: open to see the list`);
    }
    statusSlot.replaceChildren(button);
  }

  /** Item 6, step C: a dot on the pill while notice.dot, and notice.body() listed in the card; null takes both away. */
  function setNotice(next) {
    notice = next && typeof next === "object" ? { ...next } : null;
    drawPill();
    if (statusCard) replaceWith(statusCard, statusCardBody());
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
      tab.setAttribute("aria-label", live ? "In Game, our game is live" : "In Game");
    }
    renderDrawer();
  }

  function setRadio(state) {
    radioSlot.replaceChildren();
    if (state) radioSlot.append(radioBar(state));
  }

  // One Escape closes one layer (item 6): the status card first; the drawer only when no sheet or card is open over it
  // (their own Escape closes them, one at a time). A layer that closes marks the key handled.
  document.addEventListener("keydown", (event) => {
    if (event.key === "Tab") {
      trapTab(event);
      return;
    }
    if (event.key !== "Escape" || event.defaultPrevented) return;
    if (statusCard) {
      closeStatusCard();
      event.preventDefault();
      return;
    }
    if (!inlineDrawer && drawer.hasAttribute("open") && !document.querySelector(".sheet-layer[data-modal], .card-layer[data-modal]")) {
      closeDrawer();
      event.preventDefault();
    }
  });
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener("hashchange", () => {
      closeStatusCard();
      if (!inlineDrawer) closeDrawer("route"); // Back, Forward or a link changed the page: never left open over it
    });
  }
  if (!inlineDrawer) document.addEventListener("kickoff:route", () => closeDrawer("route"));

  renderDrawer();
  const root = el("div", { class: "shell" }, topbar, notes, main, radioSlot, drawer);
  return { root, main, notes, setStatus, setNotice, setCurrent, setLive, openDrawer, closeDrawer, setRadio };
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
