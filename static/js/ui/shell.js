// The app shell: top bar with the wordmark, inline tabs on wide screens, a status pill, the
// Menu button, the menu drawer, and the radio mini-bar that survives every view change.
// Phase 17 (#25, #32): the Game program is the first tab and the wordmark's home; setLive(true) marks the
// Live sheet while our game is under way (a dot in its tab and menu item, and a LIVE flag on narrow screens).
// Item 6 (owner 2026-10-11): the top bar stays above the side sheets and the player card from 700 px up, so the Menu,
// Search and the tabs work with a sheet open; the Menu closes every open layer, then opens the drawer. The drawer takes a
// history entry like a sheet (Back closes it and stays on the page), closes on any page change, keeps Tab inside itself
// and hands focus back to the Menu button. One Escape closes one layer: the status card, else the drawer when no sheet or
// card is open over it. setNotice() puts a dot on the status pill and a list in its card ("Not loaded yet"), and the
// .page-notes slot holds the notes that once opened by themselves as sheets (ui/page-notes.js); since the layout pass
// (owner 2026-10-22: "dont show that unless its in its own flyout") the slot never shows, the Menu button carries the
// count of the To do and every list of the menu a To do row at its top, which opens the To do flyout (onTodo).
// The layout pass (owner 2026-10-22, boards 2 and 3): the menu is one level at a time (ui/menu-tree.js); each level below
// the opening one takes its own history entry, so Back, Escape, a swipe right and "‹" go up one level.

import { icon } from "./icons.js";
import { ours } from "../identity.js";
import { el, reducedMotion, replaceWith, swipeToClose, syncPageLock, text } from "./dom.js";
import { closeLayers, goTo, holdLayer, placeLayers } from "./layers.js";
import { findPath, labelOf, levelAt, MENU } from "./menu-tree.js";
import { pill } from "./pills.js";

// The owner's order (2026-10-10): Newspaper, Pre-Game Program, In Game, Season; then Top 25 (item 11, owner 2026-10-13).
// The addresses stay #program and #live, so saved links and home-screen icons keep working; only the names changed. Every
// view is in the menu's Views (owner 2026-10-13: "everything should always be accessible from the menu"; a phone has no
// tabs). The top bar's tabs (the layout pass, owner 2026-10-22: "lose the top 25 and the season, we will put those in the
// menu"): Newspaper, Pre-Game Program and In Game, all three on every tablet; Season and Top 25 are in the menu only.
export const VIEWS = [
  { id: "newspaper", label: "Newspaper", tab: true },
  { id: "program", label: "Pre-Game Program", tab: true },
  { id: "live", label: "In Game", tab: true },
  { id: "season", label: "Season" },
  { id: "top25", label: "Top 25" },
];
export const TABS = VIEWS.filter((view) => view.tab);

const liveDot = () => el("span", { class: "live-dot", "aria-hidden": "true" });

export { MENU }; // the menu's tree lives in ui/menu-tree.js (the layout pass, owner 2026-10-22)

/** How many tables and pages a list holds, its lower levels included (the count beside a row that goes a level down). */
function countEntries(items) {
  return (Array.isArray(items) ? items : []).reduce((n, item) => (item && typeof item === "object" && !("heading" in item) ? n + (Array.isArray(item.items) ? countEntries(item.items) : 1) : n), 0);
}

/**
 * shell({ current, status: {kind, label}, onNavigate, onSearch, onOpen, onTodo, subOf, menu, inlineDrawer })
 * returns { root, main, notes, setStatus, setNotice, setCurrent, setLive, openDrawer, closeDrawer, setRadio }
 * onOpen(entry, { path, menu }): a table in the menu was chosen (views/panels.js opens it wide). subOf(key) -> text or a
 * promise of it: a list's line under its title ("game": the game the matchup is about). onTodo(): the To do row was
 * chosen (ui/todo.js opens the flyout); the row and the Menu's count show while "kickoff:notes" counts any item.
 * inlineDrawer: the styleguide's sample, drawn open inside the page: no history entry, no Tab trap, no page lock.
 * setNotice({ dot, title, body(), onOpen }) or null: a dot on the status pill while `dot`, and the card lists body()
 * under its title; opening the card calls onOpen (it clears the dot).
 */
