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
import { claudeSignedOutSince, signedOutWords } from "../build.js";
import { ours } from "../identity.js";
import { el, reducedMotion, replaceWith, swipeToClose, syncPageLock, teamLogo, text } from "./dom.js";
import { closeLayers, goTo, holdLayer, placeLayers, toTop } from "./layers.js";
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
  { id: "season", label: "My Team" }, // the Season page until 2026-11-01 (owner: "my team and season are the same in my eyes"); the address stays #season
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
 * shell({ current, status: {kind, label}, onNavigate, onSearch, onOpen, onTodo, onSwitchTeam, onBackHome, subOf, menu, inlineDrawer })
 * returns { root, main, notes, setStatus, setNotice, setCurrent, setLive, setViewing, openDrawer, closeDrawer, setRadio }
 * onSwitchTeam(): the top bar's team switch was tapped (batch 3, ui/team-switch.js opens its sheet); onBackHome(): its
 * "Back to <our team>"; setViewing(info|null) draws the team this device is switched to (viewing.js), null ours.
 * onOpen(entry, { path, menu }): a table in the menu was chosen (views/panels.js opens it wide). subOf(key) -> text or a
 * promise of it: a list's line under its title ("game": the game the matchup is about). onTodo(): the To do row was
 * chosen (ui/todo.js opens the flyout); the row and the Menu's count show while "kickoff:notes" counts any item.
 * inlineDrawer: the styleguide's sample, drawn open inside the page: no history entry, no Tab trap, no page lock.
 * setNotice({ dot, title, body(), onOpen }) or null: a dot on the status pill while `dot`, and the card lists body()
 * under its title; opening the card calls onOpen (it clears the dot).
 */
export function shell({ current = "program", status = { kind: "quiet", label: "Connecting" }, onNavigate, onSearch, onOpen, onTodo, onFeedback, onAsk, claudeRow, onSwitchTeam, onBackHome, subOf, menu = MENU, inlineDrawer = false } = {}) {
  let currentView = current;
  let todoCount = 0; // the To do's items listed for this page (ui/page-notes.js counts them)
  let live = false;
  let lastStatus = status && typeof status === "object" ? status : { kind: "quiet", label: "Connecting" };
  let statusCard = null;
  let notice = null;
  const statusSlot = el("div", { class: "topbar__status", role: "status" });

  // The season as one line (owner 2026-10-30): the middle tab is the stop that leads now (Season, Pre-Game Program or
  // Post-Game Program), its small line the week and the opponent; setStop() renames it and points it at the stop. The
  // Newspaper tab follows the week on screen (setNewspaperWeek): stepping the line steps the paper to that week.
  let stopHref = "#program";
  let newspaperHref = "#newspaper";
  const tabs = el(
    "nav",
    { class: "tabs", "aria-label": "Main views" },
    TABS.map((view) =>
      el(
        "a",
        {
          class: `tab${view.id === "program" ? " tab--stop" : ""}`,
          href: `#${view.id}`,
          "aria-current": view.id === currentView ? "page" : null,
          dataset: { view: view.id },
          onclick: (event) => {
            event.preventDefault();
            if (view.id === "program" && stopHref !== "#program") {
              closeDrawer("route");
              window.location.hash = stopHref.slice(1);
              return;
            }
            if (view.id === "newspaper" && newspaperHref !== "#newspaper") {
              closeDrawer("route");
              window.location.hash = newspaperHref.slice(1);
              return;
            }
            navigate(view.id);
          },
        },
        el("span", { class: "tab__label" }, view.label),
        view.id === "program" ? el("small", { class: "tab__detail", hidden: true }) : null,
        view.id === "live" ? liveDot() : null,
      ),
    ),
  );

  /** The middle tab reads the stop that leads now: { label, detail, href }. Null puts the Pre-Game Program back. */
  function setStop(stop) {
    const tab = tabs.querySelector('.tab[data-view="program"]');
    if (!tab) return;
    const label = tab.querySelector(".tab__label");
    const detail = tab.querySelector(".tab__detail");
    const s = stop && typeof stop === "object" ? stop : null;
    stopHref = s && typeof s.href === "string" && s.href.startsWith("#") ? s.href : "#program";
    if (label) label.textContent = s && typeof s.label === "string" && s.label ? s.label : "Pre-Game Program";
    if (detail) {
      const words = s && typeof s.detail === "string" ? s.detail : "";
      detail.textContent = words;
      if (words) detail.removeAttribute("hidden");
      else detail.setAttribute("hidden", "");
    }
    tab.setAttribute("href", stopHref);
  }

  /** The Newspaper tab opens the week on screen ("week-7"), or this week's paper with null. */
  function setNewspaperWeek(key) {
    const tab = tabs.querySelector('.tab[data-view="newspaper"]');
    newspaperHref = typeof key === "string" && /^(week-\d{1,2}|postseason)(-sunday)?$/.test(key) ? `#newspaper=${key}` : "#newspaper";
    if (tab) tab.setAttribute("href", newspaperHref);
  }

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

  // Switch teams (batch 3, owner 2026-11-16: "Top bar + team names"): a small switch beside the wordmark; while this device is
  // switched, that team's logo and name take the wordmark's place, ringed in the accent, with × (Back to <ours>) beside it
  const switchSlot = el("div", { class: "team-switch-bar" });
  function setViewing(info) {
    const team = info && typeof info === "object" && typeof info.school === "string" && info.school ? info : null;
    const home = ours();
    const open = el(
      "button",
      {
        type: "button",
        class: `btn team-switch-bar__open${team ? " is-away" : ""}`,
        "aria-haspopup": "dialog",
        "aria-label": team ? `Showing ${team.school}. Change team` : "Change team", // batch 3 review (owner 2026-11-19): "a change team for the switch"
        title: team ? `This device shows ${team.school}` : "See the app as another team",
        onclick: () => {
          if (typeof onSwitchTeam === "function") onSwitchTeam();
        },
      },
      team ? teamLogo(team, { size: 22, lazy: false, className: "team-switch-bar__logo" }) : el("span", { class: "team-switch-bar__swap", "aria-hidden": "true" }, "⇄"),
      el("span", { class: "team-switch-bar__name" }, team ? text(team.school) : "Change team"),
    );
    const back = team
      ? el(
          "button",
          { type: "button", class: "btn btn--quiet team-switch-bar__back", "aria-label": `Back to ${home.school || "our team"}`, onclick: () => { if (typeof onBackHome === "function") onBackHome(); } },
          el("span", { "aria-hidden": "true" }, "×"),
          el("span", { class: "team-switch-bar__back-words" }, ` Back to ${home.school || "ours"}`),
        )
      : null;
    switchSlot.replaceChildren(open, back || "");
    switchSlot.classList.toggle("is-away", Boolean(team));
    if (typeof document !== "undefined") document.body?.classList.toggle("viewing-other", Boolean(team));
  }
  if (typeof onSwitchTeam === "function") setViewing(null);

  const topbar = el(
    "header",
    { class: "topbar" },
    el("a", { class: "wordmark", href: "#program", onclick: (e) => { e.preventDefault(); navigate("program"); } }, `${ours().name || "Kickoff"} `, el("em", {}, ours().name ? "Kickoff" : "Companion", ours().name ? el("span", { class: "wordmark__long" }, " Companion") : null)),
    typeof onSwitchTeam === "function" ? switchSlot : null, // switched, it takes the wordmark's place (components.css)
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
      toTop(); // ENH-33: the page already showing goes back to its top
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
      runRow(),
      el("div", { class: "drawer__label" }, "Game day"),
      el("div", { class: "drawer__tiles" }, (Array.isArray(menu.tiles) ? menu.tiles : []).map(tileView)),
      el("div", { class: "drawer__groups" }, groups.map(groupRow)),
      askRow(),
      feedbackRow(),
    ];
  }

  /** Run with Claude (batch 4, owner 2026-11-19: "add it in the top layer of the menu"): under Search, drawn by
   *  claudeRow() (ui/claude-refresh.js), which stays hidden until the server says this page has Claude's writing to refresh. */
  function runRow() {
    if (typeof claudeRow !== "function") return null;
    try {
      const row = claudeRow({ close: () => closeDrawer() });
      return row && typeof row.nodeType === "number" ? row : null;
    } catch (error) {
      console.error("The Run with Claude row could not be drawn.", error);
      return null;
    }
  }

  /** Ask about this page (FEAT-12): beside Send feedback at the foot of the opening level. */
  function askRow() {
    if (typeof onAsk !== "function") return null;
    return el(
      "button",
      {
        class: "drawer__item drawer__group-row drawer__ask",
        type: "button",
        onclick: () => {
          closeDrawer();
          try {
            onAsk();
          } catch (error) {
            console.error("The ask sheet could not open.", error);
          }
        },
      },
      el("span", { class: "drawer__icon", "aria-hidden": "true" }, icon("page")),
      el("span", { class: "drawer__words" }, el("b", {}, "Ask about this page"), el("small", {}, "Claude Code answers from what the page shows")),
      goIcon("wide"),
    );
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
  // ENH-4 (the owner's board of 2026-10-27: "the status pill ALWAYS
  // shows data age + server connected + how often the band polls"): the pill is the server connection as a dot, the
  // data's age and how often the page's data is checked ("Updated 32 min ago · hourly"); the card is the wide Data status
  // panel: the server, this page and CFBD across its top, then each band of the page with when its source changes, when
  // the app looks and how old its copy is (/api/datastatus, read when the page reports and when the card opens).
  const STATUS_WORDS = {
    live: "The live feed is current.",
    delayed: "The live feed is running behind your spoiler delay on purpose.",
    replay: "A replay of a finished game is running.",
    quiet: "Waiting for the page's data.",
    stale: "This page shows an older copy of its data.",
    offline: "This device could not reach the app's server.",
  };
  const DOT_OF_KIND = { live: "live", delayed: "live", replay: "live", stale: "down", offline: "off", quiet: "ok" };
  const DATA_STATUS_EVERY_MS = 60000;
  const DATA_STATUS_TIMEOUT_MS = 8000;
  let pageId = current; // the route the card describes (setPage)
  let pageInfo = null; // /api/datastatus's answer for it
  let pageInfoKey = "";
  let pageInfoAt = 0;
  let pageInfoError = null;
  let loadingInfo = null;
  let serverOkAt = null; // when this device last heard from the server
  let statusScrim = null;

  function closeStatusCard() {
    if (!statusCard) return;
    statusCard.remove();
    statusScrim?.remove();
    statusCard = null;
    statusScrim = null;
    document.removeEventListener("pointerdown", onOutside, true);
    statusSlot.querySelector(".pill--button")?.setAttribute("aria-expanded", "false");
  }

  function onOutside(event) {
    if (statusCard && !statusCard.contains(event.target) && !statusSlot.contains(event.target)) closeStatusCard();
  }

  /** "just now", "8 s ago", "3 min ago", "2 h ago" from a time in ms. */
  function sinceText(at) {
    if (typeof at !== "number" || !Number.isFinite(at)) return null;
    const seconds = Math.max(0, Math.round((Date.now() - at) / 1000));
    if (seconds < 2) return "just now";
    if (seconds < 60) return `${seconds} s ago`;
    if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
    return `${Math.round(seconds / 3600)} h ago`;
  }

  /** A band's "Data from": "32 min ago" today within a few hours, "Sun 2:14 PM" within the week, "Oct 21" before. */
  function dataFromText(iso) {
    if (typeof iso !== "string" || !iso) return null;
    const when = new Date(iso);
    const ms = when.getTime();
    if (!Number.isFinite(ms)) return null;
    const seconds = (Date.now() - ms) / 1000;
    if (seconds < 6 * 3600) return sinceText(ms);
    if (seconds < 6.5 * 86400) return `${when.toLocaleDateString("en-US", { weekday: "short" })} ${when.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}`;
    return when.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }

  /** How this page asks the server: a stream for In Game and the board, else on opening and Refresh (owner 2026-11-14). */
  function asksText() {
    if (pageId === "live" || pageId === "board") return "Told of each play as it comes";
    if (pageId === "trivia") return "Asks the server every 30 s";
    return "Asks the server when you open the page or tap Refresh";
  }

  /** Whether the page on screen is refreshed by hand: every page but the live ones. */
  const refreshable = () => !["live", "board", "trivia"].includes(pageId);

  function dataStatusKey() {
    return [pageId || "", lastStatus?.gameId || "", lastStatus?.kickoff || ""].join("|");
  }

  /** /api/datastatus for the page in view: kept a minute, asked again sooner when the page or its game changes. */
  function loadDataStatus(force = false) {
    if (inlineDrawer || typeof fetch !== "function" || !pageId) return null;
    const key = dataStatusKey();
    if (!force && key === pageInfoKey && Date.now() - pageInfoAt < DATA_STATUS_EVERY_MS) return null;
    if (loadingInfo && loadingInfo.key === key) return loadingInfo.promise;
    const params = new URLSearchParams({ view: pageId });
    if (lastStatus?.gameId) params.set("gameId", lastStatus.gameId);
    if (lastStatus?.kickoff) params.set("kickoff", lastStatus.kickoff);
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    const timer = setTimeout(() => controller?.abort(), DATA_STATUS_TIMEOUT_MS);
    const promise = (async () => {
      try {
        const response = await fetch(`/api/datastatus?${params.toString()}`, { cache: "no-store", signal: controller?.signal });
        const body = await response.json().catch(() => null);
        if (!response.ok || !body || typeof body.data !== "object" || body.data === null) throw new Error(body?.errors?.[0]?.message || `the server answered ${response.status}`);
        if (key === dataStatusKey()) {
          pageInfo = body.data;
          pageInfoError = null;
        }
        serverOkAt = Date.now();
      } catch (error) {
        if (key === dataStatusKey()) pageInfoError = error?.name === "AbortError" ? "the server took too long" : text(error?.message || error);
      } finally {
        clearTimeout(timer);
        pageInfoKey = key;
        pageInfoAt = Date.now();
        loadingInfo = null;
        drawPill();
        if (statusCard) replaceWith(statusCard, statusCardBody());
      }
    })();
    loadingInfo = { key, promise };
    return promise;
  }

  /** The page the card describes: its route id (app.js on every page change). */
  function setPage(route) {
    const id = route && typeof route.id === "string" ? route.id : null;
    if (id === pageId) return;
    pageId = id;
    pageInfo = null; // the last page's "how often" is not this one's
    pageInfoError = null;
    pageInfoKey = "";
    drawPill();
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

  /** A fact across the card's top: its name, its state with a dot when it has one, and a line under it. */
  function fact(name, state, line, dot = null) {
    return el(
      "div",
      { class: "ds-fact" },
      el("span", { class: "ds-fact__name" }, name),
      el("b", { class: "ds-fact__state" }, dot ? el("span", { class: `pill__dot pill__dot--${dot}`, "aria-hidden": "true" }) : null, text(state)),
      el("span", { class: "ds-fact__line" }, text(line)),
    );
  }

  function factsRow(s) {
    const dot = s.dot || DOT_OF_KIND[s.kind] || "ok";
    const server = s.kind === "offline"
      ? fact("Server", "Not reachable", serverOkAt ? `Last heard ${sinceText(serverOkAt)}` : "Not heard from yet", "off")
      : dot === "slow"
        ? fact("Server", "Slow to answer", serverOkAt ? `Last answered ${sinceText(serverOkAt)}` : "Still working on it", "slow")
        : fact("Server", "Connected", serverOkAt ? `The server answered ${sinceText(serverOkAt)}` : "Answering", "ok");
    const page = fact("This page", s.label || "Waiting", asksText());
    const cfbd = pageInfo?.cfbd || {};
    const cfbdState = { answering: "Answering", testing: "Testing the connection", "not answering": "Not answering" }[cfbd.state] || (pageInfo ? "Unknown" : "Checking");
    const last = typeof cfbd.lastSuccessAt === "string" ? sinceText(new Date(cfbd.lastSuccessAt).getTime()) : null;
    return el("div", { class: "ds-facts" }, server, page, fact("CFBD", cfbdState, last ? `Last call ${last}` : pageInfo ? "No call yet since the server started" : "Reading the server's records"));
  }

  /** Claude Code signed out on the server computer (owner 2026-11-15): one line under the facts on the host's devices,
   *  until a run gets through (build.js noteClaude). Nothing while it is signed in. */
  function claudeLine() {
    const since = claudeSignedOutSince();
    if (!since || document.body?.dataset?.role === "guest") return null;
    return el("p", { class: "status-card__detail note note--error status-card__claude" }, signedOutWords(since));
  }

  /** Each band of the page: when its source changes, when the app looks, how old its copy is. */
  function bandsBlock() {
    const head = el("div", { class: "ds-bands__head" }, el("h3", { class: "ds-bands__title" }, "Each band on this page"), el("span", { class: "ds-bands__note" }, "when its source changes, and when the app looks"));
    const bands = Array.isArray(pageInfo?.bands) ? pageInfo.bands.filter((b) => b && typeof b === "object" && typeof b.band === "string") : null;
    let body;
    if (!pageInfo && pageInfoError) body = el("p", { class: "note note--error ds-bands__state" }, `The server's schedules could not be read: ${text(pageInfoError)}. Retry now asks again.`);
    else if (!pageInfo) body = el("div", { class: "ds-bands__state", "aria-busy": "true" }, el("div", { class: "skel skel--line" }), el("div", { class: "skel skel--line" }), el("div", { class: "skel skel--line" }));
    else if (!bands || !bands.length) body = el("p", { class: "note ds-bands__state" }, "This page has no bands of its own data: what it shows comes with the page when it opens.");
    else {
      body = el(
        "table",
        { class: "ds-table no-hints" },
        el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Band"), el("th", { scope: "col", class: "ds-table__changes" }, "Changes"), el("th", { scope: "col" }, "The app checks"), el("th", { scope: "col", class: "ds-table__from" }, "Data from"))),
        el(
          "tbody",
          {},
          bands.map((b) => {
            const due = typeof b.due === "string" && b.due ? b.due : null;
            const from = due ? el("span", { class: "ds-due" }, due) : dataFromText(b.dataFrom) || "–";
            return el("tr", {}, el("th", { scope: "row" }, text(b.band)), el("td", { class: "ds-table__changes" }, text(b.changes)), el("td", {}, text(b.checks)), el("td", { class: "ds-table__from" }, from));
          }),
        ),
      );
    }
    return el("section", { class: "ds-bands", "aria-label": "Each band on this page" }, head, body);
  }

  function statusCardBody() {
    const s = lastStatus || {};
    const fresh = (s.kind === "quiet" && (s.dot || "ok") === "ok" && typeof s.updatedAt === "number") || ["live", "delayed", "replay"].includes(s.kind);
    const detail = typeof s.detail === "string" && s.detail ? s.detail : STATUS_WORDS[s.kind] || STATUS_WORDS.quiet;
    const retry = el("button", { class: "btn btn--quiet status-card__retry", type: "button", onclick: () => {
      retry.disabled = true;
      retry.textContent = "Trying";
      document.dispatchEvent(new CustomEvent("kickoff:retry"));
      setTimeout(closeStatusCard, 600);
    } }, "Retry now");
    const close = el("button", { class: "btn btn--quiet icon-btn status-card__close", type: "button", "aria-label": "Close the data status", onclick: closeStatusCard }, icon("close"));
    return [
      el("div", { class: "status-card__head" }, el("h2", { class: "status-card__title" }, "Data status"), close),
      factsRow(s),
      claudeLine(),
      fresh ? null : el("p", { class: "status-card__detail" }, detail), // the board: a fresh page needs no sentence
      bandsBlock(),
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
    statusScrim = el("div", { class: "status-scrim", "aria-hidden": "true" });
    statusCard = el("div", { class: "status-card status-card--data", role: "dialog", "aria-label": "Data status" }, statusCardBody());
    document.body.append(statusScrim, statusCard);
    statusSlot.querySelector(".pill--button")?.setAttribute("aria-expanded", "true");
    document.addEventListener("pointerdown", onOutside, true);
    loadDataStatus(true);
    if (notice && typeof notice.onOpen === "function") {
      try {
        notice.onOpen(); // the reader has seen the list: the dot goes
      } catch (error) {
        console.error("The status card's notice did not take the opening.", error);
      }
    }
  }

  /** "Updated 4 min ago" from the time the page's data was fetched, as [words, hiddenBelowPx] pairs: "4 min ago" on an iPad
   *  (the tabs take the top bar's room), "4 min" on a phone. */
  function updatedParts(at) {
    const seconds = Math.max(0, (Date.now() - at) / 1000);
    if (seconds < 60) return [["Updated ", 900], ["just now", null]];
    if (seconds < 3600) return [["Updated ", 900], [`${Math.round(seconds / 60)} min`, null], [" ago", 480]];
    return [["Updated ", 900], [`${Math.round(seconds / 3600)} h`, null], [" ago", 480]];
  }

  function setStatus(next) {
    lastStatus = next && typeof next === "object" ? { ...next } : { kind: "quiet" };
    if (typeof lastStatus.updatedAt === "number" && Number.isFinite(lastStatus.updatedAt)) lastStatus.label = updatedParts(lastStatus.updatedAt).map(([bit]) => bit).join("");
    if (lastStatus.kind !== "offline" && lastStatus.dot !== "slow" && lastStatus.label !== "Connecting") serverOkAt = Date.now(); // the page heard from the server
    drawPill();
    if (statusCard) replaceWith(statusCard, statusCardBody()); // an open card follows the page's state
    if (lastStatus.label !== "Connecting") loadDataStatus(); // not before the page has said anything
  }

  /** The pill's parts: the dot, the words (shortened on a phone), then how often or the kept copy's age. */
  function pillProps(s) {
    const live = s.kind === "live" && s.label === "Live";
    const dot = s.dot || (s.kind === "live" && !live ? "ok" : DOT_OF_KIND[s.kind]) || "ok";
    const delayed = s.kind === "delayed" && typeof s.delay === "number" && s.delay > 0;
    const extras = [];
    // how often the app asks, on the live pages only: every other page asks when opened and on Refresh (owner 2026-11-14)
    if (!refreshable() && (dot === "ok" || dot === "live") && typeof pageInfo?.cadence === "string" && pageInfo.cadence) extras.push(pageInfo.cadence);
    if (delayed) extras.push(`${s.delay} s delay`);
    if (typeof s.more === "string" && s.more) extras.push(s.more);
    const parts = typeof s.updatedAt === "number" && Number.isFinite(s.updatedAt) ? updatedParts(s.updatedAt) : null;
    return { kind: s.kind, label: delayed ? "Live" : s.label, dot, more: extras.join(" · ") || null, parts };
  }

  function drawPill() {
    const button = pill({ ...pillProps(lastStatus || {}), onClick: toggleStatusCard });
    button.setAttribute("aria-expanded", statusCard ? "true" : "false");
    if (notice && notice.dot === true) {
      const words = text(button.textContent);
      button.classList.add("pill--notice");
      button.append(el("span", { class: "pill__notice", "aria-hidden": "true" })); // item 6, step C: something to look at
      button.setAttribute("aria-label", `${words}. ${text(notice.title)}: open to see the list`);
    }
    // manual refresh (owner 2026-11-14, "Tap the status pill"): Refresh rides beside the pill, which still opens the Data
    // status card; app.js runs it as the pull down's refresh (its line under the top bar)
    const refresh = refreshable()
      ? el("button", { class: "pill-refresh", type: "button", title: "Refresh this page", "aria-label": "Refresh this page", onclick: () => document.dispatchEvent(new CustomEvent("kickoff:refresh")) }, icon("refresh"), el("span", { class: "pill-refresh__word" }, "Refresh"))
      : null;
    statusSlot.replaceChildren(...[button, refresh].filter(Boolean)); // a null child would be written out as the word
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
    const label = updatedParts(lastStatus.updatedAt).map(([bit]) => bit).join("");
    if (label === lastStatus.label) return;
    lastStatus.label = label; // a redraw, not word from the server: the card's "answered" time stays
    drawPill();
    if (statusCard) replaceWith(statusCard, statusCardBody());
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
  return { root, main, notes, setStatus, setNotice, setCurrent, setPage, setLive, setStop, setNewspaperWeek, setViewing, openDrawer, closeDrawer, setRadio };
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