export function shell({ current = "program", status = { kind: "quiet", label: "Connecting" }, onNavigate, onSearch, onOpen, onTodo, onFeedback, subOf, menu = MENU, inlineDrawer = false } = {}) {
  let currentView = current;
  let todoCount = 0; // the To do's items listed for this page (ui/page-notes.js counts them)
  let live = false;
  let lastStatus = status && typeof status === "object" ? status : { kind: "quiet", label: "Connecting" };
  let statusCard = null;
  let notice = null;
  const statusSlot = el("div", { class: "topbar__status", role: "status" });

  const tabs = el(
    "nav",
    { class: "tabs", "aria-label": "Main views" },
    TABS.map((view) =>
      el(
        "a",
        {
          class: "tab",
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
        const fromFlyout = typeof document !== "undefined" && Boolean(document.querySelector(".sheet-layer[open] .side-sheet--wide")); // the menu opens on that table's list
        closeStatusCard();
        if (!inlineDrawer) closeLayers();
        openDrawer({ fromFlyout });
      },
    },
    "Menu",
    el("span", { class: "menu-button__badge", hidden: true, "aria-hidden": "true" }),
  );

  /** The Menu's count of the To do, and the drawer's row, follow the list (the layout pass, 2026-10-22). */
  function drawTodoCount() {
    const badge = menuButton.querySelector(".menu-button__badge");
    const on = todoCount > 0 && typeof onTodo === "function";
    if (badge) {
      badge.textContent = on ? String(todoCount) : "";
      if (on) badge.removeAttribute("hidden");
      else badge.setAttribute("hidden", "");
    }
    if (on) menuButton.setAttribute("aria-label", `Menu, ${todoCount === 1 ? "one thing" : `${todoCount} things`} to do`);
    else menuButton.removeAttribute("aria-label"); // its own word names it
  }

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

  // The menu (the layout pass, owner 2026-10-22, boards 2 and 3): one level at a time. The opening level has Search, the six
  // game-day tiles and the groups; a group slides its list in. A table opens wide by itself (onOpen, views/panels.js), a
  // page goes to that page. The menu opens where the reader is: on the list of the table open in the flyout, else of the
  // page on screen; the table opened last and the page on screen are marked in gold.
  let path = [];
  let lastOpened = null; // the table opened last from the menu (marked in its list)
  let motion = 0; // 1 going down a level, -1 going up: the list slides in from that side
  const levelReleases = []; // one history entry per level below the opening one: Back goes up one level
  const drawerBack = el("button", { class: "btn btn--quiet drawer__back", type: "button", hidden: true, onclick: () => up() });
  const drawerTitle = el("h2", {}, "Menu");
  const drawerList = el("div", { class: "drawer__levels" });
  const panel = el(
    "aside",
    { class: "drawer__panel" },
    el(
      "div",
      { class: "drawer__head" },
      drawerBack,
      drawerTitle,
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
  if (!inlineDrawer) swipeToClose(panel, () => up()); // a swipe right goes up one level, and closes the opening level

  const isMarked = (entry) => (entry.flyout || entry.live ? entry.id === lastOpened : typeof entry.page === "string" && entry.page === currentView);

  function goIcon(kind) {
    return el("span", { class: "drawer__go", "aria-hidden": "true" }, icon(kind === "level" ? "chevron-right" : kind === "wide" ? "wide" : "page"));
  }

  /** One row of a list: a table that opens wide, a page, or a list one level down with its count. */
  function entryRow(entry) {
    const kind = Array.isArray(entry.items) ? "level" : entry.flyout || entry.live ? "wide" : "page";
    const marked = isMarked(entry);
    return el(
      "a",
      {
        class: `drawer__item drawer__item--${kind}${marked ? " is-marked" : ""}`,
        href: kind === "page" ? entry.href || `#${entry.page}` : "#",
        target: entry.external ? "_blank" : null,
        rel: entry.external ? "noopener" : null,
        "aria-current": marked && kind === "page" ? "page" : null,
        dataset: { entry: entry.id },
        onclick: (event) => {
          if (entry.external) {
            closeDrawer();
            return; // a page of the server's own, in a new tab
          }
          event.preventDefault();
          choose(entry);
        },
      },
      el("span", { class: "drawer__words" }, el("b", {}, text(labelOf(entry.label))), entry.hint ? el("small", {}, text(labelOf(entry.hint))) : null),
      kind === "level" ? el("span", { class: "drawer__count" }, String(countEntries(entry.items))) : null,
      goIcon(kind),
    );
  }

  /** A row was chosen: down a level, a table opened wide, or a page. */
  function choose(entry) {
    if (Array.isArray(entry.items)) {
      down(entry.id);
      return;
    }
    if (entry.flyout || entry.live) {
      const at = [...path, entry.id];
      lastOpened = entry.id;
      closeDrawer();
      if (typeof onOpen === "function") onOpen(entry, { path: at, menu });
      return;
    }
    const page = typeof entry.page === "string" ? entry.page : null;
    if (!page) return;
    if (typeof window !== "undefined" && window.location.hash === `#${page}`) {
      closeDrawer();
      return;
    }
    if (/^[a-z0-9]+$/i.test(page)) {
      navigate(page);
      return;
    }
    closeDrawer("route"); // a page with an argument: the drawer's history entry becomes the new page's
    goTo(page);
  }

  function tileView(tile) {
    const marked = isMarked(tile);
    return el(
      "a",
      {
        class: `drawer__item drawer__tile${marked ? " is-marked" : ""}`,
        href: tile.page ? `#${tile.page}` : "#",
        "aria-current": marked && tile.page ? "page" : null,
        dataset: { entry: tile.id },
        onclick: (event) => {
          event.preventDefault();
          choose(tile);
        },
      },
      icon(tile.icon || "dot"),
      el("span", {}, text(labelOf(tile.label))),
      tile.page === "live" && live ? [liveDot(), el("span", { class: "sr-only" }, "our game is live")] : null,
    );
  }

  function groupRow(group) {
    const count = countEntries(group.items);
    return el(
      "a",
      {
        class: `drawer__item drawer__group-row${group.beta ? " drawer__group-row--beta" : ""}`,
        href: "#",
        dataset: { entry: group.id },
        onclick: (event) => {
          event.preventDefault();
          down(group.id);
        },
      },
      el("span", { class: "drawer__icon", "aria-hidden": "true" }, icon(group.icon || "dot")),
      el("span", { class: "drawer__words" }, el("b", {}, text(labelOf(group.label)), group.beta ? el("i", { class: "drawer__beta" }, "Beta") : null), group.hint ? el("small", {}, text(labelOf(group.hint))) : null),
      group.beta ? el("span", { class: "drawer__badge" }, String(count)) : null,
      goIcon("level"),
    );
  }

  /** The To do row at the top of every list of the menu (it opens on the page's own list), while anything is listed: it
   *  opens the To do flyout. */
  function todoRow() {
    if (todoCount < 1 || typeof onTodo !== "function") return null;
    return el(
      "button",
      {
        class: "drawer__item drawer__group-row drawer__todo",
        type: "button",
        onclick: () => {
          closeDrawer();
          try {
            onTodo();
          } catch (error) {
            console.error("The To do flyout could not open.", error);
          }
        },
      },
      el("span", { class: "drawer__icon", "aria-hidden": "true" }, icon("todo")),
      el("span", { class: "drawer__words" }, el("b", {}, "To do"), el("small", {}, todoCount === 1 ? "One thing to look at" : `${todoCount} things to look at`)),
      el("span", { class: "drawer__badge drawer__badge--todo" }, String(todoCount)),
      goIcon("wide"),
    );
  }

  function rootView() {
    const groups = (Array.isArray(menu.groups) ? menu.groups : []).filter((group) => !group.beta || countEntries(group.items) > 0); // New hides while it is empty
    return [
      typeof onSearch === "function"
        ? el(
            "button",
            {
              class: "drawer__search",
              type: "button",
              onclick: () => {
                closeDrawer();
                onSearch();
              },
            },
            icon("search"),
            el("span", {}, "Search teams, players and screens"),
          )
        : null,
      el("div", { class: "drawer__label" }, "Game day"),
      el("div", { class: "drawer__tiles" }, (Array.isArray(menu.tiles) ? menu.tiles : []).map(tileView)),
      el("div", { class: "drawer__groups" }, groups.map(groupRow)),
      feedbackRow(),
    ];
  }

  /** Send feedback at the foot of the opening level (owner 2026-10-23), for every device, guests too. */
  function feedbackRow() {
    if (typeof onFeedback !== "function") return null;
    return el(
      "button",
      {
        class: "drawer__item drawer__group-row drawer__feedback",
        type: "button",
        onclick: () => {
          closeDrawer();
          try {
            onFeedback();
          } catch (error) {
            console.error("The feedback sheet could not open.", error);
          }
        },
      },
      el("span", { class: "drawer__icon", "aria-hidden": "true" }, icon("page")),
      el("span", { class: "drawer__words" }, el("b", {}, "Send feedback"), el("small", {}, "a bug, an idea, with what this tablet just did")),
      goIcon("wide"),
    );
  }

  function levelView(level) {
    const subHost = el("small", {});
    if (level.sub && typeof subOf === "function") {
      let sub = "";
      try {
        sub = subOf(level.sub);
      } catch (error) {
        console.error("The menu's list line could not be read.", error);
      }
      if (sub && typeof sub.then === "function") sub.then((words) => { subHost.textContent = text(words || ""); }).catch(() => {});
      else subHost.textContent = sub ? text(sub) : "";
    }
    return [
      el("div", { class: "drawer__level" }, el("b", {}, text(labelOf(level.label))), subHost),
      (Array.isArray(level.items) ? level.items : []).map((item) => (item && typeof item === "object" && "heading" in item ? el("div", { class: "drawer__heading" }, text(labelOf(item.heading))) : item && typeof item === "object" ? entryRow(item) : null)),
    ];
  }

  function renderDrawer() {
    const level = levelAt(menu, path);
    const atRoot = !level.id;
    if (atRoot) path = [];
    drawerTitle.hidden = !atRoot;
    if (atRoot) drawerBack.setAttribute("hidden", "");
    else {
      drawerBack.removeAttribute("hidden");
      const parent = levelAt(menu, path.slice(0, -1));
      replaceWith(drawerBack, [icon("back"), el("span", {}, text(parent.id ? labelOf(parent.label) : "Menu"))]);
    }
    const list = el("div", { class: `drawer__list${motion > 0 ? " drawer__list--down" : motion < 0 ? " drawer__list--up" : ""}` }, todoRow(), atRoot ? rootView() : levelView(level)); // the To do at the top of whatever list the menu opens on
    motion = 0;
    drawerList.replaceChildren(list);
  }

  function focusFirst() {
    if (inlineDrawer) return;
    const first = drawerList.querySelector(".drawer__item.is-marked, .drawer__item, .drawer__search");
    if (first && typeof first.focus === "function") first.focus({ preventScroll: true });
  }

  /** Down one level: the list slides in, and the level takes a history entry (Back comes back up). */
  function down(id) {
    path = [...path, id];
    motion = 1;
    if (!inlineDrawer && drawer.hasAttribute("open")) levelReleases.push(holdLayer(() => upByHistory()));
    renderDrawer();
    focusFirst();
  }

  /** Up one level by "‹", Escape or a swipe; from the opening level the menu closes. */
  function up() {
    if (!path.length) {
      closeDrawer();
      return;
    }
    path = path.slice(0, -1);
    motion = -1;
    const release = levelReleases.pop();
    if (release) release("self");
    renderDrawer();
    focusFirst();
  }

  /** Back (or the page changing) took the level's entry: up one level. */
  function upByHistory() {
    levelReleases.pop();
    if (!drawer.hasAttribute("open")) return;
    path = path.slice(0, -1);
    motion = -1;
    renderDrawer();
  }

  /** The list to open on: the one asked for, else the open table's, else the page's on screen, else the opening level. */
  function startPath({ path: asked, fromFlyout = false } = {}) {
    if (Array.isArray(asked)) return asked.filter((id) => typeof id === "string");
    const found = fromFlyout && lastOpened ? findPath(menu, (entry) => entry.id === lastOpened) : findPath(menu, (entry) => typeof entry.page === "string" && entry.page === currentView);
    return found && found.length > 1 ? found.slice(0, -1) : [];
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
  // Item 6: the open drawer holds one history entry (ui/layers.js), and each level below the opening one another;
  // closeDrawer(reason) is "self" (its ×, the scrim, Escape: the entries go back out), "route" (a page change takes them)
  // or "history" (Back already took them).
  let closingTimer = null;
  let releaseDrawer = null;
  function openDrawer({ path: asked, mark, fromFlyout = false } = {}) {
    if (typeof mark === "string") lastOpened = mark;
    if (closingTimer) clearTimeout(closingTimer);
    closingTimer = null;
    drawer.classList.remove("is-closing");
    const wasOpen = drawer.hasAttribute("open");
    if (!inlineDrawer && !wasOpen) placeLayers(); // under the top bar from 700 px up (board 2), wherever the bar sits now
    drawer.setAttribute("open", "");
    path = startPath({ path: asked, fromFlyout });
    if (!inlineDrawer && !wasOpen) {
      drawer.setAttribute("data-modal", "");
      syncPageLock();
      if (!releaseDrawer) releaseDrawer = holdLayer((why) => closeDrawer(why));
      for (let i = 0; i < path.length; i += 1) levelReleases.push(holdLayer(() => upByHistory()));
    }
    menuButton.setAttribute("aria-expanded", "true");
    renderDrawer();
    focusFirst();
  }

  function closeDrawer(reason) {
    const wasOpen = drawer.hasAttribute("open");
    const at = document.activeElement;
    const focusInside = wasOpen && Boolean(at) && drawer.contains(at);
    drawer.removeAttribute("open");
    drawer.removeAttribute("data-modal");
    syncPageLock();
    menuButton.setAttribute("aria-expanded", "false");
    const how = typeof reason === "string" ? reason : "self"; // a click hands in an event: by hand
    while (levelReleases.length) {
      const release = levelReleases.pop();
      release(how);
    }
    const release = releaseDrawer;
    releaseDrawer = null;
    if (release) release(how);
    path = [];
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
  // the To do's count (ui/page-notes.js, the layout pass 2026-10-22): the Menu's badge, and the drawer's row while it is open
  if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
    document.addEventListener("kickoff:notes", (event) => {
      const n = Number(event?.detail?.count);
      const next = Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
      if (next === todoCount) return;
      todoCount = next;
      drawTodoCount();
      if (drawer.hasAttribute("open")) renderDrawer();
    });
  }
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
      up(); // one level up; from the opening level the menu closes (owner 2026-10-22)
      event.preventDefault();
    }
  });
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener("hashchange", () => {
      closeStatusCard();
      if (!inlineDrawer) closeDrawer("route"); // Back, Forward or a link changed the page: never left open over it
    });
  }
  if (!inlineDrawer) {
    document.addEventListener("kickoff:route", () => closeDrawer("route"));
    // a flyout's "‹ the list" reopens the menu on the list it came from, that table marked (views/panels.js)
    document.addEventListener("kickoff:menu-open", (event) => {
      const detail = event?.detail && typeof event.detail === "object" ? event.detail : {};
      closeStatusCard();
      openDrawer({ path: Array.isArray(detail.path) ? detail.path : [], mark: detail.mark });
    });
    document.addEventListener("kickoff:menu-mark", (event) => {
      if (typeof event?.detail?.mark === "string") lastOpened = event.detail.mark; // the flyout stepped to another table
    });
  }

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
